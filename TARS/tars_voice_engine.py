#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import base64
import wave
import subprocess
import websockets
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
except Exception:
    pass

STATE_FILE = "/home/santiago/.gemini/config/tars_state.json"
DEFAULT_EDGE_VOICE = "es-AR-TomasNeural"
HOST = "generativelanguage.googleapis.com"
MODEL = "models/gemini-2.5-flash-native-audio-latest"

def load_env(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip("'").strip('"')

def get_voice():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("voice", "edge")
    except Exception:
        pass
    return "edge"

def set_voice(voice_name):
    try:
        data = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
        data["voice"] = voice_name
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)
        return True
    except Exception as e:
        print(f"Error guardando voz: {e}", file=sys.stderr)
        return False

def clean_edge_text(t):
    import re
    t = re.sub(r"/([aeiouAEIOUÁÉÍÓÚ])/", r" vocal \1 ", t)
    t = re.sub(r"/([a-zA-ZáéíóúÁÉÍÓÚñÑ0-9]+)/", r" \1 ", t)
    t = re.sub(r"\by/o\b", " y o ", t, flags=re.IGNORECASE)
    t = t.replace("/", " ").replace("\\", " ").replace("$", " ").replace("_", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t

async def _synthesize_edge_async(text, output_wav):
    text = clean_edge_text(text)
    tmp_mp3 = output_wav + ".tmp.mp3"
    communicate = edge_tts.Communicate(text, DEFAULT_EDGE_VOICE, rate="-5%")
    await communicate.save(tmp_mp3)
    if os.path.exists(tmp_mp3):
        subprocess.run(["ffmpeg", "-y", "-i", tmp_mp3, output_wav],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            os.remove(tmp_mp3)
        except Exception:
            pass
        return os.path.exists(output_wav)
    return False

def synthesize_edge(text, output_wav):
    try:
        return asyncio.run(_synthesize_edge_async(text, output_wav))
    except Exception as e:
        print(f"Error Edge-TTS: {e}", file=sys.stderr)
        return False

async def _synthesize_puck_async(text, output_wav):
    load_env(os.path.expanduser("~/.env"))
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY no encontrada")

    ws_url = f"wss://{HOST}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={api_key}"
    async with websockets.connect(ws_url) as ws:
        setup_msg = {
            "setup": {
                "model": MODEL,
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": "Puck"
                            }
                        }
                    },
                    "thinkingConfig": {
                        "thinkingBudget": 0
                    }
                },
                "systemInstruction": {
                    "parts": [{"text": "Eres un sintetizador de voz en español rioplatense. Tu única tarea es leer en voz alta exactamente el texto que se te indica, sin agregar comentarios, saludos ni explicaciones."}]
                }
            }
        }
        await ws.send(json.dumps(setup_msg))
        await ws.recv()  # setupComplete

        req_msg = {
            "clientContent": {
                "turns": [
                    {
                        "role": "user",
                        "parts": [{"text": f"Lee en voz alta exactamente: {text}"}]
                    }
                ],
                "turnComplete": True
            }
        }
        await ws.send(json.dumps(req_msg))

        pcm_data = bytearray()
        while True:
            resp = await ws.recv()
            data = json.loads(resp)
            if "serverContent" in data:
                sc = data["serverContent"]
                if "modelTurn" in sc:
                    for p in sc["modelTurn"].get("parts", []):
                        if "inlineData" in p:
                            b64 = p["inlineData"].get("data", "")
                            if b64:
                                pcm_data.extend(base64.b64decode(b64))
                if sc.get("turnComplete"):
                    break

        if not pcm_data:
            raise ValueError("No se recibió audio de Gemini Live")

        with wave.open(output_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(pcm_data)

        return os.path.exists(output_wav)

def synthesize_puck(text, output_wav):
    try:
        return asyncio.run(asyncio.wait_for(_synthesize_puck_async(text, output_wav), timeout=25.0))
    except Exception as e:
        print(f"Fallo síntesis Puck ({e}). Usando fallback Edge-TTS.", file=sys.stderr)
        return False

def synthesize_speech(text, output_wav, voice=None):
    if voice is None:
        voice = get_voice()

    if voice == "puck":
        success = synthesize_puck(text, output_wav)
        if success:
            return True
        # Fallback automático a Edge si falla Puck
        return synthesize_edge(text, output_wav)
    else:
        return synthesize_edge(text, output_wav)

if __name__ == "__main__":
    if len(sys.argv) > 2:
        txt = sys.argv[1]
        out = sys.argv[2]
        v = sys.argv[3] if len(sys.argv) > 3 else None
        res = synthesize_speech(txt, out, v)
        print("OK" if res else "FAIL")
    else:
        print(f"Voz actual: {get_voice()}")
