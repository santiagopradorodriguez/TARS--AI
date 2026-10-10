# 🤖 TARS - Antigravity Mobile & Voice Controller

Asistente inteligente y panel de control remoto para **Google Antigravity IDE** desde dispositivos móviles (Android / iOS) y PC (Linux Mint / Ubuntu / Debian).

Permite controlar conversaciones, inyectar prompts, alternar modelos de IA, escuchar respuestas por voz y recibir notificaciones nativas en el celular con la pantalla apagada o la aplicación cerrada.

---

## 🏗️ Arquitectura del Sistema

```
                     ┌──────────────────────────────────────────────┐
                     │          Google Antigravity IDE              │
                     │    (CDP Port 35089 / Brain Logs & State)     │
                     └──────────────────────┬───────────────────────┘
                                            │
                     ┌──────────────────────┴───────────────────────┐
                     │           TARS Web Bridge Server             │
                     │          (tars_web_server.py:8443)           │
                     └──────────┬───────────────────────┬───────────┘
                                │                       │
            ┌───────────────────┴──────────┐ ┌──────────┴───────────────────┐
            │   TARS Mobile PWA (Celular)  │ │   TARS PC Daemon / Tray      │
            │  - Control remoto total      │ │  - Acceso directo rápido     │
            │  - Selector de Modelos IA    │ │  - Wake-word offline (Vosk)  │
            │  - Notificaciones Web Push   │ │  - Audio Edge-TTS en PC      │
            │  - Tailscale VPN / Cloudflare│ └──────────────────────────────┘
            └──────────────────────────────┘
```

---

## ✨ Características Principales

### 📱 TARS Mobile (PWA Instalable)
- **🧠 Selector de Modelos de IA en Vivo**: Alterná el modelo de lenguaje de Antigravity en tiempo real desde el celular:
  - **Gemini 3.8 Flash** (con selector de esfuerzo de razonamiento: *Rápido / Medio / Máximo*)
  - **Gemini 3.7 Flash** / **Gemini 3.6 Flash** / **Gemini 3.1 Pro**
  - **Claude Sonnet 4.6 (Thinking)**
  - **Claude Opus 4.6 (Thinking)**
  - **GPT-OSS 120B (Medium)**
- **💬 Navegación y Conmutación de Chats**: Explorá las conversaciones abiertas en el IDE y cambiá de chat con un solo toque o mediante botones de anterior / siguiente.
- **🔔 Notificaciones Push estilo WhatsApp**:
  - Alertas nativas en la barra de Android con vibración háptica triple (`[300ms, 120ms, 300ms, 120ms, 400ms]`) y banner flotante superior.
  - Funcionan en segundo plano **con la pantalla bloqueada o el navegador cerrado**, mediante Service Worker (`sw.js`) y VAPID / FCM.
  - Deduplicación estricta por ID de paso para evitar notificaciones repetidas.
- **🎙️ Doble Motor de Voz & TTS**:
  - Reconocimiento de voz por micrófono en español rioplatense (`es-AR`) con fallback offline instantáneo mediante **Vosk**.
  - Respuestas habladas automáticas ultra-naturales con **Microsoft Edge-TTS** (`es-AR-ElenaNeural` en el celular y `es-AR-TomasNeural` en la PC).
  - Control remoto para silenciar o activar los parlantes de la PC desde el celular.
- **⚡ Inyección Bidireccional en Antigravity IDE**: Comunicación de ultra-baja latencia vía Chrome DevTools Protocol (CDP) con foco emulado en segundo plano, streaming de razonamiento (`thinking`) y visualización de herramientas en ejecución.
- **🌐 Conectividad Segura en Cualquier Lugar**:
  - Acceso remoto cifrado punto a punto vía **Tailscale Mesh VPN**.
  - Soporte integrado para túneles HTTPS con Cloudflare.

---

## 🛠️ Instalación y Configuración

### 1. Clonar el Repositorio
```bash
git clone https://github.com/santiagopradorodriguez/TARS-AI.git
cd TARS-AI
```

### 2. Crear Entorno Virtual e Instalar Dependencias
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Dependencias principales:
- `aiohttp`, `websockets` (servidor HTTP/HTTPS asíncrono y CDP bridge)
- `edge-tts` (síntesis de voz neural de alta calidad)
- `vosk`, `SpeechRecognition` (reconocimiento de voz offline y online)
- `pywebpush`, `py-vapid` (notificaciones Web Push para Chrome en Android)

### 3. Modelo Offline Vosk (Español)
Descargar el modelo ligero en español dentro de `~/.gemini/models/`:
```bash
mkdir -p ~/.gemini/models
cd ~/.gemini/models
wget https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip
unzip vosk-model-small-es-0.42.zip
```

---

## ⚙️ Servicios en Segundo Plano (systemd)

TARS se ejecuta como servicios de usuario de `systemd` para arranque automático y tolerancia a fallos:

| Servicio | Descripción |
|---|---|
| `tars-web.service` | Servidor Web dual HTTP (8080) / HTTPS (8443) y puente CDP |
| `tars-tunnel.service` | Túnel Cloudflare para Web Push HTTPS verificado en Android |
| `tars-tray.service` | Ícono en la bandeja del sistema de Linux |
| `tars-wake-word.service` | Escucha pasiva de palabra de activación por micrófono |

Comandos útiles:
```bash
# Iniciar / Reiniciar servidor TARS
systemctl --user restart tars-web.service

# Ver logs en vivo
journalctl --user -u tars-web.service -f
```

---

## 📱 Conexión desde el Celular

1. **Vía Tailscale (Recomendado)**:
   - Conectá tu celular a tu red Tailscale.
   - Abrí en Chrome: `https://100.x.x.a:8443` (o `http://100.x.x.a:8080`).
2. **Instalar como App**:
   - En Google Chrome, tocá el menú de tres puntos (`⋮`) y seleccioná **"Instalar aplicación"** o **"Agregar a la pantalla principal"**.
3. **Habilitar Notificaciones**:
   - Tocá el botón **🔔 ON** y aceptá el permiso de notificaciones para habilitar la vibración y las alertas en segundo plano estilo WhatsApp.

---

## 📄 Licencia

Desarrollado por **Santiago Prado Rodriguez**. Distribuido bajo la Licencia MIT.
