# TARS - Antigravity Mobile & Voice Controller

Asistente inteligente y panel de control remoto para **Google Antigravity IDE** desde dispositivos móviles (Android / iOS) y PC (Linux Mint / Ubuntu / Debian).

Permite controlar conversaciones, inyectar prompts, adjuntar imágenes y archivos, alternar modelos de IA, escuchar respuestas por voz y recibir notificaciones nativas en el celular con la pantalla apagada o la aplicación cerrada.

---

## Arquitectura del Sistema

```
                     ┌──────────────────────────────────────────────┐
                     │          Google Antigravity IDE              │
                     │    (CDP Port / Brain Logs & State)           │
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
            │  - Subida de fotos y docs    │ │  - Wake-word offline (Vosk)  │
            │  - Selector de Modelos IA    │ │  - Audio Edge-TTS en PC      │
            │  - Notificaciones Web Push   │ └──────────────────────────────┘
            │  - Tailscale VPN / Cloudflare│
            └──────────────────────────────┘
```

---

## Requisitos Previos

Antes de empezar, necesitas tener instalado en tu PC:

- **Linux** (Ubuntu 20.04+, Linux Mint, Debian o similar)
- **Python 3.10+** (`python3 --version`)
- **Google Antigravity IDE** corriendo con Chrome DevTools Protocol habilitado
- **Git** (`sudo apt install git`)
- **Tailscale** (para acceso desde el celular fuera de casa): https://tailscale.com/download

---

## Instalación Paso a Paso

### Paso 1 — Clonar el repositorio

```bash
git clone https://github.com/santiagopradorodriguez/TARS--AI.git
cd TARS--AI
```

---

### Paso 2 — Crear entorno virtual e instalar dependencias

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Dependencias principales que se instalan:
- `aiohttp`, `websockets` — servidor web asíncrono y bridge CDP
- `edge-tts` — síntesis de voz neural (voz de Elena y Tomas)
- `vosk`, `SpeechRecognition` — reconocimiento de voz offline
- `pywebpush`, `py-vapid` — notificaciones push en Android

---

### Paso 3 — Configurar tus credenciales

Copiá el archivo de ejemplo y completalo con tus datos:

```bash
cp .env.example ~/.env
nano ~/.env
```

Abrís el archivo y completás estas 3 variables:

```bash
# 1. Tu API Key de Google Gemini
#    Conseguila en: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=AIzaSy...tu_clave_aqui

# 2. La IP de Tailscale de tu PC
#    Corré: tailscale ip -4
#    Te va a dar algo como 100.x.x.x
TARS_LOCAL_IP=100.x.x.x

# 3. Tu email (para las notificaciones push)
TARS_VAPID_EMAIL=tu_email@gmail.com
```

> Si no tenés API Key de Gemini, la conseguís gratis en https://aistudio.google.com/app/apikey

---

### Paso 4 — Descargar el modelo de voz offline (Vosk)

Para que TARS entienda tu voz sin internet:

```bash
mkdir -p ~/.gemini/models
cd ~/.gemini/models
wget https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip
unzip vosk-model-small-es-0.42.zip
cd -
```

---

### Paso 5 — Generar los certificados SSL

TARS corre por HTTPS (necesario para el micrófono y las notificaciones en el celular). Generá un certificado auto-firmado:

```bash
mkdir -p TARS/certs
openssl req -x509 -newkey rsa:4096 -keyout TARS/certs/key.pem -out TARS/certs/cert.pem \
  -days 3650 -nodes -subj "/CN=localhost" \
  -addext "subjectAltName=IP:$(tailscale ip -4),IP:127.0.0.1,DNS:localhost"
```

> Los certificados se generan localmente y nunca se suben a GitHub (están en `.gitignore`).

---

### Paso 6 — Generar las claves VAPID (notificaciones push)

```bash
mkdir -p ~/.gemini/config
cd ~/.gemini/config
python3 -c "
from py_vapid import Vapid01
import json, base64
v = Vapid01()
v.generate_keys()
priv = v.private_key.private_bytes(
    __import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding','PrivateFormat','NoEncryption']).Encoding.PEM,
    __import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding','PrivateFormat','NoEncryption']).PrivateFormat.TraditionalOpenSSL,
    __import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding','PrivateFormat','NoEncryption']).NoEncryption()
).decode()
pub = base64.urlsafe_b64encode(
    v.public_key.public_bytes(
        __import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding','PublicFormat']).Encoding.X962,
        __import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding','PublicFormat']).PublicFormat.UncompressedPoint
    )
).decode().rstrip('=')
json.dump({'private_key': priv, 'public_key': pub}, open('vapid_keys.json','w'), indent=2)
print('Claves VAPID generadas en vapid_keys.json')
"
cd -
```

---

### Paso 7 — Copiar el servidor al directorio de configuración

