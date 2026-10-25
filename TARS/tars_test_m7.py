#!/usr/bin/env python3
"""
Tests de aceptacion de M7 (voz en la PC) sin depender de microfono ni
altavoz reales.

Secciones:
  --nucleo     rutas, transcripcion Vosk offline, dictado -> puente -> TTS,
               cancelacion por voz con is_processing true
  --solo-tray  build de QApplication offscreen con el menu y el estado
  (ninguna)    orquesta las dos anteriores en subprocosos con timeout

Corrida tipica:

    ~/.gemini/tts_venv/bin/python TARS/tars_test_m7.py

Reglas de estos tests:
- Todos los caminos tienen timeout; no hay bucles abiertos.
- No se reproduce audio: los tonos y el reproductor se capturan con stubs.
- No se abre el microfono: el audio entra por un stream falso leido de wav.
- Todo lo que toca tars_state.json vuelve al estado inicial.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import wave

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

PY_VENV = os.path.expanduser("~/.gemini/tts_venv/bin/python")
PY_SISTEMA = "/usr/bin/python3"

WAV_DICTADO = "/tmp/tars_m7_dictado.wav"
WAV_DICTADO_16K = "/tmp/tars_m7_dictado_16k.wav"
WAV_CANCEL = "/tmp/tars_m7_cancelar.wav"
WAV_CANCEL_16K = "/tmp/tars_m7_cancelar_16k.wav"
MAPA_TEST = "/tmp/tars_m7_opencode_sessions.json"
RUTA_ESTADO_TEST = "/tmp/tars_m7_estado_previo.json"

# El mapa de sesiones de estos tests va aparte para no pisar el del usuario
os.environ.setdefault("TARS_OPENCODE_SESSIONS_FILE", MAPA_TEST)

TIMEOUT_NUCLEO = 600
TIMEOUT_TRAY = 90


def log(mensaje):
    print(f"[TARS][test] {mensaje}", flush=True)


# ---------------------------------------------------------------------------
# Utilidades de audio
# ---------------------------------------------------------------------------

def generar_wav(texto, ruta, voz="es"):
    """Sintetiza un wav corto en forma local, sin red."""
    binario = shutil.which("espeak-ng")
    if binario:
        try:
            proceso = subprocess.run(
                [binario, "-v", voz, "-s", "160", "-p", "50", "-w", ruta, texto],
                capture_output=True, timeout=60,
            )
            if proceso.returncode == 0 and os.path.exists(ruta) and os.path.getsize(ruta) > 200:
                return ruta
        except Exception as exc:
            log(f"espeak-ng fallo ({exc}), uso el wav de respaldo")
    respaldo = os.path.join(BASE_DIR, "ya_tengo_tu_respuesta.wav")
    shutil.copy(respaldo, ruta)
    return ruta


def a_16k_mono(origen, destino):
    """Deja el wav en 16 kHz mono s16, que es lo que come Vosk."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", origen, "-ar", "16000", "-ac", "1",
         "-acodec", "pcm_s16le", destino],
        capture_output=True, timeout=60,
    )
    if not os.path.exists(destino):
        raise AssertionError(f"ffmpeg no genero {destino}")
    return destino


class StreamDeArchivo:
    """
    Imita sounddevice.RawInputStream con un wav: read(n) devuelve n muestras
    int16 mono y silencio cuando se acaba el archivo.
    """

    def __init__(self, ruta, bucle=False):
        with wave.open(ruta, "rb") as archivo:
            self._datos = archivo.readframes(archivo.getnframes())
        self._pos = 0
        self._bucle = bucle

    def read(self, muestras):
        bytes_necesarios = muestras * 2
        if self._pos >= len(self._datos):
            if self._bucle:
                self._pos = 0
            else:
                return (b"\x00" * bytes_necesarios, False)
        trozo = self._datos[self._pos:self._pos + bytes_necesarios]
        self._pos += len(trozo)
        if len(trozo) < bytes_necesarios:
            trozo = trozo + (b"\x00" * (bytes_necesarios - len(trozo)))
        return (trozo, False)


