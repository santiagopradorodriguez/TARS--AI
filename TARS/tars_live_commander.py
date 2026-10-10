#!/usr/bin/env python3
import os
import sys
import json
import base64
import queue
import asyncio
import threading
import subprocess
import websockets
import sounddevice as sd
import numpy as np

def load_env(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip("'").strip('"')

load_env(os.path.expanduser("~/.env"))
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY no encontrada en ~/.env")
    sys.exit(1)

HOST = "generativelanguage.googleapis.com"
MODEL = "models/gemini-2.5-flash-native-audio-latest"
WS_URL = f"wss://{HOST}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={API_KEY}"

IN_RATE = 16000
IN_CHUNK = 1600  # 100ms exactos recomendados por Google
OUT_RATE = 24000

class TarsLiveCommander:
    def __init__(self):
        self.ws = None
        self.audio_play_queue = queue.Queue()
        self.playback_thread = None
        self.stop_playback = False

    def playback_worker(self):
        """Hilo de reproducción de audio continua sin cortes ni pérdidas."""
        try:
            with sd.RawOutputStream(samplerate=OUT_RATE, channels=1, dtype='int16') as stream:
                while not self.stop_playback:
                    try:
                        data = self.audio_play_queue.get(timeout=0.2)
                        if data is None:
                            break
                        stream.write(data)
                        self.audio_play_queue.task_done()
                    except queue.Empty:
                        continue
        except Exception as e:
            print(f"\n[Error reproduciendo audio]: {e}")

    async def setup(self):
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
                    }
                },
                "systemInstruction": {
                    "parts": [{"text": (
                        "Eres TARS, el asistente del sistema de esta PC con Pop!_OS Linux. "
                        "Hablas siempre en español rioplatense, conciso, inteligente y natural. "
                        "Tienes acceso a ejecutar comandos en la computadora del usuario mediante la herramienta 'ejecutar_comando'. "
                        "Usa 'xdg-open <url o app>' para abrir cosas, o comandos estándar de bash. "
                        "Responde de forma breve y fluida como en una conversación real."
                    )}]
                },
                "tools": [{
                    "functionDeclarations": [{
                        "name": "ejecutar_comando",
                        "description": "Ejecuta un comando en la terminal bash de Pop OS Linux.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "comando": {
                                    "type": "STRING",
                                    "description": "El comando bash a ejecutar."
                                }
                            },
                            "required": ["comando"]
                        }
                    }]
                }]
            }
        }
        await self.ws.send(json.dumps(setup_msg))
        resp = await self.ws.recv()
        data = json.loads(resp)
        if "setupComplete" in data:
            print(">> Conexión con Gemini Live establecida con éxito.")

        # Disparar saludo inicial automático de TARS
        greeting_msg = {
            "clientContent": {
                "turns": [
                    {
                        "role": "user",
                        "parts": [{"text": "Saluda brevemente con: Sistemas listos. Te escucho, Santiago."}]
                    }
                ],
                "turnComplete": True
            }
        }
        await self.ws.send(json.dumps(greeting_msg))

    async def mic_task(self):
        """Lee el micrófono, muestra un indicador de volumen visual y manda a Gemini."""
        loop = asyncio.get_event_loop()
        audio_in_queue = asyncio.Queue()

        def mic_callback(indata, frames, time_info, status):
            loop.call_soon_threadsafe(audio_in_queue.put_nowait, bytes(indata))

        with sd.RawInputStream(samplerate=IN_RATE, channels=1, dtype='int16', blocksize=IN_CHUNK, callback=mic_callback):
            while True:
                data = await audio_in_queue.get()
                
                # Cálculo de volumen RMS para feedback visual
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(samples ** 2))
                
                # Si hay sonido por encima del ruido de fondo, mostramos vúmetro
                if rms > 200:
                    bars = min(int(rms / 150), 15)
                    meter = "█" * bars + "░" * (15 - bars)
                    sys.stdout.write(f"\r🎤 [Voz detectada: |{meter}| {int(rms):4d}] ")
                    sys.stdout.flush()

                # Ganancia digital x1.8 para que Gemini escuche claro sin forzar la voz
                boosted_samples = np.clip(samples * 1.8, -32768, 32767).astype(np.int16)
                b64_audio = base64.b64encode(boosted_samples.tobytes()).decode('utf-8')
                msg = {
                    "realtimeInput": {
                        "mediaChunks": [
                            {
                                "mimeType": f"audio/pcm;rate={IN_RATE}",
                                "data": b64_audio
                            }
                        ]
                    }
                }
                if self.ws:
                    await self.ws.send(json.dumps(msg))

    async def execute_command(self, call_id, command):
        print(f"\n\n⚙️ [TARS EJECUTANDO]: {command}")
        try:
            result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, timeout=5)
            output_str = result.decode('utf-8', errors='replace')
            success = True
        except subprocess.TimeoutExpired:
            output_str = "Comando lanzado en segundo plano (aplicación gráfica iniciada)."
            success = True
        except subprocess.CalledProcessError as e:
            output_str = e.output.decode('utf-8', errors='replace')
            success = False
        except Exception as e:
            output_str = str(e)
            success = False

        print(f"📄 [Salida]: {output_str.strip()[:150]}")

        resp = {
            "toolResponse": {
                "functionResponses": [
                    {
                        "id": call_id,
                        "name": "ejecutar_comando",
                        "response": {
                            "resultado": "éxito" if success else "error",
                            "salida": output_str
                        }
                    }
                ]
            }
        }
        await self.ws.send(json.dumps(resp))

    async def receive_task(self):
        """Recibe texto, audio y herramientas de Gemini."""
        async for msg in self.ws:
            data = json.loads(msg)

            if "serverContent" in data:
                sc = data["serverContent"]

                # Interrupción del usuario (barge-in): si hablas mientras TARS habla, se calla
                if sc.get("interrupted"):
                    print("\n\n⚡ [Interrumpido por el usuario]")
                    while not self.audio_play_queue.empty():
                        try:
                            self.audio_play_queue.get_nowait()
                            self.audio_play_queue.task_done()
                        except Exception:
                            break

                if "modelTurn" in sc:
                    for p in sc["modelTurn"].get("parts", []):
                        # Mostrar el texto que va pensando/diciendo
                        if "text" in p and p["text"].strip():
                            t = p["text"].strip()
                            if not t.startswith("**"):
                                print(f"\n🤖 TARS: {t}")

                        # Reproducir audio PCM
                        if "inlineData" in p:
                            b64data = p["inlineData"].get("data", "")
                            if b64data:
                                pcm_bytes = base64.b64decode(b64data)
                                self.audio_play_queue.put(pcm_bytes)

            if "toolCall" in data:
                calls = data["toolCall"].get("functionCalls", [])
                for call in calls:
                    if call.get("name") == "ejecutar_comando":
                        call_id = call.get("id")
                        comando = call.get("args", {}).get("comando", "")
                        await self.execute_command(call_id, comando)

    async def run(self):
        print("="*60)
        print("🤖 INICIANDO TARS CONECTADO A GEMINI LIVE (TIEMPO REAL)...")
        print("="*60)

        # Iniciar hilo de reproducción
        self.playback_thread = threading.Thread(target=self.playback_worker, daemon=True)
        self.playback_thread.start()

        async with websockets.connect(WS_URL) as ws:
            self.ws = ws
            await self.setup()

            print("\n" + "="*60)
            print("🚀 TARS ONLINE: ¡Háblale directamente al micrófono!")
            print("💡 Tip: Verás la barra de volumen cuando detecte tu voz.")
            print("="*60 + "\n")

            await asyncio.gather(
                self.mic_task(),
                self.receive_task()
            )

if __name__ == "__main__":
    commander = TarsLiveCommander()
    try:
        asyncio.run(commander.run())
    except KeyboardInterrupt:
        print("\n\nApagando TARS Live Commander...")
        commander.stop_playback = True
        sys.exit(0)
