#!/usr/bin/env python3
import os
import sys
import time
import signal
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from tars_rutas import recurso_tars
except ImportError as exc:
    print(f"[TARS] No pude importar tars_rutas ({exc}); uso rutas basicas.", file=sys.stderr)

    def recurso_tars(nombre, extra=()):
        configuracion = os.environ.get("TARS_CONFIG_DIR") or os.path.expanduser("~/.gemini/config")
        for ruta in (os.path.join(BASE_DIR, nombre), os.path.join(configuracion, nombre)):
            if os.path.exists(ruta):
                return ruta
        return os.path.join(BASE_DIR, nombre)

LOCK_FILE = "/tmp/tars_speaking.lock"
AUDIO_FILE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/antigravity_response.mp3"

CHIME_FILE = recurso_tars("gemini_chime.wav")

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
            turn_cue = recurso_tars("tars_your_turn.wav")
            if os.path.exists(turn_cue):
                subprocess.run(["paplay", turn_cue],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        cleanup()

if __name__ == "__main__":
    main()
