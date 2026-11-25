#!/usr/bin/env python3
import sys
import os
import time
import subprocess
import threading

TRIGGER_CMD = [
    "/home/santiago/.gemini/tts_venv/bin/python",
    "-c",
    "import sys; sys.path.insert(0, '/home/santiago/.gemini/config'); from f12_listener import trigger_single_action; trigger_single_action()"
]

def trigger_action():
    try:
        # Ejecutar en el contexto del usuario santiago con DISPLAY=:0
        cmd = [
            "su", "-", "santiago", "-c",
            "DISPLAY=:0 /home/santiago/.gemini/tts_venv/bin/python -c \"import sys; sys.path.insert(0, '/home/santiago/.gemini/config'); from f12_listener import trigger_single_action; trigger_single_action()\""
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except Exception as e:
        print(f"[TARS BT] Error disparando accion: {e}")

def main():
    print("[TARS BT] Iniciando monitor via btmon...")
    last_trigger = 0.0

    while True:
        try:
            proc = subprocess.Popen(
                ["btmon"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            for line in iter(proc.stdout.readline, ""):
                # Detectar evento AT+BVRA=1 emitido por el auricular
                if "AT+BVRA=1" in line or "BVRA=1" in line:
                    now = time.time()
                    if now - last_trigger > 1.2:
                        last_trigger = now
                        print(f"[TARS BT] Detectado AT+BVRA=1 de auricular -> Ejecutando F12", flush=True)
                        threading.Thread(target=trigger_action, daemon=True).start()
        except Exception as e:
            print(f"[TARS BT] Error en btmon: {e}", flush=True)
            time.sleep(2)

if __name__ == "__main__":
    main()