```bash
cp TARS/tars_web_server.py ~/.gemini/config/tars_web_server.py
```

---

### Paso 8 — Configurar el servicio systemd (arranque automático)

Para que TARS arranque solo cuando prendés la PC:

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/tars-web.service << 'EOF'
[Unit]
Description=TARS Mobile Web Server & Antigravity Worker Bridge (HTTPS 8443)
After=network.target graphical-session.target

[Service]
Type=simple
WorkingDirectory=%h/.gemini/config
ExecStart=%h/.gemini/antigravity/scratch/TARS--AI/venv/bin/python3 %h/.gemini/config/tars_web_server.py
Restart=always
RestartSec=5
EnvironmentFile=%h/.env

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable tars-web.service
systemctl --user start tars-web.service
systemctl --user status tars-web.service
```

Si todo está bien vas a ver `active (running)`.

---

### Paso 9 — Instalar la app en el celular

1. Activá **Tailscale** en tu celular Android/iOS
2. Abrí **Chrome** y entrá a: `https://<TU-IP-TAILSCALE>:8443`
   - Reemplazá `<TU-IP-TAILSCALE>` por lo que te dio el comando `tailscale ip -4`
   - Chrome va a mostrar una advertencia del certificado — tocá **"Configuración avanzada" → "Acceder de todas formas"** (solo la primera vez)
3. Para instalar como app: tocá el menú de tres puntos arriba a la derecha → **"Instalar aplicación"** o **"Agregar a la pantalla principal"**

---

## Uso Diario

### Enviar mensajes por texto o voz
- **Texto**: escribí en la caja inferior y tocá Enviar o Enter
- **Voz**: tocá el micrófono, hablá, volvé a tocar para enviar
- **Cortar**: si la IA está procesando y querés frenarla, tocá el botón **Cortar**

### Silenciar la voz
- Tocá **Voz** en la barra superior para silenciar/activar la respuesta hablada
- También podés silenciarla desde la misma notificación de Android sin abrir la app

### Subir archivos o fotos
- Tocá el clip (adjunto) a la izquierda de la barra de mensaje
- Elegí Cámara, Galería o Archivos
- Agregá un mensaje opcional y tocá Enviar

### Cambiar el modelo de IA
- Tocá **Modelo IA** en la barra superior
- Elegí el modelo y el nivel de esfuerzo (Rapido / Medio / Maximo)

### Cambiar entre conversaciones
- Tocá **Chat** arriba a la derecha para ver y cambiar de conversación

### Elegir qué PC usar (Multi-PC con Tailscale)
- Tocá el nombre de la PC activa arriba a la izquierda
- Se listan automáticamente todas las PCs de tu red Tailscale que tengan TARS activo
- Tocá la que querés usar y TARS redirige todo automáticamente

---

## Actualizar TARS en tu PC

Cuando haya cambios nuevos en el repositorio:

```bash
cd TARS--AI
git pull && chmod +x actualizar_tars.sh && ./actualizar_tars.sh
```

---

## Servicios en Segundo Plano (systemd)

| Servicio | Descripción |
|---|---|
| `tars-web.service` | Servidor Web dual HTTP (8080) / HTTPS (8443) y puente CDP |
| `tars-tunnel.service` | Tunel Cloudflare para Web Push HTTPS verificado en Android |
| `tars-tray.service` | Icono en la bandeja del sistema de Linux |
| `tars-wake-word.service` | Escucha pasiva de palabra de activacion por microfono |

Comandos utiles:

```bash
# Ver estado
systemctl --user status tars-web.service

# Reiniciar
systemctl --user restart tars-web.service

# Ver logs en vivo
journalctl --user -u tars-web.service -f
```

---

## Solución de Problemas

**No puedo conectarme desde el celular**
- Verificá que Tailscale esté activo en ambos dispositivos
- Corré `systemctl --user is-active tars-web.service` — debe decir `active`
- Revisá los logs: `journalctl --user -u tars-web.service -n 50`

**No llegan notificaciones**
- Asegurate de haber activado el botón de notificaciones en la app (campana)
- En Android: mantené presionada una notificación de TARS → configura como "Alerta"
- El servicio `tars-tunnel.service` con Cloudflare es necesario para notificaciones con pantalla apagada

**La voz no funciona**
- Verificá que el modelo Vosk esté descargado en `~/.gemini/models/vosk-model-small-es-0.42`
- Revisá que `edge-tts` esté instalado: `venv/bin/pip show edge-tts`

**El cambio de modelo no funciona**
- Asegurate de que Antigravity IDE esté abierto y visible (no minimizado)
- Los logs del servidor muestran el detalle: `journalctl --user -u tars-web.service -f`

---

## Licencia

Desarrollado por **Santiago Prado Rodriguez**. Distribuido bajo la Licencia MIT.