def cargar_modelo():
    import vosk
    from tars_rutas import ruta_modelo_vosk
    ruta = ruta_modelo_vosk()
    if not os.path.isdir(ruta):
        raise AssertionError(f"No esta el modelo de Vosk en {ruta}")
    vosk.SetLogLevel(-1)
    return vosk.Model(ruta)


def transcribir(modelo, ruta_16k):
    """Corre Vosk sobre un wav y devuelve el texto final combinado."""
    import vosk
    reconocedor = vosk.KaldiRecognizer(modelo, 16000)
    stream = StreamDeArchivo(ruta_16k)
    finales = []
    parcial = ""
    inicio = time.time()
    vueltas = 0
    while vueltas < 600 and (time.time() - inicio) < 60.0:
        vueltas += 1
        data, _ = stream.read(4000)
        if reconocedor.AcceptWaveform(bytes(data)):
            texto = json.loads(reconocedor.Result()).get("text", "")
            if texto:
                finales.append(texto)
                parcial = ""
        else:
            parcial = json.loads(reconocedor.PartialResult()).get("partial", "")
        if not stream._bucle and stream._pos >= len(stream._datos) and not parcial:
            break
    ultimo = json.loads(reconocedor.FinalResult()).get("text", "")
    if ultimo:
        finales.append(ultimo)
    return " ".join(finales + ([parcial] if parcial else [])).strip()


# ---------------------------------------------------------------------------
# Seccion 1: rutas y convenciones
# ---------------------------------------------------------------------------

def seccion_rutas():
    from tars_rutas import (
        cerebro_activo,
        directorio_config_tars,
        etiqueta_servicio_opencode,
        servicio_opencode,
    )

    # Armado por partes para que este mismo archivo no se autoincrimine
    ruta_fija = "/home" + "/santiago"
    archivos = [
        "tars_wake_word.py",
        "tars_tray.py",
        "tars_voice_engine.py",
        "tars_player.py",
        "speak_response.py",
        "tars_rutas.py",
        "tars_iconos_cerebro.py",
        "tars_test_m7.py",
    ]
    for nombre in archivos:
        with open(os.path.join(BASE_DIR, nombre), "r", encoding="utf-8") as archivo:
            contenido = archivo.read()
        assert ruta_fija not in contenido, f"{nombre} tiene ruta fija de usuario"
    log("ningun archivo de M7 tiene rutas fijas de usuario")

    config = directorio_config_tars()
    hogar = os.path.expanduser("~")
    assert config.startswith(hogar), f"config fuera del home: {config}"
    log(f"directorio de config resuelto: {config}")

    cerebro = cerebro_activo()
    assert cerebro in ("opencode", "antigravity")
    log(f"cerebro por defecto: {cerebro}")

    info = servicio_opencode()
    assert "password" not in info, "el estado del servicio no puede traer password"
    etiqueta = etiqueta_servicio_opencode(info)
    assert etiqueta.startswith("OpenCode"), etiqueta
    log(f"estado del servicio: {etiqueta} (puerto={info.get('puerto')} pid={info.get('pid')})")


# ---------------------------------------------------------------------------
# Seccion 2: transcripcion Vosk offline
# ---------------------------------------------------------------------------

def seccion_vosk():
    modelo = cargar_modelo()
    origen = generar_wav("Hola TARS, probando el micrófono", WAV_DICTADO)
    wav16 = a_16k_mono(origen, WAV_DICTADO_16K)
    texto = transcribir(modelo, wav16)
    log(f"transcripcion Vosk: {texto!r}")
    assert texto.strip(), "Vosk no devolvio ninguna coincidencia"
    esperadas = ("probado", "micrófono", "microfono", "hola", "tars")
    coincidencias = [p for p in esperadas if p in texto]
    log(f"coincidencias con la frase original: {coincidencias}")
    assert coincidencias, f"ninguna coincidencia con la frase original: {texto!r}"


# ---------------------------------------------------------------------------
# Seccion 3: dictado -> puente -> TTS
# ---------------------------------------------------------------------------

