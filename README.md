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

## Instalación Rápida (Recomendada)

El proyecto incluye un instalador interactivo automatizado que configura todo el entorno, dependencias, modelo de voz offline, certificados SSL y el servicio en segundo plano:

```bash
git clone https://github.com/santiagopradorodriguez/TARS--AI.git
cd TARS--AI
chmod +x install.sh
./install.sh
```

El script se encargará automáticamente de:
1. Detectar tu distribución Linux e instalar dependencias del sistema.
2. Crear el entorno virtual (`venv`) e instalar librerías (`requirements.txt`).
3. Descargar y configurar el modelo de reconocimiento de voz offline (Vosk en español).
4. Detectar tu red Tailscale y generar certificados SSL (Let's Encrypt oficial o local).
5. Configurar e iniciar el servicio en segundo plano `tars-web.service`.
6. Mostrar en pantalla el **Código QR interactivo** para que escanees desde tu celular.

---

## Conexión desde el Celular

### 1. App Nativa Oficial de Android (APK Firmado)
La forma más cómoda y recomendada para usar TARS en tu teléfono Android:
- Descargá el APK oficial firmado directamente desde [GitHub Releases](https://github.com/santiagopradorodriguez/TARS--AI/releases).
- Instalá el archivo `TARS-Assistant.apk` en tu dispositivo Android.
- Al abrirla por primera vez, te solicitará la IP local de tu PC (que podés consultar con `hostname -I` en tu terminal) o tu dominio de Tailscale.
- Incluye soporte nativo de notificaciones flotantes con sonido y vibración estilo WhatsApp, control de micrófono y selección automática de red.

### 2. Escaneo Rápido con Código QR (Navegador / PWA)
Al finalizar la instalación (o cada vez que ejecutes TARS), la terminal imprimirá un código QR:
- Abrí la cámara de tu celular (Android o iOS).
- Apuntá al código QR que aparece en tu monitor.
- Tocá el enlace para abrir la aplicación directamente en tu navegador o instalarla como PWA.

### 3. Conexión Privada con Tailscale y SSL Oficial (PWA 1-Click)
Para que Chrome en Android permita instalar TARS como una aplicación web nativa con candado verde sin advertencias de certificado:

1. Instalá [Tailscale](https://tailscale.com/download) en tu PC y en tu celular.
2. En tu panel de administración web de Tailscale: [login.tailscale.com/admin/dns](https://login.tailscale.com/admin/dns), bajá hasta la sección **HTTPS Certificates** y hacé clic en **"Enable HTTPS"**.
3. Ejecutá `./install.sh` en tu PC. TARS detectará automáticamente tu dominio MagicDNS y generará el certificado oficial de **Let's Encrypt**.
4. Abrí en tu celular tu dominio de Tailscale:
   ```text
   https://<tu-maquina>.<tu-red>.ts.net:8443
   ```
5. Verás el candado verde 100% seguro y podrás usar TARS desde cualquier lugar fuera de tu casa.

---

## Instalación Manual (Avanzada)

Si preferís realizar la instalación paso a paso manualmente:

### Paso 1 — Crear entorno virtual e instalar dependencias
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Paso 2 — Descargar modelo Vosk de reconocimiento de voz
```bash
mkdir -p ~/.config/tars/models
cd ~/.config/tars/models
wget https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip
unzip vosk-model-small-es-0.42.zip
cd -
```

### Paso 3 — Generar certificados SSL
```bash
mkdir -p TARS/certs
# Si usas Tailscale con MagicDNS habilitado:
tailscale cert --cert-file TARS/certs/cert.pem --key-file TARS/certs/key.pem <tu-dominio>.ts.net

# O generar certificado local autofirmado:
openssl req -x509 -newkey rsa:2048 -keyout TARS/certs/key.pem -out TARS/certs/cert.pem \
  -days 3650 -nodes -subj "/CN=localhost" \
  -addext "subjectAltName=IP:127.0.0.1,IP:$(hostname -I | awk '{print $1}'),DNS:localhost"
```

### Paso 4 — Iniciar el servidor
```bash
python3 TARS/tars_web_server.py
```

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
