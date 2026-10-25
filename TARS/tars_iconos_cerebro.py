#!/usr/bin/env python3
"""
Genera los iconos del selector de cerebro del tray.

Mismo estilo que create_icons.py: circulo de 64x64 con borde suave y una
letra blanca adentro (O para OpenCode, A para Antigravity). Se corre una vez
y deja los PNG en la carpeta de este modulo:

    python3 tars_iconos_cerebro.py
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

COLORES = {
    "opencode": ((52, 152, 219, 255), "O"),
    "antigravity": ((155, 89, 182, 255), "A"),
}

NOMBRES = {
    "opencode": "tars_cerebro_opencode.png",
    "antigravity": "tars_cerebro_antigravity.png",
}

FUENTES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _fuente(tamano):
    from PIL import ImageFont
    for ruta in FUENTES:
        if os.path.exists(ruta):
            try:
                return ImageFont.truetype(ruta, tamano)
            except Exception:
                continue
    return ImageFont.load_default()


def generar_icono(ruta, color, letra):
    from PIL import Image, ImageDraw

    tamano = 64
    imagen = Image.new("RGBA", (tamano, tamano), (255, 255, 255, 0))
    dibujo = ImageDraw.Draw(imagen)

    margen = 2
    caja = [margen, margen, tamano - margen, tamano - margen]
    dibujo.ellipse(caja, fill=color, outline=(0, 0, 0, 100), width=1)

    fuente = _fuente(34)
    ancho, alto = dibujo.textbbox((0, 0), letra, font=fuente)[2:]
    x = (tamano - ancho) // 2
    y = (tamano - alto) // 2 - 2
    dibujo.text((x, y), letra, font=fuente, fill=(255, 255, 255, 255))

    imagen.save(ruta)
    return ruta


def asegurar_iconos(directorio=None):
    """Genera los PNG si no existen y devuelve sus rutas por cerebro."""
    destino = os.path.expanduser(directorio) if directorio else BASE_DIR
    rutas = {}
    for clave, nombre in NOMBRES.items():
        ruta = os.path.join(destino, nombre)
        if not os.path.exists(ruta):
            try:
                generar_icono(ruta, COLORES[clave][0], COLORES[clave][1])
            except Exception as exc:
                print(f"[TARS] No pude generar {nombre}: {exc}", file=sys.stderr)
                continue
        rutas[clave] = ruta
    return rutas


if __name__ == "__main__":
    for clave, ruta in sorted(asegurar_iconos().items()):
        print(f"[TARS] Icono {clave}: {ruta}")
