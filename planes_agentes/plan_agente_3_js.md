# Plan de Implementacion - Agente 3: Logica del Reactor, Modulos y Camara

## Objetivo
Consolidar el motor JavaScript en `TARS/web/static/app.js` utilizando como base el código de referencia `TARS/web/static/app_hud_preview.js`, garantizando la estabilidad del osciloscopio canvas, la navegación por el dock táctico, la captura directa de cámara y la total compatibilidad con las funciones de historial ya probadas.

## Archivos Afectados
- `TARS/web/static/app.js` (archivo de producción que se modificará)
- `TARS/web/static/app_hud_preview.js` (archivo de referencia con los 13 módulos completos)

## Reglas Obligatorias
- Cero emojis en mensajes, logs, textos o etiquetas.
- Preservar intactas las llamadas y contratos de endpoints (`/api/sync`, `/api/chats`, `/api/switch_chat`, `/api/chat_history`, `/api/models`, `/api/select_pc`, `/api/cancel`).
- No generar excepciones `null` si algún elemento del DOM aún no está presente: validar con `if (el)` antes de añadir listeners.

---

## Tareas Especificas de Integracion

### 1. Fusión de app_hud_preview.js con Funcionalidades Existentes
- Tomar la estructura modular de `app_hud_preview.js` que contiene:
  - Módulo 1: Núcleo reactivo Canvas (osciloscopio y estados `IDLE`, `LISTENING`, `PROCESSING`, `SPEAKING`).
  - Módulo 2: Navegación táctica por dock inferior.
  - Módulo 3: Burbuja de pensamiento en vivo, soporte KaTeX y bloques de código con botón de copiado.
  - Módulo 4: Audio keep-alive móvil, síntesis vocal Edge-TTS y barra flotante de control.
  - Módulo 5: Mensajería, chips de adjuntos y cámara táctica directa.
  - Módulo 6: Cancelación de ejecuciones y transmisión de audio/texto.
  - Módulo 7: Controles de mute para voz móvil y sonido de PC.
  - Módulo 8: Selector de chats con preservación estricta de `renderChatHistory` y `loadChatHistory`.
  - Módulo 9: Selector de modelos con botones de esfuerzo (`Low`, `Medium`, `High`).
  - Módulo 10: Control domótico Tuya (puerto 8080 con fallback a `/api/tuya/*`).
  - Módulo 11: Agenda de cuentas regresivas y gestor de tareas cron.
  - Módulo 12: Telemetría de red, gráfico de barras de latencia y gestión de nodos Multi-PC.
  - Módulo 13: Notificaciones Web Push y bucle de sincronización `syncWithAntigravity`.

### 2. Osciloscopio Canvas y Adaptación HiDPI
- En la función `renderReactiveCore`:
  - Adaptar la resolución del canvas para pantallas móviles con alta densidad de píxeles:
    ```javascript
    const dpr = window.devicePixelRatio || 1;
    if (coreCanvas.width !== 220 * dpr) {
        coreCanvas.width = 220 * dpr;
        coreCanvas.height = 42 * dpr;
    }
    ```
  - Verificar que el loop de animación no consuma batería excesiva cuando la pestaña esté oculta (`document.visibilityState === 'hidden'`).

### 3. Camara Tactica Directa
- Validar el handler del botón `camera-btn`:
  ```javascript
  if (cameraBtn && cameraInput) {
      cameraBtn.addEventListener('click', () => cameraInput.click());
      cameraInput.addEventListener('change', (e) => {
          if (e.target.files && e.target.files.length > 0) {
              for (const f of e.target.files) pendingAttachments.push(f);
              renderAttachmentPreviews();
              cameraInput.value = '';
              const currentPrompt = textInput.value.trim() || 'Analizar captura optica adjunta.';
              sendTextMessage(currentPrompt);
          }
      });
  }
  ```
  Esto permite que un solo toque abra la cámara del celular, y al aceptar la foto se envíe al chat de inmediato.

### 4. Preservacion del Historial y Spinner al Conmutar Chat
- Asegurar que `switchAntigravityChat` mantenga el indicador visual:
  ```javascript
  if (chatContainer) {
      chatContainer.innerHTML = `
          <div class="chat-loading-placeholder">
              <div class="loading-spinner"></div>
              <span>Cambiando chats, por favor espere...</span>
          </div>
      `;
  }
  ```
- Asegurar que `renderChatHistory` renderice hasta los últimos 10 mensajes sin pérdidas.

### 5. Cache Busting y Verificación
- En `index.html`, asegurar que la etiqueta apunte a `<script src="/static/app.js?v=5.0"></script>`.

---

## Verificacion de Integridad
1. Abrir la consola del navegador y comprobar que no haya errores de referencia (`Uncaught TypeError: Cannot read properties of null`).
2. Verificar que al presionar cada botón del dock táctico cambie la vista activa.
3. Probar el osciloscopio: debe pulsar en azul en reposo, rojo al grabar audio y ámbar al procesar.
