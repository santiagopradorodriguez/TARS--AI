#!/usr/bin/env python3
import sys
import os
import json
import time
import subprocess
import numpy as np
import sounddevice as sd
import vosk
from pynput import keyboard

MODEL_PATH = "/home/santiago/.gemini/models/vosk-model-small-es-0.42"
STATE_FILE = "/home/santiago/.gemini/config/tars_state.json"
START_CHIME = "/home/santiago/.gemini/config/tars_record_start.wav"
END_CHIME = "/home/santiago/.gemini/config/tars_record_end.wav"
CANCEL_TONE = "/home/santiago/.gemini/config/tars_cancel_tone.wav"
LOCK_FILE = "/tmp/tars_speaking.lock"

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
    with open(STATE_FILE, "w") as f:
        json.dump({"mode": mode}, f)
        
    msg = ""
    if mode == "auto":
        msg = "🟢 Modo Escucha Automática"
    elif mode == "button":
        msg = "🟡 Modo Solo Botón (Push-To-Talk)"
    elif mode == "off":
        msg = "🔴 TARS Apagado (Privacidad)"
    
    os.system(f'notify-send "TARS" "{msg}" -t 2000')

def send_ctrl_m():
    controller = keyboard.Controller()
    controller.press(keyboard.Key.ctrl_l)
    time.sleep(0.04)
    controller.press('m')
    time.sleep(0.04)
    controller.release('m')
    time.sleep(0.04)
    controller.release(keyboard.Key.ctrl_l)

def send_enter():
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

def handle_wake_and_auto_close(stream, close_recognizer):
    stop_all_speech()
    
    if os.path.exists(START_CHIME):
        subprocess.Popen(["paplay", START_CHIME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    time.sleep(0.15)
    send_ctrl_m()
    time.sleep(0.5)
    close_recognizer.Reset()
    
    start_time = time.time()
    action = None
    
    while True:
        if os.path.exists(LOCK_FILE):
            time.sleep(0.15)
            close_recognizer.Reset()
            continue
            
        data, overflowed = stream.read(4000)
        now = time.time()
        
        if close_recognizer.AcceptWaveform(bytes(data)):
            res = json.loads(close_recognizer.Result())
            words = res.get("text", "").lower().split()
            
            if any(w in words for w in ["enviar", "envía", "envia", "cambio", "mandar", "listo"]):
                action = "send"
                break
            elif "cancelar" in words:
                action = "cancel"
                break
        else:
            # Detección inmediata si la última palabra hablada es de envío o cancelación
            pres = json.loads(close_recognizer.PartialResult())
            pwords = pres.get("partial", "").lower().split()
            if pwords:
                last_w = pwords[-1]
                if last_w in ["enviar", "envía", "envia", "cambio", "mandar"]:
                    action = "send"
                    break
                elif last_w == "cancelar":
                    action = "cancel"
                    break
                
        # Límite amplio de 10 minutos (600s) para mensajes largos
        if now - start_time > 600.0:
            action = "timeout"
            break
                
    time.sleep(0.15)
    send_ctrl_m()
    
    if action == "send":
        if os.path.exists(END_CHIME):
            subprocess.Popen(["paplay", END_CHIME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        send_enter()
    elif action == "cancel":
        if os.path.exists(CANCEL_TONE):
            subprocess.Popen(["paplay", CANCEL_TONE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Dictado cancelado.")

def main():
    vosk.SetLogLevel(-1)
    if not os.path.exists(MODEL_PATH):
        sys.exit(1)
        
    model = vosk.Model(MODEL_PATH)
    wake_grammar = '["hola tas", "hola tarso", "hola tarde", "hola", "[unk]"]'
    wake_recognizer = vosk.KaldiRecognizer(model, 16000, wake_grammar)
    
    # Quitar la gramática restrictiva. Usar el vocabulario completo de Vosk.
    # Así evitamos que cualquier ruido se fuerce a ser "enviar" o "cancelar".
    close_recognizer = vosk.KaldiRecognizer(model, 16000)

    with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype='int16', channels=1) as stream:
        last_check = 0
        current_mode = "auto"
        
        while True:
            now = time.time()
            if now - last_check > 1.0:
                current_mode = get_mode()
                last_check = now
                
            if current_mode != "auto":
                try:
                    data, _ = stream.read(4000)
                except Exception:
                    pass
                wake_recognizer.Reset()
                time.sleep(0.1)
                continue
                
            if os.path.exists(LOCK_FILE):
                try:
                    data, _ = stream.read(4000)
                except Exception:
                    pass
                time.sleep(0.15)
                wake_recognizer.Reset()
                continue
                
            data, overflowed = stream.read(4000)
            if wake_recognizer.AcceptWaveform(bytes(data)):
                res = json.loads(wake_recognizer.Result())
                text = res.get("text", "").lower()
                if any(k in text for k in ["hola tas", "hola tarso", "hola tarde"]):
                    wake_recognizer.Reset()
                    handle_wake_and_auto_close(stream, close_recognizer)
                    time.sleep(1.0)
                    wake_recognizer.Reset()

if __name__ == "__main__":
    main()
