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
try:
    from email.utils import parsedate_to_datetime as _parsedate_to_datetime
    from datetime import timezone as _tz
    from edge_tts import constants as _etts_const, communicate as _etts_comm, drm as _etts_drm
    import aiohttp as _aiohttp
    _NEW_WSS_URL = (
        "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
        f"?Ocp-Apim-Subscription-Key={_etts_const.TRUSTED_CLIENT_TOKEN}"
    )
    _etts_const.WSS_URL = _NEW_WSS_URL
    _etts_comm.WSS_URL = _NEW_WSS_URL
    def _safe_parse_rfc2616_date(date_str):
        try:
            p = _parsedate_to_datetime(date_str)
            return (p.replace(tzinfo=_tz.utc) if p.tzinfo is None else p).timestamp()
        except Exception:
            return None
    _etts_drm.DRM.parse_rfc2616_date = staticmethod(_safe_parse_rfc2616_date)

    async def _patched_stream(self):
        if self.state["stream_was_called"]:
            raise RuntimeError("stream can only be called once.")
        self.state["stream_was_called"] = True

        for self.state["partial_text"] in self.texts:
            self.state["chunk_audio_bytes"] = 0
            try:
                async for message in self._Communicate__stream():
                    yield message
            except _aiohttp.ClientResponseError as e:
                if e.status not in (403, 429):
                    raise
                _etts_drm.DRM.handle_client_response_error(e)
                self.state["chunk_audio_bytes"] = 0
                async for message in self._Communicate__stream():
                    yield message

    _etts_comm.Communicate.stream = _patched_stream
except Exception as _e:
    print(f"[TARS Web] Warning aplicando patch edge_tts: {_e}")
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


TTS_CACHE = {}
TTS_LOCK = None

async def generate_tts_file(text):
    global TTS_LOCK
    if TTS_LOCK is None:
        TTS_LOCK = asyncio.Lock()
    clean_text = extract_conversational_speech(text)
    if not clean_text:
        return None

    async with TTS_LOCK:
        cached_url = TTS_CACHE.get(clean_text)
        if cached_url:
            cached_path = os.path.join(MEDIA_DIR, os.path.basename(cached_url))
            if os.path.exists(cached_path):
                return cached_url

        filename = f"reply_{uuid.uuid4().hex[:8]}.mp3"
        filepath = os.path.join(MEDIA_DIR, filename)
        try:
            comm = edge_tts.Communicate(clean_text, TTS_VOICE, rate="-4%")
            await comm.save(filepath)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                url = f"/media/{filename}"
                TTS_CACHE[clean_text] = url
                return url
        except Exception as e:
            print(f"[TARS Web] Error en generacion de audio TTS (edge-tts): {e}, usando fallback...")
            try:
                import urllib.parse
                def _gtts_fallback():
                    short_q = clean_text[:200]
                    g_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=es&client=tw-ob&q={urllib.parse.quote(short_q)}"
                    req = urllib.request.Request(g_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=4.0) as r:
                        with open(filepath, "wb") as f:
                            f.write(r.read())
                await asyncio.to_thread(_gtts_fallback)
                if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                    url = f"/media/{filename}"
                    TTS_CACHE[clean_text] = url
                    return url
            except Exception as e2:
                print(f"[TARS Web] Fallback TTS tambien fallo: {e2}")
                TTS_CACHE[clean_text] = None
    return None

def transcribe_wav(wav_path):
    if not os.path.exists(wav_path):
        return ""
    # 1. Intentar primero reconocimiento de alta precision en español rioplatense (es-AR)
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data, language="es-AR")
        if text and text.strip():
            return text.strip()
    except Exception as e:
        print(f"[TARS Web] Fallback a Vosk offline ({e})")

    # 2. Fallback offline con Vosk
    if not vosk_model:
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
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            targets = json.loads(resp.read().decode())
            page_targets = [t for t in targets if t.get("type") == "page"]
            for t in page_targets:
                url = t.get("url", "")
                title = t.get("title", "")
                if "127.0.0.1" in url or "localhost" in url or "/c/" in url or "antigravity" in url.lower() or "Antigravity" in title:
                    return t.get("webSocketDebuggerUrl")
            if page_targets:
                return page_targets[0].get("webSocketDebuggerUrl")
    except Exception as e:
        print(f"[TARS Web] Error obteniendo DevTools WS: {e}")
    return None


def eval_in_antigravity(js_expr):
    ws_url = get_devtools_ws_url()
    if not ws_url:
        return None
    try:
        with connect(ws_url, open_timeout=2.0) as ws:
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
            res_str = ws.recv(timeout=2.5)
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


def get_chats_from_disk():
    """Fallback y complemento: busca todas las conversaciones guardadas en ~/.gemini/antigravity/brain."""
    brain_dir = os.path.expanduser("~/.gemini/antigravity/brain")
    if not os.path.exists(brain_dir):
        return []

    chats = []
    try:
        for convo_id in os.listdir(brain_dir):
            if convo_id.startswith(".") or convo_id == "tempmediaStorage":
                continue
            transcript_path = os.path.join(brain_dir, convo_id, ".system_generated", "logs", "transcript.jsonl")
            if not os.path.exists(transcript_path):
                continue

            mtime = os.path.getmtime(transcript_path)
            title = f"Chat {convo_id[:8]}"
            try:
                with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        try:
                            step = json.loads(line)
                            if step.get("type") == "USER_INPUT" and step.get("source") == "USER_EXPLICIT":
                                content = step.get("content", "")
                                match = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, re.DOTALL)
                                prompt_text = match.group(1).strip() if match else content.strip()
                                if prompt_text:
                                    first_line = prompt_text.split("\n")[0].strip()
                                    if first_line:
                                        title = first_line[:45]
                                        break
                        except Exception:
                            pass
            except Exception:
                pass
            chats.append({"id": convo_id, "title": title, "mtime": mtime})

        chats.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    except Exception as e:
        print(f"[TARS Web] Error leyendo chats de disco: {e}")

    return chats


def get_antigravity_chats():
    cdp_res = None
    try:
        js = """
        (() => {
            const currentId = window.location.pathname.replace('/c/', '').split('?')[0];
            const seen = new Set();
            const chats = [];

            // 1. Antigravity nuevo: convo-pill
            const pills = Array.from(document.querySelectorAll('[data-testid^="convo-pill-"]'));
            pills.forEach(p => {
                const id = (p.getAttribute('data-testid') || '').replace('convo-pill-', '').trim();
                if (id && !seen.has(id)) {
                    seen.add(id);
                    const title = p.innerText.trim() || ('Conversacion ' + id.slice(0, 8));
                    chats.push({
                        id: id,
                        title: title,
                        active: id === currentId
                    });
                }
            });

            // 2. Fallback: enlaces a[href*="/c/"]
            if (chats.length === 0) {
                const links = Array.from(document.querySelectorAll('a[href*="/c/"]'));
                links.forEach(a => {
                    const href = a.getAttribute('href') || '';
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
            }

            return { current_id: currentId, chats: chats };
        })()
        """
        cdp_res = eval_in_antigravity(js)
    except Exception as e:
        print(f"[TARS Web] Error en get_antigravity_chats CDP: {e}")

    current_id = ""
    dom_chats = []
    if isinstance(cdp_res, dict):
        current_id = cdp_res.get("current_id", "") or ""
        dom_chats = cdp_res.get("chats", []) or []

    disk_chats = get_chats_from_disk()

    if not current_id and disk_chats:
        current_id = disk_chats[0]["id"]

    seen_ids = set()
    merged_chats = []

    for c in dom_chats:
        cid = c.get("id")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            merged_chats.append({
                "id": cid,
                "title": c.get("title") or f"Chat {cid[:8]}",
                "active": cid == current_id
            })

    for c in disk_chats:
        cid = c.get("id")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            merged_chats.append({
                "id": cid,
                "title": c.get("title") or f"Chat {cid[:8]}",
                "active": cid == current_id
            })

    return {"current_id": current_id, "chats": merged_chats}


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
        const pill = document.querySelector('[data-testid="convo-pill-' + targetId + '"]');
        if (pill) {{
            const btn = pill.closest('[role="button"]') || pill;
            btn.click();
            const title = pill.innerText.trim() || targetId;
            return {{ success: true, id: targetId, title: title }};
        }}
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
LAST_CANCEL_TIMESTAMP = 0.0

def cdp_call(ws, req_id, method, params=None, timeout=1.5):
    msg = {"id": req_id, "method": method}
    if params:
        msg["params"] = params
    ws.send(json.dumps(msg))
    end_t = time.time() + timeout
    while time.time() < end_t:
        try:
            r = json.loads(ws.recv(timeout=0.5))
            if r.get("id") == req_id:
                return r
        except Exception:
            pass
    return {}

