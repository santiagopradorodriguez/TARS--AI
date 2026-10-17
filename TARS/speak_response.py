#!/usr/bin/env python3
import sys
import json
import os
import re
import subprocess
import asyncio
import certifi
import edge_tts

sys.path.append("/home/santiago/.gemini/config")
os.environ["SSL_CERT_FILE"] = certifi.where()

VOICE = "es-AR-TomasNeural"
OUTPUT_FILE = "/tmp/antigravity_response.mp3"

def clean_latex_math(math_str):
    math_str = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r" \1 sobre \2 ", math_str)
    math_str = re.sub(r"\\sqrt\{([^{}]+)\}", r" raíz de \1 ", math_str)
    math_str = re.sub(r"\|([^|]+)\|", r" módulo de \1 ", math_str)
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
    math_str = re.sub(r"\\(?:text|mathbf|mathit|mathrm|mathcal|tilde|hat|bar)\{([^{}]*)\}", r" \1 ", math_str)
    math_str = re.sub(r"\^\{2\}|\^2", " al cuadrado ", math_str)
    math_str = re.sub(r"\^\{3\}|\^3", " al cubo ", math_str)
    math_str = re.sub(r"\^\{([^{}]*)\}", r" elevado a la \1 ", math_str)
    math_str = re.sub(r"\^([0-9a-zA-Z])", r" elevado a la \1 ", math_str)
    math_str = re.sub(r"_\{([^{}]*)\}", r" sub \1 ", math_str)
    math_str = re.sub(r"_([0-9a-zA-Z])", r" sub \1 ", math_str)
    math_str = re.sub(r"=", " es igual a ", math_str)
    math_str = re.sub(r"\+", " más ", math_str)
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

    # 12. Dividir por parrafos para pausas de respiracion natural
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    paced_paragraphs = []
    for p in paragraphs:
        if not p.endswith(('.', ':', '!', '?', ';')):
            p += '.'
        paced_paragraphs.append(p)
    text = ' ... '.join(paced_paragraphs)
    text = re.sub(r"\s+", " ", text).strip()
    return text

async def generate_speech(text):
    # -5% rate creates a calmer, more human conversational pace
    communicate = edge_tts.Communicate(text, VOICE, rate="-5%")
    await communicate.save(OUTPUT_FILE)

def main():
    try:
        input_data = sys.stdin.read()
        if not input_data:
            print("{}")
            return

        # Si TARS está apagado (Modo Rojo), no hablar
        state_file = "/home/santiago/.gemini/config/tars_state.json"
        try:
            if os.path.exists(state_file):
                with open(state_file, "r") as sf:
                    sdata = json.load(sf)
                    if sdata.get("mode") == "off" or sdata.get("mute_pc_audio") is True or sdata.get("pc_audio_muted") is True:
                        print("{}")
                        return
        except Exception:
            pass
            
        payload = json.loads(input_data)
        transcript_path = payload.get("transcriptPath") or payload.get("transcript_path")
        if not transcript_path or not os.path.exists(transcript_path):
            convo_id = payload.get("conversationId") or payload.get("conversation_id")
            if convo_id:
                candidate = f"/home/santiago/.gemini/antigravity/brain/{convo_id}/.system_generated/logs/transcript.jsonl"
                if os.path.exists(candidate):
                    transcript_path = candidate
        if not transcript_path or not os.path.exists(transcript_path):
            print("{}")
            return

        last_content = ""
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    step = json.loads(line)
                    if step.get("type") == "PLANNER_RESPONSE" and step.get("source") == "MODEL":
                        c = step.get("content", "")
                        if c:
                            last_content = c
                except Exception:
                    pass

        if last_content:
            clean = clean_text_for_speech(last_content)
            if clean:
                # Enviar notificacion push instantanea al celular (ntfy.sh/tars_santiago_a03) incluso si la pantalla esta apagada
                try:
                    preview = clean[:220]
                    subprocess.Popen(
                        [
                            "curl", "-s",
                            "-H", "Title: TARS - Nuevo mensaje",
                            "-H", "Priority: high",
                            "-H", "Tags: robot,speech_balloon",
                            "-H", "Click: https://" + os.environ.get("TARS_LOCAL_IP", "localhost") + ":8443",
                            "-d", preview,
                            "https://ntfy.sh/tars_santiago_a03"
                        ],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception:
                    pass
                # Limit length to ~1000 characters so it doesn't speak for 10 minutes on huge responses
                if len(clean) > 1000:
                    cut = clean[:1000]
                    last_period = cut.rfind('.')
                    if last_period != -1:
                        clean = cut[:last_period+1] + " ... El resto de la respuesta está en pantalla."
                    else:
                        clean = cut + " ... El resto de la respuesta está en pantalla."
                
                # Kill previous playback immediately so it stops talking right away
                subprocess.run(["pkill", "-9", "-f", "ffplay.*antigravity_response"], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["pkill", "-9", "-f", "tars_player.py"], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Sintetizar usando el motor dual (Puck o Edge-TTS según selección)
                wav_file = OUTPUT_FILE.replace(".mp3", ".wav")
                try:
                    from tars_voice_engine import synthesize_speech
                    synthesize_speech(clean, wav_file)
                except Exception:
                    asyncio.run(generate_speech(clean))
                    subprocess.run(["ffmpeg", "-y", "-i", OUTPUT_FILE, wav_file], 
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                               
                # Launch tars_player to mute mic, play chime, speak, and unmute mic
                subprocess.Popen(["/home/santiago/.gemini/tts_venv/bin/python", 
                                  "/home/santiago/.gemini/config/tars_player.py", wav_file], 
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, 
                                 start_new_session=True)
    except Exception:
        pass

    # Always output empty JSON to fulfill Stop hook contract
    print("{}")

if __name__ == "__main__":
    main()
