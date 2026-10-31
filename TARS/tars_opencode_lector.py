#!/usr/bin/env python3
"""
Lector de voz para los turnos de la interface de OpenCode.

Cuando un turno de OpenCode termina (session.execution.succeeded), este
demonio lee la respuesta final en voz alta con el mismo motor que TARS usa
en el resto del sistema, igual que el camino de Antigravity pero para sesiones
que no pasan por TARS (terminal, interface web u otros clientes).

Reglas:
- No se pelea con TARS: los chats que ya usan el estado del puente (los del
  mapa opencode_sessions.json, por ejemplo voz_pc y el celular) ya tienen su
  propio lector, asi que aca se saltean.
- Respeta el muteo de audio de PC del tray y la app (pc_audio_muted).
- Respeta el lock /tmp/tars_speaking.lock: si TARS esta hablando, espera.
- Corta mensajes largos a 1000 caracteres con aviso, como el wake word.
- Si el servicio se reinicia y cambia el puerto, el puente lo redescubre.
"""

from __future__ import annotations

import os
import json
import queue
import subprocess
import sys
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from integraciones.opencode_bridge import (
    PuenteOpenCode,
    ErrorPuenteOpenCode,
    ruta_mapa_sesiones,
)
from tars_rutas import cargar_estado, recurso_tars

try:
    from speak_response import clean_text_for_speech
except Exception:
    def clean_text_for_speech(texto):
        return str(texto or "")

LOCK_FILE = "/tmp/tars_speaking.lock"
WAV_RESPUESTA = "/tmp/opencode_response.wav"
MP3_RESPUESTA = "/tmp/opencode_response.mp3"
PLAYER_PY = recurso_tars("tars_player.py")
MAX_LARGO_VOZ = 1000


def log(mensaje):
    print(f"[Lector OpenCode] {mensaje}", flush=True)


def audio_suprimido():
    """True si TARS no debe hablar ahora: modo rojo o audio muteado.

    Semantica del README: verde escucha a mano alzada y habla; amarillo deja
    de escuchar salvo F12 pero SIEMPRE habla; rojo es silencio total. Este
    lector es voz de salida, asi que solo respeta rojo y el mute de audio.
    """
    try:
        datos = cargar_estado()
        modo = str(datos.get("mode") or "auto").strip().lower()
        if modo == "off":
            return True
        return bool(datos.get("pc_audio_muted"))
    except Exception:
        return False


