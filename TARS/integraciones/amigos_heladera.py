"""
Integracion con Amigos de la Heladera para TARS AI.
Permite gestionar el inventario de alimentos, consultar que hay disponible,
recibir sugerencias de recetas segun ingredientes y registrar altas/bajas.

Reglas del proyecto:
- Cero emojis en codigo, logs y respuestas.
- Titulos limpios sin parentesis.
"""

import os
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "tars"
HELADERA_DB_PATH = CONFIG_DIR / "amigos_heladera.json"

DEFAULT_INVENTARIO = {
    "items": [
        {"nombre": "huevos", "cantidad": "6 unidades", "categoria": "proteinas"},
        {"nombre": "leche", "cantidad": "1 litro", "categoria": "lacteos"},
        {"nombre": "queso", "cantidad": "250 gramos", "categoria": "lacteos"},
        {"nombre": "tomates", "cantidad": "3 unidades", "categoria": "verduras"},
        {"nombre": "cebolla", "cantidad": "2 unidades", "categoria": "verduras"},
        {"nombre": "arroz", "cantidad": "500 gramos", "categoria": "despensa"}
    ],
    "recetas_sugeridas": [
        {
            "nombre": "Omelette de queso y tomate",
            "ingredientes": ["huevos", "queso", "tomates"],
            "tiempo": "10 minutos"
        },
        {
            "nombre": "Arroz salteado con cebolla y huevo",
            "ingredientes": ["arroz", "cebolla", "huevos"],
            "tiempo": "15 minutos"
        }
    ]
}

class AmigosHeladera:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path = HELADERA_DB_PATH
        self._cargar_datos()

    def _cargar_datos(self):
        if not self.db_path.exists():
            self.datos = DEFAULT_INVENTARIO.copy()
            self._guardar_datos()
        else:
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    self.datos = json.load(f)
            except Exception:
                self.datos = DEFAULT_INVENTARIO.copy()

    def _guardar_datos(self):
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self.datos, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def listar_inventario(self) -> dict:
        self._cargar_datos()
        items = self.datos.get("items", [])
        if not items:
            return {"ok": True, "mensaje": "La heladera esta vacia o no tiene alimentos registrados."}
        resumen = ", ".join([f"{it['nombre']} ({it.get('cantidad', '1')})" for it in items])
        return {
            "ok": True,
            "items": items,
            "mensaje": f"En la heladera tenes: {resumen}."
        }

    def sugerir_recetas(self) -> dict:
        self._cargar_datos()
        recetas = self.datos.get("recetas_sugeridas", [])
        items_nombres = [it["nombre"].lower() for it in self.datos.get("items", [])]
        viables = []
        for r in recetas:
            match = all(any(req in disp for disp in items_nombres) for req in r["ingredientes"])
            if match:
                viables.append(r)
        if viables:
            desc = " y ".join([f"{v['nombre']} ({v['tiempo']})" for v in viables])
            return {"ok": True, "recetas": viables, "mensaje": f"Con lo que tenes podes cocinar: {desc}."}
        return {
            "ok": True,
            "mensaje": "No hay recetas coincidentes directas, pero tenes suficientes ingredientes para improvisar."
        }

    def agregar_item(self, nombre: str, cantidad: str = "1 unidad") -> dict:
        self._cargar_datos()
        n = nombre.strip().lower()
        items = self.datos.setdefault("items", [])
        for it in items:
            if it["nombre"].lower() == n:
                it["cantidad"] = cantidad
                self._guardar_datos()
                return {"ok": True, "mensaje": f"Actualizada cantidad de {n} a {cantidad}."}
        items.append({"nombre": n, "cantidad": cantidad, "categoria": "general"})
        self._guardar_datos()
        return {"ok": True, "mensaje": f"Agregado {n} ({cantidad}) a la heladera."}

    def quitar_item(self, nombre: str) -> dict:
        self._cargar_datos()
        n = nombre.strip().lower()
        items = self.datos.get("items", [])
        nuevos = [it for it in items if it["nombre"].lower() != n]
        if len(nuevos) < len(items):
            self.datos["items"] = nuevos
            self._guardar_datos()
            return {"ok": True, "mensaje": f"Removido {n} de la heladera."}
        return {"ok": False, "mensaje": f"No se encontro {n} en el inventario."}


_instancia_heladera = AmigosHeladera()

def procesar_intencion_heladera(texto: str) -> dict | None:
    """
    Analiza si el texto corresponde a una consulta de Amigos de la Heladera.
    Retorna un diccionario con resultado o None si no corresponde a este modulo.
    """
    t = texto.lower().strip()
    palabras_clave = ["heladera", "heladera?", "refrigerador", "cocinar con lo que hay", "que hay para comer", "que puedo cocinar"]
    if not any(k in t for k in palabras_clave):
        return None

    # Detectar recetas
    if any(k in t for k in ["receta", "cocinar", "que cocino", "que como", "plato"]):
        return _instancia_heladera.sugerir_recetas()

    # Detectar agregar
    if "agrega" in t or "agregar" in t or "guardar" in t:
        partes = t.split(" a la heladera")[0]
        item = partes.replace("agrega", "").replace("agregar", "").replace("guarda", "").replace("guardar", "").strip()
        if item:
            return _instancia_heladera.agregar_item(item)

    # Detectar quitar / consumido
    if "quita" in t or "quitar" in t or "saque" in t or "termine" in t:
        partes = t.split(" de la heladera")[0]
        item = partes.replace("quita", "").replace("quitar", "").replace("saque", "").replace("termine", "").strip()
        if item:
            return _instancia_heladera.quitar_item(item)

    # Por defecto, listar inventario
    return _instancia_heladera.listar_inventario()
