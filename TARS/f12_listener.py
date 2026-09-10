#!/usr/bin/env python3
import time
import os
import json
import subprocess
import threading
from pynput import keyboard

STATE_FILE = "/home/santiago/.gemini/config/tars_state.json"
CANCEL_TONE = "/home/santiago/.gemini/config/tars_cancel_tone.wav"
RECORD_START_TONE = "/home/santiago/.gemini/config/tars_record_start.wav"
RECORD_END_TONE = "/home/santiago/.gemini/config/tars_record_end.wav"
CHIME_FILE = "/home/santiago/.gemini/config/gemini_chime.wav"
DICTATING_LOCK = "/tmp/tars_dictating.lock"
CHATGPT_DICTATING_LOCK = "/tmp/chatgpt_dictating.lock"
SPEAKING_LOCK = "/tmp/tars_speaking.lock"
CHATGPT_VOICE_WAV = "/tmp/chatgpt_voice.wav"
PYTHON_WHISPER = "/home/santiago/repositorios/CosmicGenerator/venv/bin/python3"

tap_times = []
tap_lock = threading.Lock()

def play_sound(path, fallback=CHIME_FILE):
    target = path if os.path.exists(path) else fallback
    if os.path.exists(target):
        subprocess.Popen(["paplay", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_mode():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("mode", "auto")
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

def is_target_key(key):
    vk = getattr(key, 'vk', None)
    return key in (keyboard.Key.f12, keyboard.Key.insert) or vk == 269025090 or str(key) == '<269025090>'

def get_active_window():
    try:
        out = subprocess.check_output(["xprop", "-root", "_NET_ACTIVE_WINDOW"], text=True)
        win_id = out.split("#")[-1].strip()
        if win_id and win_id != "0x0":
            wm_class = subprocess.check_output(["xprop", "-id", win_id, "WM_CLASS"], text=True).lower()
            wm_name = subprocess.check_output(["xprop", "-id", win_id, "WM_NAME"], text=True).lower()
            return wm_class + " " + wm_name
    except Exception:
        pass
    return ""

def send_ctrl_m():
    controller = keyboard.Controller()
    time.sleep(0.04)
    controller.press(keyboard.Key.ctrl_l)
    time.sleep(0.03)
    controller.press('m')
    time.sleep(0.03)
    controller.release('m')
    time.sleep(0.03)
    controller.release(keyboard.Key.ctrl_l)

def send_enter():
    controller = keyboard.Controller()
    time.sleep(0.05)
    controller.press(keyboard.Key.enter)
    time.sleep(0.05)
    controller.release(keyboard.Key.enter)

def stop_all_speech():
    subprocess.run(["pkill", "-9", "-f", "paplay.*antigravity_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "paplay.*chatgpt_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "paplay.*wa_msg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "ffplay.*antigravity_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "ffplay.*chatgpt_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "tars_player.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if os.path.exists(SPEAKING_LOCK):
            os.remove(SPEAKING_LOCK)
    except Exception:
        pass

def trigger_killswitch():
    stop_all_speech()
    if os.path.exists(DICTATING_LOCK):
        try:
            os.remove(DICTATING_LOCK)
        except Exception:
            pass
        send_ctrl_m()
    if os.path.exists(CHATGPT_DICTATING_LOCK):
        try:
            os.remove(CHATGPT_DICTATING_LOCK)
        except Exception:
            pass
        subprocess.run(["pkill", "-9", "-f", "arecord.*chatgpt_voice.wav"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    set_mode("off")
    play_sound(CANCEL_TONE)

def process_chatgpt_transcription():
    try:
        script = """
import whisper, sys
try:
    model = whisper.load_model("tiny")
    res = model.transcribe("/tmp/chatgpt_voice.wav", language="es", fp16=False)
    text = res.get("text", "").strip()
    if text:
        sys.stdout.write(text)
except Exception:
    pass
"""
        out = subprocess.check_output([PYTHON_WHISPER, "-c", script], text=True).strip()
        if out:
            controller = keyboard.Controller()
            time.sleep(0.05)
            controller.type(out)
            time.sleep(0.1)
            send_enter()
    except Exception:
        pass

def trigger_single_action():
    stop_all_speech()
    current_mode = get_mode()
    
    if current_mode == "off":
        return

    active_win = get_active_window()
    is_chatgpt = "chatgpt" in active_win or "codex" in active_win

    if is_chatgpt:
        # Modo dictado inteligente para ChatGPT
        if os.path.exists(CHATGPT_DICTATING_LOCK):
            try:
                os.remove(CHATGPT_DICTATING_LOCK)
            except Exception:
                pass
            play_sound(RECORD_END_TONE)
            subprocess.run(["pkill", "-INT", "-f", "arecord.*chatgpt_voice.wav"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.05)
            threading.Thread(target=process_chatgpt_transcription, daemon=True).start()
        else:
            with open(CHATGPT_DICTATING_LOCK, "w") as f:
                f.write("1")
            play_sound(RECORD_START_TONE)
            subprocess.Popen(["arecord", "-D", "default", "-r", "16000", "-c", "1", "-f", "S16_LE", CHATGPT_VOICE_WAV],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Modo nativo para Antigravity
        if os.path.exists(DICTATING_LOCK):
            try:
                os.remove(DICTATING_LOCK)
            except Exception:
                pass
            play_sound(RECORD_END_TONE)
            send_ctrl_m()
            time.sleep(0.15)
            send_enter()
        else:
            with open(DICTATING_LOCK, "w") as f:
                f.write("1")
            play_sound(RECORD_START_TONE)
            send_ctrl_m()

def on_press(key):
    if not is_target_key(key):
        return

    now = time.time()
    with tap_lock:
        tap_times.append(now)
        while tap_times and now - tap_times[0] > 1.2:
            tap_times.pop(0)

        if len(tap_times) >= 3:
            tap_times.clear()
            trigger_killswitch()
            return

    trigger_single_action()

def main():
    for lock in [DICTATING_LOCK, CHATGPT_DICTATING_LOCK]:
        if os.path.exists(lock):
            try:
                os.remove(lock)
            except Exception:
                pass
    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()

if __name__ == "__main__":
    main()
