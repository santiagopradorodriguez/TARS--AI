#!/usr/bin/env python3
import sys
import os
import json
import io
import base64
import subprocess
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QApplication, QTabWidget, QWidget
)
from PyQt5.QtGui import QPixmap, QImage, QFont
from PyQt5.QtCore import Qt, QTimer

def get_connection_info():
    info = {
        "local_ip": "127.0.0.1",
        "local_url": "",
        "tailscale_ip": "",
        "tailscale_magicdns": "",
        "tailscale_url": "",
        "tailscale_state": "Desconocido",
        "tailscale_auth_url": ""
    }
    # Local IP
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.254.254.254", 1))
        info["local_ip"] = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    info["local_url"] = f"https://{info['local_ip']}:8443"

    # Tailscale
    try:
        out = subprocess.check_output(["tailscale", "status", "--json"], text=True, timeout=2.5)
        ts_data = json.loads(out)
        state = ts_data.get("BackendState", "Stopped")
        info["tailscale_state"] = state
        info["tailscale_auth_url"] = ts_data.get("AuthURL", "")

        ips = ts_data.get("TailscaleIPs", [])
        if ips:
            info["tailscale_ip"] = ips[0]
            info["tailscale_url"] = f"https://{ips[0]}:8443"

        magic = ts_data.get("Self", {}).get("DNSName", "").rstrip(".")
        if magic and ".ts.net" in magic:
            info["tailscale_magicdns"] = magic
            info["tailscale_url"] = f"https://{magic}:8443"
    except Exception:
        pass

    return info

def generate_qr_pixmap(url):
    import qrcode
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    qimg = QImage.fromData(buf.getvalue())
    return QPixmap.fromImage(qimg)

class TarsQRDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vincular Celular con TARS")
        self.setFixedSize(480, 560)
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f8fafc;
                font-family: system-ui, -apple-system, sans-serif;
            }
            QLabel {
                color: #cbd5e1;
            }
            QTabWidget::pane {
                border: 1px solid #334155;
                background: #1e293b;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #0f172a;
                color: #94a3b8;
                padding: 10px 20px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #1e293b;
                color: #38bdf8;
                border-bottom: 2px solid #38bdf8;
            }
            QPushButton {
                background-color: #0284c7;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton#btnSecondary {
                background-color: #334155;
                color: #cbd5e1;
            }
            QPushButton#btnSecondary:hover {
                background-color: #475569;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QLabel("Conectar Celular con TARS")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        sub = QLabel("Apunta la cámara de tu celular o app al código QR para vincular al instante:")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("font-size: 13px; color: #94a3b8;")
        layout.addWidget(sub)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.info = get_connection_info()

        # Tab 1: Red Local Wi-Fi
        self.tab_local = QWidget()
        self.setup_local_tab()
        self.tabs.addTab(self.tab_local, "Red Local (En Casa)")

        # Tab 2: Tailscale
        self.tab_tailscale = QWidget()
        self.setup_tailscale_tab()
        self.tabs.addTab(self.tab_tailscale, "Tailscale (Fuera de Casa)")

        # Botón Cerrar
        btn_close = QPushButton("Cerrar")
        btn_close.setObjectName("btnSecondary")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignCenter)

    def setup_local_tab(self):
        v = QVBoxLayout(self.tab_local)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)
        v.setAlignment(Qt.AlignCenter)

        url = self.info.get("local_url", "")
        pix = generate_qr_pixmap(url)
        qr_lbl = QLabel()
        qr_lbl.setPixmap(pix)
        qr_lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(qr_lbl)

        url_lbl = QLabel(f"<b>URL:</b> {url}")
        url_lbl.setStyleSheet("font-size: 13px; color: #38bdf8;")
        url_lbl.setAlignment(Qt.AlignCenter)
        url_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(url_lbl)

        hint = QLabel("Usa esta opción si el celular está conectado al mismo Wi-Fi de tu casa.")
        hint.setStyleSheet("font-size: 11px; color: #64748b;")
        hint.setAlignment(Qt.AlignCenter)
        v.addWidget(hint)

    def setup_tailscale_tab(self):
        v = QVBoxLayout(self.tab_tailscale)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)
        v.setAlignment(Qt.AlignCenter)

        state = self.info.get("tailscale_state", "")
        url = self.info.get("tailscale_url", "")

        if state == "Running" and url:
            pix = generate_qr_pixmap(url)
            qr_lbl = QLabel()
            qr_lbl.setPixmap(pix)
            qr_lbl.setAlignment(Qt.AlignCenter)
            v.addWidget(qr_lbl)

            url_lbl = QLabel(f"<b>URL Remota:</b> {url}")
            url_lbl.setStyleSheet("font-size: 13px; color: #38bdf8;")
            url_lbl.setAlignment(Qt.AlignCenter)
            url_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.addWidget(url_lbl)

            hint = QLabel("Usa esta opción si estás fuera de casa usando datos móviles o en otra red.")
            hint.setStyleSheet("font-size: 11px; color: #64748b;")
            hint.setAlignment(Qt.AlignCenter)
            v.addWidget(hint)
        else:
            status_lbl = QLabel(f"Estado de Tailscale: <b>{state}</b>")
            status_lbl.setStyleSheet("font-size: 14px; color: #f59e0b;")
            status_lbl.setAlignment(Qt.AlignCenter)
            v.addWidget(status_lbl)

            desc = QLabel("Tailscale no está conectado en esta PC. Puedes activarlo con el botón de abajo:")
            desc.setWordWrap(True)
            desc.setAlignment(Qt.AlignCenter)
            desc.setStyleSheet("font-size: 12px; color: #94a3b8;")
            v.addWidget(desc)

            btn_activate = QPushButton("Conectar Tailscale ahora")
            btn_activate.clicked.connect(self.activate_tailscale)
            v.addWidget(btn_activate, alignment=Qt.AlignCenter)

            self.ts_feedback = QLabel("")
            self.ts_feedback.setStyleSheet("font-size: 11px; color: #38bdf8;")
            self.ts_feedback.setAlignment(Qt.AlignCenter)
            v.addWidget(self.ts_feedback)

    def activate_tailscale(self):
        try:
            self.ts_feedback.setText("Conectando con Tailscale...")
            subprocess.run(["tailscale", "up", "--operator=" + os.environ.get("USER", "santiago")], capture_output=True, text=True, timeout=5)
            self.info = get_connection_info()
            # Recrear tab tailscale
            while self.tab_tailscale.layout().count():
                child = self.tab_tailscale.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            self.setup_tailscale_tab()
        except Exception as e:
            self.ts_feedback.setText(f"Error al conectar: {e}")

def show_qr_dialog():
    app = QApplication.instance()
    owns_app = False
    if not app:
        app = QApplication(sys.argv)
        owns_app = True
    dialog = TarsQRDialog()
    dialog.exec_()
    if owns_app:
        app.quit()

if __name__ == "__main__":
    show_qr_dialog()