class SubprocessFalso:
    """Captura los comandos de reproduccion sin lanzar nada de audio."""

    DEVNULL = subprocess.DEVNULL

    def __init__(self):
        self.comandos = []

    def run(self, comando, **kwargs):
        self.comandos.append(("run", list(comando)))
        return type("Resultado", (), {"returncode": 0})()

    def Popen(self, comando, **kwargs):
        self.comandos.append(("popen", list(comando)))
        return None


def _modelos_locales(puente):
    """Ids de modelos que corren en la maquina (ollama), sin depender de cuota."""
    try:
        modelos = puente.listar_modelos()
    except Exception:
        return []
    locales = []
    for modelo in modelos:
        ref = modelo.get("modelo_ref") or {}
        if ref.get("providerID") == "ollama":
            locales.append(modelo.get("id"))
    return locales


def _aplicar_modelo_local(puente, session_id):
    """
    Cambia la sesion a un modelo local si hay. Sirve para que estos tests no
    dependan de la cuota gratuita de OpenCode; en produccion no se cambia
    nada: el modelo lo elige el usuario.
    """
    locales = _modelos_locales(puente)
    if not locales:
        return None
    preferidos = [m for m in ("qwen3:1.7b", "gemma3:12b", "gemma3:4b") if m in locales]
    preferidos += [m for m in locales if m not in preferidos]
    for modelo_id in preferidos[:3]:
        try:
            r = puente.aplicar_modelo(session_id, modelo_id, proveedor="ollama")
        except Exception as exc:
            log(f"no pude aplicar {modelo_id}: {exc}")
            continue
        if r.get("ok"):
            log(f"modelo local aplicado a la sesion: {modelo_id}")
            return modelo_id
    return None


