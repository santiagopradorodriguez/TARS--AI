"""
Puente entre TARS y el servicio local de OpenCode.

TARS no es otro agente: es un cliente remoto de OpenCode. Este modulo reemplaza
las costuras de Antigravity por llamadas a la API v2 del servicio local:

- Inyectar prompt: POST /api/session/{sid}/prompt
- Leer respuesta: GET /api/event (SSE global) y estado en memoria por sesion
- Estado de herramientas: eventos session.tool.* formateados en espanol
- Modelos: GET /api/model y POST /api/session/{sid}/model
- Chats: mapa persistido chat_id de TARS <-> sessionID de OpenCode
- Cancelar: POST /api/session/{sid}/interrupt

El estado interno conserva la forma que ya consume tars_web_server.py:
is_processing, tool_action, recent_steps, generated_files. Ademas agrega
last_message, streaming_text y outcome para que el servidor no tenga que
reconstruir la respuesta final.

Decisiones de descubrimiento y autenticacion:
- La URL se descubre en cada arranque con `opencode service status`. El puerto
  cambia entre reinicios, por eso no se acepta ninguna URL hardcodeada.
- Si el comando falla, se lee el service.json del estado local de OpenCode.
- La API local pide HTTP Basic con usuario "opencode" y el password que
  OpenCode guarda en service.json. Nunca se escribe ese archivo.

Reglas del proyecto:
- Cero emojis en codigo, logs y respuestas.
- Cero rutas absolutas de usuario hardcodeadas: todo pasa por expanduser o por
  variables de entorno.
- Espanol rioplatense en comentarios y docstrings.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

import requests


__all__ = [
    "ErrorPuenteOpenCode",
    "ServicioOpenCodeNoDisponible",
    "ErrorAPI",
    "PuenteOpenCode",
    "descubrir_servicio_opencode",
    "directorio_config_tars",
    "ruta_mapa_sesiones",
    "format_spanish_tool_action",
]

# ---------------------------------------------------------------------------
# Constantes de configuracion
# ---------------------------------------------------------------------------

VERSION_MAPA = 1
NOMBRE_ARCHIVO_MAPA = "opencode_sessions.json"

USUARIO_BASICO = "opencode"
TIMEOUT_CONEXION = 5.0
TIMEOUT_LECTURA = 60.0
TIMEOUT_SSE = 120.0

ACCION_PENSANDO = "[Pensando] Analizando y planificando respuesta..."

# Limites que usa el servidor de TARS para el estado de Antigravity.
MAX_PASOS_RECIENTES = 5
MAX_LARGO_DETALLE = 130


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


class ErrorPuenteOpenCode(Exception):
    """Error base del puente."""


class ServicioOpenCodeNoDisponible(ErrorPuenteOpenCode):
    """No se pudo descubrir o contactar el servicio local de OpenCode."""


class ErrorAPI(ErrorPuenteOpenCode):
    """La API de OpenCode respondio con un error."""

    def __init__(
        self,
        mensaje: str,
        status_code: int | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(mensaje)
        self.status_code = status_code
        self.payload = payload


# ---------------------------------------------------------------------------
# Rutas de configuracion de TARS
# ---------------------------------------------------------------------------


def directorio_config_tars() -> str:
    """
    Devuelve el directorio de configuracion de TARS.

    Respeta TARS_CONFIG_DIR, que es la variable que ya usa tars_web_server.py.
    Si no esta definida, usa ~/.config/tars como pide el plan.
    """
    return os.environ.get("TARS_CONFIG_DIR") or os.path.expanduser(
        "~/.config/tars"
    )


def ruta_mapa_sesiones(config_dir: str | None = None) -> str:
    """
    Devuelve la ruta del mapa chat_id de TARS <-> sessionID de OpenCode.

    TARS_OPENCODE_SESSIONS_FILE permite apuntar a otro archivo, util para tests
    o para instalaciones con configuracion separada.
    """
    ruta_env = os.environ.get("TARS_OPENCODE_SESSIONS_FILE")
    if ruta_env:
        return os.path.expanduser(ruta_env)
    base = config_dir or directorio_config_tars()
    return os.path.join(os.path.expanduser(base), NOMBRE_ARCHIVO_MAPA)


# ---------------------------------------------------------------------------
# Descubrimiento y autenticacion del servicio
# ---------------------------------------------------------------------------


def _candidatos_binario_opencode() -> list[str]:
    """Arma la lista de binarios de OpenCode a probar, sin rutas fijas."""
    candidatos: list[str] = []
    binario_env = os.environ.get("TARS_OPENCODE_BIN")
    if binario_env:
        candidatos.append(os.path.expanduser(binario_env))
    encontrado = shutil.which("opencode")
    if encontrado:
        candidatos.append(encontrado)
    # Fallback util cuando el servicio arranca con un PATH mas pobre que el
    # de la sesion interactiva, por ejemplo desde systemd.
    local = os.path.expanduser("~/.opencode/bin/opencode")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        candidatos.append(local)
    # Deduplicar conservando el orden.
    return list(dict.fromkeys(candidatos))


def _archivos_service_json() -> list[str]:
    """Rutas posibles del service.json de OpenCode, segun XDG."""
    bases: list[str] = []
    xdg_state = os.environ.get("XDG_STATE_HOME")
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_state:
        bases.append(os.path.expanduser(xdg_state))
    if xdg_config:
        bases.append(os.path.expanduser(xdg_config))
    bases.append(os.path.expanduser("~/.local/state"))
    bases.append(os.path.expanduser("~/.config"))
    rutas: list[str] = []
    for base in dict.fromkeys(bases):
        rutas.append(os.path.join(base, "opencode", "service.json"))
    return rutas


def _password_desde_archivos() -> str:
    """Lee el password del service.json mas reciente que tenga uno."""
    for ruta in _archivos_service_json():
        try:
            with open(ruta, "r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
        except (OSError, ValueError):
            continue
        password = datos.get("password")
        if isinstance(password, str) and password:
            return password
    return ""


def _password_desde_entorno() -> str:
    """Password explicito por entorno, util para tests y despliegues."""
    for nombre in ("TARS_OPENCODE_PASSWORD", "OPENCODE_SERVICE_PASSWORD"):
        valor = os.environ.get(nombre)
        if valor:
            return valor
    return ""


def _url_desde_service_json() -> str:
    """Fallback de descubrimiento: URL guardada por el servicio."""
    for ruta in _archivos_service_json():
        try:
            with open(ruta, "r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
        except (OSError, ValueError):
            continue
        url = datos.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url.rstrip("/")
    return ""


def _url_desde_comando() -> tuple[str, str]:
    """
    Corre `opencode service status` y devuelve la URL activa.

    El comando imprime una unica linea con la URL, por ejemplo
    http://127.0.0.1:49374. No se asume el puerto.
    """
    for binario in _candidatos_binario_opencode():
        try:
            resultado = subprocess.run(
                [binario, "service", "status"],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        salida = ((resultado.stdout or "") + "\n" + (resultado.stderr or "")).strip()
        coincidencia = re.search(r"https?://[^\s\"']+", salida)
        if resultado.returncode == 0 and coincidencia:
            return coincidencia.group(0).rstrip("/"), binario
    return "", ""


def _verificar_servicio(url: str, password: str) -> dict | None:
    """Pega contra /api/info y devuelve la identidad del servicio si responde."""
    try:
        respuesta = requests.get(
            url.rstrip("/") + "/api/info",
            auth=(USUARIO_BASICO, password),
            timeout=(TIMEOUT_CONEXION, 10),
        )
    except requests.RequestException:
        return None
    if respuesta.status_code != 200:
        return None
    try:
        return respuesta.json()
    except ValueError:
        return None


def descubrir_servicio_opencode(
    url_forzada: str | None = None,
    password_forzado: str | None = None,
) -> dict:
    """
    Descubre el servicio local de OpenCode en cada arranque.

    Devuelve un dict con url, password, origen e info. Si no hay servicio vivo
    levanta ServicioOpenCodeNoDisponible. No acepta puertos hardcodeados: la
    unica fuente de verdad es `opencode service status` o el service.json.
    """
    password = (
        password_forzado
        if password_forzado is not None
        else (_password_desde_entorno() or _password_desde_archivos())
    )

    candidatos: list[tuple[str, str]] = []
    if url_forzada:
        candidatos.append((url_forzada.rstrip("/"), "url forzada"))
    else:
        url_comando, binario = _url_desde_comando()
        if url_comando:
            candidatos.append((url_comando, f"opencode service status ({binario})"))
        url_estado = _url_desde_service_json()
        if url_estado:
            candidatos.append((url_estado, "service.json"))

    if not candidatos:
        raise ServicioOpenCodeNoDisponible(
            "No encontre el servicio local de OpenCode. "
            "Corri 'opencode service status' y verifica que este vivo."
        )

    vistos: set[str] = set()
    for url, origen in candidatos:
        if url in vistos:
            continue
        vistos.add(url)
        info = _verificar_servicio(url, password)
        if info:
            return {
                "url": url,
                "password": password,
                "origen": origen,
                "info": info,
            }

    raise ServicioOpenCodeNoDisponible(
        "El servicio de OpenCode no respondio en las URLs descubiertas: "
        + ", ".join(url for url, _ in candidatos)
        + ". Revisa que este vivo y que el password de service.json sea el actual."
    )


# ---------------------------------------------------------------------------
# Formato de acciones en espanol, compatible con tars_web_server.py
# ---------------------------------------------------------------------------


def _texto_limpio(valor: Any) -> str:
    """Saca comillas y espacios, igual que format_spanish_tool_action del server."""
    return str(valor or "").replace('"', "").replace("'", "").strip()


def _primer_valor(datos: dict, *claves: str) -> Any:
    """Devuelve el primer valor no vacio entre varias claves posibles."""
    for clave in claves:
        valor = datos.get(clave)
        if valor:
            return valor
    return ""


def _comando_corto(comando: Any) -> str:
    """Primer tramo del comando, cortado a 42 caracteres como el server."""
    limpio = _texto_limpio(comando)
    if not limpio:
        return "comando"
    return limpio.split("&&")[0].strip()[:42]


def format_spanish_tool_action(t_name: Any, args: dict | None = None) -> str:
    """
    Traduce una herramienta de OpenCode o Antigravity a una accion en espanol.

    Mantiene exactamente los mismos prefijos que usa tars_web_server.py para
    que el servidor no tenga que traducir nada:
    [Leyendo], [Editando], [Creando], [Ejecutando], [Archivos], [Búsqueda],
    [Web], [Herramienta] y [Pensando].
    """
    datos = args if isinstance(args, dict) else {}
    nombre = str(t_name or "").strip().lower()

    ruta_objetivo = _texto_limpio(
        _primer_valor(
            datos,
            "TargetFile",
            "AbsolutePath",
            "filePath",
            "file_path",
            "path",
            "file",
        )
    )
    archivo = os.path.basename(ruta_objetivo) if ruta_objetivo else ""
    comando = _primer_valor(datos, "CommandLine", "command", "cmd", "script")

    if nombre in ("view_file", "read", "read_file", "fs_read"):
        return f"[Leyendo] {archivo}" if archivo else "[Leyendo] Archivo del proyecto"

    if nombre in (
        "replace_file_content",
        "multi_replace_file_content",
        "edit",
        "multiedit",
        "multi_edit",
        "apply_patch",
        "patch",
    ):
        return f"[Editando] {archivo}" if archivo else "[Editando] Código"

    if nombre in ("write_to_file", "write", "create_file", "fs_write"):
        return f"[Creando] {archivo}" if archivo else "[Escribiendo] Archivo"

    if nombre in ("run_command", "shell", "bash", "shell_command", "pty"):
        return f"[Ejecutando] {_comando_corto(comando)}"

    if nombre in ("list_dir", "list", "ls", "fs_list"):
        return "[Archivos] Listando directorio"

    if nombre in (
        "grep_search",
        "find_by_name",
        "grep",
        "glob",
        "find",
        "search",
    ):
        return "[Búsqueda] Buscando en el código"

    if nombre in (
        "search_web",
        "read_url_content",
        "webfetch",
        "websearch",
        "web_search",
        "fetch",
    ):
        return "[Web] Consultando información en la web"

    if nombre in ("task", "subagent"):
        return "[Herramienta] Delegando tarea a un subagente"

    if nombre in ("todowrite", "todoread", "todo"):
        return "[Herramienta] Actualizando plan de trabajo"

    if nombre == "skill":
        habilidad = _texto_limpio(_primer_valor(datos, "name", "skill"))
        if habilidad:
            return f"[Herramienta] Cargando habilidad {habilidad}"

    accion = _texto_limpio(
        _primer_valor(datos, "toolAction", "toolSummary", "description")
    )
    if not accion:
        accion = _texto_limpio(nombre)
    return f"[Herramienta] {accion}" if accion else "[Herramienta] Ejecutando acción"


def _detalle_herramienta(args: dict) -> str:
    """Detalle corto para la UI, con la misma prioridad que usa el server."""
    detalle = _primer_valor(
        args,
        "CommandLine",
        "command",
        "TargetFile",
        "AbsolutePath",
        "filePath",
        "file_path",
        "path",
        "Query",
        "query",
        "pattern",
        "url",
        "prompt",
    )
    limpio = _texto_limpio(detalle)
    if limpio and len(limpio) > MAX_LARGO_DETALLE:
        limpio = limpio[:MAX_LARGO_DETALLE] + "..."
    return limpio


def _archivos_generados(t_name: Any, args: dict) -> list[str]:
    """Archivos que crea o modifica una herramienta, para collect_turn_media_and_files."""
    nombre = str(t_name or "").strip().lower()
    editores = {
        "write_to_file",
        "write",
        "create_file",
        "fs_write",
        "replace_file_content",
        "multi_replace_file_content",
        "edit",
        "multiedit",
        "multi_edit",
        "apply_patch",
        "patch",
    }
    if nombre not in editores:
        return []

    rutas: list[str] = []
    ruta = _texto_limpio(
        _primer_valor(
            args,
            "TargetFile",
            "AbsolutePath",
            "filePath",
            "file_path",
            "path",
            "file",
        )
    )
    if ruta:
        rutas.append(ruta)

    # Algunos parches traen las rutas adentro del texto.
    parche = _primer_valor(args, "patch", "input", "text")
    if isinstance(parche, str) and parche:
        for coincidencia in re.finditer(
            r"^\*\*\* (?:Add|Update|Delete) File:\s*(.+)$", parche, re.MULTILINE
        ):
            candidata = coincidencia.group(1).strip()
            if candidata:
                rutas.append(candidata)

    return list(dict.fromkeys(rutas))


# ---------------------------------------------------------------------------
# Puente
# ---------------------------------------------------------------------------


class PuenteOpenCode:
    """
    Cliente remoto del servicio local de OpenCode.

    Uso minimo:

        with PuenteOpenCode() as puente:
            sid = puente.crear_sesion(titulo="Chat de TARS")
            puente.enviar_prompt(sid, "Hola")
            resultado = puente.esperar_respuesta(sid, timeout=60)
            print(resultado["texto"])
            puente.cancelar(sid)

    El hilo de eventos arranca una sola vez por proceso y es el que mantiene
    actualizado el estado en memoria de cada sesion seguida.
    """

    def __init__(
        self,
        base_url: str | None = None,
        password: str | None = None,
        config_dir: str | None = None,
        mapa_path: str | None = None,
        agente_por_defecto: str | None = None,
        verbose: bool = False,
        iniciar_hilo: bool = True,
        espera_conexion: float = 5.0,
    ) -> None:
        self.verbose = verbose
        self._url_fijada = base_url is not None
        self._password_fijado = password is not None

        descubierto = descubrir_servicio_opencode(base_url, password)
        self.url: str = descubierto["url"]
        self.password: str = descubierto["password"]
        self.origen_descubrimiento: str = descubierto["origen"]
        self.info_servicio: dict = descubierto["info"]

        self.config_dir = os.path.expanduser(config_dir or directorio_config_tars())
        self.mapa_path = ruta_mapa_sesiones(self.config_dir) if mapa_path is None else os.path.expanduser(mapa_path)
        self.agente_por_defecto = agente_por_defecto or os.environ.get(
            "TARS_OPENCODE_AGENT"
        )

        self._http = requests.Session()
        self._http.auth = (USUARIO_BASICO, self.password)
        self._http.headers.update({"Accept": "application/json"})

        self._candado = threading.RLock()
        self._candado_mapa = threading.RLock()
        self._estados: dict[str, dict] = {}
        self._nombres_herramientas: dict[str, dict[str, str]] = {}

        self._detener = threading.Event()
        self._conectado_eventos = threading.Event()
        self._hilo_eventos: threading.Thread | None = None
        self._respuesta_sse: Any = None

        self._mapa: dict[str, dict] = {}
        self._mapa_error = ""
        self._cargar_mapa()

        if iniciar_hilo:
            self.iniciar(esperar=espera_conexion)

    # -- contexto ---------------------------------------------------------

    def __enter__(self) -> "PuenteOpenCode":
        if self._hilo_eventos is None:
            self.iniciar()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cerrar()

    def _log(self, mensaje: str) -> None:
        if self.verbose:
            print(f"[Puente OpenCode] {mensaje}", flush=True)

    # -- ciclo de vida ----------------------------------------------------

    def iniciar(self, esperar: float = 0.0) -> None:
        """Arranca el hilo consumidor de SSE. Es idempotente."""
        if self._hilo_eventos and self._hilo_eventos.is_alive():
            return
        self._detener.clear()
        self._hilo_eventos = threading.Thread(
            target=self._bucle_eventos,
            name="opencode-sse",
            daemon=True,
        )
        self._hilo_eventos.start()
        if esperar > 0:
            self._conectado_eventos.wait(timeout=esperar)

    def cerrar(self) -> None:
        """Corta el hilo de eventos y libera las conexiones HTTP."""
        self._detener.set()
        respuesta = self._respuesta_sse
        if respuesta is not None:
            try:
                respuesta.close()
            except Exception:
                pass
        hilo = self._hilo_eventos
        if hilo and hilo.is_alive():
            hilo.join(timeout=3)
        self._hilo_eventos = None
        try:
            self._http.close()
        except Exception:
            pass

    def esta_disponible(self) -> bool:
        """Ping liviano contra /api/info."""
        try:
            datos = self._request("GET", "/api/info", timeout=(2, 5))
        except ErrorPuenteOpenCode:
            return False
        return bool(datos)

    # -- HTTP -------------------------------------------------------------

    def _redescubrir(self) -> None:
        """Actualiza URL y password cuando el servicio se reinicia."""
        if self._url_fijada:
            return
        descubierto = descubrir_servicio_opencode()
        with self._candado:
            self.url = descubierto["url"]
            self.password = descubierto["password"]
            self.origen_descubrimiento = descubierto["origen"]
            self.info_servicio = descubierto["info"]
            self._http.auth = (USUARIO_BASICO, self.password)
        self._log(f"Servicio redescubierto en {self.url}")

    def _request(
        self,
        metodo: str,
        ruta: str,
        json_body: Any = None,
        params: dict | None = None,
        timeout: tuple[float, float] | None = None,
    ) -> Any:
        """
        Hace una llamada a la API y normaliza los errores.

        Si el servicio se reinicio y cambio de puerto, redescubre una vez y
        reintenta. Nunca inventa un puerto.
        """
        timeout = timeout or (TIMEOUT_CONEXION, TIMEOUT_LECTURA)
        url = self.url.rstrip("/") + ruta

        for intento in (0, 1):
            try:
                respuesta = self._http.request(
                    metodo,
                    url,
                    json=json_body,
                    params=params,
                    timeout=timeout,
                )
            except requests.RequestException as error:
                if intento == 0 and not self._url_fijada:
                    try:
                        self._redescubrir()
                        url = self.url.rstrip("/") + ruta
                        continue
                    except ErrorPuenteOpenCode:
                        pass
                raise ServicioOpenCodeNoDisponible(
                    f"No pude hablar con OpenCode en {url}: {error}"
                ) from error

            if respuesta.status_code == 401 and intento == 0 and not self._url_fijada:
                try:
                    self._redescubrir()
                    url = self.url.rstrip("/") + ruta
                    continue
                except ErrorPuenteOpenCode:
                    pass

            if respuesta.status_code >= 400:
                payload: Any = None
                try:
                    payload = respuesta.json()
                except ValueError:
                    payload = respuesta.text
                if isinstance(payload, dict):
                    detalle = payload.get("message") or payload.get("_tag")
                else:
                    detalle = str(payload or "")[:300]
                detalle = detalle or respuesta.reason
                raise ErrorAPI(
                    f"OpenCode devolvio {respuesta.status_code} en "
                    f"{metodo} {ruta}: {detalle}",
                    status_code=respuesta.status_code,
                    payload=payload,
                )

            if respuesta.status_code == 204 or not respuesta.content:
                return None
            try:
                return respuesta.json()
            except ValueError as error:
                raise ErrorAPI(
                    f"OpenCode devolvio una respuesta que no es JSON en "
                    f"{metodo} {ruta}",
                    status_code=respuesta.status_code,
                    payload=respuesta.text[:500],
                ) from error

        raise ServicioOpenCodeNoDisponible(
            f"No pude hablar con OpenCode en {self.url}"
        )

    # -- SSE --------------------------------------------------------------

    def _bucle_eventos(self) -> None:
        """
        Consumidor unico del stream global GET /api/event.

        OpenCode emite un JSON por linea con el formato `data: {...}`. El
        stream es volatil por contrato: si se corta, reconectamos y
        reconciliamos el estado de las sesiones seguidas.
        """
        backoff = 1.0
        hubo_corte = False

        while not self._detener.is_set():
            try:
                respuesta = requests.get(
                    self.url.rstrip("/") + "/api/event",
                    auth=(USUARIO_BASICO, self.password),
                    headers={"Accept": "text/event-stream"},
                    stream=True,
                    timeout=(TIMEOUT_CONEXION, TIMEOUT_SSE),
                )
            except requests.RequestException as error:
                self._conectado_eventos.clear()
                if self._detener.is_set():
                    break
                self._log(f"SSE no conecto: {error}")
                hubo_corte = True
                if not self._url_fijada:
                    try:
                        self._redescubrir()
                    except ErrorPuenteOpenCode:
                        pass
                self._detener.wait(backoff)
                backoff = min(backoff * 2, 10.0)
                continue

            if respuesta.status_code != 200:
                self._conectado_eventos.clear()
                self._log(
                    f"SSE devolvio {respuesta.status_code}; reintento en {backoff}s"
                )
                respuesta.close()
                if respuesta.status_code == 401 and not self._url_fijada:
                    try:
                        self._redescubrir()
                    except ErrorPuenteOpenCode:
                        pass
                self._detener.wait(backoff)
                backoff = min(backoff * 2, 10.0)
                hubo_corte = True
                continue

            self._respuesta_sse = respuesta
            self._conectado_eventos.set()
            backoff = 1.0
            self._log("SSE conectado")

            if hubo_corte:
                self._reconciliar_estados()
                hubo_corte = False

            try:
                self._leer_stream(respuesta)
            except requests.RequestException as error:
                if not self._detener.is_set():
                    self._log(f"SSE cortado: {error}")
                    hubo_corte = True
            except Exception as error:
                # Al cerrar el puente desde otro hilo, requests puede soltar
                # el socket y romper iter_lines con AttributeError. Ese caso es
                # parte del cierre normal, no una falla del servicio.
                if not self._detener.is_set():
                    self._log(f"SSE cortado: {error}")
                    hubo_corte = True
            finally:
                self._conectado_eventos.clear()
                self._respuesta_sse = None
                try:
                    respuesta.close()
                except Exception:
                    pass

            if self._detener.is_set():
                break
            # Aunque el stream haya terminado sin excepcion, en el hueco
            # pudieron perderse eventos: al reconectar reconciliamos.
            hubo_corte = True
            self._detener.wait(backoff)
            backoff = min(backoff * 2, 10.0)

    def _leer_stream(self, respuesta: requests.Response) -> None:
        """Parsea lineas SSE y despacha cada evento completo."""
        datos: list[str] = []
        for linea_cruda in respuesta.iter_lines(chunk_size=512):
            if self._detener.is_set():
                return
            if linea_cruda is None:
                continue
            linea = linea_cruda.decode("utf-8", errors="replace")
            if linea == "":
                if datos:
                    self._despachar_linea("\n".join(datos))
                    datos = []
                continue
            if linea.startswith(":"):
                # Comentario o heartbeat.
                continue
            if linea.startswith("data:"):
                datos.append(linea[5:].lstrip())
        if datos:
            self._despachar_linea("\n".join(datos))

    def _despachar_linea(self, texto: str) -> None:
        try:
            evento = json.loads(texto)
        except ValueError:
            return
        if isinstance(evento, dict):
            self._procesar_evento(evento)

    def _procesar_evento(self, evento: dict) -> None:
        """Actualiza el estado en memoria de la sesion afectada."""
        tipo = str(evento.get("type") or "")
        datos = evento.get("data") or {}
        if not isinstance(datos, dict):
            datos = {}
        session_id = datos.get("sessionID") or evento.get("sessionID")
        if not session_id:
            durable = evento.get("durable") or {}
            session_id = durable.get("aggregateID")
        if not session_id:
            return

        with self._candado:
            estado = self._estados.get(session_id)
        if estado is None:
            return

        creado = evento.get("created")
        with self._candado:
            # Un evento viejo puede llegar tarde, por ejemplo el succeeded del
            # turno anterior justo despues de mandar un prompt nuevo. Si su
            # timestamp es anterior al inicio del turno actual, no lo dejamos
            # cerrar el turno nuevo.
            inicio_turno = int(estado.get("turno_iniciado_ms") or 0)
            if (
                isinstance(creado, (int, float))
                and inicio_turno
                and int(creado) < inicio_turno
            ):
                return

            if tipo == "session.inbox.delivered":
                # Se reinicia recien cuando OpenCode entrega el prompt al
                # agente. Asi un prompt encolado no pisa el estado del turno
                # que todavia esta corriendo.
                self._reiniciar_turno(
                    estado,
                    session_id,
                    desde_ms=int(creado) if isinstance(creado, (int, float)) else None,
                )

            elif tipo == "session.execution.started":
                estado["is_processing"] = True
                if not estado.get("tool_action"):
                    estado["tool_action"] = ACCION_PENSANDO
                    estado["thought"] = "Analizando los próximos pasos..."

            elif tipo == "session.step.started":
                estado["is_processing"] = True
                estado["step_index"] = int(estado.get("step_index") or 0) + 1
                estado["steps_count"] = int(estado.get("steps_count") or 0) + 1
                modelo = datos.get("model")
                if isinstance(modelo, dict):
                    estado["model"] = modelo
                agente = datos.get("agent")
                if agente:
                    estado["agent"] = agente
                estado["tool_action"] = ACCION_PENSANDO
                estado["thought"] = "Analizando los próximos pasos..."
                estado["tool_name"] = ""
                estado["tool_detail"] = ""

            elif tipo == "session.reasoning.started":
                estado["is_processing"] = True
                if not estado.get("tool_action"):
                    estado["tool_action"] = ACCION_PENSANDO

            elif tipo in ("session.tool.input.started", "session.tool.started"):
                nombre = str(datos.get("name") or "")
                tool_id = str(datos.get("id") or "")
                if nombre:
                    estado["tool_name"] = nombre
                    if tool_id:
                        self._nombres_herramientas.setdefault(session_id, {})[
                            tool_id
                        ] = nombre
                    estado["tool_action"] = format_spanish_tool_action(nombre, {})

            elif tipo in ("session.tool.input.ended", "session.tool.called"):
                tool_id = str(datos.get("id") or "")
                nombre = self._nombre_herramienta(session_id, tool_id) or str(
                    estado.get("tool_name") or ""
                )
                if tipo == "session.tool.input.ended":
                    entrada = self._parsear_entrada(datos.get("text"))
                else:
                    entrada = datos.get("input")
                if not isinstance(entrada, dict):
                    entrada = {}
                if nombre:
                    estado["tool_name"] = nombre
                    accion = format_spanish_tool_action(nombre, entrada)
                    self._registrar_accion(estado, accion, _detalle_herramienta(entrada))
                    self._agregar_archivos_generados(estado, nombre, entrada)

            elif tipo == "session.tool.success":
                # La accion ya quedo registrada al recibir el input. Solo
                # completamos archivos si el input no habia llegado.
                tool_id = str(datos.get("id") or "")
                nombre = self._nombre_herramienta(session_id, tool_id) or str(
                    estado.get("tool_name") or ""
                )
                entrada = datos.get("input")
                if nombre and isinstance(entrada, dict):
                    self._agregar_archivos_generados(estado, nombre, entrada)

            elif tipo == "session.tool.error":
                error = datos.get("error")
                if isinstance(error, dict):
                    estado["error"] = str(
                        error.get("message") or error.get("type") or "Herramienta con error"
                    )
                else:
                    estado["error"] = str(error or "Herramienta con error")

            elif tipo == "session.text.started":
                estado["assistant_message_id"] = str(datos.get("assistantMessageID") or "")
                estado["streaming_text"] = ""

            elif tipo == "session.text.delta":
                mensaje_id = str(datos.get("assistantMessageID") or "")
                if mensaje_id and mensaje_id != estado.get("assistant_message_id"):
                    estado["assistant_message_id"] = mensaje_id
                    estado["streaming_text"] = ""
                estado["streaming_text"] = (
                    str(estado.get("streaming_text") or "")
                    + str(datos.get("delta") or "")
                )
                estado["is_processing"] = True

            elif tipo == "session.text.ended":
                texto = datos.get("text")
                if texto is None:
                    texto = estado.get("streaming_text") or ""
                estado["last_message"] = str(texto)
                estado["streaming_text"] = str(texto)
                mensaje_id = str(datos.get("assistantMessageID") or "")
                if mensaje_id:
                    estado["assistant_message_id"] = mensaje_id

            elif tipo == "session.step.ended":
                finish = str(datos.get("finish") or "")
                if finish == "error":
                    estado["error"] = "El paso termino con error."
                if isinstance(datos.get("model"), dict):
                    estado["model"] = datos["model"]

            elif tipo == "session.step.failed":
                error = datos.get("error")
                if isinstance(error, dict):
                    estado["error"] = str(
                        error.get("message") or error.get("type") or "Paso fallido"
                    )
                else:
                    estado["error"] = str(error or "Paso fallido")

            elif tipo == "session.execution.succeeded":
                self._marcar_fin(estado, "succeeded")

            elif tipo == "session.execution.failed":
                error = datos.get("error")
                if isinstance(error, dict):
                    estado["error"] = str(
                        error.get("message") or error.get("type") or "Ejecucion fallida"
                    )
                else:
                    estado["error"] = str(error or "Ejecucion fallida")
                self._marcar_fin(estado, "failed")

            elif tipo == "session.execution.interrupted":
                self._marcar_fin(estado, "interrupted")

            elif tipo.startswith("session.execution."):
                sufijo = tipo.rsplit(".", 1)[-1]
                self._marcar_fin(estado, sufijo)

            elif tipo == "permission.asked":
                estado["permission_pending"] = {
                    "id": datos.get("id"),
                    "action": datos.get("action"),
                    "resources": datos.get("resources") or [],
                    "metadata": datos.get("metadata") or {},
                    "source": datos.get("source") or {},
                }
                estado["is_processing"] = True

            elif tipo == "permission.replied":
                pendiente = estado.get("permission_pending") or {}
                if not datos.get("requestID") or pendiente.get("id") == datos.get(
                    "requestID"
                ):
                    estado["permission_pending"] = None

            elif "idle" in tipo:
                self._marcar_fin(estado, "idle")

            elif "model" in tipo and isinstance(datos.get("model"), dict):
                estado["model"] = datos["model"]

            estado["updated_at"] = time.time()

    def _parsear_entrada(self, texto: Any) -> dict:
        """Convierte el texto JSON de session.tool.input.ended en dict."""
        if isinstance(texto, dict):
            return texto
        if not isinstance(texto, str) or not texto.strip():
            return {}
        try:
            datos = json.loads(texto)
        except ValueError:
            return {}
        return datos if isinstance(datos, dict) else {}

    def _nombre_herramienta(self, session_id: str, tool_id: str) -> str:
        if not tool_id:
            return ""
        with self._candado:
            return (self._nombres_herramientas.get(session_id) or {}).get(tool_id, "")

    def _registrar_accion(self, estado: dict, accion: str, detalle: str = "") -> None:
        """Actualiza tool_action y la lista recent_steps sin repetir consecutivos."""
        if not accion:
            return
        estado["tool_action"] = accion
        estado["tool_detail"] = detalle
        pasos = estado.setdefault("recent_steps", [])
        if not pasos or pasos[-1] != accion:
            pasos.append(accion)
            if len(pasos) > MAX_PASOS_RECIENTES:
                del pasos[:-MAX_PASOS_RECIENTES]

    def _agregar_archivos_generados(
        self, estado: dict, nombre: str, entrada: dict
    ) -> None:
        archivos = estado.setdefault("generated_files", [])
        for ruta in _archivos_generados(nombre, entrada):
            if ruta not in archivos:
                archivos.append(ruta)

    def _marcar_fin(self, estado: dict, outcome: str) -> None:
        """Cierra el turno dejando el estado coherente para el servidor."""
        estado["is_processing"] = False
        estado["outcome"] = outcome
        estado["tool_action"] = ""
        estado["thought"] = ""
        estado["tool_name"] = ""
        estado["tool_detail"] = ""
        estado["permission_pending"] = None
        if not estado.get("last_message") and estado.get("streaming_text"):
            estado["last_message"] = estado["streaming_text"]

    def _reiniciar_turno(
        self, estado: dict, session_id: str, desde_ms: int | None = None
    ) -> None:
        """Limpia lo que es por turno, igual que USER_INPUT en Antigravity."""
        estado["is_processing"] = True
        estado["turno_iniciado_ms"] = (
            int(desde_ms) if desde_ms is not None else int(time.time() * 1000)
        )
        estado["thought"] = "Analizando los próximos pasos..."
        estado["tool_name"] = ""
        estado["tool_action"] = ACCION_PENSANDO
        estado["tool_detail"] = ""
        estado["step_index"] = 0
        estado["steps_count"] = 0
        estado["recent_steps"] = []
        estado["generated_files"] = []
        estado["streaming_text"] = ""
        estado["assistant_message_id"] = ""
        estado["outcome"] = ""
        estado["error"] = ""
        estado["permission_pending"] = None
        with self._candado:
            self._nombres_herramientas.pop(session_id, None)

    def _estado_inicial(self, session_id: str) -> dict:
        return {
            "session_id": session_id,
            "is_processing": False,
            "thought": "",
            "tool_name": "",
            "tool_action": "",
            "tool_detail": "",
            "step_index": 0,
            "steps_count": 0,
            "recent_steps": [],
            "generated_files": [],
            "last_message": "",
            "streaming_text": "",
            "assistant_message_id": "",
            "last_prompt_id": "",
            "outcome": "",
            "error": "",
            "model": None,
            "agent": "",
            "permission_pending": None,
            "turno_iniciado_ms": 0,
            "updated_at": 0.0,
        }

    def _asegurar_estado(self, session_id: str) -> dict:
        with self._candado:
            return self._estados.setdefault(
                session_id, self._estado_inicial(session_id)
            )

    # -- estado publico ---------------------------------------------------

    def adjuntar_sesion(self, session_id: str, sincronizar: bool = False) -> dict:
        """
        Empieza a seguir una sesion existente sin crearla.

        Sirve cuando TARS retoma un chat mapeado o cuando otro cliente creo la
        sesion. Con sincronizar=True consulta el estado real a la API.
        """
        self._asegurar_estado(session_id)
        if sincronizar:
            return self.sincronizar_estado(session_id)
        return self.estado_sesion(session_id)

    def estado_sesion(self, session_id: str) -> dict:
        """Copia thread-safe del estado en memoria de una sesion."""
        with self._candado:
            estado = self._estados.get(session_id)
            if estado is None:
                estado = self._estado_inicial(session_id)
                self._estados[session_id] = estado
            return copy.deepcopy(estado)

    def sesiones_activas(self) -> dict[str, dict]:
        """Sesiones que OpenCode esta ejecutando ahora mismo."""
        datos = self._request("GET", "/api/session/active")
        return (datos or {}).get("data") or {}

    def sincronizar_estado(self, session_id: str) -> dict:
        """
        Reconcilia el estado en memoria con la API.

        Es la red de seguridad para cuando el SSE se corto o TARS se engancha
        a una sesion que ya estaba corriendo.
        """
        info = self.obtener_sesion(session_id)
        estado = self._asegurar_estado(session_id)
        activas = self.sesiones_activas()
        activa = session_id in activas
        outcome = info.get("outcome") or ""

        with self._candado:
            if info.get("modelo"):
                estado["model"] = info["modelo"]
            if info.get("agente"):
                estado["agent"] = info["agente"]
            if activa:
                # Mientras hay una ejecucion activa, el outcome de la sesion
                # puede ser todavia el del turno anterior. No lo usamos para
                # cerrar el turno nuevo.
                estado["is_processing"] = True
                estado["outcome"] = ""
                if not estado.get("tool_action"):
                    estado["tool_action"] = ACCION_PENSANDO
                    estado["thought"] = "Analizando los próximos pasos..."
            elif outcome:
                self._marcar_fin(estado, outcome)
            else:
                estado["is_processing"] = False

        if outcome and not activa and not estado.get("last_message"):
            texto = self._texto_ultimo_asistente(session_id)
            if texto:
                with self._candado:
                    estado["last_message"] = texto
                    if not estado.get("streaming_text"):
                        estado["streaming_text"] = texto

        return self.estado_sesion(session_id)

    def _reconciliar_estados(self) -> None:
        """Revisa todas las sesiones seguidas despues de una reconexion SSE."""
        try:
            activas = self.sesiones_activas()
        except ErrorPuenteOpenCode:
            return
        with self._candado:
            sesiones = list(self._estados.keys())
        for session_id in sesiones:
            try:
                info = self.obtener_sesion(session_id)
            except ErrorPuenteOpenCode:
                continue
            estado = self._asegurar_estado(session_id)
            with self._candado:
                if info.get("modelo"):
                    estado["model"] = info["modelo"]
                outcome = info.get("outcome") or ""
                if session_id in activas:
                    estado["is_processing"] = True
                    estado["outcome"] = ""
                elif outcome:
                    self._marcar_fin(estado, outcome)
                else:
                    estado["is_processing"] = False

    def _texto_ultimo_asistente(self, session_id: str) -> str:
        """Busca el ultimo texto de assistant en el historial de la API."""
        try:
            mensajes = self._pedir_mensajes(session_id, limite=10, orden="desc")
        except ErrorPuenteOpenCode:
            return ""
        for mensaje in mensajes:
            if mensaje.get("type") != "assistant":
                continue
            textos = [
                str(parte.get("text") or "")
                for parte in (mensaje.get("content") or [])
                if isinstance(parte, dict) and parte.get("type") == "text"
            ]
            texto = "\n".join(t for t in textos if t)
            if texto:
                return texto
        return ""

    # -- sesiones ---------------------------------------------------------

    def crear_sesion(
        self,
        titulo: str | None = None,
        agente: str | None = None,
        modelo: str | dict | None = None,
        directorio: str | None = None,
        parent_id: str | None = None,
    ) -> str:
        """
        Crea una sesion y devuelve su sessionID.

        agente suele ser "tars" para el agente configurado por M0. Si no se
        pasa, se usa TARS_OPENCODE_AGENT o el agente por defecto del servicio.
        """
        cuerpo: dict[str, Any] = {}
        if titulo:
            cuerpo["title"] = str(titulo)
        agente_final = agente or self.agente_por_defecto
        if agente_final:
            cuerpo["agent"] = str(agente_final)
        if parent_id:
            cuerpo["parentID"] = str(parent_id)
        if directorio:
            cuerpo["location"] = {"directory": os.path.abspath(os.path.expanduser(directorio))}
        if modelo:
            ref = self._resolver_modelo_ref(modelo)
            if ref:
                cuerpo["model"] = ref

        datos = self._request("POST", "/api/session", json_body=cuerpo)
        info = (datos or {}).get("data") or {}
        session_id = info.get("id")
        if not session_id:
            raise ErrorAPI("OpenCode creo la sesion pero no devolvio un id.")
        estado = self._asegurar_estado(session_id)
        with self._candado:
            estado["model"] = info.get("model")
            estado["agent"] = info.get("agent") or ""
        self._log(f"Sesion creada: {session_id}")
        return session_id

    def obtener_sesion(self, session_id: str) -> dict:
        """Devuelve la sesion normalizada, tal como la reporta la API."""
        datos = self._request("GET", f"/api/session/{session_id}")
        return self._normalizar_sesion((datos or {}).get("data") or {})

    def sesion_existe(self, session_id: str) -> bool:
        """True si la sesion existe; False solo ante un 404."""
        try:
            self._request("GET", f"/api/session/{session_id}")
            return True
        except ErrorAPI as error:
            if error.status_code == 404:
                return False
            raise

    def listar_sesiones(
        self,
        limite: int = 50,
        orden: str = "desc",
        solo_raices: bool = True,
        buscar: str | None = None,
        directorio: str | None = None,
    ) -> list[dict]:
        """
        Lista sesiones de OpenCode, por defecto solo las raices.

        Las sesiones hijas son subagentes y no deberian aparecer como chats de
        TARS. orden acepta "asc" o "desc".
        """
        params: dict[str, Any] = {
            "limit": str(max(1, int(limite))),
            "order": "asc" if str(orden).lower() == "asc" else "desc",
        }
        if solo_raices:
            params["parentID"] = "null"
        if buscar:
            params["search"] = str(buscar)
        if directorio:
            params["directory"] = os.path.abspath(os.path.expanduser(directorio))

        datos = self._request("GET", "/api/session", params=params)
        sesiones = [
            self._normalizar_sesion(item)
            for item in ((datos or {}).get("data") or [])
            if isinstance(item, dict)
        ]
        mapa_inverso = self._mapa_inverso()
        for sesion in sesiones:
            sesion["chat_id"] = mapa_inverso.get(sesion["session_id"])
        return sesiones

    def _normalizar_sesion(self, datos: dict) -> dict:
        tiempos = datos.get("time") or {}
        locacion = datos.get("location") or {}
        return {
            "session_id": datos.get("id") or "",
            "titulo": datos.get("title") or "",
            "agente": datos.get("agent") or "",
            "modelo": datos.get("model"),
            "costo": datos.get("cost"),
            "tokens": datos.get("tokens") or {},
            "outcome": datos.get("outcome") or "",
            "creada": tiempos.get("created"),
            "actualizada": tiempos.get("updated"),
            "idle": tiempos.get("idle"),
            "directorio": locacion.get("directory") or "",
            "parent_id": datos.get("parentID"),
            "revertida": bool(datos.get("revert")),
        }

    def eliminar_sesion(self, session_id: str) -> bool:
        """Borra una sesion y sus hijas. Devuelve True si la API acepto."""
        self._request("DELETE", f"/api/session/{session_id}")
        with self._candado:
            self._estados.pop(session_id, None)
            self._nombres_herramientas.pop(session_id, None)
        self._olvidar_sesion_en_mapa(session_id)
        return True

    # -- prompts ----------------------------------------------------------

    def enviar_prompt(
        self,
        session_id: str,
        texto: str,
        archivos: list[dict] | None = None,
        agente: str | None = None,
        entrega: str = "steer",
        metadata: dict | None = None,
        resume: bool | None = None,
    ) -> dict:
        """
        Envia un prompt sin bloquear y devuelve enseguida.

        El texto de la respuesta se sigue por el estado en memoria. Para
        esperar el final usar esperar_respuesta(). archivos acepta la forma
        Prompt.FileAttachment de la API.
        """
        if not str(texto or "").strip():
            raise ValueError("El prompt no puede estar vacio.")

        estado = self._asegurar_estado(session_id)
        with self._candado:
            self._reiniciar_turno(estado, session_id)

        cuerpo: dict[str, Any] = {
            "text": str(texto),
            "delivery": "queue" if str(entrega).lower() == "queue" else "steer",
        }
        if archivos:
            cuerpo["files"] = archivos
        if agente:
            cuerpo["agents"] = [{"name": str(agente)}]
        if metadata:
            cuerpo["metadata"] = metadata
        if resume is not None:
            cuerpo["resume"] = bool(resume)

        try:
            datos = self._request(
                "POST", f"/api/session/{session_id}/prompt", json_body=cuerpo
            )
        except ErrorPuenteOpenCode:
            with self._candado:
                estado["is_processing"] = False
                estado["outcome"] = "failed"
                estado["tool_action"] = ""
            raise

        item = (datos or {}).get("data") or {}
        with self._candado:
            estado["last_prompt_id"] = str(item.get("id") or "")
        return {
            "ok": True,
            "session_id": session_id,
            "prompt_id": item.get("id"),
            "entrega": cuerpo["delivery"],
            "estado": self.estado_sesion(session_id),
        }

    def esperar_respuesta(
        self,
        session_id: str,
        timeout: float = 120.0,
        intervalo: float = 0.2,
        sincronizar_cada: float = 3.0,
    ) -> dict:
        """
        Espera a que la sesion termine y devuelve la respuesta final.

        Ademas de mirar el SSE, cada pocos segundos reconcilia contra la API
        para no quedarse colgado si se perdio un evento.
        """
        inicio = time.time()
        ultima_sincronizacion = 0.0
        while time.time() - inicio < timeout:
            estado = self.estado_sesion(session_id)
            if not estado.get("is_processing") and estado.get("outcome"):
                return {
                    "ok": estado.get("outcome") == "succeeded",
                    "outcome": estado.get("outcome"),
                    "texto": estado.get("last_message") or "",
                    "session_id": session_id,
                    "estado": estado,
                }
            ahora = time.time()
            if sincronizar_cada > 0 and ahora - ultima_sincronizacion >= sincronizar_cada:
                ultima_sincronizacion = ahora
                try:
                    self.sincronizar_estado(session_id)
                except ErrorPuenteOpenCode:
                    pass
            time.sleep(intervalo)

        estado = self.estado_sesion(session_id)
        return {
            "ok": False,
            "outcome": estado.get("outcome") or "timeout",
            "timeout": True,
            "texto": estado.get("last_message") or "",
            "session_id": session_id,
            "estado": estado,
        }

    def cancelar(self, session_id: str, resume: bool = False) -> dict:
        """
        Interrumpe la ejecucion activa de una sesion.

        Devuelve interrupted=True solo si habia algo corriendo. El kill del
        audio de TARS queda del lado del servidor: este puente solo frena el
        cerebro de OpenCode.
        """
        params = {"resume": "true" if resume else "false"}
        datos = self._request(
            "POST", f"/api/session/{session_id}/interrupt", params=params
        )
        interrupted = bool((datos or {}).get("interrupted"))
        if interrupted:
            with self._candado:
                estado = self._asegurar_estado(session_id)
                self._marcar_fin(estado, "interrupted")
                estado["updated_at"] = time.time()
        return {
            "ok": True,
            "session_id": session_id,
            "interrupted": interrupted,
            "mensaje": (
                "Ejecucion interrumpida."
                if interrupted
                else "La sesion ya estaba inactiva; no habia nada que interrumpir."
            ),
            "estado": self.estado_sesion(session_id),
        }

    # -- modelos ----------------------------------------------------------

    def listar_modelos(self, directorio: str | None = None) -> list[dict]:
        """
        Lista los modelos reales que ofrece OpenCode.

        Cada item trae modelo_ref con la forma exacta que espera la API para
        aplicar_modelo o crear_sesion.
        """
        params: dict[str, Any] = {}
        if directorio:
            params["location[directory]"] = os.path.abspath(os.path.expanduser(directorio))
        datos = self._request("GET", "/api/model", params=params or None)
        modelos: list[dict] = []
        for item in ((datos or {}).get("data") or []):
            if not isinstance(item, dict):
                continue
            modelo_id = item.get("modelID") or item.get("id")
            proveedor = item.get("providerID") or ""
            if not modelo_id or not proveedor:
                continue
            variantes = [
                str(v.get("id"))
                for v in (item.get("variants") or [])
                if isinstance(v, dict) and v.get("id")
            ]
            modelos.append(
                {
                    "id": str(modelo_id),
                    "nombre": item.get("name") or str(modelo_id),
                    "proveedor": str(proveedor),
                    "habilitado": bool(item.get("enabled", True)),
                    "estado": item.get("status") or "",
                    "variantes": variantes,
                    "modelo_ref": {"id": str(modelo_id), "providerID": str(proveedor)},
                }
            )
        return modelos

    def _resolver_modelo_ref(
        self,
        modelo: str | dict,
        proveedor: str | None = None,
        variante: str | None = None,
    ) -> dict | None:
        """Convierte un id o dict en el Model.Ref exacto de la API."""
        if isinstance(modelo, dict):
            ref_id = modelo.get("id") or modelo.get("modelID")
            ref_proveedor = (
                modelo.get("providerID")
                or modelo.get("provider_id")
                or modelo.get("proveedor")
                or proveedor
            )
            ref_variante = modelo.get("variant") or modelo.get("variante") or variante
            if not ref_id or not ref_proveedor:
                raise ValueError("El modelo necesita id y proveedor.")
            ref: dict[str, Any] = {
                "id": str(ref_id),
                "providerID": str(ref_proveedor),
            }
            if ref_variante:
                ref["variant"] = str(ref_variante)
            return ref

        modelo_id = str(modelo or "").strip()
        if not modelo_id:
            return None
        proveedor_final = proveedor
        if not proveedor_final:
            for item in self.listar_modelos():
                if item["id"] == modelo_id and item["habilitado"]:
                    proveedor_final = item["proveedor"]
                    break
        if not proveedor_final:
            raise ValueError(
                f"No encontre el modelo '{modelo_id}' entre los modelos de OpenCode."
            )
        ref = {"id": modelo_id, "providerID": str(proveedor_final)}
        if variante:
            ref["variant"] = str(variante)
        return ref

    def modelo_activo(self, session_id: str) -> dict | None:
        """Modelo que la sesion usa ahora, leido de la API y no del SSE."""
        return self.obtener_sesion(session_id).get("modelo")

    def aplicar_modelo(
        self,
        session_id: str,
        modelo_id: str | dict,
        proveedor: str | None = None,
        variante: str | None = None,
    ) -> dict:
        """
        Aplica un modelo a una sesion viva y verifica que la API lo acepto.

        La verificacion se hace releyendo GET /api/session/{sid}: no se
        confia en lo que el modelo diga de si mismo.
        """
        ref = self._resolver_modelo_ref(modelo_id, proveedor, variante)
        if not ref:
            raise ValueError("Falta indicar el modelo.")
        self._request(
            "POST", f"/api/session/{session_id}/model", json_body={"model": ref}
        )
        activo = self.modelo_activo(session_id)
        coincide = bool(
            activo
            and activo.get("id") == ref["id"]
            and activo.get("providerID") == ref["providerID"]
        )
        if coincide and ref.get("variant"):
            coincide = activo.get("variant") == ref["variant"]
        if coincide:
            with self._candado:
                self._asegurar_estado(session_id)["model"] = activo
        return {
            "ok": coincide,
            "session_id": session_id,
            "modelo_solicitado": ref,
            "modelo_activo": activo,
            "mensaje": (
                "Modelo aplicado y verificado en la sesion."
                if coincide
                else "La API acepto el cambio pero la sesion sigue con otro modelo."
            ),
        }

    # -- historial --------------------------------------------------------

    def historial(
        self,
        session_id: str,
        limite: int = 100,
        orden: str = "asc",
    ) -> list[dict]:
        """
        Devuelve el historial normalizado de una sesion.

        Solo incluye turnos utiles para un chat: usuario y tars. Las herramientas
        quedan como detalle del turno de tars, no como mensajes sueltos.
        """
        crudos = self._pedir_mensajes(session_id, limite=limite, orden=orden)
        historial: list[dict] = []
        for mensaje in crudos:
            tipo = mensaje.get("type")
            tiempos = mensaje.get("time") or {}
            if tipo == "user":
                historial.append(
                    {
                        "id": mensaje.get("id"),
                        "rol": "usuario",
                        "texto": mensaje.get("text") or "",
                        "fecha": tiempos.get("created"),
                        "archivos": mensaje.get("files") or [],
                    }
                )
            elif tipo == "assistant":
                textos: list[str] = []
                herramientas: list[dict] = []
                for parte in mensaje.get("content") or []:
                    if not isinstance(parte, dict):
                        continue
                    if parte.get("type") == "text":
                        texto = str(parte.get("text") or "")
                        if texto:
                            textos.append(texto)
                    elif parte.get("type") == "tool":
                        nombre = str(parte.get("name") or "")
                        estado_parte = parte.get("state") or {}
                        entrada = estado_parte.get("input")
                        if not isinstance(entrada, dict):
                            entrada = {}
                        herramientas.append(
                            {
                                "nombre": nombre,
                                "estado": estado_parte.get("status") or "",
                                "accion": format_spanish_tool_action(nombre, entrada),
                            }
                        )
                texto = "\n".join(textos).strip()
                if not texto and not herramientas:
                    continue
                historial.append(
                    {
                        "id": mensaje.get("id"),
                        "rol": "tars",
                        "texto": texto,
                        "fecha": tiempos.get("created"),
                        "modelo": mensaje.get("model"),
                        "agente": mensaje.get("agent") or "",
                        "herramientas": herramientas,
                        "finish": mensaje.get("finish") or "",
                    }
                )
        return historial

    def _pedir_mensajes(
        self, session_id: str, limite: int = 100, orden: str = "asc"
    ) -> list[dict]:
        """Pide mensajes paginando con cursor hasta juntar el limite."""
        restantes = max(0, int(limite))
        if restantes == 0:
            return []
        cursor: str | None = None
        mensajes: list[dict] = []
        while restantes > 0:
            params: dict[str, Any] = {"limit": str(min(100, restantes))}
            if cursor:
                params["cursor"] = cursor
            else:
                params["order"] = "desc" if str(orden).lower() == "desc" else "asc"
            datos = self._request(
                "GET", f"/api/session/{session_id}/message", params=params
            )
            pagina = (datos or {}).get("data") or []
            mensajes.extend(item for item in pagina if isinstance(item, dict))
            restantes = max(0, int(limite) - len(mensajes))
            cursor = ((datos or {}).get("cursor") or {}).get("next")
            if not cursor or not pagina:
                break
        return mensajes

    # -- permisos, base para M5 ------------------------------------------

    def permisos_pendientes(self, session_id: str) -> list[dict]:
        """Lista los pedidos de permiso pendientes de una sesion."""
        datos = self._request("GET", f"/api/session/{session_id}/permission")
        return (datos or {}).get("data") or []

    def responder_permiso(
        self, session_id: str, request_id: str, decision: str = "once"
    ) -> bool:
        """
        Responde un permiso pendiente.

        decision acepta once, always o reject, los valores de Permission.Reply.
        """
        if decision not in ("once", "always", "reject"):
            raise ValueError("decision debe ser once, always o reject.")
        self._request(
            "POST",
            f"/api/session/{session_id}/permission/{request_id}/reply",
            json_body={"decision": decision},
        )
        return True

    # -- mapa chat_id de TARS <-> sessionID ------------------------------

    def _cargar_mapa(self) -> None:
        ruta = self.mapa_path
        with self._candado_mapa:
            if not os.path.exists(ruta):
                self._mapa = {}
                return
            try:
                with open(ruta, "r", encoding="utf-8") as archivo:
                    datos = json.load(archivo)
            except (OSError, ValueError) as error:
                self._mapa = {}
                self._mapa_error = f"No pude leer {ruta}: {error}"
                print(f"[Puente OpenCode] {self._mapa_error}", flush=True)
                return
            if isinstance(datos, dict) and isinstance(datos.get("chats"), dict):
                self._mapa = datos["chats"]
            elif isinstance(datos, dict):
                # Compatibilidad con un mapa plano chat_id -> sessionID.
                self._mapa = datos
            else:
                self._mapa = {}

    def _guardar_mapa(self) -> bool:
        """Guarda el mapa de forma atomica. Devuelve False si no pudo."""
        with self._candado_mapa:
            try:
                os.makedirs(os.path.dirname(self.mapa_path) or ".", exist_ok=True)
                temporal = self.mapa_path + ".tmp"
                with open(temporal, "w", encoding="utf-8") as archivo:
                    json.dump(
                        {"version": VERSION_MAPA, "chats": self._mapa},
                        archivo,
                        ensure_ascii=False,
                        indent=2,
                    )
                os.replace(temporal, self.mapa_path)
                self._mapa_error = ""
                return True
            except OSError as error:
                self._mapa_error = f"No pude guardar {self.mapa_path}: {error}"
                print(f"[Puente OpenCode] {self._mapa_error}", flush=True)
                return False

    def _entrada_mapa(self, valor: Any) -> dict:
        if isinstance(valor, str):
            return {"session_id": valor, "titulo": "", "actualizado": None}
        if isinstance(valor, dict):
            return {
                "session_id": str(valor.get("session_id") or valor.get("sessionID") or ""),
                "titulo": str(valor.get("titulo") or valor.get("title") or ""),
                "actualizado": valor.get("actualizado") or valor.get("updated"),
            }
        return {"session_id": "", "titulo": "", "actualizado": None}

    def vincular_chat(
        self, chat_id: str, session_id: str, titulo: str | None = None
    ) -> bool:
        """Guarda o actualiza el mapa chat_id de TARS -> sessionID."""
        chat_id = str(chat_id or "").strip()
        session_id = str(session_id or "").strip()
        if not chat_id or not session_id:
            raise ValueError("chat_id y session_id son obligatorios.")
        with self._candado_mapa:
            anterior = self._entrada_mapa(self._mapa.get(chat_id) or {})
            self._mapa[chat_id] = {
                "session_id": session_id,
                "titulo": str(titulo or anterior.get("titulo") or ""),
                "actualizado": int(time.time() * 1000),
            }
            return self._guardar_mapa()

    def desvincular_chat(self, chat_id: str) -> bool:
        """Borra un chat del mapa persistido."""
        chat_id = str(chat_id or "").strip()
        with self._candado_mapa:
            if chat_id not in self._mapa:
                return True
            self._mapa.pop(chat_id, None)
            return self._guardar_mapa()

    def sesion_de_chat(self, chat_id: str) -> str | None:
        """Devuelve el sessionID asociado a un chat de TARS."""
        with self._candado_mapa:
            valor = self._mapa.get(str(chat_id or "").strip())
            if valor is None:
                return None
            session_id = self._entrada_mapa(valor)["session_id"]
            return session_id or None

    def chat_de_sesion(self, session_id: str) -> str | None:
        """Devuelve el chat de TARS asociado a un sessionID."""
        return self._mapa_inverso().get(str(session_id or ""))

    def _mapa_inverso(self) -> dict[str, str]:
        with self._candado_mapa:
            inverso: dict[str, str] = {}
            for chat_id, valor in self._mapa.items():
                session_id = self._entrada_mapa(valor)["session_id"]
                if session_id and session_id not in inverso:
                    inverso[session_id] = chat_id
            return inverso

    def listar_chats(self) -> dict[str, dict]:
        """Copia del mapa persistido, normalizada."""
        with self._candado_mapa:
            return {
                chat_id: self._entrada_mapa(valor)
                for chat_id, valor in self._mapa.items()
            }

    def _olvidar_sesion_en_mapa(self, session_id: str) -> None:
        with self._candado_mapa:
            chats = [
                chat_id
                for chat_id, valor in self._mapa.items()
                if self._entrada_mapa(valor)["session_id"] == session_id
            ]
            for chat_id in chats:
                self._mapa.pop(chat_id, None)
            if chats:
                self._guardar_mapa()

    def crear_sesion_para_chat(
        self,
        chat_id: str,
        titulo: str | None = None,
        agente: str | None = None,
        modelo: str | dict | None = None,
        directorio: str | None = None,
        reutilizar: bool = True,
    ) -> str:
        """
        Devuelve el sessionID del chat, creandolo si hace falta.

        Con reutilizar=True valida que la sesion mapeada siga existiendo; si el
        usuario la borro desde OpenCode, se crea una nueva y se actualiza el mapa.
        """
        if reutilizar:
            existente = self.sesion_de_chat(chat_id)
            if existente and self.sesion_existe(existente):
                return existente
        session_id = self.crear_sesion(
            titulo=titulo or chat_id,
            agente=agente,
            modelo=modelo,
            directorio=directorio,
        )
        self.vincular_chat(chat_id, session_id, titulo=titulo or chat_id)
        return session_id

    # -- atajos por chat, para M3 ----------------------------------------

    def estado_chat(self, chat_id: str) -> dict | None:
        """Estado de la sesion asociada a un chat, o None si no hay mapa."""
        session_id = self.sesion_de_chat(chat_id)
        if not session_id:
            return None
        return self.estado_sesion(session_id)

    def sincronizar_chat(self, chat_id: str) -> dict | None:
        """Reconcilia contra la API el estado del chat mapeado."""
        session_id = self.sesion_de_chat(chat_id)
        if not session_id:
            return None
        self.adjuntar_sesion(session_id)
        return self.sincronizar_estado(session_id)

    def enviar_prompt_chat(
        self,
        chat_id: str,
        texto: str,
        titulo: str | None = None,
        agente: str | None = None,
        modelo: str | dict | None = None,
        directorio: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """Atajo: resuelve o crea la sesion del chat y manda el prompt."""
        session_id = self.crear_sesion_para_chat(
            chat_id,
            titulo=titulo,
            agente=agente,
            modelo=modelo,
            directorio=directorio,
        )
        resultado = self.enviar_prompt(session_id, texto, **kwargs)
        resultado["chat_id"] = chat_id
        return resultado

    def cancelar_chat(self, chat_id: str, resume: bool = False) -> dict:
        """Atajo: interrumpe la sesion asociada a un chat."""
        session_id = self.sesion_de_chat(chat_id)
        if not session_id:
            return {
                "ok": False,
                "chat_id": chat_id,
                "interrupted": False,
                "mensaje": "Ese chat de TARS no tiene una sesion de OpenCode.",
            }
        resultado = self.cancelar(session_id, resume=resume)
        resultado["chat_id"] = chat_id
        return resultado

    def historial_chat(self, chat_id: str, limite: int = 100) -> list[dict]:
        """Atajo: historial del chat mapeado."""
        session_id = self.sesion_de_chat(chat_id)
        if not session_id:
            return []
        self.adjuntar_sesion(session_id)
        return self.historial(session_id, limite=limite)

    def aplicar_modelo_chat(
        self,
        chat_id: str,
        modelo_id: str | dict,
        proveedor: str | None = None,
        variante: str | None = None,
    ) -> dict:
        """Atajo: aplica el modelo a la sesion asociada a un chat."""
        session_id = self.sesion_de_chat(chat_id)
        if not session_id:
            return {
                "ok": False,
                "chat_id": chat_id,
                "mensaje": "Ese chat de TARS no tiene una sesion de OpenCode.",
            }
        resultado = self.aplicar_modelo(
            session_id, modelo_id, proveedor=proveedor, variante=variante
        )
        resultado["chat_id"] = chat_id
        return resultado


# ---------------------------------------------------------------------------
# CLI de aceptacion
# ---------------------------------------------------------------------------


def _imprimir_estado_clave(estado: dict) -> str:
    """Resumen legible del estado para los tests de aceptacion."""
    claves = (
        "session_id",
        "is_processing",
        "outcome",
        "tool_action",
        "recent_steps",
        "generated_files",
        "last_message",
    )
    return json.dumps(
        {clave: estado.get(clave) for clave in claves},
        ensure_ascii=False,
        indent=2,
    )


def _test_m1(args: argparse.Namespace) -> int:
    """Criterio M1: prompt, respuesta llegando e interrupt a mitad de camino."""
    print("Descubriendo el servicio local de OpenCode...")
    with PuenteOpenCode(verbose=True) as puente:
        print(f"Servicio: {puente.url} ({puente.origen_descubrimiento})")
        session_id = puente.crear_sesion(titulo="TARS test M1")
        print(f"Sesion: {session_id}")
        print(f"Mapa de chats: {puente.mapa_path}")

        puente.enviar_prompt(session_id, args.prompt)
        print("Prompt enviado. Esperando la respuesta por SSE...")

        inicio = time.time()
        primer_texto = None
        ultimo_largo = 0
        while time.time() - inicio < args.max_espera:
            estado = puente.estado_sesion(session_id)
            texto = estado.get("streaming_text") or ""
            if len(texto) > ultimo_largo:
                if primer_texto is None:
                    primer_texto = time.time()
                    print("\n[TARS responde] ", end="", flush=True)
                print(texto[ultimo_largo:], end="", flush=True)
                ultimo_largo = len(texto)
            if primer_texto is not None and time.time() - primer_texto >= args.cortar_en:
                break
            time.sleep(0.15)

        print("\n\nCancelando a mitad de la respuesta...")
        resultado_cancelar = puente.cancelar(session_id)
        print(
            "Interrupt:",
            json.dumps(resultado_cancelar, ensure_ascii=False)[:400],
        )

        limite = time.time() + 10
        estado_final = puente.estado_sesion(session_id)
        while time.time() < limite:
            estado_final = puente.estado_sesion(session_id)
            if not estado_final.get("is_processing"):
                break
            time.sleep(0.2)
        if estado_final.get("is_processing"):
            estado_final = puente.sincronizar_estado(session_id)

        print("\nEstado final:")
        print(_imprimir_estado_clave(estado_final))
        print("\nHistorial final:")
        for mensaje in puente.historial(session_id, limite=10):
            texto = (mensaje.get("texto") or "").replace("\n", " ")
            print(
                f"- {mensaje['rol']}: {texto[:180]}"
                + ("..." if len(texto) > 180 else "")
            )

        ok = (
            primer_texto is not None
            and not estado_final.get("is_processing")
            and estado_final.get("outcome") == "interrupted"
            and bool(estado_final.get("last_message"))
        )
        print(
            "\nResultado M1:",
            "OK" if ok else "FALLO",
            "(respuesta parcial conservada e interrupt confirmado)",
        )
        return 0 if ok else 1


def _elegir_modelos(puente: PuenteOpenCode, preferido_a: str, preferido_b: str) -> tuple[dict, dict]:
    """Elige dos modelos habilitados, prefiriendo los pedidos por CLI."""
    modelos = [m for m in puente.listar_modelos() if m.get("habilitado")]
    por_id = {m["id"]: m for m in modelos}
    modelo_a = por_id.get(preferido_a)
    modelo_b = por_id.get(preferido_b)
    if not modelo_a and modelos:
        modelo_a = modelos[0]
    if not modelo_b:
        modelo_b = next((m for m in modelos if m["id"] != modelo_a["id"]), None)
    if not modelo_a or not modelo_b:
        raise SystemExit("No hay al menos dos modelos habilitados para el test M2.")
    return modelo_a, modelo_b


def _modelo_del_ultimo_turno(mensajes: list[dict]) -> dict | None:
    """Devuelve el modelo del ultimo turno de tars del historial."""
    for mensaje in reversed(mensajes):
        if mensaje.get("rol") == "tars" and mensaje.get("modelo"):
            return mensaje["modelo"]
    return None


def _test_m2(args: argparse.Namespace) -> int:
    """Criterio M2: modelos, sesiones e historial contra el servicio vivo."""
    with PuenteOpenCode(verbose=True) as puente:
        print(f"Servicio: {puente.url} ({puente.origen_descubrimiento})")

        modelos = puente.listar_modelos()
        print(f"Modelos disponibles: {len(modelos)}")
        for modelo in modelos[:12]:
            print(
                f"- {modelo['proveedor']}/{modelo['id']} | {modelo['nombre']} "
                f"| variantes={modelo['variantes']}"
            )

        modelo_a, modelo_b = _elegir_modelos(
            puente, args.modelo_a, args.modelo_b
        )
        print(
            f"\nModelo A: {modelo_a['proveedor']}/{modelo_a['id']}\n"
            f"Modelo B: {modelo_b['proveedor']}/{modelo_b['id']}"
        )

        session_id = puente.crear_sesion(
            titulo="TARS test M2", modelo=modelo_a["modelo_ref"]
        )
        print(f"Sesion: {session_id}")

        cambio_a = puente.aplicar_modelo(
            session_id, modelo_a["modelo_ref"]
        )
        activo_a = puente.modelo_activo(session_id)
        print(f"\nCambio a A: {json.dumps(cambio_a, ensure_ascii=False)}")
        print(f"Modelo activo leido de la API: {json.dumps(activo_a, ensure_ascii=False)}")

        puente.enviar_prompt(
            session_id,
            "Responde en una sola oracion: decime que modelo estas usando.",
        )
        respuesta_a = puente.esperar_respuesta(session_id, timeout=args.timeout)
        print(f"\nRespuesta con A: {respuesta_a.get('texto')}")
        historial_a = puente.historial(session_id, limite=50)
        modelo_respuesta_a = _modelo_del_ultimo_turno(historial_a)
        print(
            "Modelo del mensaje assistant A: "
            f"{json.dumps(modelo_respuesta_a, ensure_ascii=False)}"
        )

        cambio_b = puente.aplicar_modelo(
            session_id, modelo_b["modelo_ref"]
        )
        activo_b = puente.modelo_activo(session_id)
        print(f"\nCambio a B: {json.dumps(cambio_b, ensure_ascii=False)}")
        print(f"Modelo activo leido de la API: {json.dumps(activo_b, ensure_ascii=False)}")

        puente.enviar_prompt(
            session_id,
            "Responde en una sola oracion: decime que modelo estas usando ahora.",
        )
        respuesta_b = puente.esperar_respuesta(session_id, timeout=args.timeout)
        print(f"\nRespuesta con B: {respuesta_b.get('texto')}")
        historial_b = puente.historial(session_id, limite=50)
        modelo_respuesta_b = _modelo_del_ultimo_turno(historial_b)
        print(
            "Modelo del mensaje assistant B: "
            f"{json.dumps(modelo_respuesta_b, ensure_ascii=False)}"
        )

        print(f"\nHistorial del chat: {len(historial_b)} turnos utiles")
        for mensaje in historial_b:
            texto = (mensaje.get("texto") or "").replace("\n", " ")
            print(
                f"- {mensaje['rol']}: {texto[:160]}"
                + ("..." if len(texto) > 160 else "")
            )

        sesiones = puente.listar_sesiones(limite=10)
        print(f"\nSesiones listadas: {len(sesiones)}")
        for sesion in sesiones[:5]:
            print(
                f"- {sesion['session_id']} | {sesion['titulo']} | "
                f"{sesion['modelo']}"
            )

        def coincide(modelo: dict | None, esperado: dict) -> bool:
            return bool(
                modelo
                and modelo.get("id") == esperado["id"]
                and modelo.get("providerID") == esperado["providerID"]
            )

        ok = (
            coincide(activo_a, modelo_a["modelo_ref"])
            and coincide(modelo_respuesta_a, modelo_a["modelo_ref"])
            and coincide(activo_b, modelo_b["modelo_ref"])
            and coincide(modelo_respuesta_b, modelo_b["modelo_ref"])
            and respuesta_a.get("ok")
            and respuesta_b.get("ok")
            and any(s["session_id"] == session_id for s in sesiones)
        )
        print("\nResultado M2:", "OK" if ok else "FALLO")
        return 0 if ok else 1


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Puente entre TARS y el servicio local de OpenCode."
    )
    subparsers = parser.add_subparsers(dest="comando")

    estado_parser = subparsers.add_parser(
        "estado", help="Muestra servicio, mapa y sesiones activas."
    )
    estado_parser.add_argument("--sesiones", type=int, default=5)

    m1_parser = subparsers.add_parser(
        "test-m1", help="Test de aceptacion de M1: prompt e interrupt."
    )
    m1_parser.add_argument(
        "--prompt",
        default=(
            "Contame un cuento largo capitulo a capitulo, con muchos detalles. "
            "Empeza por el capitulo 1 y segui con el capitulo 2."
        ),
    )
    m1_parser.add_argument("--cortar-en", type=float, default=5.0)
    m1_parser.add_argument("--max-espera", type=float, default=60.0)

    m2_parser = subparsers.add_parser(
        "test-m2", help="Test de aceptacion de M2: modelos e historial."
    )
    m2_parser.add_argument(
        "--modelo-a", default="deepseek-v4.1-flash-free"
    )
    m2_parser.add_argument("--modelo-b", default="mimo-v2.6-flash-free")
    m2_parser.add_argument("--timeout", type=float, default=180.0)

    args = parser.parse_args(argv)
    if args.comando == "test-m1":
        return _test_m1(args)
    if args.comando == "test-m2":
        return _test_m2(args)

    with PuenteOpenCode(verbose=True) as puente:
        print(f"Servicio: {puente.url}")
        print(f"Origen: {puente.origen_descubrimiento}")
        print(f"Version: {puente.info_servicio.get('version')}")
        print(f"Mapa de chats: {puente.mapa_path}")
        print(f"Sesiones activas: {json.dumps(puente.sesiones_activas(), ensure_ascii=False)}")
        print(f"Chats mapeados: {json.dumps(puente.listar_chats(), ensure_ascii=False)}")
        for sesion in puente.listar_sesiones(limite=args.sesiones):
            print(
                f"- {sesion['session_id']} | {sesion['titulo']} | "
                f"{sesion['modelo']} | outcome={sesion['outcome']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