def sesiones_de_tars():
    """Sesiones de OpenCode que ya tienen lector propio en TARS (el mapa)."""
    try:
        with open(ruta_mapa_sesiones(), "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        chats = datos.get("chats") or {}
    except Exception:
        return set()
    return {
        str(entrada.get("session_id") or "")
        for entrada in chats.values()
        if isinstance(entrada, dict)
    }


class LectorPuente(PuenteOpenCode):
    """Puente que ademas encola los turnos cuyo fin detecta via SSE."""

    def __init__(self):
        super().__init__(iniciar_hilo=False, verbose=False)
        self.iniciar(esperar=5.0)
        self._cola_fines: "queue.Queue[str]" = queue.Queue()
        self._hablado: set = set()  # (session_id, assistant_message_id)
        self._candado_hablado = threading.Lock()

    def _procesar_evento(self, evento: dict) -> None:
        sid = None
        super()._procesar_evento(evento)

        tipo = str(evento.get("type") or "")
        if tipo != "session.execution.succeeded":
            return
        datos = evento.get("data") or {}
        if not isinstance(datos, dict):
            return
        sid = datos.get("sessionID") or evento.get("sessionID")
        if sid:
            self._cola_fines.put(str(sid))
            log(f"Turno exitoso en {str(sid)[-8:]}, lo encolo para hablar.")

    # -- voz --------------------------------------------------------------

    def _esperar_vez(self, tope: float = 120.0) -> bool:
        """Espera a que el lock de voz de TARS quede libre.

        Si el lock queda huerfano, por ejemplo si alguien mato a tars_player
        con kill -9 sin dejar que limpie su archivo, no bloqueamos para
        siempre: un lock de mas de 90 segundos es basura y se saca.
        """
        inicio = time.time()
        while time.time() - inicio < tope:
            if not os.path.exists(LOCK_FILE):
                return True
            try:
                edad = time.time() - os.path.getmtime(LOCK_FILE)
                if edad > 90:
                    log(f"Lock de voz huerfano ({int(edad)}s): lo considero basura y sigo.")
                    os.remove(LOCK_FILE)
                    return True
            except OSError:
                return True
            time.sleep(0.5)
        return False

    def _es_subagente(self, session_id: str) -> bool:
        try:
            info = self.obtener_sesion(session_id)
        except ErrorPuenteOpenCode:
            # Si no devolvi sesion, no la hablo: mejor mudo que inventado.
            return True
        return bool(info.get("parent_id"))

    def leer_turno(self, session_id: str) -> bool:
        """Sintetiza y reproduce la respuesta final de un turno."""
        estado = self.estado_sesion(session_id)
        if estado.get("is_processing"):
            log(f"Sesion {str(session_id)[-8:]} volvio a trabajar: no la hablo.")
            return False

        texto = str(estado.get("last_message") or estado.get("streaming_text") or "").strip()
        if not texto:
            texto = self._texto_ultimo_asistente(session_id)
        if not texto:
            log(f"Sesion {str(session_id)[-8:]} sin texto para hablar.")
            return False
        if estado.get("outcome") == "failed" or estado.get("error"):
            log(f"Sesion {str(session_id)[-8:]} fallo, no hablo el texto.")
            return False

        mensaje_id = str(estado.get("assistant_message_id") or texto[:80])
        llave = (session_id, mensaje_id)
        with self._candado_hablado:
            if llave in self._hablado:
                return False
            self._hablado.add(llave)
            if len(self._hablado) > 200:
                self._hablado.clear()

        if audio_suprimido():
            log("TARS en rojo/amarillo o audio muteado: respuesta quedo en silencio.")
            return False
        if not self._esperar_vez():
            log("TARS llevaba dos minutos hablando: no pise su respuesta.")
            return False

        limpio = clean_text_for_speech(texto)
        if len(limpio) > MAX_LARGO_VOZ:
            corte = limpio[:MAX_LARGO_VOZ]
            ultimo_punto = corte.rfind(".")
            if ultimo_punto != -1:
                limpio = corte[: ultimo_punto + 1] + " ... El resto de la respuesta esta en pantalla."
            else:
                limpio = corte + " ... El resto de la respuesta esta en pantalla."
        if not limpio:
            return False

        try:
            from tars_voice_engine import synthesize_speech
            exito = bool(synthesize_speech(limpio, WAV_RESPUESTA))
        except Exception as error:
            log(f"Error de sintesis: {error}")
            exito = False
        if not exito or not os.path.exists(WAV_RESPUESTA):
            log("No pude sintetizar el audio.")
            return False

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", WAV_RESPUESTA, MP3_RESPUESTA],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
            )
        except Exception:
            pass

        subprocess.Popen(
            [sys.executable, PLAYER_PY, WAV_RESPUESTA],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        log(f"Hablando respuesta de {str(session_id)[-8:]} ({len(limpio)} chars)")
        return True

    # -- bucle ------------------------------------------------------------

    def bucle_lectura(self):
        while True:
            sid = self._cola_fines.get()
            try:
                if sid in sesiones_de_tars():
                    log(f"Sesion {str(sid)[-8:]} es un chat de TARS: la lee su propio flujo.")
                    continue
                if self._es_subagente(sid):
                    log(f"Sesion {str(sid)[-8:]} es un subagente: mudo.")
                    continue
                self.leer_turno(sid)
            except Exception as error:
                log(f"Error leyendo turno {str(sid)[-8:]}: {error}")
            finally:
                self._cola_fines.task_done()


def main():
    log("Arranco: escucho los turnos de OpenCode que quedan fuera de TARS.")
    lector = LectorPuente()
    hilo = threading.Thread(target=lector.bucle_lectura, name="tars-opencode-voz", daemon=True)
    hilo.start()
    log(f"Puente en {lector.url} ({lector.origen_descubrimiento}); listo.")
    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        log("Cierro.")
    finally:
        lector.cerrar()


if __name__ == "__main__":
    main()
