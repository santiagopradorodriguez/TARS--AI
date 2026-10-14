# Plan de Implementacion - Agente 1: Maquetacion HTML y Dock Tactico

## Objetivo
Reestructurar completamente `TARS/web/index.html` para transformarlo en la interfaz táctica tipo HUD de 4 módulos independientes, manteniendo intactos todos los IDs que el motor JavaScript necesita.

## Archivo Afectado
- `TARS/web/index.html`

## Reglas Obligatorias
- Cero emojis en texto, atributos o comentarios. Usar únicamente iconos SVG vectoriales limpios.
- No romper ni renombrar ningún ID requerido por el frontend JavaScript.
- Mobile-first: la estructura debe estar pensada para visualización y control táctil en teléfonos.

---

## Estructura Requerida de index.html

### 1. Encabezado Táctico (Header)
- Marca TARS con versión y estado general.
- Contenedor del reactor osciloscopio:
  - `<canvas id="tars-core-canvas" width="220" height="42"></canvas>`
  - `<div class="core-readout-wrap">` con:
    - `<span id="hud-status-dot" class="status-indicator online"></span>`
    - `<span id="core-state-readout">STATE // STANDBY</span>`
- Contenedores de botones rápidos en cabecera:
  - Botón selector de PCs: `id="pc-selector-btn"` con `id="current-pc-title"`
  - Botón selector de chats: `id="chat-selector-btn"` con `id="current-chat-title"`
  - Botón selector de modelos IA: `id="model-selector-btn"` con `id="current-model-title"`
  - Botón de notificaciones push: `id="notify-toggle-btn"` con `id="notify-btn-label"`
  - Botón de silenciar voz móvil: `id="mobile-voice-toggle-btn"` con iconos `mobile-voice-on-icon` y `mobile-voice-off-icon`
  - Botón de silenciar PC: `id="pc-sound-toggle-btn"` con iconos `pc-sound-on-icon` y `pc-sound-off-icon`
  - Botón de instalación PWA: `id="pwa-install-btn"`

### 2. Barra Flotante de Audio (Audio Control Bar)
- Elemento `id="audio-control-bar"` con clase `hidden`.
- Lectura de estado: `id="audio-status-text"` ("SINTESIS VOCAL ACTIVA").
- Botón de pausa: `id="audio-pause-btn"` con `id="pause-icon"` y `id="play-icon"`.
- Botón de detener: `id="audio-stop-btn"`.

### 3. Modulo 1: Chat y Asistente (`id="view-chat" class="hud-module-view active"`)
- Contenedor principal de mensajes: `id="chat-container"`.
- Barra de previsualización de archivos adjuntos: `id="attachment-preview-bar"` con clase `hidden`.
- Input file oculto para archivos generales: `id="file-input"` (multiple).
- Input file oculto para cámara táctica: `id="camera-input"` con `accept="image/*"` y `capture="environment"`.
- Barra de entrada de comandos y texto:
  - Botón de adjuntar: `id="attach-btn"`.
  - Botón de cámara: `id="camera-btn"`.
  - Campo de texto: `id="text-input"` con placeholder `Transmitir comando a TARS...`.
  - Botón de envío: `id="send-btn"`.
- Fila inferior de captura de voz:
  - Botón de abortar/cortar: `id="cancel-proc-btn"` con `id="cancel-proc-label"`.
  - Botón central de micrófono: `id="mic-btn"`.
  - Etiqueta de estado del canal de audio: `id="mic-status-label"`.

