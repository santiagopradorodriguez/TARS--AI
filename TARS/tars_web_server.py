#!/usr/bin/env python3
import re
import os
import sys
import json
import uuid
import time
import ssl
import socket
import wave
import subprocess
import asyncio
import urllib.request
from websockets.sync.client import connect
from aiohttp import web
import edge_tts
import vosk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
STATIC_DIR = os.path.join(WEB_DIR, "static")
MEDIA_DIR = os.path.join(WEB_DIR, "media")
CERTS_DIR = os.path.join(BASE_DIR, "certs")
CERT_FILE = os.path.join(CERTS_DIR, "cert.pem")
KEY_FILE = os.path.join(CERTS_DIR, "key.pem")

VOSK_MODEL_PATH = "/home/santiago/.gemini/models/vosk-model-small-es-0.42"
TTS_VOICE = "es-AR-ElenaNeural"

os.makedirs(MEDIA_DIR, exist_ok=True)

vosk.SetLogLevel(-1)
vosk_model = None
if os.path.exists(VOSK_MODEL_PATH):
    try:
        vosk_model = vosk.Model(VOSK_MODEL_PATH)
        print("[TARS Web] Modelo Vosk cargado exitosamente.")
    except Exception as e:
        print(f"[TARS Web] Error cargando Vosk: {e}")

def clean_latex_math(math_str):
    # Fracciones: \frac{a}{b} -> a sobre b
    math_str = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r" \1 sobre \2 ", math_str)
    # Raices: \sqrt{x} -> raiz de x
    math_str = re.sub(r"\\sqrt\{([^{}]+)\}", r" raíz de \1 ", math_str)
    # Modulo o valor absoluto |x|
    math_str = re.sub(r"\|([^|]+)\|", r" módulo de \1 ", math_str)
    # Operadores y comparadores
    math_str = re.sub(r"\\(?:approx)\b", " aproximadamente ", math_str)
    math_str = re.sub(r"\\(?:neq|ne)\b", " distinto de ", math_str)
    math_str = re.sub(r"\\(?:leq|le)\b", " menor o igual a ", math_str)
    math_str = re.sub(r"\\(?:geq|ge)\b", " mayor o igual a ", math_str)
    math_str = re.sub(r"\\times\b", " por ", math_str)
    math_str = re.sub(r"\\pm\b", " más o menos ", math_str)
    math_str = re.sub(r"\\cdot\b", " por ", math_str)
    math_str = re.sub(r"\\in\b", " en ", math_str)
    math_str = re.sub(r"\\max\b", " máximo ", math_str)
    math_str = re.sub(r"\\min\b", " mínimo ", math_str)
    math_str = re.sub(r"\\sum\b", " suma ", math_str)
    math_str = re.sub(r"\\int\b", " integral ", math_str)
    # Letras griegas
    math_str = re.sub(r"\\alpha\b", " alfa ", math_str)
    math_str = re.sub(r"\\beta\b", " beta ", math_str)
    math_str = re.sub(r"\\gamma\b", " gamma ", math_str)
    math_str = re.sub(r"\\delta\b", " delta ", math_str)
    math_str = re.sub(r"\\theta\b", " tita ", math_str)
    math_str = re.sub(r"\\mu\b", " micro ", math_str)
    math_str = re.sub(r"\\pi\b", " pi ", math_str)
    math_str = re.sub(r"\\sigma\b", " sigma ", math_str)
    math_str = re.sub(r"\\tau\b", " tau ", math_str)
    math_str = re.sub(r"\\omega\b", " omega ", math_str)
    # Envolturas comunes: \text{...}, \mathbf{...}, \tilde{...}
    math_str = re.sub(r"\\(?:text|mathbf|mathit|mathrm|mathcal|tilde|hat|bar)\{([^{}]*)\}", r" \1 ", math_str)
    # Potencias
    math_str = re.sub(r"\^\{2\}|\^2", " al cuadrado ", math_str)
    math_str = re.sub(r"\^\{3\}|\^3", " al cubo ", math_str)
    math_str = re.sub(r"\^\{([^{}]*)\}", r" elevado a la \1 ", math_str)
    math_str = re.sub(r"\^([0-9a-zA-Z])", r" elevado a la \1 ", math_str)
    # Subindices
    math_str = re.sub(r"_\{([^{}]*)\}", r" sub \1 ", math_str)
    math_str = re.sub(r"_([0-9a-zA-Z])", r" sub \1 ", math_str)
    # Igualdad y signos
    math_str = re.sub(r"=", " es igual a ", math_str)
    math_str = re.sub(r"\+", " más ", math_str)
    # Limpieza de sintaxis residual
    math_str = re.sub(r"\\(?:left|right|big|Big)\b", "", math_str)
    math_str = re.sub(r"\\[a-zA-Z]+", " ", math_str)
    math_str = re.sub(r"[{}\[\]()]", " ", math_str)
    math_str = math_str.replace("_", " ")
    return " " + math_str + " "