def seccion_dictado():
    import vosk
    import tars_wake_word as ww

    modelo = cargar_modelo()
    origen = generar_wav("Hola TARS, probando el micrófono", WAV_DICTADO)
    wav16 = a_16k_mono(origen, WAV_DICTADO_16K)

    # Dictado con el micro simulado por el wav
    reconocedor = vosk.KaldiRecognizer(modelo, 16000)
    stream = StreamDeArchivo(wav16)
    modo_original = ww.get_mode
    ww.get_mode = lambda: "auto"
    try:
        inicio = time.time()
        accion, texto = ww.correr_dictado(
            stream, reconocedor, lim_silencio=1.0, lim_inicio=6.0, lim_total=25.0
        )
        duracion = time.time() - inicio
    finally:
        ww.get_mode = modo_original

    log(f"dictado accion={accion} texto={texto!r} en {duracion:.1f}s")
    assert accion == "send", f"el dictado debia terminar en send y salio {accion}"
    assert texto.strip(), "el dictado quedo vacio"

    # Con modo off el dictado se corta sin tocar tars_state.json
    reconocedor_off = vosk.KaldiRecognizer(modelo, 16000)
    stream_off = StreamDeArchivo(wav16)
    ww.get_mode = lambda: "off"
    try:
        accion_off, _ = ww.correr_dictado(
            stream_off, reconocedor_off, lim_silencio=1.0, lim_inicio=6.0, lim_total=25.0
        )
    finally:
        ww.get_mode = modo_original
    log(f"dictado con modo off: accion={accion_off}")
    assert accion_off == "cancel", "con modo off el dictado tenia que cancelarse"

    prompt = ww.construir_prompt(texto)
    log(f"prompt armado para el puente: {prompt!r}")
    assert prompt, "el prompt quedo vacio despues de limpiar la wake word"
    # Los tests no quieren que el modelo salga a correr herramientas: eso
    # dejaria el turno esperando permiso. En produccion el pedido va tal cual.
    prompt_prueba = prompt + " No uses herramientas de ninguna clase: contesta en una sola frase y nada mas."

    puente = ww.obtener_puente()
    if puente is None:
        log("servicio OpenCode caido: salto la parte de red, el dictado quedo validado igual")
        return
    try:
        sid = puente.crear_sesion_para_chat(
            ww.CHAT_VOZ, titulo=ww.TITULO_CHAT, agente=ww.AGENTE_VOZ
        )
        previo = puente.estado_chat(ww.CHAT_VOZ) or {}
        log(
            "estado previo: is_processing={} outcome={} tool_action={!r}".format(
                previo.get("is_processing"), previo.get("outcome"), previo.get("tool_action")
            )
        )
        if previo.get("is_processing"):
            # Un turno colgado de una corrida anterior bloquea el chat entero
            log("habia un turno sin cerrar, lo interrumpo antes de seguir")
            puente.cancelar_chat(ww.CHAT_VOZ)
            time.sleep(1.0)
            log(f"tras el interrupt: is_processing={(puente.estado_chat(ww.CHAT_VOZ) or {}).get('is_processing')}")

        modelo_local = _aplicar_modelo_local(puente, sid)
        if modelo_local is None:
            log("sin modelo local: el turno depende de la cuota gratuita de OpenCode")

        enviado = ww._enviar_prompt(puente, prompt_prueba)
        log(f"prompt enviado: ok={enviado.get('ok')} session={enviado.get('session_id')}")

        esperado = puente.esperar_respuesta(sid, timeout=150.0)
        log(
            "respuesta: outcome={} texto={!r}".format(
                esperado.get("outcome"), str(esperado.get("texto"))[:160]
            )
        )
        if not esperado.get("ok"):
            detalle = ((esperado.get("estado") or {}).get("error") or "")[:200]
            log(f"turno fallido: {detalle}")
            if modelo_local or _aplicar_modelo_local(puente, sid):
                puente.cancelar_chat(ww.CHAT_VOZ)
                time.sleep(1.0)
                ww._enviar_prompt(puente, prompt_prueba)
                esperado = puente.esperar_respuesta(sid, timeout=150.0)
                log(
                    "respuesta reintento: outcome={} texto={!r}".format(
                        esperado.get("outcome"), str(esperado.get("texto"))[:160]
                    )
                )
        assert esperado.get("ok"), f"el turno no termino bien: {esperado.get('outcome')}"
        respuesta_texto = ww.respuesta_final(puente, esperado)
        log(f"texto final para el TTS: {respuesta_texto[:160]!r}")
        assert respuesta_texto, "el cerebro no devolvio texto"

        # El mismo TTS que usa speak_response.py, dejando artefactos en /tmp
        info = ww.preparar_audio(respuesta_texto)
        assert info, "no pude sintetizar la respuesta"
        assert os.path.getsize(info["wav"]) > 1000, "el wav del TTS quedo vacio"
        log(f"TTS wav={info['wav']} ({os.path.getsize(info['wav'])} bytes)")
        assert info["mp3"] and os.path.getsize(info["mp3"]) > 500, "falta el mp3 en /tmp"
        log(f"TTS mp3={info['mp3']} ({os.path.getsize(info['mp3'])} bytes)")

        # Reproduccion capturada: se valida el comando y no suena nada
        stub = SubprocessFalso()
        original = ww.subprocess
        ww.subprocess = stub
        try:
            lanzado = ww.reproducir_audio(info)
        finally:
            ww.subprocess = original
        assert lanzado, "reproducir_audio devolvio False"
        players = [
            c for modo, c in stub.comandos
            if modo == "popen" and any("tars_player.py" in arg for arg in c)
        ]
        assert players, f"no se lanzo tars_player.py: {stub.comandos}"
        assert players[0][-1] == info["wav"], f"el player se lanzo con {players[0]}"
        log(f"reproduccion capturada sin sonido: {players[0]}")
    finally:
        ww.cerrar_puente()


# ---------------------------------------------------------------------------
# Seccion 4: cancelar por voz con is_processing true
# ---------------------------------------------------------------------------

class PuenteDoble:
    """Doble del puente: queda procesando hasta que lo cancelan."""

    def __init__(self):
        self.procesando = True
        self.cancelado = False

    def esperar_respuesta(self, session_id, timeout=120.0, **kwargs):
        limite = time.time() + timeout
        while time.time() < limite and not self.cancelado:
            time.sleep(0.1)
        return {
            "ok": False,
            "outcome": "interrupted" if self.cancelado else "timeout",
            "texto": "",
        }

    def estado_chat(self, chat_id):
        return {"is_processing": self.procesando}

    def cancelar_chat(self, chat_id, resume=False):
        self.cancelado = True
        self.procesando = False
        return {"ok": True, "interrupted": True, "mensaje": "Ejecucion interrumpida."}


