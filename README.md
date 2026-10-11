# TARS - Antigravity Mobile & Voice Controller

Asistente inteligente y panel de control remoto para **Google Antigravity IDE** desde dispositivos móviles (Android / iOS) y PC (Linux Mint / Ubuntu / Debian).

Permite controlar conversaciones, inyectar prompts, adjuntar imágenes y archivos, alternar modelos de IA, escuchar respuestas por voz y recibir notificaciones nativas en el celular con la pantalla apagada o la aplicación cerrada.

---

## Arquitectura del Sistema

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
            │  - Subida de fotos y docs    │ │  - Wake-word offline (Vosk)  │
            │  - Selector de Modelos IA    │ │  - Audio Edge-TTS en PC      │
            │  - Notificaciones Web Push   │ └──────────────────────────────┘
            │  - Tailscale VPN / Cloudflare│
            └──────────────────────────────┘
```

---

## Características Principales

### TARS Mobile (PWA Instalable)
- **Subida de Imágenes, Fotos y Archivos**: Adjuntá fotos tomadas con la cámara del celular, capturas de pantalla, documentos PDF o archivos de código directamente al chat de Antigravity IDE mediante inyección nativa por CDP (`DOM.setFileInputFiles`).
- **Selector de Modelos de IA en Vivo**: Alterná el modelo de lenguaje de Antigravity en tiempo real desde el celular:
  - **Gemini 3.8 Flash** (con selector de esfuerzo de razonamiento: *Rápido / Medio / Máximo*)
  - **Gemini 3.7 Flash** / **Gemini 3.6 Flash** / **Gemini 3.1 Pro**
  - **Claude Sonnet 4.6 (Thinking)**
  - **Claude Opus 4.6 (Thinking)**
  - **GPT-OSS 120B (Medium)**
- **Navegación y Conmutación de Chats**: Explorá las conversaciones abiertas en el IDE y cambiá de chat con un solo toque o mediante botones de anterior / siguiente.
- **Notificaciones Push estilo WhatsApp**:
  - Alertas nativas en la barra de Android con vibración háptica triple (`[300ms, 120ms, 300ms, 120ms, 400ms]`) y banner flotante superior.
  - Funcionan en segundo plano **con la pantalla bloqueada o el navegador cerrado**, mediante Service Worker (`sw.js`) y VAPID / FCM.
  - Deduplicación estricta por ID de paso para evitar notificaciones repetidas.
- **Doble Motor de Voz & TTS**:
  - Reconocimiento de voz por micrófono en español rioplatense (`es-AR`) con fallback offline instantáneo mediante **Vosk**.
  - Respuestas habladas automáticas ultra-naturales con **Microsoft Edge-TTS** (`es-AR-ElenaNeural` en el celular y `es-AR-TomasNeural` en la PC).
  - Control remoto para silenciar o activar los parlantes de la PC desde el celular.
- **Inyección Bidireccional en Antigravity IDE**: Comunicación de ultra-baja latencia vía Chrome DevTools Protocol (CDP) con foco emulado en segundo plano, streaming de razonamiento (`thinking`) y visualización de herramientas en ejecución.
- **Conectividad Segura en Cualquier Lugar**:
  - Acceso remoto cifrado punto a punto vía **Tailscale Mesh VPN**.
  - Soporte integrado para túneles HTTPS con Cloudflare.

---

## Instalación y Configuración

### 1. Clonar el Repositorio
```bash
git clone https://github.com/santiagopradorodriguez/Jarvis.git
cd Jarvis
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

## Instrucciones de Uso

### 1. Conectarse desde el Celular e Instalar la App (PWA)
Podés acceder a TARS tanto dentro de tu casa como desde la calle (colectivo, datos móviles o cualquier otra red Wi-Fi):

1. **Vía Tailscale VPN (Recomendado para cualquier lugar)**:
   - Activá la app de **Tailscale** en tu celular Android/iOS.
   - Abrí Chrome y entrá a: `https://<IP-TAILSCALE-PC1>:8443` (o `http://<IP-TAILSCALE-PC1>:8080`).
2. **Vía Túnel HTTPS de Cloudflare (Para Web Push con certificado público)**:
   - Consultá la URL activa del túnel ejecutando en la PC:
     ```bash
     journalctl --user -u tars-tunnel.service -n 30 | grep trycloudflare
     ```
   - Abrí el enlace `https://xxxx.trycloudflare.com` en Chrome desde tu celular.