def clean_text_for_speech(text):
    if not text:
        return ""
    # 1. Bloques de codigo multilínea
    text = re.sub(r"```[\s\S]*?```", " [código en pantalla] ", text)
    # 2. Bloques display de formulas ($$...$$ o \[...\])
    def replace_display_math(m):
        inner = m.group(1).strip()
        if len(inner) > 60:
            return " [fórmula en pantalla] "
        return clean_latex_math(inner)
    text = re.sub(r"\$\$([\s\S]*?)\$\$", replace_display_math, text)
    text = re.sub(r"\\\[([\s\S]*?)\\\]", replace_display_math, text)
    # 3. Formulas inline: $...$ o \(...\)
    text = re.sub(r"\$([^\$\n]+)\$", lambda m: clean_latex_math(m.group(1)), text)
    text = re.sub(r"\\\((.*?)\\\)", lambda m: clean_latex_math(m.group(1)), text)
    # 4. Links y URLs
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[(.*?)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"file://\S+", "", text)

    # 5. Tratamiento fonético exhaustivo de BARRAS DIAGONALES (evitar 'barra diagonal')
    # 5.1 Fonemas o letras aisladas entre barras: /a/, /e/, /i/, /o/, /u/ -> vocal a, vocal e...
    text = re.sub(r"/([aeiouAEIOUÁÉÍÓÚ])/", r" vocal \1 ", text)
    # 5.2 Fonemas consonánticos o palabras entre barras: /pa/, /s/, /t/ -> pa, s, t
    text = re.sub(r"/([a-zA-ZáéíóúÁÉÍÓÚñÑ0-9]+)/", r" \1 ", text)
    # 5.3 Abreviaturas comunes con barra
    text = re.sub(r"\by/o\b", " y o ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bc/u\b", " cada uno ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bs/d\b", " sin datos ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bn/a\b", " no aplica ", text, flags=re.IGNORECASE)
    # 5.4 Fechas numéricas: 28/08/2026 o 28/08
    text = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", r" \1 de \2 de \3 ", text)
    text = re.sub(r"\b(\d{1,2})/(\d{1,2})\b", r" \1 del \2 ", text)
    # 5.5 Unidades comunes con barra
    text = re.sub(r"\bkm/h\b", " kilómetros por hora ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bm/s\b", " metros por segundo ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bbits/s\b", " bits por segundo ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmuestras/s(?:eg)?\b", " muestras por segundo ", text, flags=re.IGNORECASE)
    # 5.6 Rutas de archivos y carpetas: separar niveles y conservar nombres limpios
    text = re.sub(r'([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+\.[a-zA-Z0-9]+)', r'\1 \2', text)
    text = re.sub(r'/(?=[\w.-]+/)', ' ', text)
    # 5.7 Alternativas entre palabras (ej. PCA/UMAP -> PCA o UMAP)
    text = re.sub(r"([a-zA-ZáéíóúÁÉÍÓÚñÑ0-9]+)/([a-zA-ZáéíóúÁÉÍÓÚñÑ0-9]+)", r"\1 o \2", text)
    # 5.8 ELIMINACION TOTAL Y ABSOLUTA DE CUALQUIER BARRA DIAGONAL O INVERTIDA RESTANTE
    text = text.replace("/", " ")
    text = text.replace("\\", " ")

    # 6. Codigo inline entre backticks
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # 7. Tags HTML
    text = re.sub(r"<[^>]+>", "", text)
    # 8. Unidades de ingenieria y bioelectricas
    text = re.sub(r"\bkHz\b", " kilohertz ", text)
    text = re.sub(r"\bHz\b", " hertz ", text)
    text = re.sub(r"\bms\b", " milisegundos ", text)
    text = re.sub(r"\bseg\b", " segundos ", text)
    text = re.sub(r"\b(\d+)\s*s\b", r"\1 segundos ", text)
    text = re.sub(r"\buV\b|\bµV\b", " microvoltios ", text)
    # 9. Listas numeradas y viñetas
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[#]+\s*", "", text, flags=re.MULTILINE)
    # 10. ELIMINACION DEFINITIVA DE SIMBOLOS PROBLEMÁTICOS PARA TTS
    text = text.replace("$", " ")
    text = text.replace("_", " ")  # Nunca mas Edge-TTS pronunciando "guión bajo"
    text = re.sub(r"[*#~`><|\\^]", " ", text)
    text = re.sub(r"[{}[\]]", " ", text)
    # 11. Normalizar puntuacion (sin romper numeros decimales como 1.25)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"(?<!\d)\s*\.\s*|\s*\.\s*(?!\d)", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_conversational_speech(text):
    clean = clean_text_for_speech(text)
    if not clean:
        return ""
    if len(clean) <= 320:
        return clean

    # Sintesis concisa de las primeras 2 oraciones para no cansar al oido
    sentences = re.split(r'(?<=[.!?])\s+', clean)
    summary = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(summary) + len(s) < 300:
            summary = (summary + " " + s).strip()
        else:
            break

    if not summary:
        summary = clean[:250].rsplit(".", 1)[0] + "."

    if not summary.endswith(('.', '!', '?')):
        summary += "."

    return summary + " El detalle completo y código lo tenés en pantalla."


async def generate_tts_file(text):
    clean_text = extract_conversational_speech(text)
    if not clean_text:
        return None

    filename = f"reply_{uuid.uuid4().hex[:8]}.mp3"
    filepath = os.path.join(MEDIA_DIR, filename)
    try:
        comm = edge_tts.Communicate(clean_text, TTS_VOICE, rate="-4%")
        await comm.save(filepath)
        if os.path.exists(filepath):
            return f"/media/{filename}"
    except Exception as e:
        print(f"[TARS Web] Error en generacion de audio TTS: {e}")
    return None

def transcribe_wav(wav_path):
    if not vosk_model or not os.path.exists(wav_path):
        return ""
    try:
        wf = wave.open(wav_path, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
            wf.close()
            return ""
        rec = vosk.KaldiRecognizer(vosk_model, 16000)
        rec.SetWords(True)
        results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                if res.get("text"):
                    results.append(res["text"])
        final_res = json.loads(rec.FinalResult())
        if final_res.get("text"):
            results.append(final_res["text"])
        wf.close()
        return " ".join(results).strip()
    except Exception as e:
        print(f"[TARS Web] Error transcribiendo audio: {e}")
        return ""


def query_antigravity(prompt_text):
    print(f"[TARS Web] Consultando a Antigravity (rapido): {prompt_text}")
    try:
        cmd = [
            "/home/santiago/.local/bin/agy",
            "--model", "gemini-3.8-flash-low",
            "--effort", "low",
            "--mode", "accept-edits",
            "--dangerously-skip-permissions",
            "-p",
            f"El usuario te consulta desde su celular en la red local. Responde de forma concisa, en espanol rioplatense y directa (sin introducciones de relleno ni markdown excesivo). Si creas o buscas archivos, indica la ruta. Consulta: {prompt_text}"
        ]
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=45)
        return result.strip()
    except subprocess.TimeoutExpired:
        return "La consulta en Antigravity tomo demasiado tiempo. Intenta con algo mas puntual."
    except subprocess.CalledProcessError as e:
        return f"Error ejecutando en Antigravity: {e.output[:150]}"
    except Exception as e:
        return f"No pude conectar con el cerebro de Antigravity: {e}"


def get_devtools_ws_url():
    port_file = os.path.expanduser("~/.config/Antigravity/DevToolsActivePort")
    if not os.path.exists(port_file):
        return None
    try:
        with open(port_file, "r") as f:
            port = f.readline().strip()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/list")
        with urllib.request.urlopen(req, timeout=0.2) as resp:
            targets = json.loads(resp.read().decode())
            for t in targets:
                if t.get("type") == "page" and "127.0.0.1" in t.get("url", ""):
                    return t.get("webSocketDebuggerUrl")
    except Exception as e:
        print(f"[TARS Web] Error obteniendo DevTools WS: {e}")
    return None


def eval_in_antigravity(js_expr):
    ws_url = get_devtools_ws_url()
    if not ws_url:
        return None
    try:
        with connect(ws_url, open_timeout=0.3) as ws:
            req_id = int(time.time() * 1000) % 100000
            msg = {
                "id": req_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": js_expr,
                    "returnByValue": True
                }
            }
            ws.send(json.dumps(msg))
            res_str = ws.recv(timeout=0.5)
            res = json.loads(res_str)
            result = res.get("result", {}).get("result", {})
            return result.get("value")
    except Exception as e:
        print(f"[TARS Web] Error evaluando en Antigravity via CDP: {e}")
        return None


