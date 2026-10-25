#!/usr/bin/env python3
"""
Rutas, estado compartido y descubrimiento liviano de TARS.

Un solo lugar para resolver la carpeta de configuracion, el estado compartido
de tars_state.json, los recursos (chimes, iconos, scripts) y el estado del
servicio local de OpenCode.

Reglas del proyecto:
- Sin rutas fijas de usuario: TARS_CONFIG_DIR primero y despues expanduser.
- El service.json de OpenCode se lee solo para url, puerto y pid; el password
  nunca se carga ni se imprime.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CEREBROS = ("opencode", "antigravity")


def directorio_config_tars() -> str:
    """
    Carpeta de configuracion de TARS.

    Orden: TARS_CONFIG_DIR, despues ~/.gemini/config si ahi esta el
    tars_state.json, despues ~/.config/tars, y si no existe nada se cae en
    ~/.gemini/config como hace tars_web_server.py.
    """
    env = os.environ.get("TARS_CONFIG_DIR")
    if env:
        return os.path.expanduser(env)
    legacy = os.path.expanduser("~/.gemini/config")
    if os.path.exists(os.path.join(legacy, "tars_state.json")):
        return legacy
    nuevo = os.path.expanduser("~/.config/tars")
    if os.path.exists(os.path.join(nuevo, "tars_state.json")):
        return nuevo
    if os.path.isdir(legacy):
        return legacy
    return nuevo


def ruta_estado() -> str:
    """tars_state.json compartido entre server, tray y voz."""
    return os.path.join(directorio_config_tars(), "tars_state.json")


def cargar_estado() -> dict:
    """Lee el estado compartido sin tirar excepciones."""
    try:
        with open(ruta_estado(), "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        return datos if isinstance(datos, dict) else {}
    except Exception:
        return {}


def guardar_llave_estado(clave: str, valor) -> bool:
    """
    Escribe una llave del estado compartido preservando el resto, igual que
    save_voice y save_mode del tray.
    """
    try:
        datos = cargar_estado()
        datos[clave] = valor
        ruta = ruta_estado()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo)
        return True
    except Exception:
        return False


def cerebro_activo() -> str:
    """Cerebro vigente. Por defecto OpenCode, como quedo cerrado con el usuario."""
    valor = cargar_estado().get("cerebro", "opencode")
    return valor if valor in CEREBROS else "opencode"


def recurso_tars(nombre: str, extra: tuple = ()) -> str:
    """
    Resuelve un recurso del repo: primero junto al modulo que lo pide,
    despues en la carpeta de configuracion y despues en los extras.
    """
    candidatos = [
        os.path.join(BASE_DIR, nombre),
        os.path.join(directorio_config_tars(), nombre),
    ]
    candidatos.extend(os.path.join(os.path.expanduser(base), nombre) for base in extra)
    for ruta in candidatos:
        if os.path.exists(ruta):
            return ruta
    return candidatos[0]


def python_tts() -> str:
    """Interprete que corre tars_player.py: el venv de TTS si existe."""
    venv = os.path.expanduser("~/.gemini/tts_venv/bin/python")
    if os.path.isfile(venv):
        return venv
    return sys.executable or "python3"


def ruta_modelo_vosk() -> str:
    """Modelo de Vosk, con los mismos candidatos que usa tars_web_server.py."""
    env = os.environ.get("VOSK_MODEL_PATH")
    if env:
        return os.path.expanduser(env)
    candidatos = [
        os.path.expanduser("~/.gemini/models/vosk-model-small-es-0.42"),
        os.path.expanduser("~/.config/tars/models/vosk-model-small-es-0.42"),
        os.path.join(BASE_DIR, "models", "vosk-model-small-es-0.42"),
    ]
    for ruta in candidatos:
        if os.path.isdir(ruta):
            return ruta
    return candidatos[0]


def ruta_service_opencode() -> str:
    """service.json del servicio local de OpenCode, sin tocar el password."""
    bases = []
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        bases.append(os.path.expanduser(xdg_state))
    bases.append(os.path.expanduser("~/.local/state"))
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        bases.append(os.path.expanduser(xdg_config))
    bases.append(os.path.expanduser("~/.config"))
    for base in bases:
        ruta = os.path.join(base, "opencode", "service.json")
        if os.path.isfile(ruta):
            return ruta
    return os.path.join(bases[0], "opencode", "service.json")


def _pid_vivo(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _puerto_escucha(host: str, puerto: int) -> bool:
    try:
        with socket.create_connection((host, puerto), timeout=0.3):
            return True
    except Exception:
        return False


def servicio_opencode() -> dict:
    """
    Estado del servicio local de OpenCode para mostrar en el tray.

    Solo url, puerto y pid del service.json: ni el password se lee ni se
    guarda en el dict. "corriendo" es puerto escuchando y proceso vivo.
    """
    info = {
        "disponible": False,
        "corriendo": False,
        "url": "",
        "puerto": None,
        "pid": None,
    }
    try:
        with open(ruta_service_opencode(), "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except Exception:
        return info

    url = str(datos.get("url") or "").rstrip("/")
    info["url"] = url
    info["disponible"] = bool(url)
    pid = datos.get("pid")
    info["pid"] = pid if isinstance(pid, int) else None

    coincidencia = re.search(r":(\d+)$", url)
    if not coincidencia:
        return info
    puerto = int(coincidencia.group(1))
    info["puerto"] = puerto
    info["corriendo"] = _puerto_escucha("127.0.0.1", puerto) and (
        info["pid"] is None or _pid_vivo(info["pid"])
    )
    return info


def etiqueta_servicio_opencode(info: dict) -> str:
    """Texto del menu del tray, sin password ni nada sensible."""
    if info.get("corriendo") and info.get("puerto"):
        return f"OpenCode: corriendo en puerto {info['puerto']}"
    return "OpenCode apagado"
