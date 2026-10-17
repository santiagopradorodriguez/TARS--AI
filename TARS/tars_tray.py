#!/usr/bin/env python3
import sys
import os
import json
import subprocess
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QActionGroup
from PyQt5.QtGui import QIcon, QCursor
from PyQt5.QtCore import QTimer

STATE_FILE = "/home/santiago/.gemini/config/tars_state.json"
ICON_GREEN = "/home/santiago/.gemini/config/tars_green.png"
ICON_YELLOW = "/home/santiago/.gemini/config/tars_yellow.png"
ICON_RED = "/home/santiago/.gemini/config/tars_red.png"

START_CHIME = "/home/santiago/.gemini/config/tars_record_start.wav"
END_CHIME = "/home/santiago/.gemini/config/tars_record_end.wav"
CANCEL_TONE = "/home/santiago/.gemini/config/tars_cancel_tone.wav"


def get_voice():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("voice", "edge")
    except Exception:
        pass
    return "edge"

def save_voice(voice):
    try:
        data = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
        data["voice"] = voice
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)
        msg = "Voz Clásica (Tomás)" if voice == "edge" else "Voz Neuronal (Puck)"
        os.system(f'notify-send "TARS" "Voz seleccionada: {msg}" -t 2000')
    except Exception:
        pass

def get_mode():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("mode", "auto")
    except Exception:
        pass
    return "auto"

def stop_all_speech():
    subprocess.run(["pkill", "-9", "-f", "paplay.*antigravity_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "paplay.*wa_msg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "ffplay.*antigravity_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "tars_player.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if os.path.exists("/tmp/tars_speaking.lock"):
            os.remove("/tmp/tars_speaking.lock")
        if os.path.exists("/tmp/tars_dictating.lock"):
            os.remove("/tmp/tars_dictating.lock")
    except Exception:
        pass

def save_mode(mode):
    with open(STATE_FILE, "w") as f:
        json.dump({"mode": mode}, f)
        
    sound = None
    msg = ""
    if mode == "auto":
        sound = START_CHIME
        msg = "Modo: Verde - Escucha Automatica"
    elif mode == "button":
        sound = END_CHIME
        msg = "Modo: Amarillo - Solo Boton F12"
    elif mode == "off":
        # Cortar inmediatamente cualquier reproducción de voz activa de TARS
        stop_all_speech()
        sound = CANCEL_TONE
        msg = "Modo: Rojo - Silencio Total"

    os.system(f'notify-send "TARS" "{msg}" -t 2000')

    if sound and os.path.exists(sound):
        subprocess.Popen(["paplay", sound], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

class TarsTrayApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.tray = QSystemTrayIcon()
        self.current_mode = get_mode()
        self.current_voice = get_voice()

        self.create_menu()
        self.update_display(self.current_mode)

        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

        # Timer para sincronizar si el estado cambia por voz o F12
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_state_sync)
        self.timer.start(500)

    def on_tray_activated(self, reason):
        # Desplegar el menú selector directamente en la posición del cursor
        self.menu.popup(QCursor.pos())

    def create_menu(self):
        self.menu = QMenu()

        self.header_action = QAction("Estado: " + self.current_mode.upper(), self.menu)
        self.header_action.setEnabled(False)
        self.menu.addAction(self.header_action)
        self.menu.addSeparator()

        self.group = QActionGroup(self.menu)

        self.action_auto = QAction("Modo Verde: Automático (Hola TARS)", self.menu, checkable=True)
        self.action_auto.triggered.connect(lambda: self.switch_mode("auto"))
        self.group.addAction(self.action_auto)
        self.menu.addAction(self.action_auto)

        self.action_button = QAction("Modo Amarillo: Solo Botón (F12)", self.menu, checkable=True)
        self.action_button.triggered.connect(lambda: self.switch_mode("button"))
        self.group.addAction(self.action_button)
        self.menu.addAction(self.action_button)

        self.action_off = QAction("Modo Rojo: Apagar TARS (Silencio)", self.menu, checkable=True)
        self.action_off.triggered.connect(lambda: self.switch_mode("off"))
        self.group.addAction(self.action_off)
        self.menu.addAction(self.action_off)

        self.menu.addSeparator()

        # Submenú de Selección de Voz
        self.voice_menu = self.menu.addMenu("Voz de TARS")
        self.voice_group = QActionGroup(self.voice_menu)

        self.action_voice_edge = QAction("Clásica (Tomás / Edge)", self.voice_menu, checkable=True)
        self.action_voice_edge.triggered.connect(lambda: self.switch_voice("edge"))
        self.voice_group.addAction(self.action_voice_edge)
        self.voice_menu.addAction(self.action_voice_edge)

        self.action_voice_puck = QAction("Neuronal (Puck / Gemini)", self.voice_menu, checkable=True)
        self.action_voice_puck.triggered.connect(lambda: self.switch_voice("puck"))
        self.voice_group.addAction(self.action_voice_puck)
        self.voice_menu.addAction(self.action_voice_puck)

        self.update_voice_display(self.current_voice)

        self.menu.addSeparator()
        self.action_exit = QAction("Salir", self.menu)
        self.action_exit.triggered.connect(self.exit_app)
        self.menu.addAction(self.action_exit)

        self.tray.setContextMenu(self.menu)

    def exit_app(self):
        try:
            self.tray.hide()
        except Exception:
            pass
        save_mode("off")
        stop_all_speech()
        try:
            subprocess.run(
                ["systemctl", "--user", "stop", "--no-block", "tars-wake-word.service", "antigravity-f12.service", "tars-tray.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass
        self.app.quit()

    def switch_voice(self, new_voice):
        if self.current_voice != new_voice:
            self.current_voice = new_voice
            save_voice(new_voice)
            self.update_voice_display(new_voice)

    def update_voice_display(self, voice):
        if voice == "puck":
            self.action_voice_puck.setChecked(True)
        else:
            self.action_voice_edge.setChecked(True)

    def switch_mode(self, new_mode):
        if self.current_mode != new_mode:
            self.current_mode = new_mode
            save_mode(new_mode)
            self.update_display(new_mode)

    def update_display(self, mode):
        self.header_action.setText(f"Estado: {mode.upper()}")
        if mode == "auto":
            icon_path = ICON_GREEN
            tooltip = "TARS: Escucha Automática (Hola TARS)"
            self.action_auto.setChecked(True)
        elif mode == "button":
            icon_path = ICON_YELLOW
            tooltip = "TARS: Modo Solo Tecla (F12)"
            self.action_button.setChecked(True)
        else:
            icon_path = ICON_RED
            tooltip = "TARS: Apagado (Micrófono cerrado)"
            self.action_off.setChecked(True)

        if os.path.exists(icon_path):
            self.tray.setIcon(QIcon(icon_path))
        self.tray.setToolTip(tooltip)

    def check_state_sync(self):
        disk_mode = get_mode()
        if disk_mode != self.current_mode:
            self.current_mode = disk_mode
            self.update_display(disk_mode)

        disk_voice = get_voice()
        if disk_voice != self.current_voice:
            self.current_voice = disk_voice
            self.update_voice_display(disk_voice)

    def run(self):
        sys.exit(self.app.exec_())

if __name__ == "__main__":
    app = TarsTrayApp()
    app.run()