def get_current_antigravity_convo_id():
    js = "window.location.pathname.replace('/c/', '').split('?')[0]"
    val = eval_in_antigravity(js)
    if val and isinstance(val, str) and len(val) > 10:
        return val.strip()
    return None


def get_antigravity_chats():
    js = """
    (() => {
        const links = Array.from(document.querySelectorAll('a[href*="/c/"]'));
        const currentId = window.location.pathname.replace('/c/', '').split('?')[0];
        const seen = new Set();
        const chats = [];
        links.forEach(a => {
            const href = a.getAttribute('href');
            const match = href.match(/\\/c\\/([a-f0-9\\-]+)/);
            if (match && !seen.has(match[1])) {
                seen.add(match[1]);
                let title = a.getAttribute('aria-label') || a.innerText.trim().replace(/\\n+/g, ' ');
                if (!title && a.parentElement) {
                    title = a.parentElement.innerText.split('\\n')[0].trim();
                }
                if (!title) {
                    title = 'Conversacion ' + match[1].slice(0, 8);
                }
                chats.push({
                    id: match[1],
                    title: title,
                    active: match[1] === currentId
                });
            }
        });
        return { current_id: currentId, chats: chats };
    })()
    """
    res = eval_in_antigravity(js)
    if isinstance(res, dict):
        return res
    return {"current_id": "", "chats": []}


def switch_antigravity_chat(target):
    chats_data = get_antigravity_chats()
    chats = chats_data.get("chats", [])
    current_id = chats_data.get("current_id", "")

    if not chats:
        return {"success": False, "error": "No se encontraron chats disponibles en Antigravity"}

    target_id = None
    target_title = None

    if target == "siguiente":
        current_idx = 0
        for i, c in enumerate(chats):
            if c["id"] == current_id or c.get("active"):
                current_idx = i
                break
        next_idx = (current_idx + 1) % len(chats)
        target_id = chats[next_idx]["id"]
        target_title = chats[next_idx]["title"]

    elif target == "anterior":
        current_idx = 0
        for i, c in enumerate(chats):
            if c["id"] == current_id or c.get("active"):
                current_idx = i
                break
        prev_idx = (current_idx - 1) % len(chats)
        target_id = chats[prev_idx]["id"]
        target_title = chats[prev_idx]["title"]

    else:
        # 0. Si el target ya es un UUID directo
        import re
        if re.match(r'^[a-f0-9\-]{20,}$', target.strip()):
            target_id = target.strip()
            for c in chats:
                if c["id"] == target_id:
                    target_title = c["title"]
                    break

        # 1. Coincidencia exacta por ID en lista de chats
        if not target_id:
            for c in chats:
                if c["id"] == target:
                    target_id = c["id"]
                    target_title = c["title"]
                    break

        # 2. Coincidencia por subcadena en el titulo
        if not target_id:
            query = target.lower().strip()
            for c in chats:
                if query in c["title"].lower():
                    target_id = c["id"]
                    target_title = c["title"]
                    break

        # 3. Coincidencia aproximada de palabras
        if not target_id:
            query_words = target.lower().split()
            for c in chats:
                t_lower = c["title"].lower()
                if any(w in t_lower for w in query_words if len(w) > 3):
                    target_id = c["id"]
                    target_title = c["title"]
                    break

    if not target_id:
        return {"success": False, "error": f"No se encontro ningun chat con '{target}'"}

    # Ejecutar click en el enlace mediante CDP
    js_click = f"""
    (() => {{
        const targetId = "{target_id}";
        const link = document.querySelector('a[href*="/c/' + targetId + '"]');
        if (link) {{
            link.click();
            const title = link.getAttribute('aria-label') || link.innerText.trim().replace(/\\n+/g, ' ');
            return {{ success: true, id: targetId, title: title }};
        }}
        // Fallback: Si no esta en el sidebar visible, navegar directamente por pathname
        window.location.pathname = '/c/' + targetId;
        return {{ success: true, id: targetId, title: "{target_title or ''}" }};
    }})()
    """
    res = eval_in_antigravity(js_click)
    if isinstance(res, dict) and res.get("success"):
        return {"success": True, "id": target_id, "title": target_title or res.get("title")}

    return {"success": False, "error": res.get("error") if isinstance(res, dict) else "Error al cambiar chat"}


