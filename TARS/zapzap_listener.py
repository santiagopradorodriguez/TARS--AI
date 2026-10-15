#!/usr/bin/env python3
import sys
import subprocess
import os
import re
import time
import asyncio
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if "/home/santiago/.gemini/config" not in sys.path:
    sys.path.append("/home/santiago/.gemini/config")

def get_resource(filename, fallback_dirs=("/home/santiago/.gemini/config", "/home/santiago/repositorios/Jarvis-Assistant/TARS")):
    local_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(local_path):
        return local_path
    for fb in fallback_dirs:
        fb_path = os.path.join(fb, filename)
        if os.path.exists(fb_path):
            return fb_path
    return local_path

import certifi
import edge_tts
from tars_voice_engine import synthesize_speech, get_voice

os.environ["SSL_CERT_FILE"] = certifi.where()

PYTHON_BIN = "/home/santiago/.gemini/tts_venv/bin/python"
if not os.path.exists(PYTHON_BIN):
    PYTHON_BIN = sys.executable

TARS_PLAYER = get_resource("tars_player.py")
DEFAULT_SOUND = get_resource("tenes_un_mensaje_de_whatsapp.wav")
VOICE = "es-AR-TomasNeural"

recent_senders = {}
COOLDOWN_SECONDS = 30  # 30 segundos de silencio para la misma persona

async def generate_speech(text, mp3_path):
    communicate = edge_tts.Communicate(text, VOICE, rate="-5%")
    await communicate.save(mp3_path)

def announce_message(sender_name):
    # Limpiar nombre del remitente
    clean_sender = re.sub(r'[^\w\s]', '', sender_name).strip()
    if not clean_sender:
        clean_sender = "WhatsApp"

    text = f"Mensaje de {clean_sender}"
    mp3_file = "/tmp/wa_msg.mp3"
    wav_file = "/tmp/wa_msg.wav"

    try:
        if os.path.exists(wav_file):
            os.remove(wav_file)
        if os.path.exists(mp3_file):
            os.remove(mp3_file)
    except Exception:
        pass

    success = False
    try:
        # Sintetizar usando el motor dual (Puck o Edge-TTS según selección)
        success = synthesize_speech(text, wav_file)
        if success and os.path.exists(wav_file) and os.path.getsize(wav_file) > 100:
            subprocess.run([PYTHON_BIN, TARS_PLAYER, wav_file],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    except Exception as e:
        print(f"Error en TTS dual de WhatsApp: {e}", flush=True)

    if not (success and os.path.exists(wav_file) and os.path.getsize(wav_file) > 100):
        try:
            asyncio.run(generate_speech(text, mp3_file))
            if os.path.exists(mp3_file) and os.path.getsize(mp3_file) > 100:
                subprocess.run(["ffmpeg", "-y", "-i", mp3_file, wav_file],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(wav_file) and os.path.getsize(wav_file) > 100:
                    subprocess.run([PYTHON_BIN, TARS_PLAYER, wav_file],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
        except Exception as e2:
            print(f"Error en generate_speech de WhatsApp: {e2}", flush=True)

    # Fallback si falla todo: reproducir sonido base según la voz activa
    fallback_sound = DEFAULT_SOUND
    try:
        if get_voice() == "puck":
            puck_sound = get_resource("cues_puck/tenes_un_mensaje_de_whatsapp.wav")
            if os.path.exists(puck_sound):
                fallback_sound = puck_sound
    except Exception:
        pass

    if os.path.exists(fallback_sound):
        subprocess.run([PYTHON_BIN, TARS_PLAYER, fallback_sound],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    print("Iniciando ZapZap Listener robusto...", flush=True)
    cmd = ["dbus-monitor", "type='method_call',interface='org.freedesktop.Notifications',member='Notify'"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)

    in_call = False
    call_lines = []
    strings = []

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if line.startswith("method call"):
            # Procesar la llamada anterior si la había
            if in_call and call_lines:
                process_notification(call_lines, strings)
            in_call = True
            call_lines = [line]
            strings = []
            continue

        if in_call:
            call_lines.append(line)
            # Extraer strings
            match = re.search(r'string\s+"(.*?)"', line)
            if match:
                strings.append(match.group(1))
            # El último parámetro del método Notify es siempre int32 expire_timeout
            if line.startswith("int32"):
                process_notification(call_lines, strings)
                in_call = False
                call_lines = []
                strings = []

def process_notification(call_lines, strings):
    # Si TARS está en modo apagado (Rojo), silencio absoluto
    try:
        state_f = get_resource("tars_state.json")
        if os.path.exists(state_f):
            import json
            with open(state_f, "r") as sf:
                if json.load(sf).get("mode") == "off":
                    return
    except Exception:
        pass

    full_text = "\n".join(call_lines)
    # Detectar si la notificación proviene de ZapZap o WhatsApp en cualquier campo
    is_zapzap = bool(re.search(r'(?:ZapZap|zapzap|com\.rtosta\.zapzap|WhatsApp|whatsdesk)', full_text, re.IGNORECASE))
    if not is_zapzap:
        return

    # En la firma de Notify:
    # strings[0] = app_name (ej. "ZapZap" o "")
    # strings[1] = app_icon (ej. "")
    # strings[2] = summary (nombre del remitente o grupo)
    # strings[3] = body (texto del mensaje)
    summary = ""
    if len(strings) >= 3:
        summary = strings[2].strip()
    elif len(strings) >= 1:
        summary = strings[0].strip()

    if not summary or summary.lower() in ("zapzap", "whatsapp"):
        # Si el summary no tiene el nombre, buscar en body si existe
        if len(strings) >= 4 and strings[3].strip():
            # A veces el formato es "Remitente: Mensaje"
            parts = strings[3].split(":", 1)
            summary = parts[0].strip() if len(parts) > 1 else summary

    sender = summary if summary else "WhatsApp"
    now = time.time()
    last_time = recent_senders.get(sender, 0)

    # Ventana de cooldown para no spamear si mandan muchos mensajes juntos
    if now - last_time > COOLDOWN_SECONDS:
        print(f"Notificando mensaje de: {sender}", flush=True)
        recent_senders[sender] = now
        announce_message(sender)
    else:
        print(f"Mensaje en cooldown de: {sender}", flush=True)
        recent_senders[sender] = now

if __name__ == "__main__":
    main()
