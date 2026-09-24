#!/usr/bin/env python3
import re
import os
import sys
import json
import uuid
import time
import ssl
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

async def generate_tts_file(text):
    clean_text = re.sub(r'```[\s\S]*?```', ' codigo en pantalla ', text)
    clean_text = re.sub(r'\[(.*?)\]\([^\)]+\)', r'\1', clean_text)
    clean_text = re.sub(r'https?://\S+', '', clean_text)
    clean_text = clean_text.replace("*", "").replace("#", "").replace("`", "").replace(">", "").strip()
    if len(clean_text) > 450:
        clean_text = clean_text[:450] + " El resto de la respuesta esta en pantalla."

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
        with urllib.request.urlopen(req, timeout=1.5) as resp:
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
        with connect(ws_url, open_timeout=2) as ws:
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
            res_str = ws.recv(timeout=3)
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
        # 1. Coincidencia exacta por ID
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
        return {{ success: false, error: "Elemento no hallado en la interfaz" }};
    }})()
    """
    res = eval_in_antigravity(js_click)
    if isinstance(res, dict) and res.get("success"):
        return {"success": True, "id": target_id, "title": target_title or res.get("title")}

    return {"success": False, "error": res.get("error") if isinstance(res, dict) else "Error al cambiar chat"}


def send_to_antigravity_ide(text):
    try:
        from Xlib import X, display, Xatom
        import Xlib.protocol.event
        from pynput import keyboard

        d = display.Display(":0")
        root = d.screen().root
        client_list = root.get_full_property(d.intern_atom("_NET_CLIENT_LIST"), Xatom.WINDOW)
        antigravity_win = None
        if client_list:
            for w_id in client_list.value:
                w = d.create_resource_object("window", w_id)
                wm_class = w.get_wm_class()
                if wm_class and any("antigravity" in c.lower() for c in wm_class):
                    antigravity_win = w_id
                    break

        if not antigravity_win:
            print("[TARS Web] Ventana de Antigravity IDE no encontrada en el escritorio.")
            return False

        # 1. Activar y enfocar la ventana de Antigravity (source=2 para evitar bloqueo de Mutter)
        data = [2, 0, 0, 0, 0]
        event = Xlib.protocol.event.ClientMessage(
            window=antigravity_win,
            client_type=d.intern_atom("_NET_ACTIVE_WINDOW"),
            data=(32, data)
        )
        root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        d.sync()
        time.sleep(0.18)

        # 2. Asegurar foco en el input del chat con Ctrl+L
        controller = keyboard.Controller()
        controller.press(keyboard.Key.ctrl_l)
        controller.press('l')
        time.sleep(0.04)
        controller.release('l')
        controller.release(keyboard.Key.ctrl_l)
        time.sleep(0.08)

        # 3. Escribir el texto y presionar Enter
        controller.type(text)
        time.sleep(0.08)
        controller.press(keyboard.Key.enter)
        time.sleep(0.04)
        controller.release(keyboard.Key.enter)

        print(f"[TARS Web] Mensaje inyectado con exito en Antigravity IDE: {text[:50]}")
        return True
    except Exception as e:
        print(f"[TARS Web] Error inyectando texto en Antigravity IDE: {e}")
        return False


def execute_pc_task(command_text):
    cmd_lower = command_text.lower().strip()
    reply = ""
    media = []
    sent_to_ide = False

    # 0. Control y cambio de chats en Antigravity
    if "siguiente chat" in cmd_lower or "proximo chat" in cmd_lower or "avanzar chat" in cmd_lower or "otro chat" in cmd_lower:
        res = switch_antigravity_chat(target="siguiente")
        if res.get("success"):
            return f"Cambiado al chat: {res.get('title')}", media, sent_to_ide
        else:
            return f"No pude cambiar de chat: {res.get('error', 'desconocido')}", media, sent_to_ide

    if "chat anterior" in cmd_lower or "volver al chat" in cmd_lower or "retroceder chat" in cmd_lower:
        res = switch_antigravity_chat(target="anterior")
        if res.get("success"):
            return f"Cambiado al chat: {res.get('title')}", media, sent_to_ide
        else:
            return f"No pude cambiar de chat: {res.get('error', 'desconocido')}", media, sent_to_ide

    if "listar chats" in cmd_lower or "que chats hay" in cmd_lower or "cuales chats" in cmd_lower or "lista de chats" in cmd_lower or "mostrar chats" in cmd_lower:
        chats_info = get_antigravity_chats()
        chats = chats_info.get("chats", [])
        if not chats:
            return "No encontre chats abiertos en Antigravity.", media, sent_to_ide
        nombres = [f"- {c['title']}" + (" (activo)" if c.get('active') else "") for c in chats[:6]]
        total = len(chats)
        res_text = f"Hay {total} chats en la lista. Primeros:\n" + "\n".join(nombres)
        return res_text, media, sent_to_ide

    if any(cmd_lower.startswith(p) for p in ["cambiar al chat", "cambiar a chat", "cambiar chat", "ir al chat", "abrir chat", "poner el chat"]):
        cleaned = cmd_lower
        for p in ["cambiar al chat de ", "cambiar al chat ", "cambiar a chat ", "cambiar chat a ", "cambiar chat de ", "cambiar chat ", "ir al chat de ", "ir al chat ", "abrir chat de ", "abrir chat ", "poner el chat de ", "poner el chat "]:
            if cleaned.startswith(p):
                cleaned = cleaned[len(p):].strip()
                break
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
    if send_to_antigravity_ide(command_text):
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
        if not user_text:
            return web.json_response({"reply": "No recibi ningun texto."})

        reply_text, media, sent_to_ide = await asyncio.to_thread(execute_pc_task, user_text)
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
        field = await reader.next()
        if not field or field.name != "audio":
            return web.json_response({"reply": "No se envio ningun archivo de audio."}, status=400)

        temp_id = uuid.uuid4().hex[:8]
        raw_path = f"/tmp/upload_{temp_id}.raw"
        wav_path = f"/tmp/upload_{temp_id}.wav"

        with open(raw_path, "wb") as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                f.write(chunk)

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
            reply_text, media, sent_to_ide = await asyncio.to_thread(execute_pc_task, user_text)
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
                        if d.get("type") == "PLANNER_RESPONSE" and d.get("source") == "MODEL" and d.get("content"):
                            latest_msg = d.get("content")
                            latest_idx = d.get("step_index", 0)
                    except:
                        pass
        except Exception as e:
            print(f"[TARS Web] Error leyendo transcript: {e}")
    return latest_idx, latest_msg


async def handle_sync(request):
    last_idx = int(request.query.get("last_index", 0))
    client_chat_id = request.query.get("chat_id", "").strip()
    media = []

    active_id = await asyncio.to_thread(get_current_antigravity_convo_id) or ""
    chat_changed = bool(client_chat_id and active_id and client_chat_id != active_id)

    latest_idx, latest_msg = await asyncio.to_thread(get_latest_transcript_message)

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
            audio_url = await generate_tts_file(latest_msg[:400])

        return web.json_response({
            "has_new": True,
            "step_index": latest_idx,
            "content": latest_msg,
            "media": media,
            "audio_url": audio_url,
            "chat_id": active_id,
            "chat_changed": chat_changed
        })

    return web.json_response({
        "has_new": False,
        "step_index": latest_idx,
        "chat_id": active_id,
        "chat_changed": False
    })

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
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/audio", handle_audio)
    app.router.add_get("/api/sync", handle_sync)
    app.router.add_static("/static/", STATIC_DIR)
    app.router.add_static("/media/", MEDIA_DIR)
    return app

def main():
    port = 8443
    host = "0.0.0.0"
    app = init_app()

    ssl_context = None
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(CERT_FILE, KEY_FILE)
        print(f"[TARS Web] SSL habilitado. Servidor listo en: https://192.168.1.y:{port}")
    else:
        print(f"[TARS Web] Servidor listo (sin SSL) en: http://192.168.1.y:{port}")

    web.run_app(app, host=host, port=port, ssl_context=ssl_context)

if __name__ == "__main__":
    main()