import threading
_ide_send_lock = threading.Lock()

def send_to_antigravity_ide(text, target_chat_id=None):
    ws_url = get_devtools_ws_url()
    if not ws_url:
        print("[TARS Web] DevTools WS no disponible para inyectar texto.")
        return False

    with _ide_send_lock:
        try:
            # 0. Si el usuario indico un chat especifico, asegurar que la ventana de Antigravity este en ese chat
            if target_chat_id:
                curr_id = get_current_antigravity_convo_id()
                if curr_id and curr_id != target_chat_id:
                    print(f"[TARS Web] Cambiando chat activo de Antigravity de {curr_id} a {target_chat_id}...")
                    switch_antigravity_chat(target_chat_id)
                    time.sleep(0.5)

            with connect(ws_url, open_timeout=3) as ws:
                # 1. Si Antigravity esta generando una respuesta (boton Stop visible), esperar a que termine (hasta 60s)
                busy_expr = """(() => {
                    const stop = document.querySelector('button[aria-label*="Stop"], button[aria-label*="stop"], button[aria-label*="Detener"], button[aria-label*="detener"]');
                    return Boolean(stop);
                })()"""
                for _ in range(240):  # 240 * 0.25s = 60s
                    ws.send(json.dumps({
                        "id": 99,
                        "method": "Runtime.evaluate",
                        "params": {"expression": busy_expr, "returnByValue": True}
                    }))
                    try:
                        res = json.loads(ws.recv(timeout=1))
                        is_busy = res.get("result", {}).get("result", {}).get("value")
                        if not is_busy:
                            break
                    except Exception:
                        break
                    time.sleep(0.25)

                # 2. Esperar de forma activa a que el input de Lexical este montado y enfocarlo (hasta 4s)
                focus_expr = """(() => {
                    const el = document.querySelector('[aria-label="Message input"]');
                    if (el) {
                        el.focus();
                        return true;
                    }
                    return false;
                })()"""
                focused = False
                for _ in range(40):
                    ws.send(json.dumps({
                        "id": 101,
                        "method": "Runtime.evaluate",
                        "params": {"expression": focus_expr, "returnByValue": True}
                    }))
                    try:
                        res = json.loads(ws.recv(timeout=1))
                        if res.get("result", {}).get("result", {}).get("value") is True:
                            focused = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.1)

                if not focused:
                    print("[TARS Web] Error: No se encontro el input de Antigravity para inyectar.")
                    return False

                # 3. Borrar cualquier texto residual (Ctrl+A -> Backspace)
                ws.send(json.dumps({"id": 102, "method": "Input.dispatchKeyEvent", "params": {"type": "keyDown", "modifiers": 2, "windowsVirtualKeyCode": 65, "key": "a", "code": "KeyA"}}))
                ws.recv(timeout=1)
                ws.send(json.dumps({"id": 103, "method": "Input.dispatchKeyEvent", "params": {"type": "keyUp", "modifiers": 2, "windowsVirtualKeyCode": 65, "key": "a", "code": "KeyA"}}))
                ws.recv(timeout=1)
                ws.send(json.dumps({"id": 104, "method": "Input.dispatchKeyEvent", "params": {"type": "keyDown", "windowsVirtualKeyCode": 8, "key": "Backspace", "code": "Backspace"}}))
                ws.recv(timeout=1)
                ws.send(json.dumps({"id": 105, "method": "Input.dispatchKeyEvent", "params": {"type": "keyUp", "windowsVirtualKeyCode": 8, "key": "Backspace", "code": "Backspace"}}))
                ws.recv(timeout=1)

                # 4. Insertar el texto a traves de CDP Input domain (nativo en el render de Chrome)
                ws.send(json.dumps({
                    "id": 106,
                    "method": "Input.insertText",
                    "params": {"text": text}
                }))
                ws.recv(timeout=1)

                # 5. Esperar de forma activa a que el boton de envio este habilitado y clickearlo (hasta 4s)
                click_expr = """(() => {
                    const btn = document.querySelector('button[aria-label="Send message"]');
                    if (btn && !btn.disabled) {
                        btn.click();
                        return true;
                    }
                    return false;
                })()"""
                clicked = False
                for _ in range(40):
                    time.sleep(0.1)
                    ws.send(json.dumps({
                        "id": 107,
                        "method": "Runtime.evaluate",
                        "params": {"expression": click_expr, "returnByValue": True}
                    }))
                    try:
                        res = json.loads(ws.recv(timeout=1))
                        if res.get("result", {}).get("result", {}).get("value") is True:
                            clicked = True
                            break
                    except Exception:
                        pass

                # Fallback por Enter si el boton no respondio pero esta el foco
                if not clicked:
                    ws.send(json.dumps({"id": 108, "method": "Input.dispatchKeyEvent", "params": {"type": "rawKeyDown", "windowsVirtualKeyCode": 13, "key": "Enter", "code": "Enter", "text": "\\r", "unmodifiedText": "\\r"}}))
                    ws.recv(timeout=1)
                    ws.send(json.dumps({"id": 109, "method": "Input.dispatchKeyEvent", "params": {"type": "keyUp", "windowsVirtualKeyCode": 13, "key": "Enter", "code": "Enter"}}))
                    ws.recv(timeout=1)
                    # Verificar si al apretar enter se envio
                    check_empty_expr = """(() => {
                        const el = document.querySelector('[aria-label="Message input"]');
                        return el ? (el.innerText.trim() === '') : false;
                    })()"""
                    ws.send(json.dumps({"id": 110, "method": "Runtime.evaluate", "params": {"expression": check_empty_expr, "returnByValue": True}}))
                    try:
                        res = json.loads(ws.recv(timeout=1))
                        if res.get("result", {}).get("result", {}).get("value") is True:
                            clicked = True
                    except Exception:
                        pass

                print(f"[TARS Web] Mensaje inyectado en Antigravity via CDP (clicked={clicked}): {text[:50]}")
                return clicked
        except Exception as e:
            print(f"[TARS Web] Error inyectando texto via CDP: {e}")
            return False


