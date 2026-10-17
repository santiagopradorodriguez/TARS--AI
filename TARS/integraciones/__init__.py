"""
Modulo de integraciones externas para TARS AI.
Provee adaptadores modulares para Tuya (control de luces) y Amigos de la Heladera (almacenamiento y recetas).
Regla: Cero emojis.
"""

from .control_luces import ControlLucesTuya, procesar_intencion_luces
from .amigos_heladera import AmigosHeladera, procesar_intencion_heladera

__all__ = [
    "ControlLucesTuya",
    "procesar_intencion_luces",
    "AmigosHeladera",
    "procesar_intencion_heladera",
]