### 4. Modulo 2: Domótica y Luces Tuya (`id="view-tuya" class="hud-module-view"`)
- Tarjeta de enlace domótico:
  - Campo de host: `id="tuya-endpoint-input"` (ej. `http://127.0.0.1:8080`).
  - Botón fijar host: `id="tuya-save-host-btn"`.
  - Badge de estado: `id="tuya-conn-badge"` (OFFLINE / OK // xx ms).
- Control de alimentación general:
  - Botón de encendido: `id="tuya-power-on-btn"`.
  - Botón de apagado: `id="tuya-power-off-btn"`.
- Control de brillo:
  - Slider: `id="tuya-brightness-slider"` (min 1, max 100, step 1).
  - Indicador de valor: `id="tuya-brightness-val"` ("50%").
- Control de color espectral:
  - Input selector: `id="tuya-color-picker"` tipo `color`.
  - Lectura hexadecimal: `id="tuya-color-hex"` ("#FFFFFF").
  - Botón de aplicación: `id="tuya-apply-color-btn"`.
  - Paleta de muestras rápidas: botones `.swatch-btn` con atributo `data-hex` (rojo, verde, azul, blanco frío, cálido, ámbar).
- Tarjetas de presets tácticos:
  - Botones o tarjetas `.tuya-preset-card` con atributos `data-color`, `data-brightness`, `data-name`:
    - Preset Laboratorio (blanco frío 100%).
    - Preset Concentración (ámbar 80%).
    - Preset Lectura (cálido 50%).
    - Preset Noche (rojo tenue 15%).
- Consola de telemetría de eventos domóticos:
  - Caja de log con scroll: `id="tuya-telemetry-log"`.

### 5. Modulo 3: Agenda, Timers y Cron Jobs (`id="view-agenda" class="hud-module-view"`)
- Panel de cuentas regresivas (Timers):
  - Encabezado con contador: `id="active-timers-count"` ("0 ACTIVOS").
  - Formulario de nuevo temporizador:
    - Input de descripción: `id="timer-label-input"`.
    - Input de minutos: `id="timer-minutes-input"` (tipo number, valor 15).
    - Botón agregar timer local: `id="add-timer-btn"`.
    - Botón enviar recordatorio a TARS: `id="send-agent-reminder-btn"`.
  - Lista de temporizadores activos: `id="timers-list-container"`.
- Panel de tareas programadas (Cron):
  - Formulario de nueva tarea:
    - Input expresión cron: `id="cron-expr-input"` (placeholder `0 * * * *`).
    - Input comando o script: `id="cron-cmd-input"`.
    - Botón programar cron: `id="add-cron-btn"`.
    - Botón sincronizar crontab con TARS: `id="sync-cron-btn"`.
  - Lista de tareas registradas: `id="cron-list-container"`.

### 6. Modulo 4: Telemetria y Nodos Multi-PC (`id="view-telemetry" class="hud-module-view"`)
- Panel de métricas de red y enlace:
  - Nodo activo: `id="telemetry-node-val"`.
  - Latencia RTT: `id="telemetry-latency-val"` ("0 ms").
  - Historial de latencia en barras: `id="latency-bars-wrapper"`.
  - Índice de paso sincronizado: `id="telemetry-step-val"`.
  - Estado del audio de máquina: `id="telemetry-audio-val"`.
  - Badge de sincronización: `id="telemetry-sync-badge"` ("SYNC OK").
  - Botón de silenciado directo: `id="telemetry-mute-pc-btn"`.
- Administrador de nodos en red:
  - Botón refrescar lista: `id="telemetry-refresh-pcs-btn"`.
  - Lista de nodos detectados: `id="telemetry-pcs-list"`.
  - Formulario para agregar nodo:
    - Input nombre: `id="telemetry-pc-name"`.
    - Input IP: `id="telemetry-pc-ip"`.
    - Botón agregar: `id="telemetry-add-pc-btn"`.

### 7. Dock Tactico Inferior (Navegacion Fija)
- Elemento `<nav class="hud-dock">` con 4 botones:
  - `<button class="dock-tab active" data-target="view-chat">`: icono chat + texto `CHAT`.
  - `<button class="dock-tab" data-target="view-tuya">`: icono bombilla + texto `LUCES`.
  - `<button class="dock-tab" data-target="view-agenda">`: icono reloj + texto `AGENDA`.
  - `<button class="dock-tab" data-target="view-telemetry">`: icono antena/red + texto `NODOS`.

### 8. Modales del Sistema y Toasts
- Modal de chats: `id="chats-modal"` con overlay `id="chats-modal-overlay"`, botón cerrar `id="chats-modal-close"`, lista `id="chats-list"`, y botones `id="prev-chat-btn"`, `id="next-chat-btn"`.
- Modal de modelos: `id="models-modal"` con overlay `id="models-modal-overlay"`, botón cerrar `id="models-modal-close"` y lista `id="models-list"`.
- Modal de PCs: `id="pcs-modal"` con overlay `id="pcs-modal-overlay"`, botón cerrar `id="pcs-modal-close"`, lista `id="pcs-list"`, inputs `id="custom-pc-name"`, `id="custom-pc-ip"` y botón `id="add-custom-pc-btn"`.
- Banner Toast flotante estilo WhatsApp: `id="wa-toast-banner"` con `id="wa-toast-title"` y `id="wa-toast-text"`.

---

## Verificacion de Integridad
1. Validar que no falte ningún ID de los listados arriba mediante grep o búsqueda textual.
2. Comprobar que todos los tags cierren correctamente.
3. Asegurar que las etiquetas de importación carguen `/static/style.css?v=5.0` y `/static/app.js?v=5.0`.