def seccion_cancel():
    import vosk
    import tars_wake_word as ww

    modelo = cargar_modelo()
    origen = generar_wav("cancelar cancelar", WAV_CANCEL)
    wav16 = a_16k_mono(origen, WAV_CANCEL_16K)

    reconocedor = vosk.KaldiRecognizer(modelo, 16000)
    stream = StreamDeArchivo(wav16, bucle=True)

    eventos = []
    modo_original = ww.get_mode
    stop_original = ww.stop_all_speech
    tocar_original = ww.tocar
    ww.get_mode = lambda: "auto"
    ww.stop_all_speech = lambda: eventos.append("stop_speech")
    ww.tocar = lambda ruta: eventos.append("tono:" + os.path.basename(ruta or ""))
    doble = PuenteDoble()
    try:
        inicio = time.time()
        resultado = ww._esperar_con_cancelacion(doble, "sid-test", stream, reconocedor, timeout=25.0)
        duracion = time.time() - inicio
    finally:
        ww.get_mode = modo_original
        ww.stop_all_speech = stop_original
        ww.tocar = tocar_original

    log(f"cancel por voz: outcome={resultado.get('outcome')} eventos={eventos} en {duracion:.1f}s")
    assert resultado.get("outcome") == "interrupted", "la cancelacion no corto el turno"
    assert doble.cancelado, "no se llamo a cancelar_chat"
    assert doble.procesando is False, "el estado no se reseteo al toque"
    assert any(e.startswith("tono:tars_cancel_tone") for e in eventos), f"falta el tono: {eventos}"
    assert "stop_speech" in eventos, "no se corto el audio previo"
    log("reset inmediato de is_processing y tono de cancel verificados")

    # Contra el servicio real: mando una respuesta larga y la interrumpo
    puente = ww.obtener_puente()
    if puente is None:
        log("servicio OpenCode caido: salto el interrupt real")
        return
    try:
        sid = puente.crear_sesion_para_chat(
            ww.CHAT_VOZ, titulo=ww.TITULO_CHAT, agente=ww.AGENTE_VOZ
        )
        previo = puente.estado_chat(ww.CHAT_VOZ) or {}
        if previo.get("is_processing"):
            log("habia un turno sin cerrar, lo interrumpo antes de mandar la tarea larga")
            puente.cancelar_chat(ww.CHAT_VOZ)
            time.sleep(1.0)
        if _aplicar_modelo_local(puente, sid) is None:
            log("sin modelo local: el interrupt real depende de la cuota de OpenCode")
        try:
            puente.enviar_prompt_chat(
                ww.CHAT_VOZ,
                "Escribi cuatro parrafos largos sobre la historia de los trenes en "
                "Argentina. No uses herramientas.",
                titulo=ww.TITULO_CHAT,
                agente=ww.AGENTE_VOZ,
            )
        except Exception as exc:
            log(f"no pude mandar la tarea larga: {exc}")
            return

        visto = False
        limite = time.time() + 25.0
        while time.time() < limite:
            estado = puente.estado_chat(ww.CHAT_VOZ) or {}
            if estado.get("is_processing"):
                visto = True
                break
            time.sleep(0.2)

        if not visto:
            log("no observe is_processing=true en 25s: el modelo contesto muy rapido")
            return

        # Dejo que el modelo arranpe de verdad antes de cortar
        time.sleep(1.5)
        log("is_processing=true observado, lanzo el interrupt")
        cancelado = puente.cancelar_chat(ww.CHAT_VOZ)
        log(f"cancelar_chat: {cancelado.get('mensaje')}")

        limite = time.time() + 8.0
        estado = {}
        while time.time() < limite:
            estado = puente.estado_chat(ww.CHAT_VOZ) or {}
            if not estado.get("is_processing"):
                break
            time.sleep(0.2)
        log(f"estado post interrupt: is_processing={estado.get('is_processing')} outcome={estado.get('outcome')!r}")
        assert estado.get("is_processing") is False, "el interrupt no reseteo is_processing"
        if estado.get("outcome") != "interrupted":
            log(f"AVISO: outcome {estado.get('outcome')!r} en vez de interrupted")
    finally:
        ww.cerrar_puente()


