#!/usr/bin/env python3
import subprocess
import time
import os
import re

EDGE_TTS = "/home/santiago/.gemini/tts_venv/bin/edge-tts"
TARS_PLAYER = "/home/santiago/.gemini/config/tars_player.py"
PYTHON_BIN = "/home/santiago/.gemini/tts_venv/bin/python"

# Guardar los últimos remitentes para no repetir si envían muchos mensajes seguidos
recent_senders = {}
COOLDOWN_SECONDS = 30  # 30 segundos de silencio para la misma persona

def announce_sender(sender_name):
    # Generar el audio
    text = f"Mensaje de {sender_name}"
    from tars_rutas import ruta_runtime
    audio_file = ruta_runtime("wa_msg.mp3")
    
    try:
        subprocess.run([EDGE_TTS, "--text", text, "--voice", "es-AR-TomasNeural", "--rate", "-5%", "--write-media", audio_file], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(audio_file):
            wav_file = audio_file.replace(".mp3", ".wav")
            subprocess.run(["ffmpeg", "-y", "-i", audio_file, wav_file], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Reproducir usando tars_player (que silencia el mic para no auto-escucharse)
            subprocess.run([PYTHON_BIN, TARS_PLAYER, wav_file], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Error reproduciendo TTS: {e}")

def main():
    print("Iniciando TARS WhatsApp Monitor (ZapZap)...")
    proc = subprocess.Popen(
        ['dbus-monitor', "interface='org.freedesktop.Notifications',member='Notify'"],
        stdout=subprocess.PIPE,
        universal_newlines=True
    )

    in_method_call = False
    string_count = 0
    app_name = None
    summary = None

    for line in proc.stdout:
        line = line.strip()
        
        if line.startswith("method call"):
            in_method_call = True
            app_name = None
            summary = None
            string_count = 0
            continue
            
        if in_method_call:
            if line.startswith("string"):
                # Extraer contenido del string
                match = re.search(r'string\s+"(.*?)"', line)
                if match:
                    val = match.group(1)
                else:
                    # En caso de multilínea o formato raro
                    parts = line.split('"', 1)
                    val = parts[1].rsplit('"', 1)[0] if len(parts) > 1 else ""
                    
                string_count += 1
                
                if string_count == 1:
                    app_name = val
                elif string_count == 3:
                    summary = val
                    
            elif line.startswith("array"):
                # Hemos leído los primeros argumentos
                if app_name and app_name.lower() == "zapzap" and summary:
                    # summary es el nombre del remitente (ej. "Santiago Prado" o "Grupo X")
                    now = time.time()
                    last_time = recent_senders.get(summary, 0)
                    
                    if now - last_time > COOLDOWN_SECONDS:
                        print(f"Nuevo mensaje de: {summary}")
                        recent_senders[summary] = now
                        announce_sender(summary)
                    else:
                        print(f"Mensaje ignorado (cooldown): {summary}")
                        # Opcional: Actualizar el tiempo para que siga callado si la persona sigue hablando
                        recent_senders[summary] = now
                        
                in_method_call = False

if __name__ == "__main__":
    main()