def execute_pc_task(command_text, target_chat_id=None):
    import re
    cmd_lower = command_text.lower().strip()
    cmd_clean = re.sub(r'[^a-z0-9 áéíóúñ]', '', cmd_lower)
    reply = ""
    media = []
    sent_to_ide = False

    # 0. Control y cambio de chats en Antigravity
    if "siguiente chat" in cmd_clean or "proximo chat" in cmd_lower or "avanzar chat" in cmd_lower or "otro chat" in cmd_lower:
        res = switch_antigravity_chat(target="siguiente")
        if res.get("success"):
            return f"Cambiado al chat: {res.get('title')}", media, sent_to_ide
        else:
            return f"No pude cambiar de chat: {res.get('error', 'desconocido')}", media, sent_to_ide

    if "chat anterior" in cmd_clean or "volver al chat" in cmd_lower or "retroceder chat" in cmd_lower:
        res = switch_antigravity_chat(target="anterior")
        if res.get("success"):
            return f"Cambiado al chat: {res.get('title')}", media, sent_to_ide
        else:
            return f"No pude cambiar de chat: {res.get('error', 'desconocido')}", media, sent_to_ide

    if "listar chats" in cmd_clean or "que chats hay" in cmd_lower or "cuales chats" in cmd_lower or "lista de chats" in cmd_lower or "mostrar chats" in cmd_lower:
        chats_info = get_antigravity_chats()
        chats = chats_info.get("chats", [])
        if not chats:
            return "No encontre chats abiertos en Antigravity.", media, sent_to_ide
        nombres = [f"- {c['title']}" + (" (activo)" if c.get('active') else "") for c in chats[:6]]
        total = len(chats)
        res_text = f"Hay {total} chats en la lista. Primeros:\n" + "\n".join(nombres)
        return res_text, media, sent_to_ide

    # Buscar comandos de cambio de chat en cualquier parte de la frase
    prefix_found = None
    for p in ["cambiar al chat de", "cambiar al chat", "cambiar a chat", "cambiar chat a", "cambiar chat de", "cambiar chat", "ir al chat de", "ir al chat", "abrir chat de", "abrir chat", "poner el chat de", "poner el chat", "cambiar a"]:
        if p in cmd_clean:
            prefix_found = p
            break
            
    if prefix_found:
        idx = cmd_clean.find(prefix_found)
        cleaned = cmd_clean[idx + len(prefix_found):].strip()
        # Limpiar si el usuario dijo "enviar" al final u otra cosa
        cleaned = cleaned.replace("enviar.", "").replace("enviar", "").strip()
        if not cleaned or cleaned == "de chat":
            res = switch_antigravity_chat(target="siguiente")
        else:
            res = switch_antigravity_chat(target=cleaned)
        if res.get("success"):
            return f"Cambiado al chat: {res.get('title')}", media, sent_to_ide
        else:
            return f"No encontre un chat que coincida con '{cleaned}'.", media, sent_to_ide

    # 1. Captura de pantalla
    if "captura" in cmd_lower or "pantalla" in cmd_lower or "screenshot" in cmd_lower:
        img_name = f"screen_{int(time.time())}.png"
        img_path = os.path.join(MEDIA_DIR, img_name)
        try:
            subprocess.run(["gnome-screenshot", "-f", img_path], check=True, timeout=5)
            if os.path.exists(img_path):
                reply = "He tomado una captura de pantalla de la computadora."
                media.append({"type": "image", "url": f"/media/{img_name}", "name": img_name})
            else:
                reply = "No se pudo generar la captura de pantalla."
        except Exception as e:
            reply = f"Error tomando captura: {e}"
        return reply, media, sent_to_ide

    # 2. Control de Spotify / Multimedia
    if "spotify" in cmd_lower or "musica" in cmd_lower:
        if "pausa" in cmd_lower or "parar" in cmd_lower or "pausar" in cmd_lower:
            subprocess.run(["playerctl", "pause"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Reproduccion de Spotify pausada.", media, sent_to_ide
        elif "play" in cmd_lower or "reanudar" in cmd_lower or "reproducir" in cmd_lower:
            subprocess.run(["playerctl", "play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Reproduciendo musica en Spotify.", media, sent_to_ide
        elif "siguiente" in cmd_lower or "pasar" in cmd_lower or "proxima" in cmd_lower:
            subprocess.run(["playerctl", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Pasando a la siguiente cancion.", media, sent_to_ide
        elif "anterior" in cmd_lower or "previa" in cmd_lower:
            subprocess.run(["playerctl", "previous"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Volviendo a la cancion anterior.", media, sent_to_ide
        else:
            try:
                title = subprocess.check_output(["playerctl", "metadata", "title"], text=True, timeout=2).strip()
                artist = subprocess.check_output(["playerctl", "metadata", "artist"], text=True, timeout=2).strip()
                return f"Sonando ahora: {title} de {artist}.", media, sent_to_ide
            except Exception:
                return "Spotify no parece estar reproduciendo contenido en este momento.", media, sent_to_ide

    # 3. Creacion de archivos / notas
    if "crea un archivo" in cmd_lower or "crear archivo" in cmd_lower or "guardar nota" in cmd_lower:
        filename = f"nota_{int(time.time())}.txt"
        filepath = os.path.join(MEDIA_DIR, filename)
        content = f"Nota creada remotamente desde el celular:\n\n{command_text}\nFecha: {time.ctime()}\n"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            reply = f"He creado el archivo {filename} en el sistema."
            media.append({"type": "file", "url": f"/media/{filename}", "name": filename})
        except Exception as e:
            reply = f"Error creando archivo: {e}"
        return reply, media

    # 4. Abrir aplicaciones o paginas
    if cmd_lower.startswith("abre ") or cmd_lower.startswith("abrir "):
        target = cmd_lower.replace("abre ", "").replace("abrir ", "").strip()
        if "firefox" in target or "navegador" in target:
            subprocess.Popen(["xdg-open", "https://google.com"])
            return "Abriendo el navegador Firefox en la PC.", media, sent_to_ide
        elif "youtube" in target:
            subprocess.Popen(["xdg-open", "https://youtube.com"])
            return "Abriendo YouTube en la PC.", media, sent_to_ide
        elif "terminal" in target:
            subprocess.Popen(["gnome-terminal"])
            return "Abriendo una terminal en la PC.", media, sent_to_ide
        else:
            subprocess.Popen(["xdg-open", target])
            return f"Lanzando {target} en la PC.", media, sent_to_ide

    # 5. Estado general de la maquina
    if "estado" in cmd_lower or "como estas" in cmd_lower:
        return "Todos los sistemas de TARS estan en linea. Puedo controlar Spotify, tomar capturas de pantalla, crear archivos y abrir programas.", media, sent_to_ide

    # 6. Para todo lo demas: Inyectar directamente a esta ventana activa de Antigravity IDE
    if send_to_antigravity_ide(command_text, target_chat_id=target_chat_id):
        sent_to_ide = True
        return "Mensaje enviado a Antigravity en la computadora.", media, sent_to_ide

    # Fallback si Antigravity IDE no esta abierto en el escritorio
    ai_reply = query_antigravity(command_text)
    import re
    img_matches = re.findall(r'(/[\w\-./]+\.(?:png|jpg|jpeg|gif))', ai_reply)
    for img_path in img_matches:
        if os.path.exists(img_path):
            img_name = os.path.basename(img_path)
            dest = os.path.join(MEDIA_DIR, img_name)
            if not os.path.exists(dest):
                subprocess.run(["cp", img_path, dest])
            media.append({"type": "image", "url": f"/media/{img_name}", "name": img_name})

    return ai_reply, media, sent_to_ide

# Handlers HTTP
async def handle_index(request):
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_path):
        return web.FileResponse(index_path)
    return web.Response(text="Interfaz de TARS no encontrada", status=404)

async def handle_chat(request):
    try:
        data = await request.json()
        user_text = data.get("text", "").strip()
        client_chat_id = data.get("chat_id")
        if not user_text:
            return web.json_response({"reply": "No recibi ningun texto."})

        reply_text, media, sent_to_ide = await asyncio.to_thread(execute_pc_task, user_text, client_chat_id)
        if sent_to_ide:
            return web.json_response({
                "sent_to_ide": True,
                "user_text": user_text
            })

        audio_url = await generate_tts_file(reply_text)
        return web.json_response({
            "reply": reply_text,
            "media": media,
            "audio_url": audio_url
        })
    except Exception as e:
        return web.json_response({"reply": f"Error interno: {e}"}, status=500)

async def handle_audio(request):
    try:
        reader = await request.multipart()
        client_chat_id = None
        temp_id = uuid.uuid4().hex[:8]
        raw_path = f"/tmp/upload_{temp_id}.raw"
        wav_path = f"/tmp/upload_{temp_id}.wav"

        while True:
            field = await reader.next()
            if not field:
                break
            if field.name == "audio":
                with open(raw_path, "wb") as f:
                    while True:
                        chunk = await field.read_chunk()
                        if not chunk:
                            break
                        f.write(chunk)
            elif field.name == "chat_id":
                val = await field.read()
                client_chat_id = val.decode().strip()

        if not os.path.exists(raw_path):
            return web.json_response({"reply": "No se envio ningun archivo de audio."}, status=400)

        # Convertir a WAV 16kHz mono con ffmpeg
        await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-y", "-i", raw_path, "-ar", "16000", "-ac", "1", wav_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )

        user_text = await asyncio.to_thread(transcribe_wav, wav_path)
        try:
            os.remove(raw_path)
            os.remove(wav_path)
        except Exception:
            pass

        if not user_text:
            user_text = "[Audio no reconocido con claridad]"
            reply_text = "No pude entender con claridad el audio. Intenta hablar mas cerca del microfono."
            media = []
            audio_url = await generate_tts_file(reply_text)
            return web.json_response({
                "user_text": user_text,
                "reply": reply_text,
                "media": media,
                "audio_url": audio_url
            })
        else:
            reply_text, media, sent_to_ide = await asyncio.to_thread(execute_pc_task, user_text, client_chat_id)
            if sent_to_ide:
                return web.json_response({
                    "sent_to_ide": True,
                    "user_text": user_text
                })

            audio_url = await generate_tts_file(reply_text)
            return web.json_response({
                "user_text": user_text,
                "reply": reply_text,
                "media": media,
                "audio_url": audio_url
            })
    except Exception as e:
        print(f"[TARS Web] Error en endpoint de audio: {e}")
        return web.json_response({"reply": f"Error procesando audio: {e}"}, status=500)


def get_active_transcript_path():
    brain_dir = os.path.expanduser("~/.gemini/antigravity/brain")
    if not os.path.exists(brain_dir):
        return ""
    # 1. Intentar obtener el ID exacto del chat activo via CDP
    try:
        active_id = get_current_antigravity_convo_id()
        if active_id:
            p = os.path.join(brain_dir, active_id, ".system_generated", "logs", "transcript.jsonl")
            if os.path.exists(p):
                return p
    except Exception as e:
        print(f"[TARS Web] Error leyendo id activo via CDP: {e}")

    # 2. Fallback: buscar por mtime
    latest_time = 0
    latest_path = ""
    try:
        for convo in os.listdir(brain_dir):
            p = os.path.join(brain_dir, convo, ".system_generated", "logs", "transcript.jsonl")
            if os.path.exists(p):
                mtime = os.path.getmtime(p)
                if mtime > latest_time:
                    latest_time = mtime
                    latest_path = p
    except Exception as e:
        print(f"[TARS Web] Error buscando transcript activo por mtime: {e}")
    return latest_path


def get_latest_transcript_message():
    latest_msg = ""
    latest_idx = 0
    proc_info = {
        "is_processing": False,
        "thought": "",
        "tool_name": "",
        "tool_action": "",
        "tool_detail": "",
        "step_index": 0
    }
    transcript_path = get_active_transcript_path()
    if transcript_path and os.path.exists(transcript_path):
        try:
            with open(transcript_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                read_size = min(size, 1048576)
                f.seek(size - read_size)
                chunk = f.read(read_size).decode("utf-8", errors="ignore")
                lines = chunk.splitlines()
                if read_size < size and len(lines) > 1:
                    lines = lines[1:]
                for line in lines:
                    try:
                        d = json.loads(line)
                        if d.get("type") == "PLANNER_RESPONSE" and d.get("source") == "MODEL":
                            idx = d.get("step_index", 0)
                            if d.get("content"):
                                latest_msg = d.get("content")
                                latest_idx = idx
                                proc_info["is_processing"] = False
                            else:
                                proc_info["is_processing"] = True
                                proc_info["step_index"] = idx

                                # Extraer pensamiento
                                raw_thinking = d.get("thinking", "").strip()
                                if raw_thinking:
                                    lines_think = [l.strip() for l in raw_thinking.splitlines() if l.strip()]
                                    proc_info["thought"] = lines_think[-1] if lines_think else raw_thinking[:220]
                                else:
                                    proc_info["thought"] = "Razonando..."

                                # Extraer llamadas a herramientas
                                tool_calls = d.get("tool_calls", [])
                                if tool_calls:
                                    last_tool = tool_calls[-1]
                                    t_name = last_tool.get("name", "")
                                    args = last_tool.get("args", {})
                                    proc_info["tool_name"] = t_name
                                    act = args.get("toolAction") or args.get("toolSummary") or t_name
                                    proc_info["tool_action"] = str(act).replace('"', "").replace("'", "")
                                    detail = args.get("CommandLine") or args.get("TargetFile") or args.get("Query") or ""
                                    if detail:
                                        detail = str(detail).replace('"', "").replace("'", "")
                                        if len(detail) > 130:
                                            detail = detail[:130] + "..."
                                    proc_info["tool_detail"] = detail
                                else:
                                    proc_info["tool_name"] = ""
                                    proc_info["tool_action"] = "Pensando..."
                                    proc_info["tool_detail"] = ""
                    except Exception:
                        pass
        except Exception as e:
            print(f"[TARS Web] Error leyendo transcript: {e}")
    return latest_idx, latest_msg, proc_info


async def handle_sync(request):
    last_idx = int(request.query.get("last_index", 0))
    client_chat_id = request.query.get("chat_id", "").strip()
    media = []

    active_id = await asyncio.to_thread(get_current_antigravity_convo_id) or ""
    chat_changed = bool(client_chat_id and active_id and client_chat_id != active_id)

    latest_idx, latest_msg, proc_info = await asyncio.to_thread(get_latest_transcript_message)

    if chat_changed or (latest_idx > last_idx and latest_msg):
        # Extraer imagenes si las hay
        img_matches = re.findall(r'(/[\w\-./]+\.(?:png|jpg|jpeg|gif))', latest_msg)
        for img_path in img_matches:
            if os.path.exists(img_path):
                img_name = os.path.basename(img_path)
                dest = os.path.join(MEDIA_DIR, img_name)
                if not os.path.exists(dest):
                    subprocess.run(["cp", img_path, dest])
                media.append({"type": "image", "url": f"/media/{img_name}", "name": img_name})

        # Generar TTS solo si no fue cambio de chat
        audio_url = None
        if not chat_changed and latest_msg:
            audio_url = await generate_tts_file(latest_msg)

        return web.json_response({
            "has_new": True,
            "step_index": latest_idx,
            "content": latest_msg,
            "media": media,
            "audio_url": audio_url,
            "chat_id": active_id,
            "chat_changed": chat_changed,
            "processing_info": proc_info,
            "processing_status": proc_info.get("tool_action", "") if proc_info.get("is_processing") else "",
            "pc_audio_muted": get_pc_sound_muted()
        })

    return web.json_response({
        "has_new": False,
        "step_index": latest_idx,
        "chat_id": active_id,
        "chat_changed": False,
        "processing_info": proc_info,
        "processing_status": proc_info.get("tool_action", "") if proc_info.get("is_processing") else "",
        "pc_audio_muted": get_pc_sound_muted()
    })

TARS_STATE_FILE = "/home/santiago/.gemini/config/tars_state.json"

def get_pc_sound_muted():
    try:
        if os.path.exists(TARS_STATE_FILE):
            with open(TARS_STATE_FILE, "r") as f:
                data = json.load(f)
                return bool(data.get("pc_audio_muted", False))
    except Exception:
        pass
    return False

def set_pc_sound_muted(muted):
    try:
        data = {}
        if os.path.exists(TARS_STATE_FILE):
            with open(TARS_STATE_FILE, "r") as f:
                data = json.load(f)
        data["pc_audio_muted"] = bool(muted)
        with open(TARS_STATE_FILE, "w") as f:
            json.dump(data, f)
        if muted:
            subprocess.run(["pkill", "-9", "-f", "ffplay.*antigravity_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-9", "-f", "tars_player.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-9", "-f", "paplay.*antigravity_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"[TARS Web] Error guardando estado sonido PC: {e}")
        return False

async def handle_toggle_pc_sound(request):
    try:
        curr = get_pc_sound_muted()
        new_state = not curr
        await asyncio.to_thread(set_pc_sound_muted, new_state)
        return web.json_response({"success": True, "pc_audio_muted": new_state})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_get_chats(request):
    chats_data = await asyncio.to_thread(get_antigravity_chats)
    return web.json_response(chats_data)

async def handle_switch_chat(request):
    try:
        data = await request.json()
        target = data.get("target") or data.get("id") or data.get("direction") or ""
        if not target:
            return web.json_response({"success": False, "error": "Debe indicar objetivo o direccion"}, status=400)

        result = await asyncio.to_thread(switch_antigravity_chat, target)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_manifest(request):
    manifest_path = os.path.join(WEB_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        return web.FileResponse(manifest_path, headers={"Content-Type": "application/json"})
    return web.Response(text="Manifest no encontrado", status=404)

def init_app():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/manifest.json", handle_manifest)
    app.router.add_get("/api/chats", handle_get_chats)
    app.router.add_post("/api/switch_chat", handle_switch_chat)
    app.router.add_post("/api/toggle_pc_sound", handle_toggle_pc_sound)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/audio", handle_audio)
    app.router.add_get("/api/sync", handle_sync)
    app.router.add_static("/static/", STATIC_DIR)
    app.router.add_static("/media/", MEDIA_DIR)
    return app


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.254.254.254", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def get_tailscale_ip():
    try:
        res = subprocess.check_output(["tailscale", "ip", "-4"], text=True, timeout=2).strip()
        if res:
            return res.split()[0]
    except Exception:
        pass
    return None

def ensure_ssl_certificates(local_ip, tailscale_ip=None):
    os.makedirs(CERTS_DIR, exist_ok=True)
    needs_gen = not (os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE))
    if not needs_gen:
        try:
            out = subprocess.check_output(["openssl", "x509", "-text", "-noout", "-in", CERT_FILE], text=True)
            if f"IP Address:{local_ip}" not in out and f"IP:{local_ip}" not in out:
                needs_gen = True
            if tailscale_ip and f"IP Address:{tailscale_ip}" not in out:
                needs_gen = True
        except Exception:
            needs_gen = True

    if needs_gen:
        san_parts = [
            "DNS:pop-os.local",
            "DNS:localhost",
            "IP:127.0.0.1",
            f"IP:{local_ip}"
        ]
        if tailscale_ip:
            san_parts.append(f"IP:{tailscale_ip}")
            san_parts.append("DNS:pop-os")

        san = "subjectAltName=" + ",".join(san_parts)
        cmd = [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", KEY_FILE, "-out", CERT_FILE,
            "-days", "3650", "-nodes",
            "-subj", f"/CN={local_ip}",
            "-addext", san
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            print(f"[TARS Web] Certificado SSL generado con exito para IP {local_ip}")
        except Exception as e:
            print(f"[TARS Web] Error generando certificado SSL: {e}")

def main():
    port = 8443
    host = "0.0.0.0"
    app = init_app()

    local_ip = get_local_ip()
    ts_ip = get_tailscale_ip()
    ensure_ssl_certificates(local_ip, ts_ip)

    ssl_context = None
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(CERT_FILE, KEY_FILE)
        print(f"[TARS Web] SSL habilitado. Servidor listo en:")
        print(f"           - https://{local_ip}:{port}")
        print(f"           - https://pop-os.local:{port}")
        if ts_ip:
            print(f"           - https://{ts_ip}:{port} (Remoto Tailscale)")
        
        # Notificacion visual en Pop!_OS para saber la direccion de un vistazo
        try:
            msg = f"https://{local_ip}:{port}\no https://pop-os.local:{port}"
            subprocess.Popen(["notify-send", "TARS Móvil Listo", msg, "-t", "8000"])
        except Exception:
            pass
    else:
        print(f"[TARS Web] Servidor listo (sin SSL) en: http://{local_ip}:{port}")

    web.run_app(app, host=host, port=port, ssl_context=ssl_context)

if __name__ == "__main__":
    main()