def cancel_antigravity_ide():
    global LAST_CANCEL_TIMESTAMP
    LAST_CANCEL_TIMESTAMP = time.time()
    # Detener también cualquier voz TTS que esté sonando en la PC
    try:
        subprocess.run(["pkill", "-9", "-f", "ffplay.*antigravity_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "-f", "tars_player.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "-f", "paplay.*antigravity_response"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    ws_url = get_devtools_ws_url()
    if not ws_url:
        return {"success": False, "error": "No se encontró conexión CDP con Antigravity"}

    try:
        with connect(ws_url, open_timeout=2.5) as ws:
            try:
                ws.send(json.dumps({"id": 900, "method": "Page.bringToFront"}))
                ws.recv(timeout=0.4)
            except Exception:
                pass
            try:
                ws.send(json.dumps({"id": 901, "method": "Emulation.setFocusEmulationEnabled", "params": {"enabled": True}}))
                ws.recv(timeout=0.4)
            except Exception:
                pass

            cancel_js = """(() => {
                const selectors = [
                    '[data-tooltip-id="input-send-button-cancel-tooltip"]',
                    'button[aria-label*="Cancel"]',
                    'button[aria-label="Stop execution"]',
                    'button[aria-label*="Stop"]',
                    'button[aria-label*="stop"]',
                    'button[aria-label*="Detener"]'
                ];
                let clicked = false;
                for (const sel of selectors) {
                    const btns = Array.from(document.querySelectorAll(sel));
                    for (const btn of btns) {
                        const r = btn.getBoundingClientRect();
                        if (!btn.disabled && r.width > 0 && r.height > 0) {
                            btn.click();
                            clicked = true;
                        }
                    }
                    if (clicked) break;
                }
                const ed = document.querySelector('[aria-label="Message input"]');
                if (ed && ed.innerText.trim().length > 0) {
                    ed.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('delete', false, null);
                }
                return clicked;
            })()"""

            stopped = False
            for attempt in range(8):
                ws.send(json.dumps({
                    "id": 910 + attempt,
                    "method": "Runtime.evaluate",
                    "params": {"expression": cancel_js, "returnByValue": True}
                }))
                try:
                    res = json.loads(ws.recv(timeout=0.8))
                    if res.get("result", {}).get("result", {}).get("value") is True:
                        stopped = True
                        break
                except Exception:
                    pass
                time.sleep(0.15)

            if not stopped:
                # Fallback: enviar atajo nativo Ctrl+D (Cancel en Antigravity IDE)
                ws.send(json.dumps({"id": 930, "method": "Input.dispatchKeyEvent", "params": {"type": "keyDown", "modifiers": 2, "windowsVirtualKeyCode": 68, "key": "d", "code": "KeyD"}}))
                try:
                    ws.recv(timeout=0.4)
                except Exception:
                    pass
                ws.send(json.dumps({"id": 931, "method": "Input.dispatchKeyEvent", "params": {"type": "keyUp", "modifiers": 2, "windowsVirtualKeyCode": 68, "key": "d", "code": "KeyD"}}))
                try:
                    ws.recv(timeout=0.4)
                except Exception:
                    pass

            print(f"[TARS Web] Procesamiento cancelado en Antigravity IDE (stopped_btn={stopped})")
            return {"success": True, "stopped": stopped}
    except Exception as e:
        print(f"[TARS Web] Error cancelando en Antigravity via CDP: {e}")
        return {"success": False, "error": str(e)}


def send_to_antigravity_ide(text, target_chat_id=None, file_paths=None):
    send_start_ts = time.time()
    if send_start_ts - LAST_CANCEL_TIMESTAMP < 1.5:
        print("[TARS Web] Inyección abortada antes de iniciar por cancelación reciente.")
        return False

    ws_url = get_devtools_ws_url()
    if not ws_url:
        print("[TARS Web] DevTools WS no disponible para inyectar texto.")
        return False

    with _ide_send_lock:
        if time.time() - LAST_CANCEL_TIMESTAMP < 2.0 or LAST_CANCEL_TIMESTAMP >= send_start_ts:
            print("[TARS Web] Inyección abortada al tomar lock por cancelación del usuario.")
            return False
        try:
            # 0. Si el usuario indico un chat especifico, asegurar que la ventana de Antigravity este en ese chat
            if target_chat_id:
                curr_id = get_current_antigravity_convo_id()
                if curr_id and curr_id != target_chat_id:
                    print(f"[TARS Web] Cambiando chat activo de Antigravity de {curr_id} a {target_chat_id}...")
                    switch_antigravity_chat(target_chat_id)
                    time.sleep(0.5)

            with connect(ws_url, open_timeout=3) as ws:
                # 0.5 Forzar foco emulado en Chromium para que funcione aunque la ventana este en segundo plano o pantalla apagada
                try:
                    ws.send(json.dumps({"id": 90, "method": "Page.bringToFront"}))
                    ws.recv(timeout=0.5)
                except Exception:
                    pass
                try:
                    ws.send(json.dumps({"id": 91, "method": "Emulation.setFocusEmulationEnabled", "params": {"enabled": True}}))
                    ws.recv(timeout=0.5)
                except Exception:
                    pass

                # 0.8 Si hay archivos adjuntos (imagenes, pdf, docs, codigo), inyectarlos mediante DOM.setFileInputFiles
                if file_paths and len(file_paths) > 0:
                    try:
                        valid_files = [os.path.abspath(f) for f in file_paths if os.path.exists(f)]
                        if valid_files:
                            r_eval = cdp_call(ws, 95, "Runtime.evaluate", {"expression": "document.querySelector('input[type=file]')"})
                            obj_id = r_eval.get("result", {}).get("result", {}).get("objectId")
                            if obj_id:
                                cdp_call(ws, 96, "DOM.setFileInputFiles", {"files": valid_files, "objectId": obj_id})
                                time.sleep(0.4)
                                print(f"[TARS Web] Adjuntos inyectados a Antigravity ({len(valid_files)} archivos): {valid_files}")
                    except Exception as e_file:
                        print(f"[TARS Web] Error adjuntando archivos via CDP: {e_file}")

                # 1. Si Antigravity esta generando una respuesta (boton Stop/Cancel visible), esperar a que termine (hasta 60s)
                busy_expr = """(() => {
                    const stop = document.querySelector('[data-tooltip-id="input-send-button-cancel-tooltip"], button[aria-label*="Cancel"], button[aria-label*="Stop"], button[aria-label*="stop"], button[aria-label*="Detener"]');
                    return Boolean(stop);
                })()"""
                for _ in range(240):  # 240 * 0.25s = 60s
                    if LAST_CANCEL_TIMESTAMP >= send_start_ts:
                        return False
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
                    if LAST_CANCEL_TIMESTAMP >= send_start_ts:
                        return False
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

                # Si el usuario solo envio archivos sin texto, poner un prompt descriptivo por defecto
                prompt_to_send = text.strip() if (text and text.strip()) else "Por favor analizá los archivos / imágenes adjuntos."

                # 3. Borrar cualquier texto residual (Ctrl+A -> Backspace)
                ws.send(json.dumps({"id": 102, "method": "Input.dispatchKeyEvent", "params": {"type": "keyDown", "modifiers": 2, "windowsVirtualKeyCode": 65, "key": "a", "code": "KeyA"}}))
                ws.recv(timeout=1)
                ws.send(json.dumps({"id": 103, "method": "Input.dispatchKeyEvent", "params": {"type": "keyUp", "modifiers": 2, "windowsVirtualKeyCode": 65, "key": "a", "code": "KeyA"}}))
                ws.recv(timeout=1)
                ws.send(json.dumps({"id": 104, "method": "Input.dispatchKeyEvent", "params": {"type": "keyDown", "windowsVirtualKeyCode": 8, "key": "Backspace", "code": "Backspace"}}))
                ws.recv(timeout=1)
                ws.send(json.dumps({"id": 105, "method": "Input.dispatchKeyEvent", "params": {"type": "keyUp", "windowsVirtualKeyCode": 8, "key": "Backspace", "code": "Backspace"}}))
                ws.recv(timeout=1)

                if LAST_CANCEL_TIMESTAMP >= send_start_ts:
                    return False

                # 4. Insertar el texto a traves de CDP Input domain (nativo en el render de Chrome)
                ws.send(json.dumps({
                    "id": 106,
                    "method": "Input.insertText",
                    "params": {"text": prompt_to_send}
                }))
                ws.recv(timeout=1)

                # 4.5 Verificar que el texto haya entrado en Lexical; si no, inyectar con execCommand('insertText')
                verify_insert_expr = f"""(() => {{
                    const el = document.querySelector('[aria-label="Message input"]');
                    if (!el) return false;
                    if (el.innerText.trim().length === 0) {{
                        el.focus();
                        document.execCommand('insertText', false, {json.dumps(text)});
                    }}
                    return el.innerText.trim().length > 0;
                }})()"""
                ws.send(json.dumps({
                    "id": 1065,
                    "method": "Runtime.evaluate",
                    "params": {"expression": verify_insert_expr, "returnByValue": True}
                }))
                try:
                    ws.recv(timeout=1)
                except Exception:
                    pass

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
                    if LAST_CANCEL_TIMESTAMP >= send_start_ts:
                        return False
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

                # Fallback por Enter si el boton no respondio pero el texto estaba en el input
                if not clicked and LAST_CANCEL_TIMESTAMP < send_start_ts:
                    ws.send(json.dumps({"id": 108, "method": "Input.dispatchKeyEvent", "params": {"type": "rawKeyDown", "windowsVirtualKeyCode": 13, "key": "Enter", "code": "Enter", "text": "\\r", "unmodifiedText": "\\r"}}))
                    ws.recv(timeout=1)
                    ws.send(json.dumps({"id": 109, "method": "Input.dispatchKeyEvent", "params": {"type": "keyUp", "windowsVirtualKeyCode": 13, "key": "Enter", "code": "Enter"}}))
                    ws.recv(timeout=1)
                    time.sleep(0.15)
                    check_empty_expr = """(() => {
                        const stop = document.querySelector('button[aria-label*="Cancel"], button[aria-label*="Stop"], button[aria-label*="stop"]');
                        return Boolean(stop);
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


UPLOADS_DIR = os.path.expanduser("~/.gemini/antigravity/scratch/TARS_uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

def execute_pc_task(command_text, target_chat_id=None, file_paths=None):
    import re
    cmd_lower = command_text.lower().strip()
    cmd_clean = re.sub(r'[^a-z0-9 áéíóúñ]', '', cmd_lower)
    reply = ""
    media = []
    sent_to_ide = False

    # Si hay archivos adjuntos, enviarlos prioritariamente a Antigravity IDE
    if file_paths and len(file_paths) > 0:
        if send_to_antigravity_ide(command_text, target_chat_id=target_chat_id, file_paths=file_paths):
            sent_to_ide = True
            return "Archivos inyectados en Antigravity IDE.", media, sent_to_ide

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

    # 1. Captura de pantalla (solo si es una orden explícita)
    screenshot_triggers = [
        "sacar captura", "saca captura", "tomar captura", "toma captura",
        "captura de pantalla", "screenshot", "hacer screenshot", "sacale captura"
    ]
    if any(st in cmd_clean for st in screenshot_triggers):
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

    # 2. Control de Spotify / Multimedia (solo si son órdenes directas de reproducción)
    is_music_cmd = False
    if any(kw in cmd_clean for kw in ["pausa la musica", "pausar musica", "pausa musica", "pausar spotify", "pausa spotify", "parar musica", "parar spotify"]):
        subprocess.run(["playerctl", "pause"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Reproduccion de Spotify pausada.", media, sent_to_ide
    elif any(kw in cmd_clean for kw in ["pone musica", "poner musica", "play musica", "reproducir musica", "reproduce musica", "reanudar musica", "play spotify", "pone spotify", "poner spotify"]):
        subprocess.run(["playerctl", "play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Reproduciendo musica en Spotify.", media, sent_to_ide
    elif any(kw in cmd_clean for kw in ["siguiente cancion", "proxima cancion", "pasar cancion", "cambiar cancion", "pasar de cancion", "tema siguiente", "proximo tema"]):
        subprocess.run(["playerctl", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Pasando a la siguiente cancion.", media, sent_to_ide
    elif any(kw in cmd_clean for kw in ["cancion anterior", "anterior cancion", "volver a la cancion", "tema anterior"]):
        subprocess.run(["playerctl", "previous"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Volviendo a la cancion anterior.", media, sent_to_ide
    elif any(kw in cmd_clean for kw in ["que cancion suena", "que cancion es", "que cancion esta sonando", "que tema suena", "que tema esta sonando", "que suena"]):
        try:
            title = subprocess.check_output(["playerctl", "metadata", "title"], text=True, timeout=2).strip()
            artist = subprocess.check_output(["playerctl", "metadata", "artist"], text=True, timeout=2).strip()
            return f"Sonando ahora: {title} de {artist}.", media, sent_to_ide
        except Exception:
            return "Spotify no parece estar reproduciendo contenido en este momento.", media, sent_to_ide

    # 3. Creacion de archivos / notas (solo ordenes explicitas)
    if cmd_clean.startswith("crea un archivo de texto") or cmd_clean.startswith("crear archivo de texto") or cmd_clean.startswith("guardar nota rapida"):
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

    # 4. Abrir aplicaciones o paginas explicitas
    if cmd_clean in ["abrir firefox", "abre firefox", "abrir navegador", "abre el navegador"]:
        subprocess.Popen(["xdg-open", "https://google.com"])
        return "Abriendo el navegador Firefox en la PC.", media, sent_to_ide
    elif cmd_clean in ["abrir youtube", "abre youtube"]:
        subprocess.Popen(["xdg-open", "https://youtube.com"])
        return "Abriendo YouTube en la PC.", media, sent_to_ide
    elif cmd_clean in ["abrir terminal", "abre terminal", "abrir una terminal", "abre la terminal"]:
        subprocess.Popen(["gnome-terminal"])
        return "Abriendo una terminal en la PC.", media, sent_to_ide

    # 5. Estado general de TARS o suspension programada hasta las 8 AM
    if cmd_clean in ["como estas", "estado del sistema", "estado de tars", "reporte de estado"]:
        return "Todos los sistemas de TARS estan en linea y conectados a Antigravity.", media, sent_to_ide
    elif any(kw in cmd_clean for kw in ["suspender hasta las 8", "dormir hasta las 8", "descansar hasta las 8", "suspender pc hasta las 8", "apagar hasta las 8"]):
        script_path = os.path.join(BASE_DIR, "dormir_hasta_las_8.sh")
        subprocess.Popen(["bash", "-c", f"sleep 4 && bash '{script_path}' 08:00"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Perfecto. En 4 segundos la PC entrará en suspensión y volverá a encenderse sola a las 8 de la mañana con Antigravity listo. ¡Buenas noches!", media, sent_to_ide

    # 6. Para todo lo demas: Inyectar directamente a esta ventana activa de Antigravity IDE
    if send_to_antigravity_ide(command_text, target_chat_id=target_chat_id, file_paths=file_paths):
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
        user_text = ""
        client_chat_id = None
        file_paths = []

        if request.content_type.startswith("multipart/"):
            reader = await request.multipart()
            while True:
                part = await reader.next()
                if not part:
                    break
                if part.name == "text":
                    user_text = (await part.read()).decode("utf-8", errors="ignore").strip()
                elif part.name == "chat_id":
                    client_chat_id = (await part.read()).decode("utf-8", errors="ignore").strip()
                elif part.name == "files":
                    orig_filename = part.filename or f"upload_{int(time.time())}.dat"
                    clean_name = re.sub(r'[^\w\-.]', '_', orig_filename)
                    saved_name = f"{int(time.time())}_{clean_name}"
                    dest = os.path.join(UPLOADS_DIR, saved_name)
                    with open(dest, "wb") as f:
                        while True:
                            chunk = await part.read_chunk()
                            if not chunk:
                                break
                            f.write(chunk)
                    file_paths.append(dest)
        else:
            data = await request.json()
            user_text = data.get("text", "").strip()
            client_chat_id = data.get("chat_id")

        if not user_text and not file_paths:
            return web.json_response({"reply": "No recibi ningun texto ni archivo."})

        if is_remote_pc_active():
            rem_ip = get_active_pc_ip()
            prompt_to_send = user_text if user_text else "Por favor analizá los archivos adjuntos."
            rem_res = await asyncio.to_thread(
                remote_api_request,
                rem_ip,
                "/api/chat",
                method="POST",
                json_body={"text": prompt_to_send, "chat_id": client_chat_id}
            )
            if isinstance(rem_res, dict):
                if rem_res.get("audio_url"):
                    await asyncio.to_thread(ensure_remote_media_cached, rem_ip, rem_res["audio_url"])
                for m in (rem_res.get("media") or []):
                    if isinstance(m, dict) and m.get("url"):
                        await asyncio.to_thread(ensure_remote_media_cached, rem_ip, m["url"])
                return web.json_response(rem_res)

        reply_text, media, sent_to_ide = await asyncio.to_thread(
            execute_pc_task,
            user_text,
            target_chat_id=client_chat_id,
            file_paths=file_paths
        )
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
    req_start = time.time()
    try:
        reader = await request.multipart()
        client_chat_id = None
        file_paths = []
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
            elif field.name == "files":
                orig_filename = field.filename or f"upload_{int(time.time())}.dat"
                clean_name = re.sub(r'[^\w\-.]', '_', orig_filename)
                saved_name = f"{int(time.time())}_{clean_name}"
                dest = os.path.join(UPLOADS_DIR, saved_name)
                with open(dest, "wb") as f:
                    while True:
                        chunk = await field.read_chunk()
                        if not chunk:
                            break
                        f.write(chunk)
                file_paths.append(dest)

        if not os.path.exists(raw_path):
            return web.json_response({"reply": "No se envio ningun archivo de audio."}, status=400)

        if LAST_CANCEL_TIMESTAMP >= req_start:
            try:
                os.remove(raw_path)
            except Exception:
                pass
            return web.json_response({"cancelled": True, "reply": "Envío cancelado."})

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

        if LAST_CANCEL_TIMESTAMP >= req_start:
            return web.json_response({
                "cancelled": True,
                "user_text": user_text or "[Cancelado]",
                "reply": "🛑 Procesamiento cancelado antes de enviar."
            })

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
            if is_remote_pc_active():
                rem_ip = get_active_pc_ip()
                rem_res = await asyncio.to_thread(
                    remote_api_request,
                    rem_ip,
                    "/api/chat",
                    method="POST",
                    json_body={"text": user_text, "chat_id": client_chat_id}
                )
                if isinstance(rem_res, dict):
                    if rem_res.get("audio_url"):
                        await asyncio.to_thread(ensure_remote_media_cached, rem_ip, rem_res["audio_url"])
                    for m in (rem_res.get("media") or []):
                        if isinstance(m, dict) and m.get("url"):
                            await asyncio.to_thread(ensure_remote_media_cached, rem_ip, m["url"])
                    rem_res["user_text"] = user_text
                    return web.json_response(rem_res)

            reply_text, media, sent_to_ide = await asyncio.to_thread(
                execute_pc_task,
                user_text,
                target_chat_id=client_chat_id,
                file_paths=file_paths
            )
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


def format_spanish_tool_action(t_name, args):
    target_file = str(args.get("TargetFile") or args.get("AbsolutePath") or "").replace('"', "").replace("'", "")
    base_file = os.path.basename(target_file) if target_file else ""
    cmd_line = str(args.get("CommandLine") or "").replace('"', "").replace("'", "").strip()

    if t_name == "view_file":
        return f"📖 Leyendo {base_file}" if base_file else "📖 Leyendo archivo del proyecto"
    elif t_name in ("replace_file_content", "multi_replace_file_content"):
        return f"✏️ Editando {base_file}" if base_file else "✏️ Editando código"
    elif t_name == "write_to_file":
        return f"📝 Creando/actualizando {base_file}" if base_file else "📝 Escribiendo archivo"
    elif t_name == "run_command":
        short_cmd = cmd_line.split("&&")[0].strip()[:42] if cmd_line else "comando"
        return f"💻 Ejecutando: {short_cmd}"
    elif t_name == "list_dir":
        return "📂 Listando archivos del directorio"
    elif t_name in ("grep_search", "find_by_name"):
        return "🔍 Buscando en el código"
    elif t_name in ("search_web", "read_url_content"):
        return "🌐 Consultando información en la web"
    act = str(args.get("toolAction") or args.get("toolSummary") or t_name).replace('"', "").replace("'", "")
    return f"⚙️ {act}" if act else "⚙️ Ejecutando herramienta"


def get_latest_transcript_message():
    latest_msg = ""
    latest_idx = 0
    proc_info = {
        "is_processing": False,
        "thought": "",
        "tool_name": "",
        "tool_action": "",
        "tool_detail": "",
        "step_index": 0,
        "steps_count": 0,
        "recent_steps": [],
        "generated_files": []
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
                        if d.get("type") == "USER_INPUT":
                            proc_info["steps_count"] = 0
                            proc_info["recent_steps"] = []
                            proc_info["generated_files"] = []
                            continue
                        status_val = str(d.get("status", "")).upper()
                        if status_val in ("CANCELED", "CANCELLED", "ERROR"):
                            proc_info["is_processing"] = False
                            continue
                        if d.get("type") == "PLANNER_RESPONSE" and d.get("source") == "MODEL":
                            idx = d.get("step_index", 0)
                            tool_calls = d.get("tool_calls", [])
                            if tool_calls:
                                for tc in tool_calls:
                                    tc_name = tc.get("name", "")
                                    tc_args = tc.get("args", {}) or {}
                                    if tc_name in ("write_to_file", "replace_file_content", "multi_replace_file_content"):
                                        tf = str(tc_args.get("TargetFile") or tc_args.get("AbsolutePath") or "").strip()
                                        if tf and tf not in proc_info["generated_files"]:
                                            proc_info["generated_files"].append(tf)
                            if d.get("content") and not tool_calls:
                                latest_msg = d.get("content")
                                latest_idx = idx
                                proc_info["is_processing"] = False
                            else:
                                proc_info["is_processing"] = True
                                proc_info["step_index"] = idx
                                proc_info["steps_count"] = proc_info.get("steps_count", 0) + 1

                                # Extraer llamadas a herramientas y formatear en español claro
                                if tool_calls:
                                    last_tool = tool_calls[-1]
                                    t_name = last_tool.get("name", "")
                                    args = last_tool.get("args", {})
                                    proc_info["tool_name"] = t_name
                                    spanish_act = format_spanish_tool_action(t_name, args)
                                    proc_info["tool_action"] = spanish_act
                                    raw_act = str(args.get("toolAction") or args.get("toolSummary") or "").replace('"', "").replace("'", "")
                                    proc_info["thought"] = raw_act if raw_act else spanish_act
                                    detail = args.get("CommandLine") or args.get("TargetFile") or args.get("AbsolutePath") or args.get("Query") or ""
                                    if detail:
                                        detail = str(detail).replace('"', "").replace("'", "")
                                        if len(detail) > 130:
                                            detail = detail[:130] + "..."
                                    proc_info["tool_detail"] = detail
                                    if not proc_info["recent_steps"] or proc_info["recent_steps"][-1] != spanish_act:
                                        proc_info["recent_steps"].append(spanish_act)
                                        if len(proc_info["recent_steps"]) > 5:
                                            proc_info["recent_steps"] = proc_info["recent_steps"][-5:]
                                else:
                                    proc_info["tool_name"] = ""
                                    proc_info["tool_action"] = "🧠 Analizando y planificando respuesta..."
                                    proc_info["thought"] = "Analizando los próximos pasos..."
                                    proc_info["tool_detail"] = ""
                    except Exception:
                        pass
            if proc_info["is_processing"]:
                try:
                    if LAST_CANCEL_TIMESTAMP >= os.path.getmtime(transcript_path):
                        proc_info["is_processing"] = False
                except Exception:
                    pass
        except Exception as e:
            print(f"[TARS Web] Error leyendo transcript: {e}")
    return latest_idx, latest_msg, proc_info


_REMOTE_PROC_TRACKER = {}

def enrich_remote_sync_data(rem_ip, rem_data):
    if not isinstance(rem_data, dict):
        return rem_data
    p_info = rem_data.get("processing_info") or {}
    is_proc = bool(p_info.get("is_processing"))

    # Regla estricta: NUNCA mandar mensajes ni notificaciones intermedias mientras está procesando
    if is_proc and not rem_data.get("chat_changed"):
        rem_data["has_new"] = False
        rem_data.pop("content", None)
        rem_data.pop("audio_url", None)

    if is_proc:
        tracker = _REMOTE_PROC_TRACKER.setdefault(rem_ip, {"last_step": 0, "steps_count": 0, "recent_steps": []})
        t_name = p_info.get("tool_name", "")
        raw_act = p_info.get("tool_action", "")
        if "recent_steps" not in p_info:
            sp_act = format_spanish_tool_action(t_name, {"toolAction": raw_act, "CommandLine": p_info.get("tool_detail", ""), "TargetFile": p_info.get("tool_detail", "")})
            p_info["tool_action"] = sp_act
            step_idx = p_info.get("step_index", 0)
            if step_idx != tracker["last_step"]:
                tracker["last_step"] = step_idx
                tracker["steps_count"] += 1
            if not tracker["recent_steps"] or tracker["recent_steps"][-1] != sp_act:
                tracker["recent_steps"].append(sp_act)
                if len(tracker["recent_steps"]) > 5:
                    tracker["recent_steps"] = tracker["recent_steps"][-5:]
            p_info["steps_count"] = max(1, tracker["steps_count"])
            p_info["recent_steps"] = list(tracker["recent_steps"])
            rem_data["processing_info"] = p_info
            rem_data["processing_status"] = sp_act
    else:
        _REMOTE_PROC_TRACKER.pop(rem_ip, None)

    # Si la respuesta remota tiene enlaces file:///..., agregarlos a media si no están ya
    if rem_data.get("content") and not is_proc:
        import urllib.parse
        rem_media = list(rem_data.get("media") or [])
        existing_names = {m.get("name") for m in rem_media if isinstance(m, dict)}
        for m_link in re.findall(r'file://(/[^\)\s#"<>`]+)', rem_data["content"]):
            clean_p = urllib.parse.unquote(m_link).split("#")[0].strip()
            fname = os.path.basename(clean_p)
            if fname and fname not in existing_names:
                existing_names.add(fname)
                rem_media.append({
                    "type": "file",
                    "url": f"/api/download?path={urllib.parse.quote(clean_p)}",
                    "name": fname
                })
        rem_data["media"] = rem_media

    rem_data["mobile_voice_muted"] = get_mobile_voice_muted()
    rem_data["active_pc"] = get_active_pc_info()
    return rem_data


def collect_turn_media_and_files(latest_msg, proc_info):
    import urllib.parse
    media = []
    seen_paths = set()
    candidates = []

    # 1. Archivos creados o modificados durante el turno por herramientas de Antigravity
    for gf in (proc_info.get("generated_files") or []):
        if gf:
            candidates.append(gf)

    # 2. Links file:///... dentro del mensaje Markdown
    if latest_msg:
        for m in re.findall(r'file://(/[^\)\s#"<>`]+)', latest_msg):
            candidates.append(urllib.parse.unquote(m))
        # 3. Rutas absolutas directas mencionadas en el mensaje
        for m in re.findall(r'((?:/home|/tmp|/var|/opt)/[\w\-./]+\.[a-zA-Z0-9]{1,8})', latest_msg):
            candidates.append(m)

    img_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    for raw_p in candidates:
        clean_p = raw_p.split("#")[0].strip()
        if not clean_p or clean_p in seen_paths:
            continue
        if not os.path.isfile(clean_p):
            continue
        seen_paths.add(clean_p)
        fname = os.path.basename(clean_p)
        ext = os.path.splitext(fname)[1].lower()
        if ext in img_exts:
            dest = os.path.join(MEDIA_DIR, fname)
            if not os.path.exists(dest):
                try:
                    subprocess.run(["cp", clean_p, dest], timeout=3)
                except Exception:
                    pass
            media.append({"type": "image", "url": f"/media/{fname}", "name": fname})
        else:
            dl_url = f"/api/download?path={urllib.parse.quote(clean_p)}"
            media.append({"type": "file", "url": dl_url, "name": fname})

    return media


async def handle_download(request):
    import urllib.parse
    import zipfile
    raw_path = request.query.get("path", "").strip()
    if not raw_path:
        return web.json_response({"error": "Ruta vacia"}, status=400)

    clean_path = urllib.parse.unquote(raw_path)
    if clean_path.startswith("file://"):
        clean_path = clean_path.replace("file://", "", 1)
    clean_path = clean_path.split("#")[0].strip()

    # Si está activa la PC remota en Tailscale, proxear el archivo desde allá
    if is_remote_pc_active():
        rem_ip = get_active_pc_ip()
        fname = os.path.basename(clean_path.rstrip("/")) or "archivo"
        rem_url = f"https://{rem_ip}:8443/api/download?path={urllib.parse.quote(clean_path)}"
        fallback_media_url = f"https://{rem_ip}:8443/media/{urllib.parse.quote(fname)}"
        def _fetch_rem_file():
            ctx = ssl._create_unverified_context()
            try:
                req = urllib.request.Request(rem_url, method="GET")
                with urllib.request.urlopen(req, context=ctx, timeout=25) as resp:
                    return resp.read(), resp.headers.get("Content-Type", "application/octet-stream")
            except Exception:
                req2 = urllib.request.Request(fallback_media_url, method="GET")
                with urllib.request.urlopen(req2, context=ctx, timeout=25) as resp2:
                    return resp2.read(), resp2.headers.get("Content-Type", "application/octet-stream")
        try:
            body, ctype = await asyncio.to_thread(_fetch_rem_file)
            return web.Response(
                body=body,
                content_type=ctype,
                headers={"Content-Disposition": f'attachment; filename="{fname}"'}
            )
        except Exception as e:
            return web.json_response({"error": f"No se pudo descargar de PC remota: {e}"}, status=404)

    if not os.path.exists(clean_path):
        return web.json_response({"error": f"Archivo no encontrado: {clean_path}"}, status=404)

    # Si es una carpeta, empaquetarla en un .zip al vuelo
    if os.path.isdir(clean_path):
        folder_name = os.path.basename(clean_path.rstrip("/")) or "carpeta"
        zip_filename = f"{folder_name}.zip"
        zip_path = os.path.join("/tmp", f"tars_dl_{int(time.time())}_{zip_filename}")
        def _make_zip():
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(clean_path):
                    dirs[:] = [d for d in dirs if d not in (".git", "venv", "node_modules", "__pycache__")]
                    for file in files:
                        full_f = os.path.join(root, file)
                        rel_f = os.path.relpath(full_f, os.path.dirname(clean_path.rstrip("/")))
                        zf.write(full_f, rel_f)
            return zip_path
        await asyncio.to_thread(_make_zip)
        return web.FileResponse(
            zip_path,
            headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
        )

    fname = os.path.basename(clean_path)
    return web.FileResponse(
        clean_path,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'}
    )


async def handle_sync(request):
    last_idx = int(request.query.get("last_index", 0))
    client_chat_id = request.query.get("chat_id", "").strip()
    media = []

    if is_remote_pc_active():
        import urllib.parse
        rem_ip = get_active_pc_ip()
        qs = f"/api/sync?last_index={last_idx}&chat_id={urllib.parse.quote(client_chat_id)}"
        rem_data = await asyncio.to_thread(remote_api_request, rem_ip, qs, "GET", None, 20.0)
        if isinstance(rem_data, dict) and not rem_data.get("_proxy_error"):
            rem_data = enrich_remote_sync_data(rem_ip, rem_data)
            if rem_data.get("has_new"):
                if rem_data.get("audio_url"):
                    await asyncio.to_thread(ensure_remote_media_cached, rem_ip, rem_data["audio_url"])
                for m in (rem_data.get("media") or []):
                    if isinstance(m, dict) and m.get("url") and m.get("url", "").startswith("/media/"):
                        await asyncio.to_thread(ensure_remote_media_cached, rem_ip, m["url"])
            return web.json_response(rem_data)
        return web.json_response({
            "has_new": False,
            "step_index": last_idx,
            "chat_id": client_chat_id,
            "chat_changed": False,
            "pc_audio_muted": get_pc_sound_muted(),
            "mobile_voice_muted": get_mobile_voice_muted(),
            "active_pc": get_active_pc_info()
        })

    active_id = await asyncio.to_thread(get_current_antigravity_convo_id) or ""
    current_model = await asyncio.to_thread(get_current_antigravity_model) or ""
    chat_changed = bool(client_chat_id and active_id and client_chat_id != active_id)

    latest_idx, latest_msg, proc_info = await asyncio.to_thread(get_latest_transcript_message)

    if chat_changed or (not proc_info.get("is_processing") and latest_idx > last_idx and latest_msg):
        # Extraer imágenes y archivos generados o linkeados en la respuesta
        media = await asyncio.to_thread(collect_turn_media_and_files, latest_msg, proc_info)

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
            "current_model": current_model,
            "chat_changed": chat_changed,
            "processing_info": proc_info,
            "processing_status": proc_info.get("tool_action", "") if proc_info.get("is_processing") else "",
            "pc_audio_muted": get_pc_sound_muted(),
            "mobile_voice_muted": get_mobile_voice_muted(),
            "active_pc": get_active_pc_info()
        })

    return web.json_response({
        "has_new": False,
        "step_index": latest_idx,
        "chat_id": active_id,
        "current_model": current_model,
        "chat_changed": False,
        "processing_info": proc_info,
        "processing_status": proc_info.get("tool_action", "") if proc_info.get("is_processing") else "",
        "pc_audio_muted": get_pc_sound_muted(),
        "mobile_voice_muted": get_mobile_voice_muted(),
        "active_pc": get_active_pc_info()
    })


def get_chat_history(convo_id, limit=10):
    if not convo_id:
        return {"chat_id": "", "messages": [], "last_step_index": 0}

    brain_dir = os.path.expanduser("~/.gemini/antigravity/brain")
    transcript_path = os.path.join(brain_dir, convo_id, ".system_generated", "logs", "transcript.jsonl")
    if not os.path.exists(transcript_path):
        return {"chat_id": convo_id, "messages": [], "last_step_index": 0}

    lines = []
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            read_size = min(size, 2097152)  # Leer hasta los ultimos 2 MB
            f.seek(size - read_size)
            chunk = f.read(read_size).decode("utf-8", errors="ignore")
            all_lines = chunk.splitlines()
            if read_size < size and len(all_lines) > 1:
                lines = all_lines[1:]
            else:
                lines = all_lines
    except Exception as e:
        print(f"[TARS Web] Error leyendo transcript para historial ({convo_id}): {e}")
        return {"chat_id": convo_id, "messages": [], "last_step_index": 0}

    turns = []
    for line in lines:
        try:
            step = json.loads(line)
            stype = step.get("type")
            source = step.get("source")
            content = step.get("content", "")

            if stype == "USER_INPUT" and source == "USER_EXPLICIT":
                match = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, re.DOTALL)
                clean_text = match.group(1).strip() if match else content.strip()
                if clean_text and not clean_text.startswith("{{ CHECKPOINT"):
                    turns.append({
                        "role": "user",
                        "content": clean_text,
                        "step_index": step.get("step_index", 0)
                    })

            elif stype == "PLANNER_RESPONSE" and source == "MODEL":
                tool_calls = step.get("tool_calls", [])
                if content and not tool_calls:
                    media = collect_turn_media_and_files(content, {})
                    turns.append({
                        "role": "assistant",
                        "content": content.strip(),
                        "media": media,
                        "step_index": step.get("step_index", 0)
                    })
        except Exception:
            pass

    recent = turns[-limit:] if len(turns) > limit else turns
    last_idx = recent[-1]["step_index"] if recent else 0
    return {
        "chat_id": convo_id,
        "messages": recent,
        "last_step_index": last_idx
    }


async def handle_chat_history(request):
    chat_id = request.query.get("chat_id", "").strip()
    try:
        limit = int(request.query.get("limit", 10))
    except Exception:
        limit = 10

    if is_remote_pc_active():
        import urllib.parse
        rem_ip = get_active_pc_ip()
        qs = f"/api/chat_history?chat_id={urllib.parse.quote(chat_id)}&limit={limit}"
        rem_data = await asyncio.to_thread(remote_api_request, rem_ip, qs, "GET", None, 12.0)
        if isinstance(rem_data, dict) and not rem_data.get("_proxy_error"):
            for msg in rem_data.get("messages", []):
                for m in (msg.get("media") or []):
                    if isinstance(m, dict) and m.get("url") and m.get("url", "").startswith("/media/"):
                        await asyncio.to_thread(ensure_remote_media_cached, rem_ip, m["url"])
            return web.json_response(rem_data)

    if not chat_id:
        active_id = await asyncio.to_thread(get_current_antigravity_convo_id) or ""
        chat_id = active_id

    data = await asyncio.to_thread(get_chat_history, chat_id, limit)
    return web.json_response(data)


TARS_STATE_FILE = "/home/santiago/.gemini/config/tars_state.json"

def _read_tars_state():
    try:
        if os.path.exists(TARS_STATE_FILE):
            with open(TARS_STATE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _write_tars_state(updates):
    try:
        data = _read_tars_state()
        data.update(updates)
        with open(TARS_STATE_FILE, "w") as f:
            json.dump(data, f)
        return True
    except Exception as e:
        print(f"[TARS Web] Error guardando estado TARS: {e}")
        return False

def format_friendly_pc_name(hostname, ip=""):
    h = (hostname or "").strip()
    hl = h.lower()
    if "lenovo" in hl or "yoga" in hl:
        return "Lenovo Yoga"
    if "pop-os" in hl or "pop_os" in hl:
        return "Pop!_OS"
    if h:
        return h[:18]
    return ip or "PC Local"

def get_active_pc_ip():
    st = _read_tars_state()
    val = str(st.get("active_pc_ip") or "local").strip()
    return val if val else "local"

def get_active_pc_info():
    st = _read_tars_state()
    ip = str(st.get("active_pc_ip") or "local").strip()
    local_hostname = socket.gethostname()
    local_friendly = format_friendly_pc_name(local_hostname)
    if ip == "local" or ip in ("127.0.0.1", "localhost"):
        return {
            "id": "local",
            "ip": get_tailscale_ip() or get_local_ip(),
            "name": local_friendly,
            "hostname": local_hostname,
            "is_local": True
        }
    return {
        "id": ip,
        "ip": ip,
        "name": st.get("active_pc_name") or format_friendly_pc_name("", ip),
        "hostname": st.get("active_pc_hostname") or ip,
        "is_local": False
    }

def is_remote_pc_active():
    ip = get_active_pc_ip()
    if ip in ("local", "127.0.0.1", "localhost", ""):
        return False
    my_ts = get_tailscale_ip()
    my_loc = get_local_ip()
    if ip in (my_ts, my_loc):
        return False
    return True

def check_tcp_port(ip, port=8443, timeout=0.45):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, port)) == 0
    except Exception:
        return False
    finally:
        s.close()

def remote_api_request(remote_ip, path, method="GET", json_body=None, timeout=20.0):
    ctx = ssl._create_unverified_context()
    url = f"https://{remote_ip}:8443{path}"
    data_bytes = None
    headers = {}
    if json_body is not None:
        data_bytes = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            return json.loads(raw)
    except Exception as e:
        print(f"[TARS Web] Error proxy a PC remota ({remote_ip}{path}): {e}")
        return {"_proxy_error": str(e)}

def ensure_remote_media_cached(remote_ip, media_url):
    if not media_url or not str(media_url).startswith("/media/"):
        return
    fname = os.path.basename(media_url)
    local_dest = os.path.join(MEDIA_DIR, fname)
    if os.path.exists(local_dest) and os.path.getsize(local_dest) > 0:
        return
    ctx = ssl._create_unverified_context()
    url = f"https://{remote_ip}:8443/media/{fname}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx, timeout=15.0) as resp:
            content = resp.read()
            if content:
                with open(local_dest, "wb") as f:
                    f.write(content)
    except Exception as e:
        print(f"[TARS Web] Error descargando media remota {url}: {e}")

def discover_pcs():
    active_ip = get_active_pc_ip()
    local_hostname = socket.gethostname()
    local_ts_ip = get_tailscale_ip() or get_local_ip()
    local_friendly = format_friendly_pc_name(local_hostname, local_ts_ip)

    pcs = [{
        "id": "local",
        "ip": local_ts_ip,
        "name": local_friendly,
        "hostname": local_hostname,
        "os": "linux",
        "is_local": True,
        "online": True,
        "tars_online": True,
        "active": (not is_remote_pc_active()),
        "direct_url": f"https://{local_ts_ip}:8443"
    }]

    seen_ips = {local_ts_ip, get_local_ip(), "127.0.0.1"}

    # Auto-descubrir otras PCs de la red Tailscale
    try:
        out = subprocess.check_output(["tailscale", "status", "--json"], text=True, timeout=2.5)
        ts_data = json.loads(out)
        peers = ts_data.get("Peer") or {}
        for _, peer in peers.items():
            os_name = str(peer.get("OS") or "").lower()
            if os_name in ("android", "ios"):
                continue
            ips = peer.get("TailscaleIPs") or []
            ipv4 = next((x for x in ips if "." in x), "")
            if not ipv4 or ipv4 in seen_ips:
                continue
            seen_ips.add(ipv4)
            h_name = peer.get("HostName") or ipv4
            friendly = format_friendly_pc_name(h_name, ipv4)
            is_online = bool(peer.get("Online", False))
            tars_ok = check_tcp_port(ipv4, 8443, timeout=0.45) if is_online else False
            pcs.append({
                "id": ipv4,
                "ip": ipv4,
                "name": friendly,
                "hostname": h_name,
                "os": os_name or "pc",
                "is_local": False,
                "online": is_online,
                "tars_online": tars_ok,
                "active": (active_ip == ipv4),
                "direct_url": f"https://{ipv4}:8443"
            })
    except Exception as e:
        print(f"[TARS Web] Error consultando tailscale status: {e}")

    # Agregar PCs personalizadas guardadas manualmente
    st = _read_tars_state()
    for custom in (st.get("custom_pcs") or []):
        c_ip = str(custom.get("ip") or "").strip()
        if not c_ip or c_ip in seen_ips:
            continue
        seen_ips.add(c_ip)
        c_name = custom.get("name") or format_friendly_pc_name("", c_ip)
        tars_ok = check_tcp_port(c_ip, 8443, timeout=0.45)
        pcs.append({
            "id": c_ip,
            "ip": c_ip,
            "name": c_name,
            "hostname": c_ip,
            "os": "pc",
            "is_local": False,
            "online": tars_ok,
            "tars_online": tars_ok,
            "active": (active_ip == c_ip),
            "direct_url": f"https://{c_ip}:8443"
        })

    return {
        "active_pc": get_active_pc_info(),
        "pcs": pcs
    }

async def handle_get_pcs(request):
    data = await asyncio.to_thread(discover_pcs)
    return web.json_response(data)

async def handle_select_pc(request):
    try:
        body = await request.json()
        target_id = str(body.get("id") or body.get("ip") or "local").strip()
        target_name = str(body.get("name") or "").strip()
        target_hostname = str(body.get("hostname") or "").strip()

        my_ts = get_tailscale_ip()
        my_loc = get_local_ip()
        if target_id in ("local", "127.0.0.1", "localhost", my_ts, my_loc):
            _write_tars_state({
                "active_pc_ip": "local",
                "active_pc_name": format_friendly_pc_name(socket.gethostname()),
                "active_pc_hostname": socket.gethostname()
            })
            # Actualizar indice de notificacion local para no re-disparar mensajes viejos
            try:
                idx, _, _ = await asyncio.to_thread(get_latest_transcript_message)
                LAST_NOTIFIED_STEP["idx"] = idx
            except Exception:
                pass
        else:
            if not target_name:
                target_name = format_friendly_pc_name(target_hostname, target_id)
            _write_tars_state({
                "active_pc_ip": target_id,
                "active_pc_name": target_name,
                "active_pc_hostname": target_hostname or target_id
            })
            # Sincronizar ultimo step_index de la PC remota para no notificar mensajes viejos
            try:
                rem_sync = await asyncio.to_thread(remote_api_request, target_id, "/api/sync?last_index=999999", "GET", None, 2.5)
                if isinstance(rem_sync, dict) and "step_index" in rem_sync:
                    LAST_NOTIFIED_STEP["idx"] = int(rem_sync.get("step_index") or 0)
            except Exception:
                pass

        return web.json_response({
            "success": True,
            "active_pc": get_active_pc_info()
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_add_pc(request):
    try:
        body = await request.json()
        raw_ip = str(body.get("ip") or "").strip()
        raw_ip = re.sub(r"^https?://", "", raw_ip).split(":")[0].split("/")[0].strip()
        name = str(body.get("name") or "").strip() or format_friendly_pc_name("", raw_ip)
        if not raw_ip:
            return web.json_response({"success": False, "error": "IP inválida"}, status=400)
        st = _read_tars_state()
        custom_pcs = [c for c in (st.get("custom_pcs") or []) if c.get("ip") != raw_ip]
        custom_pcs.append({"ip": raw_ip, "name": name})
        _write_tars_state({
            "custom_pcs": custom_pcs,
            "active_pc_ip": raw_ip,
            "active_pc_name": name,
            "active_pc_hostname": raw_ip
        })
        data = await asyncio.to_thread(discover_pcs)
        return web.json_response({"success": True, **data})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

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

def get_mobile_voice_muted():
    try:
        if os.path.exists(TARS_STATE_FILE):
            with open(TARS_STATE_FILE, "r") as f:
                data = json.load(f)
                return bool(data.get("mobile_voice_muted", False))
    except Exception:
        pass
    return False

def set_mobile_voice_muted(muted):
    try:
        data = {}
        if os.path.exists(TARS_STATE_FILE):
            with open(TARS_STATE_FILE, "r") as f:
                data = json.load(f)
        data["mobile_voice_muted"] = bool(muted)
        with open(TARS_STATE_FILE, "w") as f:
            json.dump(data, f)
        return True
    except Exception as e:
        print(f"[TARS Web] Error guardando estado voz movil: {e}")
        return False

async def handle_toggle_mobile_voice(request):
    try:
        target_state = None
        try:
            body = await request.json()
            if isinstance(body, dict) and "muted" in body:
                target_state = bool(body["muted"])
        except Exception:
            pass
        if target_state is None:
            curr = get_mobile_voice_muted()
            target_state = not curr
        await asyncio.to_thread(set_mobile_voice_muted, target_state)
        return web.json_response({"success": True, "mobile_voice_muted": target_state})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_toggle_pc_sound(request):
    try:
        if is_remote_pc_active():
            rem_ip = get_active_pc_ip()
            rem_res = await asyncio.to_thread(remote_api_request, rem_ip, "/api/toggle_pc_sound", "POST", {})
            if isinstance(rem_res, dict) and "pc_audio_muted" in rem_res:
                return web.json_response(rem_res)
        curr = get_pc_sound_muted()
        new_state = not curr
        await asyncio.to_thread(set_pc_sound_muted, new_state)
        return web.json_response({"success": True, "pc_audio_muted": new_state})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_get_chats(request):
    if is_remote_pc_active():
        rem_ip = get_active_pc_ip()
        pc_info = get_active_pc_info()
        rem_chats = await asyncio.to_thread(remote_api_request, rem_ip, "/api/chats", "GET", None, 8.0)
        if isinstance(rem_chats, dict) and "chats" in rem_chats:
            return web.json_response(rem_chats)
        return web.json_response({
            "current_id": "",
            "chats": [],
            "remote_offline": True,
            "error": f"El servidor TARS en {pc_info.get('name', rem_ip)} ({rem_ip}:8443) no responde. Actualizalo o reinicialo en esa PC."
        })
    chats_data = await asyncio.to_thread(get_antigravity_chats)
    return web.json_response(chats_data)

async def handle_switch_chat(request):
    try:
        data = await request.json()
        target = data.get("target") or data.get("id") or data.get("direction") or ""
        if not target:
            return web.json_response({"success": False, "error": "Debe indicar objetivo o direccion"}, status=400)

        if is_remote_pc_active():
            rem_ip = get_active_pc_ip()
            rem_res = await asyncio.to_thread(remote_api_request, rem_ip, "/api/switch_chat", "POST", data)
            if isinstance(rem_res, dict) and not rem_res.get("_proxy_error"):
                return web.json_response(rem_res)

        result = await asyncio.to_thread(switch_antigravity_chat, target)
        if isinstance(result, dict) and result.get("success") and result.get("id"):
            hist = await asyncio.to_thread(get_chat_history, result["id"], 10)
            result["messages"] = hist.get("messages", [])
            result["last_step_index"] = hist.get("last_step_index", 0)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

def get_current_antigravity_model():
    js = """(() => {
        const btn = document.querySelector('button[aria-label^="Select model"]');
        return btn ? btn.innerText.trim().replace(/\\s+/g, ' ') : '';
    })()"""
    val = eval_in_antigravity(js)
    return val if isinstance(val, str) else ""

def get_antigravity_models():
    current_model = get_current_antigravity_model()
    eval_in_antigravity("""(() => {
        const items = document.querySelectorAll('[role="menuitem"]');
        if (!items.length) {
            const btn = document.querySelector('button[aria-label^="Select model"]');
            if (btn) btn.click();
        }
    })()""")
    time.sleep(0.28)
    js_read = """(() => {
        const btn = document.querySelector('button[aria-label^="Select model"]');
        const curr = btn ? btn.innerText.trim().replace(/\\s+/g, ' ') : '';
        const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
        const models = [];
        for (const el of items) {
            const rawLines = (el.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
            if (!rawLines.length || rawLines[0] === 'View Usage') continue;
            const baseEl = el.querySelector('[data-model-base]');
            const name = baseEl ? baseEl.getAttribute('data-model-base') : rawLines[0];
            const hasEffort = Boolean(baseEl) || el.getAttribute('aria-haspopup') === 'menu';
            const effort = (hasEffort && rawLines.length > 1 && ['Low', 'Medium', 'High'].includes(rawLines[1])) ? rawLines[1] : '';
            const badge = rawLines.find(x => x === 'Leaving Soon' || x === 'Notice') || '';
            const active = curr.toLowerCase().startsWith(name.toLowerCase());
            models.push({
                name: name,
                effort: effort,
                has_effort: hasEffort,
                badge: badge,
                active: active
            });
        }
        if (btn && items.length) btn.click();
        return { current_model: curr, models: models };
    })()"""
    res = eval_in_antigravity(js_read)
    if isinstance(res, dict) and res.get("models"):
        return res
    # Fallback list if menu couldn't open momentarily
    default_models = [
        {"name": "Gemini 3.8 Flash", "effort": "High", "has_effort": True, "badge": "", "active": "3.8" in current_model},
        {"name": "Gemini 3.7 Flash", "effort": "Medium", "has_effort": True, "badge": "Leaving Soon", "active": "3.7" in current_model},
        {"name": "Gemini 3.6 Flash", "effort": "Medium", "has_effort": True, "badge": "Leaving Soon", "active": "3.6" in current_model},
        {"name": "Gemini 3.1 Pro", "effort": "Low", "has_effort": True, "badge": "Leaving Soon", "active": "3.1 Pro" in current_model},
        {"name": "Claude Sonnet 4.6 (Thinking)", "effort": "", "has_effort": False, "badge": "", "active": "Sonnet" in current_model},
        {"name": "Claude Opus 4.6 (Thinking)", "effort": "", "has_effort": False, "badge": "", "active": "Opus" in current_model},
        {"name": "GPT-OSS 120B (Medium)", "effort": "", "has_effort": False, "badge": "", "active": "GPT-OSS" in current_model},
    ]
    return {"current_model": current_model, "models": default_models}

def switch_antigravity_model(model_name, effort=None):
    if not model_name:
        return {"success": False, "error": "Nombre de modelo vacio"}

    print(f"[TARS Web] Cambiando modelo -> '{model_name}' effort={effort}")

    target_json = json.dumps(model_name.strip())
    effort_json = json.dumps((effort or "").strip())

    # Paso 1: Cerrar menú si estuviera abierto
    eval_in_antigravity("""(() => {
        const menu = document.querySelector('[role="menu"]');
        if (menu) {
            const btn = document.querySelector('button[aria-label^="Select model"]');
            if (btn) btn.click();
        }
    })()""")
    time.sleep(0.15)

    # Paso 2: Abrir el menú
    open_res = eval_in_antigravity("""(() => {
        const btn = document.querySelector('button[aria-label^="Select model"]');
        if (!btn) return 'NO_BTN';
        btn.click();
        return 'opened';
    })()""")
    print(f"[TARS Web] Menú abierto: {open_res}")
    time.sleep(0.4)

    if effort:
        # Paso 3a: ArrowRight en el item principal para abrir submenu de effort
        focus_res = eval_in_antigravity(f"""(() => {{
            const target = {target_json}.toLowerCase();
            const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
            const item = items.find(el => (el.innerText || '').toLowerCase().includes(target));
            if (!item) return 'ITEM_NOT_FOUND: ' + target + ' in ' + items.length + ' items';
            item.focus();
            item.dispatchEvent(new KeyboardEvent('keydown', {{key: 'ArrowRight', code: 'ArrowRight', bubbles: true}}));
            return 'arrow_sent: ' + (item.innerText || '').trim().slice(0, 30);
        }})()""")
        print(f"[TARS Web] Arrow submenu: {focus_res}")
        time.sleep(0.35)

        # Paso 4a: Click en el subitem de effort
        click_res = eval_in_antigravity(f"""(() => {{
            const eff = {effort_json}.toLowerCase();
            const items = Array.from(document.querySelectorAll('[role="menuitem"], [role="menuitemradio"]'));
            const sub = items.find(el => (el.innerText || '').trim().toLowerCase() === eff);
            if (sub) {{ sub.click(); return 'clicked_effort: ' + (sub.innerText || '').trim(); }}
            const target = {target_json}.toLowerCase();
            const mainItem = items.find(el => (el.innerText || '').toLowerCase().includes(target));
            if (mainItem) {{ mainItem.click(); return 'clicked_main_fallback'; }}
            return 'NOTHING_FOUND among ' + items.length + ' items';
        }})()""")
        print(f"[TARS Web] Click effort: {click_res}")
    else:
        # Paso 3b: Click directo en el item de modelo
        click_res = eval_in_antigravity(f"""(() => {{
            const target = {target_json}.toLowerCase();
            const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
            const item = items.find(el => (el.innerText || '').toLowerCase().includes(target));
            if (!item) return 'ITEM_NOT_FOUND: ' + target + ' in ' + items.length + ' items';
            item.click();
            return 'clicked: ' + (item.innerText || '').trim().slice(0, 30);
        }})()""")
        print(f"[TARS Web] Click modelo: {click_res}")

    time.sleep(0.35)

    # Paso 5: Confirmar modelo actual
    new_model = get_current_antigravity_model()
    print(f"[TARS Web] Modelo resultante: '{new_model}'")
    return {"success": True, "current_model": new_model or model_name}

async def handle_get_models(request):
    if is_remote_pc_active():
        rem_ip = get_active_pc_ip()
        rem_models = await asyncio.to_thread(remote_api_request, rem_ip, "/api/models", "GET")
        if isinstance(rem_models, dict) and "models" in rem_models:
            return web.json_response(rem_models)
    data = await asyncio.to_thread(get_antigravity_models)
    return web.json_response(data)

async def handle_switch_model(request):
    try:
        data = await request.json()
        if is_remote_pc_active():
            rem_ip = get_active_pc_ip()
            rem_res = await asyncio.to_thread(remote_api_request, rem_ip, "/api/switch_model", "POST", data)
            if isinstance(rem_res, dict) and not rem_res.get("_proxy_error"):
                return web.json_response(rem_res)
        model_name = data.get("model") or data.get("name") or ""
        effort = data.get("effort") or None
        res = await asyncio.to_thread(switch_antigravity_model, model_name, effort)
        return web.json_response(res)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

NTFY_TOPIC = "tars_santiago_a03"
VAPID_FILE = "/home/santiago/.gemini/config/vapid_keys.json"
SUBSCRIPTIONS_FILE = "/home/santiago/.gemini/config/push_subscriptions.json"
LAST_NOTIFIED_STEP = {"idx": 0}

def get_vapid_keys():
    try:
        if os.path.exists(VAPID_FILE):
            with open(VAPID_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def send_web_push_all(title, body, url="/", tag="tars-msg-latest"):
    clean_body = clean_text_for_speech(body)[:240] if body else "Nuevo mensaje de Antigravity."
    # 1. Enviar Web Push nativo (FCM / Chrome Android con pestaña cerrada)
    try:
        import base64
        from py_vapid import Vapid01
        from pywebpush import webpush, WebPushException
        keys = get_vapid_keys()
        priv_pem = keys.get("private_pem")
        if priv_pem and os.path.exists(SUBSCRIPTIONS_FILE):
            v = Vapid01.from_pem(priv_pem.encode("utf-8"))
            raw_priv = base64.urlsafe_b64encode(
                v.private_key.private_numbers().private_value.to_bytes(32, "big")
            ).decode("ascii").rstrip("=")
            with open(SUBSCRIPTIONS_FILE, "r") as f:
                subs = json.load(f)
            payload = json.dumps({
                "title": title,
                "body": clean_body,
                "url": url,
                "tag": tag,
                "voice_muted": get_mobile_voice_muted(),
                "ts": int(time.time() * 1000)
            })
            valid_subs = []
            for sub in subs:
                try:
                    webpush(
                        subscription_info=sub,
                        data=payload,
                        vapid_private_key=raw_priv,
                        vapid_claims={"sub": "mailto:" + os.environ.get("TARS_VAPID_EMAIL", "user@example.com")},
                        ttl=3600
                    )
                    valid_subs.append(sub)
                except WebPushException as ex:
                    if ex.response is not None and ex.response.status_code in (404, 410):
                        continue
                    valid_subs.append(sub)
                except Exception as e:
                    print(f"[TARS Web] Error WebPush individual: {e}")
                    valid_subs.append(sub)
            with open(SUBSCRIPTIONS_FILE, "w") as f:
                json.dump(valid_subs, f)
    except Exception as e:
        print(f"[TARS Web] Error general en WebPush: {e}")

    # 2. Enviar también al canal ntfy.sh por si usa la app ntfy
    try:
        ascii_title = title.encode("ascii", errors="ignore").decode("ascii").strip() or "TARS - Antigravity"
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=clean_body.encode("utf-8"),
            headers={
                "Title": ascii_title,
                "Priority": "high",
                "Tags": "robot,speech_balloon",
                "Click": "https://" + os.environ.get("TARS_LOCAL_IP", "localhost") + ":8443"
            },
            method="POST"
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception as e:
        print(f"[TARS Web] Error enviando push ntfy: {e}")

async def handle_vapid_public_key(request):
    keys = get_vapid_keys()
    return web.json_response({"public_key": keys.get("public_key", "")})

async def handle_push_subscribe(request):
    try:
        sub = await request.json()
        if not sub or "endpoint" not in sub:
            return web.json_response({"success": False, "error": "Invalid subscription"}, status=400)
        subs = []
        if os.path.exists(SUBSCRIPTIONS_FILE):
            try:
                with open(SUBSCRIPTIONS_FILE, "r") as f:
                    subs = json.load(f)
            except Exception:
                subs = []
        subs = [s for s in subs if s.get("endpoint") != sub.get("endpoint")]
        subs.append(sub)
        with open(SUBSCRIPTIONS_FILE, "w") as f:
            json.dump(subs, f)
        print(f"[TARS Web] Celular suscripto a Web Push (total={len(subs)})")
        return web.json_response({"success": True, "count": len(subs)})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_sw(request):
    sw_path = os.path.join(WEB_DIR, "sw.js")
    if os.path.exists(sw_path):
        return web.FileResponse(sw_path, headers={
            "Content-Type": "application/javascript",
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache"
        })
    return web.Response(text="SW no encontrado", status=404)

async def handle_test_notify(request):
    delay = 0
    try:
        body = await request.json()
        delay = float(body.get("delay", 0))
    except Exception:
        pass

    async def _delayed_push():
        if delay > 0:
            await asyncio.sleep(delay)
        await asyncio.to_thread(
            send_web_push_all,
            "🤖 TARS • Antigravity",
            "¡Hola! Esta notificación llegó en segundo plano con la pestaña cerrada, igual que un mensaje de WhatsApp."
        )

    asyncio.create_task(_delayed_push())
    return web.json_response({"success": True, "topic": NTFY_TOPIC, "delay": delay})

async def handle_manifest(request):
    manifest_path = os.path.join(WEB_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        return web.FileResponse(manifest_path, headers={"Content-Type": "application/manifest+json"})
    return web.Response(text="Manifest no encontrado", status=404)

async def handle_tunnel_url(request):
    tunnel_url = ""
    try:
        if os.path.exists("/tmp/cloudflared.log"):
            with open("/tmp/cloudflared.log", "r") as f:
                content = f.read()
            m = re.search(r"https://[-a-z0-9.]*\.trycloudflare\.com", content)
            if m:
                tunnel_url = m.group(0)
    except Exception:
        pass
    return web.json_response({"tunnel_url": tunnel_url})

async def handle_cancel(request):
    global LAST_CANCEL_TIMESTAMP
    LAST_CANCEL_TIMESTAMP = time.time()
    if is_remote_pc_active():
        rem_ip = get_active_pc_ip()
        rem_res = await asyncio.to_thread(remote_api_request, rem_ip, "/api/cancel", "POST", {})
        if isinstance(rem_res, dict) and not rem_res.get("_proxy_error"):
            return web.json_response(rem_res)
    res = await asyncio.to_thread(cancel_antigravity_ide)
    return web.json_response(res)

def init_app():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/sw.js", handle_sw)
    app.router.add_get("/manifest.json", handle_manifest)
    app.router.add_get("/api/tunnel_url", handle_tunnel_url)
    app.router.add_get("/api/vapid_public_key", handle_vapid_public_key)
    app.router.add_post("/api/push_subscribe", handle_push_subscribe)
    app.router.add_get("/api/pcs", handle_get_pcs)
    app.router.add_post("/api/select_pc", handle_select_pc)
    app.router.add_post("/api/add_pc", handle_add_pc)
    app.router.add_get("/api/chats", handle_get_chats)
    app.router.add_get("/api/chat_history", handle_chat_history)
    app.router.add_post("/api/switch_chat", handle_switch_chat)
    app.router.add_get("/api/models", handle_get_models)
    app.router.add_post("/api/switch_model", handle_switch_model)
    app.router.add_post("/api/toggle_pc_sound", handle_toggle_pc_sound)
    app.router.add_post("/api/toggle_mobile_voice", handle_toggle_mobile_voice)
    app.router.add_post("/api/test_notify", handle_test_notify)
    app.router.add_post("/api/cancel", handle_cancel)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/audio", handle_audio)
    app.router.add_get("/api/sync", handle_sync)
    app.router.add_get("/api/download", handle_download)
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
            if "Let's Encrypt" in out or "tail0ec03b.ts.net" in out or "Tailscale" in out:
                needs_gen = False
            else:
                if f"IP Address:{local_ip}" not in out and f"IP:{local_ip}" not in out:
                    needs_gen = True
                if tailscale_ip and f"IP Address:{tailscale_ip}" not in out:
                    needs_gen = True
        except Exception:
            needs_gen = True

    if needs_gen:
        host_name = socket.gethostname()
        san_parts = [
            "DNS:pop-os.local",
            f"DNS:{host_name}.local",
            f"DNS:{host_name}",
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

async def _pipe_stream(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass

async def _handle_dual_8443(client_reader, client_writer, internal_tls_port, default_host):
    try:
        first_chunk = await asyncio.wait_for(client_reader.read(4096), timeout=5.0)
        if not first_chunk:
            client_writer.close()
            return
        # 0x16 = TLS Handshake (ClientHello)
        if first_chunk[0] == 0x16:
            backend_reader, backend_writer = await asyncio.open_connection("127.0.0.1", internal_tls_port)
            backend_writer.write(first_chunk)
            await backend_writer.drain()
            await asyncio.gather(
                _pipe_stream(client_reader, backend_writer),
                _pipe_stream(backend_reader, client_writer)
            )
        else:
            # Plain HTTP on 8443 -> Redirect to https://
            req_text = first_chunk.decode("latin-1", errors="ignore")
            host_hdr = f"{default_host}:8443"
            path = "/"
            lines = req_text.splitlines()
            if lines:
                parts = lines[0].split()
                if len(parts) >= 2:
                    path = parts[1]
            for line in lines[1:]:
                if line.lower().startswith("host:"):
                    host_hdr = line.split(":", 1)[1].strip()
                    if ":" not in host_hdr:
                        host_hdr = f"{host_hdr}:8443"
                    break
            location = f"https://{host_hdr}{path}"
            resp = (
                f"HTTP/1.1 302 Found\r\n"
                f"Location: {location}\r\n"
                f"Content-Length: 0\r\n"
                f"Connection: close\r\n\r\n"
            )
            client_writer.write(resp.encode("latin-1"))
            await client_writer.drain()
            client_writer.close()
    except Exception:
        try:
            client_writer.close()
        except Exception:
            pass

async def watch_transcript_for_push():
    # Inicializar en el paso actual para no re-notificar mensajes viejos al arrancar
    try:
        if is_remote_pc_active():
            rem_ip = get_active_pc_ip()
            rem_sync = await asyncio.to_thread(remote_api_request, rem_ip, "/api/sync?last_index=999999", "GET", None, 2.5)
            if isinstance(rem_sync, dict):
                LAST_NOTIFIED_STEP["idx"] = int(rem_sync.get("step_index") or 0)
        else:
            idx, _, _ = await asyncio.to_thread(get_latest_transcript_message)
            LAST_NOTIFIED_STEP["idx"] = idx
    except Exception:
        pass

    while True:
        await asyncio.sleep(1.5)
        try:
            if is_remote_pc_active():
                rem_ip = get_active_pc_ip()
                pc_info = get_active_pc_info()
                rem_data = await asyncio.to_thread(remote_api_request, rem_ip, f"/api/sync?last_index={LAST_NOTIFIED_STEP['idx']}", "GET", None, 3.0)
                if isinstance(rem_data, dict) and not rem_data.get("_proxy_error"):
                    p_info = rem_data.get("processing_info") or {}
                    latest_idx = int(rem_data.get("step_index") or 0)
                    latest_msg = rem_data.get("content") or ""
                    if not p_info.get("is_processing") and latest_idx > LAST_NOTIFIED_STEP["idx"] and latest_msg:
                        LAST_NOTIFIED_STEP["idx"] = latest_idx
                        await asyncio.to_thread(
                            send_web_push_all,
                            f"🤖 TARS ({pc_info.get('name', 'PC')}) • Antigravity",
                            latest_msg,
                            "/",
                            f"tars-step-{latest_idx}"
                        )
            else:
                latest_idx, latest_msg, proc_info = await asyncio.to_thread(get_latest_transcript_message)
                if not proc_info.get("is_processing") and latest_idx > LAST_NOTIFIED_STEP["idx"] and latest_msg:
                    LAST_NOTIFIED_STEP["idx"] = latest_idx
                    await asyncio.to_thread(
                        send_web_push_all,
                        "🤖 TARS • Antigravity",
                        latest_msg,
                        "/",
                        f"tars-step-{latest_idx}"
                    )
        except Exception as e:
            print(f"[TARS Web] Error en watch_transcript_for_push: {e}")

async def async_main():
    port = 8443
    internal_tls_port = 8444
    http_port = 8080
    app = init_app()

    local_ip = get_local_ip()
    ts_ip = get_tailscale_ip()
    ensure_ssl_certificates(local_ip, ts_ip)

    # Iniciar monitor autonomo de respuestas para enviar Push aunque el navegador del celular este cerrado
    asyncio.create_task(watch_transcript_for_push())

    # Publicar alias pop-os.local por mDNS en la red local
    try:
        subprocess.Popen(
            ["avahi-publish", "-a", "-R", "pop-os.local", local_ip],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

    runner = web.AppRunner(app)
    await runner.setup()

    ssl_context = None
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(CERT_FILE, KEY_FILE)

    if ssl_context:
        tls_site = web.TCPSite(runner, "127.0.0.1", internal_tls_port, ssl_context=ssl_context)
        await tls_site.start()
        default_host = ts_ip or local_ip
        server_8443 = await asyncio.start_server(
            lambda r, w: _handle_dual_8443(r, w, internal_tls_port, default_host),
            host=["0.0.0.0", "::"],
            port=port
        )
        try:
            http_site = web.TCPSite(runner, "0.0.0.0", http_port)
            await http_site.start()
        except Exception as e:
            print(f"[TARS Web] Puerto HTTP {http_port} ocupado ({e}), continuando en 8443.")
        print(f"[TARS Web] SSL + Auto-Redirect HTTP->HTTPS habilitado en puerto {port} (y HTTP en {http_port}):")
        print(f"           - https://santiago-lenovo-yoga-510-14isk.tail0ec03b.ts.net:{port} (SSL Oficial Let's Encrypt - PWA)")
        print(f"           - https://{local_ip}:{port}")
        print(f"           - https://pop-os.local:{port}")
        if ts_ip:
            print(f"           - https://{ts_ip}:{port} (Remoto Tailscale)")
            print(f"           - http://{ts_ip}:{http_port} (HTTP directo)")
        await server_8443.serve_forever()
    else:
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"[TARS Web] Servidor listo (sin SSL) en: http://{local_ip}:{port}")
        while True:
            await asyncio.sleep(3600)

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