def correr_nucleo():
    seccion_rutas()
    seccion_vosk()
    seccion_dictado()
    seccion_cancel()
    return 0


# ---------------------------------------------------------------------------
# Seccion 5: tray offscreen
# ---------------------------------------------------------------------------

def _textos_menu(menu):
    lineas = []
    for accion in menu.actions():
        if accion.isSeparator():
            lineas.append("  ---")
            continue
        sub = accion.menu()
        if sub is not None:
            lineas.append(f"  {accion.text()}:")
            for subaccion in sub.actions():
                marca = ""
                if subaccion.isCheckable():
                    marca = "[x] " if subaccion.isChecked() else "[ ] "
                lineas.append(f"    {marca}{subaccion.text()}")
        else:
            marca = ""
            if accion.isCheckable():
                marca = "[x] " if accion.isChecked() else "[ ] "
            lineas.append(f"  {marca}{accion.text()}")
    return lineas


def seccion_tray():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from tars_rutas import ruta_estado
    ruta_estado_tray = ruta_estado()
    with open(ruta_estado_tray, "rb") as archivo:
        previo = archivo.read()
    log(f"tars_state.json antes: {previo.decode('utf-8', 'replace')}")

    avisos = []
    import tars_tray
    tars_tray.os.system = lambda comando: avisos.append(comando) or 0

    app = None
    try:
        app = tars_tray.TarsTrayApp()
        lineas = _textos_menu(app.menu)
        log("menu del tray:\n" + "\n".join(lineas))
        texto_menu = "\n".join(lineas)

        assert "Cerebro de TARS" in texto_menu, "falta el submenu de cerebro"
        sub_cerebro = app.brain_menu.actions()
        etiquetas = [a.text() for a in sub_cerebro]
        assert etiquetas == ["OpenCode", "Antigravity"], f"opciones raras: {etiquetas}"
        marcados = [a for a in sub_cerebro if a.isCheckable() and a.isChecked()]
        assert len(marcados) == 1, "el selector de cerebro tiene que ser radio de a uno"
        assert app.current_brain == marcados[0].text().lower(), (
            f"el marcado ({marcados[0].text()}) no coincide con el estado ({app.current_brain})"
        )
        log(f"submenu de cerebro ok, marcado={marcados[0].text()}")

        texto_estado = app.service_action.text()
        assert texto_estado.startswith("OpenCode"), texto_estado
        assert "password" not in texto_estado.lower()
        assert "corriendo en puerto" in texto_estado or texto_estado.endswith("apagado"), texto_estado
        log(f"estado del servicio en el tray: {texto_estado}")

        # Escritura del cerebro: cambia la llave y preserva el resto
        assert app.current_brain == "opencode", "por defecto tenia que venir OpenCode"
        app.switch_brain("antigravity")
        with open(ruta_estado_tray, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        log(f"estado al elegir Antigravity: {datos}")
        assert datos.get("cerebro") == "antigravity", "no se escribio la llave cerebro"
        assert datos.get("mode") == "off", "se perdio la llave mode"
        assert any("Cerebro seleccionado" in comando for comando in avisos), avisos

        app.switch_brain("opencode")
        with open(ruta_estado_tray, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        assert datos.get("cerebro") == "opencode"
        assert datos.get("mode") == "off"
        log("vuelta a OpenCode ok, mode intacto")

        # Ningun comando del tray puede frenar servicios en este test
        assert not any("systemctl" in comando for comando in avisos), avisos
        log("el tray no intento reiniciar ni detener nada")
    finally:
        with open(ruta_estado_tray, "wb") as archivo:
            archivo.write(previo)
        with open(ruta_estado_tray, "rb") as archivo:
            final = archivo.read()
        log(f"tars_state.json despues: {final.decode('utf-8', 'replace')}")
        assert final == previo, "tars_state.json no quedo igual que al arrancar"
        if app is not None:
            try:
                app.timer.stop()
                app.tray.hide()
            except Exception:
                pass
    log("tray offscreen sin segmentacion, estado restaurado")
    return 0


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def _tiene_pyqt(interprete):
    try:
        proceso = subprocess.run(
            [interprete, "-c", "import PyQt5"], capture_output=True, timeout=30
        )
        return proceso.returncode == 0
    except Exception:
        return False


def correr_bloque(comandos, timeout, titulo):
    log(f"arranco {titulo} (timeout {timeout}s)")
    entorno = dict(os.environ)
    entorno.setdefault("TARS_OPENCODE_SESSIONS_FILE", MAPA_TEST)
    inicio = time.time()
    try:
        proceso = subprocess.run(comandos, env=entorno, timeout=timeout)
        codigo = 0 if proceso.returncode == 0 else 1
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT en {titulo} despues de {timeout}s")
        codigo = 1
    log(f"{titulo}: rc={codigo} en {time.time() - inicio:.1f}s")
    return codigo


def orquestar():
    archivo = os.path.abspath(__file__)

    ruta_fija = "/home" + "/santiago"
    with open(os.path.join(BASE_DIR, "tars_rutas.py"), "r", encoding="utf-8") as f:
        assert ruta_fija not in f.read()
    from tars_rutas import ruta_estado
    ruta_estado_orquesta = ruta_estado()
    with open(ruta_estado_orquesta, "rb") as archivo_estado:
        estado_inicial = archivo_estado.read()
    log(f"estado inicial de tars_state.json: {estado_inicial.decode('utf-8', 'replace')}")

    codigo = 0

    py_nucleo = sys.executable
    try:
        import vosk  # noqa: F401
    except Exception:
        if os.path.isfile(PY_VENV):
            py_nucleo = PY_VENV
    if not os.path.exists(py_nucleo):
        log(f"no encuentro el interprete {py_nucleo}")
        return 1
    codigo |= correr_bloque([py_nucleo, archivo, "--nucleo"], TIMEOUT_NUCLEO, "nucleo")

    py_tray = sys.executable if _tiene_pyqt(sys.executable) else PY_SISTEMA
    if not _tiene_pyqt(py_tray):
        log("no hay PyQt5 disponible para el test del tray")
        codigo |= 1
    else:
        entorno_tray = dict(os.environ)
        entorno_tray["QT_QPA_PLATFORM"] = "offscreen"
        log(f"arranco tray offscreen con {py_tray} (timeout {TIMEOUT_TRAY}s)")
        try:
            proceso = subprocess.run(
                [py_tray, archivo, "--solo-tray"], env=entorno_tray, timeout=TIMEOUT_TRAY
            )
            codigo |= 0 if proceso.returncode == 0 else 1
        except subprocess.TimeoutExpired:
            log(f"TIMEOUT en tray despues de {TIMEOUT_TRAY}s")
            codigo |= 1

    with open(ruta_estado_orquesta, "rb") as archivo_estado:
        estado_final = archivo_estado.read()
    if estado_final != estado_inicial:
        log("FALLO tars_state.json quedo distinto al estado inicial")
        codigo |= 1
    else:
        log("tars_state.json intacto al final de todos los tests")

    if os.path.exists(MAPA_TEST):
        log(f"mapa de sesiones del test: {MAPA_TEST}")
    if os.path.exists("/tmp/tars_speaking.lock"):
        log("aviso: quedo /tmp/tars_speaking.lock de otro proceso, no lo toco")

    log("RESULTADO " + ("OK" if codigo == 0 else "CON FALLOS"))
    return codigo


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--nucleo" in argv:
        return correr_nucleo()
    if "--solo-tray" in argv:
        return seccion_tray()
    return orquestar()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        log(f"FALLO {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        log("interrumpido")
        sys.exit(130)