3. **Instalar como Aplicación Nativa**:
   - En Chrome, tocá el menú de tres puntos arriba a la derecha y elegí **"Instalar aplicación"** o **"Agregar a la pantalla principal"**.
   - TARS quedará instalada en tu cajón de aplicaciones con su propio ícono y a pantalla completa.

---

### 2. Activar las Notificaciones Push y Vibración
Para que el celular vibre y te muestre alertas tipo WhatsApp cuando Antigravity termina una tarea (incluso con la pantalla apagada o mientras usás otra app):

1. En la barra superior de TARS, tocá el botón **Notificaciones OFF** para activarlas.
2. Cuando el navegador te pida permiso de notificaciones, tocá **"Permitir"**.
3. En Android, para asegurar que la notificación suene, vibre y despliegue el cartel emergente superior:
   - Mantené presionada la primera notificación de TARS que recibas (o andá a *Ajustes → Aplicaciones → Chrome → Notificaciones*).
   - Asegurate de que la categoría del sitio esté configurada en **"Alerta"** y con **"Mostrar como ventana emergente"** activado.

---

### 3. Enviar Mensajes por Texto, por Voz y Cortar Procesamiento
- **Por Texto**: Escribí tu mensaje o instrucción en la caja inferior y presioná el botón de enviar o `Enter`. Tu prompt se inyectará automáticamente en la ventana activa de Antigravity IDE aunque la laptop tenga la pantalla bloqueada o en otra ventana.
- **Por Voz**:
  1. Tocá el botón del micrófono en la barra inferior.
  2. Hablá normalmente en español; al terminar de hablar tocá el micrófono de nuevo para enviarlo.
- **Cortar Grabación o Procesamiento**:
  - **Mientras estás grabando un audio**: Tocá el botón rojo **Cancelar** al lado del micrófono para descartar el audio sin enviarlo si te equivocaste o hubo ruido.
  - **Si el mensaje salió mal o querés frenar a la IA**: Tocá **Cortar** (al lado del micrófono, debajo de tu mensaje enviado o dentro de la tarjeta azul *"Antigravity pensando..."*). Esto aborta el envío en curso y presiona automáticamente *Cancel (Ctrl+D)* en Antigravity IDE para detener el procesamiento al instante.
- **Control de Voz y Modo Silencioso**:
  - **Desde la App**: Tocá el botón **Voz** para pasarlo a **Mudo** (rojo). Si Elena estaba hablando se calla en el acto, y los próximos mensajes entrarán en silencio (solo texto y vibración) sin hablarte en voz alta cuando estés ocupado o en una reunión.
  - **Desde la Notificación de Android**: Cada notificación que te llega arriba incluye el botón rápido **Silenciar voz** (o **Activar voz**) para callar o activar la voz sin siquiera abrir la aplicación.
  - **PC**: Activa o silencia los parlantes de la laptop de forma remota.

---

### 4. Subir Imágenes, Fotos de Cámara y Documentos
Podés mandarle fotos, capturas de pantalla, archivos `.txt`, `.pdf`, `.py`, `.js`, `.json`, `.zip`, etc. directamente a Antigravity desde el celular:

1. Tocá el botón del clip a la izquierda de la barra de mensaje.
2. Elegí sacar una foto con la **Cámara**, seleccionar una imagen de la **Galería** o buscar cualquier documento en tus **Archivos** (podés seleccionar varios a la vez).
3. Verás una barra de vista previa encima del cuadro de texto con las miniaturas y nombres de los archivos seleccionados (podés quitar cualquiera tocando la X).
4. Escribí un mensaje opcional (por ejemplo: *"Qué dice esta imagen?"* o *"Revisá este archivo"*) o usá el micrófono, y tocá **Enviar**.
   - Si no escribís ningún texto y tocás enviar, TARS le pedirá automáticamente a Antigravity que analice el archivo adjunto.

---

### 5. Cambiar de Modelo de IA en Vivo
Podés alternar qué cerebro usa Antigravity en cualquier momento sin tocar la PC:

