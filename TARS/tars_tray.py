#!/usr/bin/env python3
import sys
import os
import json
import threading
import subprocess
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QActionGroup
from PyQt5.QtGui import QIcon, QCursor
from PyQt5.QtCore import QTimer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from tars_rutas import (
        cargar_estado,
        etiqueta_servicio_opencode,
        guardar_llave_estado,
        recurso_tars,
        ruta_estado,
        servicio_opencode,
    )
except ImportError as exc:
    # Respaldo minimo si el instalador no llevo tars_rutas.py
    print(f"[TARS] No pude importar tars_rutas ({exc}); uso rutas basicas.", file=sys.stderr)

    def directorio_config_tars():
        return os.environ.get("TARS_CONFIG_DIR") or os.path.expanduser("~/.gemini/config")

    def ruta_estado():
        return os.path.join(directorio_config_tars(), "tars_state.json")

    def cargar_estado():
        try:
            with open(ruta_estado(), "r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
            return datos if isinstance(datos, dict) else {}
        except Exception:
            return {}

    def guardar_llave_estado(clave, valor):
        try:
            datos = cargar_estado()
            datos[clave] = valor
            with open(ruta_estado(), "w", encoding="utf-8") as archivo:
                json.dump(datos, archivo)
            return True
        except Exception:
            return False

    def recurso_tars(nombre, extra=()):
        for ruta in (os.path.join(BASE_DIR, nombre), os.path.join(directorio_config_tars(), nombre)):
            if os.path.exists(ruta):
                return ruta
        return os.path.join(BASE_DIR, nombre)

    def servicio_opencode():
        return {"disponible": False, "corriendo": False, "url": "", "puerto": None, "pid": None}

    def etiqueta_servicio_opencode(info):
        return "OpenCode apagado"

STATE_FILE = ruta_estado()
ICON_GREEN = recurso_tars("tars_green.png")
ICON_YELLOW = recurso_tars("tars_yellow.png")
ICON_RED = recurso_tars("tars_red.png")

START_CHIME = recurso_tars("tars_record_start.wav")
END_CHIME = recurso_tars("tars_record_end.wav")
CANCEL_TONE = recurso_tars("tars_cancel_tone.wav")

ICON_CEREBRO = {
    "opencode": recurso_tars("tars_cerebro_opencode.png"),
    "antigravity": recurso_tars("tars_cerebro_antigravity.png"),
}
try:
    # Si faltan los PNG del selector de cerebro se generan una vez y listo
    from tars_iconos_cerebro import asegurar_iconos as _asegurar_iconos
    ICON_CEREBRO.update(_asegurar_iconos())
except Exception:
    pass
NOMBRE_CEREBRO = {"opencode": "OpenCode", "antigravity": "Antigravity"}
CEREBROS = ("opencode", "antigravity")

# Cada cuantos ticks del timer (500 ms) se vuelve a consultar el servicio
INTERVALO_ESTADO_SERVICIO = 6


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

def get_brain():
    """Cerebro activo. Por defecto OpenCode, como quedo cerrado con el usuario."""
    try:
        valor = cargar_estado().get("cerebro", "opencode")
        return valor if valor in CEREBROS else "opencode"
    except Exception:
        return "opencode"

def save_brain(brain):
    """
    Escribe la llave cerebro en tars_state.json sin reiniciar nada: el server,
    el wake word y el tray lo releen en cada vuelta.
    """
    if not guardar_llave_estado("cerebro", brain):
        return False
    nombre = NOMBRE_CEREBRO.get(brain, brain)
    os.system(f'notify-send "TARS" "Cerebro seleccionado: {nombre}" -t 2000')
    return True

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
        self.current_brain = get_brain()

        # Estado del servicio OpenCode: se consulta en un hilo para no
        # trabar la interfaz con el chequeo de puerto.
        self._tick_estado = 0
        self._hilo_estado = None
        self._estado_servicio = servicio_opencode()
        self._texto_servicio = ""

        self.create_menu()
        self.update_display(self.current_mode)
        self.update_brain_display(self.current_brain)
        self.update_service_display()

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

        self.service_action = QAction("OpenCode: verificando", self.menu)
        self.service_action.setEnabled(False)
        self.menu.addAction(self.service_action)
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

        # Submenú de Selección de Cerebro
        self.brain_menu = self.menu.addMenu("Cerebro de TARS")
        self.brain_group = QActionGroup(self.brain_menu)

        self.action_brain_opencode = QAction("OpenCode", self.brain_menu, checkable=True)
        self.action_brain_opencode.triggered.connect(lambda: self.switch_brain("opencode"))
        self.brain_group.addAction(self.action_brain_opencode)
        self.brain_menu.addAction(self.action_brain_opencode)

        self.action_brain_antigravity = QAction("Antigravity", self.brain_menu, checkable=True)
        self.action_brain_antigravity.triggered.connect(lambda: self.switch_brain("antigravity"))
        self.brain_group.addAction(self.action_brain_antigravity)
        self.brain_menu.addAction(self.action_brain_antigravity)

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

    def switch_brain(self, new_brain):
        if new_brain not in CEREBROS:
            return
        if self.current_brain != new_brain:
            self.current_brain = new_brain
            save_brain(new_brain)
            self.update_brain_display(new_brain)

    def update_brain_display(self, brain):
        acciones = {
            "opencode": self.action_brain_opencode,
            "antigravity": self.action_brain_antigravity,
        }
        for nombre, accion in acciones.items():
            if brain == nombre:
                accion.setChecked(True)
            icono = ICON_CEREBRO.get(nombre)
            if icono and os.path.exists(icono):
                accion.setIcon(QIcon(icono))

    def update_service_display(self):
        texto = etiqueta_servicio_opencode(self._estado_servicio)
        if texto != self._texto_servicio:
            self._texto_servicio = texto
            self.service_action.setText(texto)

    def _consultar_servicio(self):
        """Dispara la consulta del servicio en un hilo corto, sin bloquear Qt."""
        if self._hilo_estado is not None and self._hilo_estado.is_alive():
            return

        def _trabajo():
            try:
                self._estado_servicio = servicio_opencode()
            except Exception:
                self._estado_servicio = {"corriendo": False, "puerto": None}

        self._hilo_estado = threading.Thread(target=_trabajo, name="estado-opencode", daemon=True)
        self._hilo_estado.start()

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

        disk_brain = get_brain()
        if disk_brain != self.current_brain:
            self.current_brain = disk_brain
            self.update_brain_display(disk_brain)

        self._tick_estado += 1
        if self._tick_estado % INTERVALO_ESTADO_SERVICIO == 1:
            self._consultar_servicio()
        self.update_service_display()

    def run(self):
        sys.exit(self.app.exec_())

if __name__ == "__main__":
    app = TarsTrayApp()
    app.run()
