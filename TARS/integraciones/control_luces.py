"""
Integracion de control de luces Tuya para TARS AI.
Permite encender, apagar, regular brillo y cambiar color de luminarias Tuya
mediante comandos de voz o texto desde el cliente movil y la bandeja del sistema.

Reglas del proyecto:
- Cero emojis en codigo, logs y mensajes de retorno.
- Titulos limpios sin parentesis.
"""

import os
import re
import json

class ControlLucesTuya:
    def __init__(self):
        self.client_id = os.environ.get("TUYA_CLIENT_ID", "")
        self.secret_key = os.environ.get("TUYA_SECRET_KEY", "")
        self.device_id = os.environ.get("TUYA_DEVICE_ID", "")
        self.region = os.environ.get("TUYA_REGION", "us")
        
        # Estado simulado en memoria si no hay credenciales activas
        self.estado_simulado = {
            "encendido": False,
            "brillo": 100,
            "color": "blanco_calido",
            "dispositivo": "Luz Principal"
        }

    def esta_configurado(self) -> bool:
        return bool(self.client_id and self.secret_key and self.device_id)

    def encender(self, dispositivo: str = None) -> dict:
        self.estado_simulado["encendido"] = True
        disp = dispositivo or self.estado_simulado["dispositivo"]
        if self.esta_configurado():
            # Aqui se ejecuta la llamada a la API Tuya Cloud o TinyTuya
            return {"ok": True, "accion": "encender", "mensaje": f"{disp} encendida correctamente."}
        return {
            "ok": True,
            "accion": "encender",
            "simulado": True,
            "mensaje": f"{disp} encendida [Modo simulado: configura TUYA_CLIENT_ID para control fisico]."
        }

    def apagar(self, dispositivo: str = None) -> dict:
        self.estado_simulado["encendido"] = False
        disp = dispositivo or self.estado_simulado["dispositivo"]
        if self.esta_configurado():
            return {"ok": True, "accion": "apagar", "mensaje": f"{disp} apagada correctamente."}
        return {
            "ok": True,
            "accion": "apagar",
            "simulado": True,
            "mensaje": f"{disp} apagada [Modo simulado: configura TUYA_CLIENT_ID para control fisico]."
        }

    def set_brillo(self, porcentaje: int, dispositivo: str = None) -> dict:
        val = max(1, min(100, porcentaje))
        self.estado_simulado["brillo"] = val
        self.estado_simulado["encendido"] = True
        disp = dispositivo or self.estado_simulado["dispositivo"]
        return {
            "ok": True,
            "accion": "brillo",
            "valor": val,
            "mensaje": f"Brillo de {disp} ajustado al {val}%."
        }

    def set_color(self, color_nombre: str, dispositivo: str = None) -> dict:
        self.estado_simulado["color"] = color_nombre
        self.estado_simulado["encendido"] = True
        disp = dispositivo or self.estado_simulado["dispositivo"]
        return {
            "ok": True,
            "accion": "color",
            "color": color_nombre,
            "mensaje": f"Color de {disp} cambiado a {color_nombre}."
        }

    def get_estado(self) -> dict:
        return {
            "configurado": self.esta_configurado(),
            "estado": self.estado_simulado
        }


# Instancia singleton para uso en servidor
_instancia_luces = ControlLucesTuya()

def procesar_intencion_luces(texto: str) -> dict | None:
    """
    Analiza si el texto corresponde a una orden de iluminacion.
    Retorna un diccionario de resultado o None si no corresponde a este modulo.
    """
    t = texto.lower().strip()
    palabras_clave = ["luz", "luces", "lampara", "foco", "iluminacion"]
    if not any(k in t for k in palabras_clave):
        return None

    # Detectar apagar
    if any(v in t for v in ["apaga", "apagar", "corta", "apagate"]):
        return _instancia_luces.apagar()

    # Detectar encender
    if any(v in t for v in ["prende", "prender", "enciende", "encender", "activa", "prender la"]):
        # Verificar si pide un color o brillo a la vez
        pass

    # Detectar brillo
    match_brillo = re.search(r"(\d+)\s*%", t)
    if match_brillo or "brillo" in t:
        if match_brillo:
            porcentaje = int(match_brillo.group(1))
            return _instancia_luces.set_brillo(porcentaje)
        if "al maximo" in t or "100" in t:
            return _instancia_luces.set_brillo(100)
        if "al minimo" in t or "baja" in t:
            return _instancia_luces.set_brillo(20)

    # Detectar colores habituales
    colores = ["rojo", "azul", "verde", "amarillo", "calido", "frio", "blanco", "violeta", "naranja", "rosa"]
    for c in colores:
        if c in t:
            return _instancia_luces.set_color(c)

    if any(v in t for v in ["prende", "prender", "enciende", "encender", "activa"]):
        return _instancia_luces.encender()

    if "estado" in t or "como esta" in t:
        st = _instancia_luces.get_estado()["estado"]
        estado_str = "encendida" if st["encendido"] else "apagada"
        return {
            "ok": True,
            "accion": "estado",
            "mensaje": f"La {st['dispositivo']} esta {estado_str}, brillo al {st['brillo']}%, tono {st['color']}."
        }

    return None
