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
    last_speech_time = None
    spoken_any_word = False
    action = None
    
    while True:
        # Si el usuario cambio de modo fuera de auto (ej. amarillo o rojo), cancelar inmediatamente
        if get_mode() != "auto":
            action = "cancel"
            break

        if os.path.exists(LOCK_FILE):
            time.sleep(0.15)
            close_recognizer.Reset()
            continue
            
        data, overflowed = stream.read(4000)
        now = time.time()
        
        has_new_text = False
        words = []
        if close_recognizer.AcceptWaveform(bytes(data)):
            res = json.loads(close_recognizer.Result())
            raw_text = res.get("text", "").lower()
            words = raw_text.split()
            if words:
                has_new_text = True
        else:
            pres = json.loads(close_recognizer.PartialResult())
            raw_text = pres.get("partial", "").lower()
            words = raw_text.split()
            if words:
                has_new_text = True

        if has_new_text and words:
            if any(w in words for w in ["enviar", "envía", "envia", "cambio", "mandar", "listo"]):
                action = "send"
                break
            elif "cancelar" in words:
                action = "cancel"
                break
            else:
                spoken_any_word = True
                last_speech_time = now

        # Deteccion de silencio post-dictado:
        # Si el usuario ya hablo su mensaje y hubo 2.2 segundos de silencio, enviar automaticamente
        if spoken_any_word and last_speech_time and (now - last_speech_time > 2.2):
            action = "send"
            break

        # Si pasaron 6 segundos desde el Hola TARS y no se detecto ninguna palabra hablada, cancelar
        if not spoken_any_word and (now - start_time > 6.0):
            action = "cancel"
            break

        # Limite maximo razonable para dictados continuos: 60 segundos
        if now - start_time > 60.0:
            action = "send" if spoken_any_word else "cancel"
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
        print("Dictado cerrado o cancelado.")

def main():
    vosk.SetLogLevel(-1)
    if not os.path.exists(MODEL_PATH):
        sys.exit(1)
        
    model = vosk.Model(MODEL_PATH)
    wake_grammar = '["hola tars", "hola tas", "hola tarso", "hola tarde", "hola tar", "hola dar", "hola ters", "hola tarts", "hola", "oye tars", "ey tars", "tars", "[unk]"]'
    wake_recognizer = vosk.KaldiRecognizer(model, 16000, wake_grammar)
    
    close_recognizer = vosk.KaldiRecognizer(model, 16000)

    with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype='int16', channels=1) as stream:
        last_check = 0
        current_mode = "auto"
        prev_mode = "auto"
        
        while True:
            now = time.time()
            if now - last_check > 0.3:
                current_mode = get_mode()
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
                    handle_wake_and_auto_close(stream, close_recognizer)
                    try:
                        while stream.read_available > 0:
                            stream.read(min(stream.read_available, 4000))
                    except Exception:
                        pass
                    wake_recognizer.Reset()

if __name__ == "__main__":
    main()