1. Tocá el botón **Modelo IA** en la barra superior de la app.
2. Se abrirá el panel con todos los modelos disponibles e indicará cuál está seleccionado actualmente:
   - **Gemini 3.8 Flash**: Incluye 3 botones rápidos para elegir el nivel de pensamiento (**Rapido**, **Medio**, **Maximo**).
   - **Gemini 3.7 Flash** / **Gemini 3.6 Flash** / **Gemini 3.1 Pro**
   - **Claude Sonnet 4.6 (Thinking)** / **Claude Opus 4.6 (Thinking)**
   - **GPT-OSS 120B (Medium)**
3. Tocá el modelo (o nivel de esfuerzo) que quieras usar; TARS lo cambiará en tiempo real dentro de Antigravity IDE y actualizará el indicador superior.

---

### 6. Cambiar entre Conversaciones de Antigravity
- **Lista de Chats**: Tocá el botón **Chat** arriba a la derecha para ver todas las conversaciones recientes de Antigravity IDE (con su título e indicador del chat actual). Tocá cualquiera para saltar a esa conversación y cargar su historial en el celular.
- **Navegación Rápida**: Usá los botones **Anterior** y **Siguiente** dentro del panel para pasar rápidamente de un chat a otro.
- **Por Comando de Voz o Texto**: También podés decir o escribir *"cambiá al chat de..."* o *"siguiente chat"*.

---

### 7. Elegir qué PC con Antigravity Usar (Multi-PC en Tailscale)
Si estás trabajando con dos o más computadoras con Antigravity (por ejemplo **Lenovo Yoga** `<IP-TAILSCALE-PC1>` y **Pop!_OS** `<IP-TAILSCALE-PC2>`):

1. Tocá el botón **Lenovo Yoga** (o **Pop!_OS**) arriba a la izquierda en la barra superior de TARS.
2. Se abrirá el panel **"Elegir PC con Antigravity"**, que detecta automáticamente todas tus PCs conectadas a tu red **Tailscale** y verifica en vivo si tienen TARS activo.
3. **Tocá la PC que quieras usar**:
   - Sin cambiar de aplicación ni aceptar certificados nuevos, TARS enruta automáticamente tus mensajes, audios, lista de chats y notificaciones hacia la PC elegida.
   - Si querés abrir el servidor web de la otra PC en una pestaña directa, también tenés el botón **Directo** al lado de cada PC.
4. **Para actualizar ambas PCs con las últimas mejoras desde GitHub**:
   En cualquiera de tus PCs, entrá a la carpeta del repositorio y ejecutá:
   ```bash
   git pull && chmod +x actualizar_tars.sh && ./actualizar_tars.sh
   ```

---

### 8. Comandos Rápidos del Sistema y Uso en PC
Además de conversar con Antigravity, TARS reconoce comandos directos para controlar tu Linux:
- **Música / Multimedia**: *"Pone música"*, *"Pausa la música"*, *"Siguiente canción"*, *"Subí el volumen"*, *"Bajá el volumen"*.
- **Capturas de Pantalla de la PC**: *"Sacá una captura de pantalla"* (toma una captura del escritorio de tu PC y te la muestra).
- **Notas Rápidas**: *"Anotá comprar café"* o *"Leé mis notas"*.
- **Modo Escucha en PC (Wake-Word)**: Cuando estás frente a la laptop, podés activar la escucha por micrófono desde el ícono de bandeja del sistema (`tars-tray`) o mediante el atajo de teclado configurado para hablarle directamente a TARS sin abrir el navegador.

---

## Servicios en Segundo Plano (systemd)

TARS se ejecuta como servicios de usuario de `systemd` para arranque automático y tolerancia a fallos:

| Servicio | Descripción |
|---|---|
| `tars-web.service` | Servidor Web dual HTTP (8080) / HTTPS (8443) y puente CDP |
| `tars-tunnel.service` | Túnel Cloudflare para Web Push HTTPS verificado en Android |
| `tars-tray.service` | Icono en la bandeja del sistema de Linux |
| `tars-wake-word.service` | Escucha pasiva de palabra de activación por micrófono |

Comandos útiles de administración:
```bash
# Ver estado de los servicios
systemctl --user status tars-web.service tars-tunnel.service

# Reiniciar el servidor web de TARS
systemctl --user restart tars-web.service

# Ver logs en tiempo real
journalctl --user -u tars-web.service -f
```

---

## Licencia

Desarrollado por **Santiago Prado Rodriguez**. Distribuido bajo la Licencia MIT.
