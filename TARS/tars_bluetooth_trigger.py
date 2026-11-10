#!/usr/bin/env python3
import sys
import os
import time
import socket
import struct
import subprocess

STATE_FILE = "/home/santiago/.gemini/config/tars_state.json"
TRIGGER_CMD = ["/home/santiago/.gemini/tts_venv/bin/python", "-c", "import sys; sys.path.insert(0, '/home/santiago/.gemini/config'); from f12_listener import trigger_single_action; trigger_single_action()"]

HCI_CHANNEL_RAW = 0
HCI_CHANNEL_USER = 1
HCI_CHANNEL_CONTROL = 2
HCI_CHANNEL_LOGGING = 3

def trigger_action():
    try:
        subprocess.run(TRIGGER_CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except Exception as e:
        print(f"[TARS BT] Error disparando accion: {e}")

def main():
    print("[TARS BT] Iniciando monitor de eventos Bluetooth Voice Recognition (AT+BVRA)...")
    last_trigger_time = 0.0

    while True:
        try:
            # Crear socket raw HCI
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
            s.bind((0,))
            
            while True:
                data = s.recv(2048)
                if not data:
                    continue
                # Buscar secuencia de comando de reconocimiento por voz de auricular HFP
                if b"AT+BVRA=1" in data or b"+BVRA: 1" in data:
                    now = time.time()
                    if now - last_trigger_time > 1.2:
                        last_trigger_time = now
                        print(f"[TARS BT] Capturado AT+BVRA=1 (Boton Asistente Auricular) -> Disparando F12")
                        trigger_action()
        except PermissionError:
            print("[TARS BT] Error de permisos raw HCI. Se requiere root o CAP_NET_RAW / CAP_NET_ADMIN.", file=sys.stderr)
            time.sleep(10)
        except Exception as e:
            time.sleep(2)

if __name__ == "__main__":
    main()
