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
    print(f"[TARS Web] Consultando a Antigravity: {prompt_text}")
    try:
        cmd = [
            "/home/santiago/.local/bin/agy",
            "--dangerously-skip-permissions",
            "-p",
            f"El usuario te consulta desde su celular en la red local. Responde de forma concisa, en espanol rioplatense y directa (sin introducciones de relleno). Si creas o buscas archivos, indica la ruta. Consulta: {prompt_text}"
        ]
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=90)
        return result.strip()
    except subprocess.TimeoutExpired:
        return "La consulta en Antigravity tomo demasiado tiempo. Intenta con algo mas puntual."
    except subprocess.CalledProcessError as e:
        return f"Error ejecutando en Antigravity: {e.output[:150]}"
    except Exception as e:
        return f"No pude conectar con el cerebro de Antigravity: {e}"

def execute_pc_task(command_text):
    cmd_lower = command_text.lower().strip()
    reply = ""
    media = []

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
        return reply, media

    # 2. Control de Spotify / Multimedia
    if "spotify" in cmd_lower or "musica" in cmd_lower:
        if "pausa" in cmd_lower or "parar" in cmd_lower or "pausar" in cmd_lower:
            subprocess.run(["playerctl", "pause"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Reproduccion de Spotify pausada.", media
        elif "play" in cmd_lower or "reanudar" in cmd_lower or "reproducir" in cmd_lower:
            subprocess.run(["playerctl", "play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Reproduciendo musica en Spotify.", media
        elif "siguiente" in cmd_lower or "pasar" in cmd_lower or "proxima" in cmd_lower:
            subprocess.run(["playerctl", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Pasando a la siguiente cancion.", media
        elif "anterior" in cmd_lower or "previa" in cmd_lower:
            subprocess.run(["playerctl", "previous"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Volviendo a la cancion anterior.", media
        else:
            try:
                title = subprocess.check_output(["playerctl", "metadata", "title"], text=True, timeout=2).strip()
                artist = subprocess.check_output(["playerctl", "metadata", "artist"], text=True, timeout=2).strip()
                return f"Sonando ahora: {title} de {artist}.", media
            except Exception:
                return "Spotify no parece estar reproduciendo contenido en este momento.", media

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
            return "Abriendo el navegador Firefox en la PC.", media
        elif "youtube" in target:
            subprocess.Popen(["xdg-open", "https://youtube.com"])
            return "Abriendo YouTube en la PC.", media
        elif "terminal" in target:
            subprocess.Popen(["gnome-terminal"])
            return "Abriendo una terminal en la PC.", media
        else:
            subprocess.Popen(["xdg-open", target])
            return f"Lanzando {target} en la PC.", media

    # 5. Estado general de la maquina
    if "estado" in cmd_lower or "como estas" in cmd_lower:
        return "Todos los sistemas de TARS estan en linea. Puedo controlar Spotify, tomar capturas de pantalla, crear archivos y abrir programas.", media

    # Consultar directamente al cerebro de Antigravity para todo lo demas
    ai_reply = query_antigravity(command_text)
    
    # Detectar si Antigravity genero o menciono alguna imagen local
    import re
    img_matches = re.findall(r'(/[\w\-./]+\.(?:png|jpg|jpeg|gif))', ai_reply)
    for img_path in img_matches:
        if os.path.exists(img_path):
            img_name = os.path.basename(img_path)
            dest = os.path.join(MEDIA_DIR, img_name)
            if not os.path.exists(dest):
                subprocess.run(["cp", img_path, dest])
            media.append({"type": "image", "url": f"/media/{img_name}", "name": img_name})

    return ai_reply, media

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

        reply_text, media = execute_pc_task(user_text)
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
        subprocess.run(["ffmpeg", "-y", "-i", raw_path, "-ar", "16000", "-ac", "1", wav_path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        user_text = transcribe_wav(wav_path)
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
        else:
            reply_text, media = execute_pc_task(user_text)
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


TRANSCRIPT_PATH = "/home/santiago/.gemini/antigravity/brain/02625e27-4d6d-4e62-bf4b-64dd80390943/.system_generated/logs/transcript.jsonl"

async def handle_sync(request):
    last_idx = int(request.query.get("last_index", 0))
    latest_msg = ""
    latest_idx = 0
    media = []

    if os.path.exists(TRANSCRIPT_PATH):
        try:
            with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        if d.get("type") == "PLANNER_RESPONSE" and d.get("source") == "MODEL" and d.get("content"):
                            latest_msg = d.get("content")
                            latest_idx = d.get("step_index", 0)
                    except:
                        pass
        except Exception as e:
            print(f"[TARS Web] Error leyendo transcript: {e}")

    if latest_idx > last_idx and latest_msg:
        # Extraer imagenes si las hay
        img_matches = re.findall(r'(/[\w\-./]+\.(?:png|jpg|jpeg|gif))', latest_msg)
        for img_path in img_matches:
            if os.path.exists(img_path):
                img_name = os.path.basename(img_path)
                dest = os.path.join(MEDIA_DIR, img_name)
                if not os.path.exists(dest):
                    subprocess.run(["cp", img_path, dest])
                media.append({"type": "image", "url": f"/media/{img_name}", "name": img_name})

        # Generar TTS de la respuesta
        audio_url = await generate_tts_file(latest_msg[:400])
        return web.json_response({
            "has_new": True,
            "step_index": latest_idx,
            "content": latest_msg,
            "media": media,
            "audio_url": audio_url
        })

    return web.json_response({"has_new": False, "step_index": latest_idx})

def init_app():
    app = web.Application()
    app.router.add_get("/", handle_index)
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
