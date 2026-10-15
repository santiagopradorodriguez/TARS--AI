#!/usr/bin/env python3
import os
import sys
import time
import signal
import subprocess

LOCK_FILE = "/tmp/tars_speaking.lock"
AUDIO_FILE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/antigravity_response.mp3"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_resource(filename, fallback_dirs=("/home/santiago/.gemini/config", "/home/santiago/repositorios/Jarvis-Assistant/TARS")):
    local_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(local_path):
        return local_path
    for fb in fallback_dirs:
        fb_path = os.path.join(fb, filename)
        if os.path.exists(fb_path):
            return fb_path
    return local_path

CHIME_FILE = get_resource("gemini_chime.wav")

def cleanup(signum=None, frame=None):
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass
    if signum is not None:
        sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def main():
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        
        # Only play chime if it's the main antigravity response
        if "antigravity_response" in AUDIO_FILE and os.path.exists(CHIME_FILE):
            subprocess.run(["paplay", CHIME_FILE],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.1)
            
        if os.path.exists(AUDIO_FILE):
            # Usar paplay si es WAV, ffplay si es mp3
            if AUDIO_FILE.endswith(".wav"):
                subprocess.run(["paplay", AUDIO_FILE],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["ffplay", "-nodisp", "-autoexit", AUDIO_FILE],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        if "antigravity_response" in AUDIO_FILE:
            turn_cue = get_resource("tars_your_turn.wav")
            if os.path.exists(turn_cue):
                subprocess.run(["paplay", turn_cue],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        cleanup()

if __name__ == "__main__":
    main()
