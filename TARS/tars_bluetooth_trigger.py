#!/usr/bin/env python3
"""
Disparador Bluetooth endurecido para TARS.
- No usa `su - usuario` ni shell strings; debe ejecutarse como servicio de usuario
  con CAP_NET_RAW en `btmon` (o en el grupo correspondiente).
- Filtra por direccion MAC autorizada via TARS_BT_ALLOWED_MAC si esta configurada.
"""
import os
import re
import sys
import time
import subprocess
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALLOWED_MAC = os.environ.get("TARS_BT_ALLOWED_MAC", "").strip().upper()
MAC_RE = re.compile(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})")


def _python_bin():
    venv = os.path.expanduser("~/.gemini/tts_venv/bin/python")
    return venv if os.path.isfile(venv) else (sys.executable or "python3")


def trigger_action():
    try:
        env = dict(os.environ)
        env.setdefault("DISPLAY", ":0")
        cmd = [
            _python_bin(),
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); from f12_listener import trigger_single_action; trigger_single_action()",
            BASE_DIR,
        ]
        subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except Exception as e:
        print(f"[TARS BT] Error disparando accion: {e}", flush=True)


def main():
    print("[TARS BT] Iniciando monitor endurecido via btmon...", flush=True)
    if ALLOWED_MAC:
        print(f"[TARS BT] Filtrando exclusivamente por MAC autorizada: {ALLOWED_MAC}", flush=True)
    else:
        print("[TARS BT] Aviso: defina TARS_BT_ALLOWED_MAC=AA:BB:CC:DD:EE:FF para restringir a su auricular.", flush=True)

    last_trigger = 0.0
    last_seen_mac = ""

    while True:
        try:
            proc = subprocess.Popen(
                ["btmon"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in iter(proc.stdout.readline, ""):
                m = MAC_RE.search(line)
                if m:
                    last_seen_mac = m.group(1).upper()
                if "AT+BVRA=1" in line or "BVRA=1" in line:
                    if ALLOWED_MAC and last_seen_mac != ALLOWED_MAC:
                        continue
                    now = time.time()
                    if now - last_trigger > 1.2:
                        last_trigger = now
                        print("[TARS BT] Detectado AT+BVRA=1 autorizado -> Ejecutando F12", flush=True)
                        threading.Thread(target=trigger_action, daemon=True).start()
        except Exception as e:
            print(f"[TARS BT] Error en btmon: {e}", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
