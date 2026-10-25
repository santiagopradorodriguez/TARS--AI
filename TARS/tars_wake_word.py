#!/usr/bin/env python3
"""
Wake word de TARS en la PC.

Flujo con OpenCode (cerebro por defecto):

    "Hola TARS" -> dictado con Vosk -> prompt al puente (chat voz_pc)
    -> esperar_respuesta -> TTS del repo (tars_voice_engine + tars_player)
    -> "cancelar" o "detener" por voz -> cancelar_chat (interrupt)

Si el cerebro activo es antigravity se mantiene el flujo de siempre: Ctrl+M
sobre la ventana enfocada, dictado y Enter.

Los modos de tars_state.json siguen aplicando igual que antes:
- auto: escucha continua con wake word
- button: la voz la despierta solo la tecla F12, aca no se escucha
- off: nada de nada
"""

import sys
import os
import json
import time
import threading
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from tars_rutas import (
        cargar_estado,
        cerebro_activo,
        python_tts,
        recurso_tars,
        ruta_estado,
        ruta_modelo_vosk,
    )
except ImportError as exc:
    # Respaldo minimo si el instalador no llevo tars_rutas.py
    print(f"[TARS] No pude importar tars_rutas ({exc}); uso rutas basicas.", file=sys.stderr)

    def directorio_config_tars():
        return os.environ.get("TARS_CONFIG_DIR") or os.path.expanduser("~/.gemini/config")

    def ruta_estado():
        return os.path.join(directorio_config_tars(), "tars_state.json")

    def cargar_estado():
        try:
            with open(ruta_estado(), "r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
            return datos if isinstance(datos, dict) else {}
        except Exception:
            return {}

    def cerebro_activo():
        valor = cargar_estado().get("cerebro", "opencode")
        return valor if valor in ("opencode", "antigravity") else "opencode"

    def recurso_tars(nombre, extra=()):
        for ruta in (os.path.join(BASE_DIR, nombre), os.path.join(directorio_config_tars(), nombre)):
            if os.path.exists(ruta):
                return ruta
        return os.path.join(BASE_DIR, nombre)

    def python_tts():
        venv = os.path.expanduser("~/.gemini/tts_venv/bin/python")
        return venv if os.path.isfile(venv) else (sys.executable or "python3")

    def ruta_modelo_vosk():
        env = os.environ.get("VOSK_MODEL_PATH")
        if env:
            return os.path.expanduser(env)
        return os.path.expanduser("~/.gemini/models/vosk-model-small-es-0.42")

import sounddevice as sd
import vosk

try:
    from pynput import keyboard
except Exception:
    # Solo hace falta para el camino Antigravity (tipiar en la ventana).
    keyboard = None

STATE_FILE = ruta_estado()
MODEL_PATH = ruta_modelo_vosk()
START_CHIME = recurso_tars("tars_record_start.wav")
END_CHIME = recurso_tars("tars_record_end.wav")
CANCEL_TONE = recurso_tars("tars_cancel_tone.wav")
PLAYER_PY = recurso_tars("tars_player.py")
LOCK_FILE = "/tmp/tars_speaking.lock"

CHAT_VOZ = "voz_pc"
TITULO_CHAT = "TARS voz PC"
AGENTE_VOZ = "tars"
TIMEOUT_RESPUESTA = 120.0
WAV_RESPUESTA = "/tmp/antigravity_response.wav"
MP3_RESPUESTA = "/tmp/antigravity_response.mp3"

PALABRAS_ENVIAR = ("enviar", "envía", "envia", "cambio", "mandar", "listo")
PALABRAS_CANCELAR = ("cancelar", "detener")

_PUENTE = None


def log(mensaje):
    print(f"[TARS] {mensaje}", flush=True)


def get_mode():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if "mode" in data:
                    return data["mode"]
                return "auto" if data.get("enabled", True) else "off"
    except Exception:
        pass
    return "auto"


def set_mode(mode):
    try:
        data = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
        data["mode"] = mode
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

    msg = ""
    if mode == "auto":
        msg = "Modo: Verde - Escucha Automatica"
    elif mode == "button":
        msg = "Modo: Amarillo - Solo Boton F12"
    elif mode == "off":
        msg = "Modo: Rojo - Silencio Total"

    os.system(f'notify-send "TARS" "{msg}" -t 2000')


def send_ctrl_m():
    if keyboard is None:
        return
    controller = keyboard.Controller()
    controller.press(keyboard.Key.ctrl_l)
    time.sleep(0.04)
    controller.press('m')
    time.sleep(0.04)
    controller.release('m')
    time.sleep(0.04)
    controller.release(keyboard.Key.ctrl_l)


def send_enter():
    if keyboard is None:
        return
    controller = keyboard.Controller()
    time.sleep(0.05)
    controller.press(keyboard.Key.enter)
    time.sleep(0.05)
    controller.release(keyboard.Key.enter)


def stop_all_speech():
    subprocess.run(["pkill", "-9", "-f", "paplay.*antigravity_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "paplay.*wa_msg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "ffplay.*antigravity_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "tars_player.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass


def tocar(ruta):
    if ruta and os.path.exists(ruta):
        subprocess.Popen(["paplay", ruta], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def contiene_palabra(texto, palabras):
    return any(palabra in texto for palabra in palabras)


def construir_prompt(texto):
    """
    Arma el prompt final del chat de voz: el dictado limpio, sin la wake word
    que lo desperto ni sin las muletillas de envio.
    """
    limpio = " ".join((texto or "").split())
    bajada = limpio.lower()
    wake_words = ("hola tarso", "hola tarde", "hola tars", "hola tas", "oye tars", "ey tars", "tars")
    for wake in wake_words:
        if bajada.startswith(wake):
            limpio = limpio[len(wake):].lstrip(" ,.:-;¿?¡!")
            bajada = limpio.lower()
            break

    palabras = limpio.split()
    while palabras and palabras[-1].lower().strip(",.:-;") in PALABRAS_ENVIAR:
        palabras.pop()
    return " ".join(palabras)


# ---------------------------------------------------------------------------
# Dictado
# ---------------------------------------------------------------------------

def correr_dictado(stream, close_recognizer, lim_silencio=2.2, lim_inicio=6.0,
                   lim_total=60.0, callback=None):
    """
    Escucha hasta que el usuario termine de hablar, cancele o se le acabe el
    tiempo. Devuelve (accion, texto) con accion en {"send", "cancel"}.

    callback() se invoca en cada vuelta y corta el dictado con "cancel" si
    devuelve False: asi se respeta un cambio de modo en plena escucha.
    """
    start_time = time.time()
    last_speech_time = None
    spoken_any_word = False
    finales = []
    parcial_actual = ""
    action = None

    while True:
        # Si el usuario cambio de modo fuera de auto (ej. amarillo o rojo), cortar
        if get_mode() != "auto":
            action = "cancel"
            break

        if callback is not None and not callback():
            action = "cancel"
            break

        if os.path.exists(LOCK_FILE):
            time.sleep(0.15)
            close_recognizer.Reset()
            continue

        data, overflowed = stream.read(4000)
        now = time.time()

        palabras = []
        if close_recognizer.AcceptWaveform(bytes(data)):
            res = json.loads(close_recognizer.Result())
            raw_text = res.get("text", "").lower()
            palabras = raw_text.split()
            if palabras:
                finales.append(raw_text)
                parcial_actual = ""
        else:
            pres = json.loads(close_recognizer.PartialResult())
            raw_text = pres.get("partial", "").lower()
            palabras = raw_text.split()
            if palabras:
                parcial_actual = raw_text

        if palabras:
            if contiene_palabra(" ".join(palabras), PALABRAS_ENVIAR):
                action = "send"
                break
            elif contiene_palabra(" ".join(palabras), PALABRAS_CANCELAR):
                action = "cancel"
                break
            else:
                spoken_any_word = True
                last_speech_time = now

        # Silencio post-dictado: 2.2 segundos y se manda solo
        if spoken_any_word and last_speech_time and (now - last_speech_time > lim_silencio):
            action = "send"
            break

        # Sin ninguna palabra hablada a los lim_inicio segundos: cancelar
        if not spoken_any_word and (now - start_time > lim_inicio):
            action = "cancel"
            break

        # Limite maximo razonable para dictados continuos
        if now - start_time > lim_total:
            action = "send" if spoken_any_word else "cancel"
            break

    texto = " ".join(finales + ([parcial_actual] if parcial_actual else [])).strip()
    return action or "cancel", texto


def handle_wake_and_auto_close(stream, close_recognizer):
    """Camino Antigravity: dictado tipado en la ventana enfocada."""
    stop_all_speech()

    tocar(START_CHIME)
    time.sleep(0.15)
    send_ctrl_m()
    time.sleep(0.5)
    close_recognizer.Reset()

    action, texto = correr_dictado(stream, close_recognizer)

    time.sleep(0.15)
    send_ctrl_m()

    if action == "send":
        tocar(END_CHIME)
        time.sleep(0.15)
        send_enter()
    else:
        tocar(CANCEL_TONE)
        print("Dictado cerrado o cancelado.")

    return texto if action == "send" else ""


# ---------------------------------------------------------------------------
# Puente de OpenCode
# ---------------------------------------------------------------------------

def _importar_clase_puente():
    integraciones = os.path.join(BASE_DIR, "integraciones")
    if integraciones not in sys.path:
        sys.path.insert(0, integraciones)
    from opencode_bridge import PuenteOpenCode
    return PuenteOpenCode


def obtener_puente():
    """Puente vivo, redescubriendo el servicio si se reinicio."""
    global _PUENTE
    if _PUENTE is not None:
        try:
            if _PUENTE.esta_disponible():
                return _PUENTE
            _PUENTE.cerrar()
        except Exception:
            pass
        _PUENTE = None
    try:
        clase = _importar_clase_puente()
        _PUENTE = clase(verbose=False, espera_conexion=3.0)
        log(f"Puente de OpenCode conectado en {_PUENTE.url}")
        return _PUENTE
    except Exception as exc:
        log(f"No pude conectar con OpenCode: {exc}")
        _PUENTE = None
        return None


def cerrar_puente():
    global _PUENTE
    if _PUENTE is not None:
        try:
            _PUENTE.cerrar()
        except Exception:
            pass
        _PUENTE = None


def _enviar_prompt(puente, texto):
    """Manda el dictado al chat de voz del PC, con reintento sin agente."""
    try:
        return puente.enviar_prompt_chat(
            CHAT_VOZ, texto, titulo=TITULO_CHAT, agente=AGENTE_VOZ
        )
    except Exception as primera:
        log(f"Reintento sin agente tras: {primera}")
        return puente.enviar_prompt_chat(CHAT_VOZ, texto, titulo=TITULO_CHAT)


def _esperar_con_cancelacion(puente, session_id, stream, close_recognizer,
                             timeout=TIMEOUT_RESPUESTA):
    """
    Espera la respuesta del puente mientras sigue escuchando el microfono:
    "cancelar" o "detener" cortan el turno con interrupt.

    Devuelve el resultado de esperar_respuesta y un flag de si el usuario
    cancelo por voz o por modo. Todo con timeouts, nada de bucles abiertos.
    """
    caja = {}

    def _correr():
        try:
            caja.update(puente.esperar_respuesta(session_id, timeout=timeout))
        except Exception as exc:
            caja.update({"ok": False, "outcome": "error", "texto": "", "error": str(exc)})

    close_recognizer.Reset()
    hilo = threading.Thread(target=_correr, name="espera-voz", daemon=True)
    hilo.start()

    inicio = time.time()
    cancelado = False
    motivo = ""
    while hilo.is_alive() and (time.time() - inicio) < (timeout + 10.0):
        try:
            modo = get_mode()
        except Exception:
            modo = "auto"
        if modo != "auto":
            cancelado = True
            motivo = "off" if modo == "off" else "modo"
            break

        try:
            data, _ = stream.read(4000)
        except Exception as exc:
            # Si el micro flashea sigo esperando igual: no corto la tarea
            log(f"No pude leer el microfono durante la espera: {exc}")
            time.sleep(0.2)
            continue

        try:
            if close_recognizer.AcceptWaveform(bytes(data)):
                res = json.loads(close_recognizer.Result())
                texto = res.get("text", "").lower()
            else:
                pres = json.loads(close_recognizer.PartialResult())
                texto = pres.get("partial", "").lower()
        except Exception:
            texto = ""

        if texto and contiene_palabra(texto, PALABRAS_CANCELAR):
            cancelado = True
            motivo = "voz"
            break

    if cancelado:
        try:
            resultado = puente.cancelar_chat(CHAT_VOZ)
            log(f"Cancelacion por {motivo}: {resultado.get('mensaje', '')}")
        except Exception as exc:
            log(f"Fallo cancelar_chat: {exc}")
        stop_all_speech()
        if motivo != "off":
            tocar(CANCEL_TONE)

    hilo.join(timeout=5.0)
    if cancelado:
        return {"ok": False, "outcome": "interrupted", "texto": ""}
    return caja or {"ok": False, "outcome": "timeout", "texto": ""}


def preparar_audio(texto):
    """
    Sintetiza la respuesta con el TTS actual del repo y deja los archivos en
    /tmp. Devuelve {"ok", "texto", "wav", "mp3"} o None si no hay nada que
    decir.
    """
    from speak_response import clean_text_for_speech

    limpio = clean_text_for_speech(texto)
    if not limpio:
        return None

    if len(limpio) > 1000:
        corte = limpio[:1000]
        ultimo_punto = corte.rfind(".")
        if ultimo_punto != -1:
            limpio = corte[:ultimo_punto + 1] + " ... El resto de la respuesta está en pantalla."
        else:
            limpio = corte + " ... El resto de la respuesta está en pantalla."

    try:
        from tars_voice_engine import synthesize_speech
        ok = bool(synthesize_speech(limpio, WAV_RESPUESTA))
    except Exception as exc:
        log(f"Fallo la sintesis de voz: {exc}")
        ok = False
    if not ok or not os.path.exists(WAV_RESPUESTA):
        return None

    # Derivado mp3 para dejar la misma artefactacion que speak_response.py
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", WAV_RESPUESTA, MP3_RESPUESTA],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
    except Exception:
        pass

    return {
        "ok": True,
        "texto": limpio,
        "wav": WAV_RESPUESTA,
        "mp3": MP3_RESPUESTA if os.path.exists(MP3_RESPUESTA) else "",
    }


def reproducir_audio(info):
    """Lanza tars_player.py, que toma el lock /tmp/tars_speaking.lock."""
    if not info or not info.get("wav") or not os.path.exists(info["wav"]):
        return False
    subprocess.run(["pkill", "-9", "-f", "ffplay.*antigravity_response"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "tars_player.py"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(PLAYER_PY):
        log(f"No encuentro tars_player.py en {PLAYER_PY}")
        return False
    subprocess.Popen(
        [python_tts(), PLAYER_PY, info["wav"]],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    return True


def hablar(texto):
    """Sintetiza y reproduce de una. Devuelve la info del audio o None."""
    info = preparar_audio(texto)
    if info:
        reproducir_audio(info)
    return info


def respuesta_final(puente, resultado):
    """
    Texto hablable de un turno terminado.

    El SSE a veces marca el fin del turno antes de traer el texto: si viene
    vacio sincronizo contra la API y, en ultima instancia, leo el historial
    del chat. Nunca se queda mudo por un tema de orden de eventos.
    """
    texto = (resultado.get("texto") or "").strip()
    if texto:
        return texto
    try:
        estado = puente.sincronizar_chat(CHAT_VOZ) or {}
        texto = (estado.get("last_message") or "").strip()
    except Exception as exc:
        log(f"No pude sincronizar la sesion del chat de voz: {exc}")
    if texto:
        return texto
    try:
        for mensaje in puente.historial_chat(CHAT_VOZ, limite=8):
            candidato = (mensaje.get("texto") or "").strip()
            if mensaje.get("rol") == "tars" and candidato:
                return candidato
    except Exception as exc:
        log(f"No pude leer el historial del chat de voz: {exc}")
    return ""


def _tareas_pendientes(puente):
    """True si el chat de voz del PC tiene el cerebro trabajando ahora mismo."""
    try:
        estado = puente.estado_chat(CHAT_VOZ) or {}
    except Exception:
        return False
    return bool(estado.get("is_processing"))


def flujo_voz_opencode(stream, close_recognizer, texto_dictado=None):
    """
    Camino OpenCode: dictado -> puente -> respuesta hablada.

    Si texto_dictado ya viene armado (se uso en los tests o llego por otro
    disparador) se saltea la escucha.
    """
    if texto_dictado is None:
        stop_all_speech()
        tocar(START_CHIME)
        time.sleep(0.15)
        close_recognizer.Reset()
        action, texto_dictado = correr_dictado(stream, close_recognizer)
        if action != "send":
            tocar(CANCEL_TONE)
            if _PUENTE is not None and _tareas_pendientes(_PUENTE):
                try:
                    _PUENTE.cancelar_chat(CHAT_VOZ)
                    log("Cancelacion de la tarea que seguia corriendo.")
                except Exception as exc:
                    log(f"Fallo cancelar la tarea previa: {exc}")
            return None
        tocar(END_CHIME)
        time.sleep(0.15)

    texto_dictado = construir_prompt(texto_dictado)
    if not texto_dictado:
        log("Dictado vacio, no mando nada.")
        return None

    puente = obtener_puente()
    if puente is None:
        os.system('notify-send "TARS" "OpenCode apagado, no se mando el pedido" -t 3000')
        tocar(CANCEL_TONE)
        return None

    # Un turno anterior sin cerrar dejaria este pedido en cola: lo corto
    estado_previo = puente.estado_chat(CHAT_VOZ) or {}
    if estado_previo.get("is_processing"):
        log("Habia un turno de voz sin cerrar, lo interrumpo antes de mandar este.")
        try:
            puente.cancelar_chat(CHAT_VOZ)
        except Exception as exc:
            log(f"No pude interrumpir el turno previo: {exc}")
        time.sleep(0.5)

    try:
        enviado = _enviar_prompt(puente, texto_dictado)
    except Exception as exc:
        log(f"No pude enviar el prompt: {exc}")
        tocar(CANCEL_TONE)
        return None

    session_id = enviado.get("session_id") or puente.sesion_de_chat(CHAT_VOZ)
    log(f"Prompt al chat {CHAT_VOZ}: {texto_dictado[:80]}")

    resultado = _esperar_con_cancelacion(puente, session_id, stream, close_recognizer)
    if resultado.get("outcome") == "interrupted":
        return resultado

    if not resultado.get("ok"):
        log(f"Turno sin exito: {resultado.get('outcome')}")
        if resultado.get("outcome") == "timeout":
            hablar("No obtuve respuesta de OpenCode a tiempo.")
        else:
            # Aviso hablado para que el pedido no quede en el aire
            hablar("El cerebro de OpenCode no pudo responder, revisalo desde el celular.")
        return resultado

    respuesta = respuesta_final(puente, resultado)
    if not respuesta:
        log("Respuesta vacia del cerebro.")
        return resultado

    info = hablar(respuesta)
    resultado["audio"] = info
    return resultado


def get_cerebro():
    try:
        return cerebro_activo()
    except Exception:
        return "opencode"


def main():
    vosk.SetLogLevel(-1)
    if not os.path.exists(MODEL_PATH):
        log(f"No encuentro el modelo de Vosk en {MODEL_PATH}")
        sys.exit(1)

    model = vosk.Model(MODEL_PATH)
    wake_grammar = '["hola tars", "hola tas", "hola tarso", "hola tarde", "hola tar", "hola dar", "hola ters", "hola tarts", "hola", "oye tars", "ey tars", "tars", "[unk]"]'
    wake_recognizer = vosk.KaldiRecognizer(model, 16000, wake_grammar)

    close_recognizer = vosk.KaldiRecognizer(model, 16000)

    with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype='int16', channels=1) as stream:
        last_check = 0
        current_mode = "auto"
        prev_mode = "auto"
        cerebro = "opencode"

        while True:
            now = time.time()
            if now - last_check > 0.3:
                current_mode = get_mode()
                cerebro = get_cerebro()
                last_check = now

            if current_mode != "auto":
                prev_mode = current_mode
                try:
                    while stream.read_available > 0:
                        stream.read(min(stream.read_available, 4000))
                except Exception:
                    pass
                wake_recognizer.Reset()
                time.sleep(0.15)
                continue

            if prev_mode != "auto":
                try:
                    while stream.read_available > 0:
                        stream.read(min(stream.read_available, 4000))
                except Exception:
                    pass
                wake_recognizer.Reset()
                prev_mode = "auto"

            if os.path.exists(LOCK_FILE):
                try:
                    while stream.read_available > 0:
                        stream.read(min(stream.read_available, 4000))
                except Exception:
                    pass
                time.sleep(0.15)
                wake_recognizer.Reset()
                continue

            data, overflowed = stream.read(4000)

            text = ""
            if wake_recognizer.AcceptWaveform(bytes(data)):
                res = json.loads(wake_recognizer.Result())
                text = res.get("text", "").lower()
            else:
                pres = json.loads(wake_recognizer.PartialResult())
                text = pres.get("partial", "").lower()

            if text:
                targets = ["hola tars", "hola tas", "hola tarso", "hola tarde", "hola tar", "hola dar", "hola ters", "hola tarts", "oye tars", "ey tars", "tars"]
                if any(k in text for k in targets) or ("hola" in text and any(w in text for w in ["tar", "tas", "tarso", "tarde", "tars", "ter"])):
                    wake_recognizer.Reset()
                    if cerebro == "antigravity":
                        handle_wake_and_auto_close(stream, close_recognizer)
                    else:
                        flujo_voz_opencode(stream, close_recognizer)
                    try:
                        while stream.read_available > 0:
                            stream.read(min(stream.read_available, 4000))
                    except Exception:
                        pass
                    wake_recognizer.Reset()

    cerrar_puente()


if __name__ == "__main__":
    main()
