# Plan de Implementación: Puente Remoto de Modo Llamada (TARS v1.2.0)

> **Objetivo:** Permitir llamadas de voz bidireccionales en tiempo real desde la app móvil/web de TARS hacia el **Voice Mode** nativo de Antigravity en la PC Linux, funcionando tanto por Wi-Fi local como por Tailscale.
>
> **Reglas obligatorias para todos los subagentes:**
> - **Cero emojis** en código, comentarios, logs, UI o commits.
> - **Edición no destructiva:** No borrar ni refactorizar código existente fuera del alcance de la tarea.
> - **Sin IPs privadas hardcodeadas:** Nunca escribir IPs locales o de Tailscale reales en el repositorio.
> - **Sincronización:** Todo cambio en `/home/santiago/repositorios/Jarvis-Assistant/TARS/` debe sincronizarse con `/home/santiago/.gemini/config/`.

---

## Arquitectura del Sistema

```text
[Celular (TARS Web / APK)]
      |   ^
      |   |  WSS /ws/voice_call (PCM 16kHz mono / Int16)
      v   |
[TARS/tars_web_server.py]
      |   |-- CDP -> Control de "Start/Stop Voice mode" en Antigravity
      |   |-- PipeWire Virtual Mic  (TARS_Phone_Mic) -> Entrada de Antigravity
      |   +-- PipeWire Virtual Sink (TARS_Antigravity_Out) -> Salida de Antigravity
      v
[Antigravity IDE (Voice Mode)]
```

---

## División de Tareas para Subagentes (Optimizado para bajo consumo de tokens)

Cada subagente recibe un alcance aislado, archivos exactos y criterios de verificación concretos.

---

### Subagente 1: Control CDP de Voice Mode (Backend)
- **Modelo recomendado:** `flash`
- **Archivos objetivo:**
  - `/home/santiago/repositorios/Jarvis-Assistant/TARS/tars_web_server.py`
- **Tareas:**
  1. Inspeccionar vía CDP los selectores exactos del DOM de Antigravity cuando Voice Mode está inactivo y cuando está activo (`button[data-testid="voice-start-button"]`, botón de colgar/detener y botón de mute).
  2. Agregar funciones auxiliares en `tars_web_server.py`:
     - `antigravity_voice_call_start()`
     - `antigravity_voice_call_stop()`
     - `antigravity_voice_call_status()`
  3. Registrar los endpoints REST en `init_app()`:
     - `POST /api/voice_call/start`
     - `POST /api/voice_call/stop`
     - `GET /api/voice_call/status`
- **Criterio de terminado:**
  - `curl -X GET http://127.0.0.1:8080/api/voice_call/status` devuelve JSON válido `{"active": false, ...}`.
  - `POST /api/voice_call/start` y `stop` activan y cierran el Voice Mode en Antigravity sin errores.

---

### Subagente 2: Enrutador de Audio Virtual PipeWire (Módulo independiente)
- **Modelo recomendado:** `flash`
- **Archivos objetivo:**
  - Crear `/home/santiago/repositorios/Jarvis-Assistant/TARS/tars_voice_bridge.py`
- **Tareas:**
  1. Implementar una clase `PipeWireVoiceBridge` usando `pactl` / `pw-cli` / `parec` / `pacat`:
     - `setup()`: Crea un sink nulo (`TARS_Phone_Mic_Sink`) con su source monitor como micrófono virtual, y un sink nulo (`TARS_Antigravity_Out`) para capturar la salida de Antigravity.
     - `route_antigravity_audio()`: Detecta los `sink-inputs` y `source-outputs` pertenecientes al proceso de Antigravity/Electron y los mueve a los nodos virtuales.
     - `write_mic_chunk(pcm_bytes)`: Escribe audio PCM 16kHz mono proveniente del celular hacia el micrófono virtual.
     - `read_speaker_stream()`: Generador/callback que lee PCM 16kHz mono desde `TARS_Antigravity_Out.monitor`.
     - `teardown()`: Restaura los streams de audio a los dispositivos por defecto y destruye los módulos virtuales creados.
  2. Asegurar limpieza automática ante desconexiones inesperadas o excepciones (`try/finally`).
- **Criterio de terminado:**
  - Script ejecutable con prueba unitaria/smoke test (`python3 tars_voice_bridge.py --test`) que cree los nodos, verifique su existencia con `pactl list short sinks` y los limpie por completo al salir.

---

### Subagente 3: WebSocket Bidireccional de Audio (Integración Servidor)
- **Modelo recomendado:** `flash`
- **Archivos objetivo:**
  - `/home/santiago/repositorios/Jarvis-Assistant/TARS/tars_web_server.py`
- **Dependencias:** Requiere Subagente 1 y Subagente 2 completados.
- **Tareas:**
  1. Añadir endpoint WebSocket `GET /ws/voice_call` usando `aiohttp.web.WebSocketResponse`.
  2. Al conectar un cliente al WebSocket:
     - Inicializar `PipeWireVoiceBridge.setup()`.
     - Invocar `antigravity_voice_call_start()`.
     - Redirigir audio de Antigravity (`route_antigravity_audio()`).
     - Lanzar dos corutinas concurrentes:
       - Recepción de frames binarios (PCM Int16 del celular) -> `bridge.write_mic_chunk()`.
       - Envío de frames binarios (PCM Int16 de Antigravity) -> `ws.send_bytes()`.
  3. Al cerrar el WebSocket (o tras timeout/error de red):
     - Llamar a `antigravity_voice_call_stop()`.
     - Llamar a `bridge.teardown()`.
- **Criterio de terminado:**
  - Conexión WebSocket estable sobre WSS (puerto 8443) y HTTP (puerto 8080), con limpieza verificada en logs al desconectar.

---

### Subagente 4: Interfaz de Llamada Web (Frontend)
- **Modelo recomendado:** `flash`
- **Archivos objetivo:**
  - `/home/santiago/repositorios/Jarvis-Assistant/TARS/web/index.html`
  - `/home/santiago/repositorios/Jarvis-Assistant/TARS/web/static/app.js`
  - `/home/santiago/repositorios/Jarvis-Assistant/TARS/web/static/style.css`
- **Tareas:**
  1. Agregar botón de acceso a **Llamada** en la barra superior de `index.html`.
  2. Crear modal/overlay de llamada activa con:
     - Indicador de estado (`Conectando`, `En llamada`, `Silenciado`).
     - Temporizador `MM:SS`.
     - Botones: `Silenciar micrófono`, `Colgar`.
  3. En `app.js`, implementar `VoiceCallClient`:
     - Captura de micrófono con `navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, sampleRate: 16000 } })`.
     - Conversión a PCM Int16 vía `AudioContext` / `AudioWorklet` (o `ScriptProcessorNode` como fallback) y envío por `/ws/voice_call`.
     - Reproducción en streaming de los chunks PCM Int16 recibidos desde el servidor usando cola de buffers en `AudioContext`.
- **Criterio de terminado:**
  - Abrir el modal desde navegador móvil, iniciar llamada, verificar tráfico bidireccional de audio sin eco y colgar limpiamente.

---

### Subagente 5: Soporte en Segundo Plano APK Android (v1.2.0)
- **Modelo recomendado:** `flash`
- **Archivos objetivo:**
  - `/home/santiago/repositorios/Jarvis-Assistant/android/app/src/main/AndroidManifest.xml`
  - `/home/santiago/repositorios/Jarvis-Assistant/android/app/src/main/java/com/tars/assistant/TarsSyncService.kt`
  - `/home/santiago/repositorios/Jarvis-Assistant/android/app/src/main/java/com/tars/assistant/MainActivity.kt`
  - `/home/santiago/repositorios/Jarvis-Assistant/android/app/build.gradle`
  - `/home/santiago/repositorios/Jarvis-Assistant/.github/workflows/build_apk.yml`
- **Tareas:**
  1. Agregar permiso `FOREGROUND_SERVICE_MICROPHONE` en `AndroidManifest.xml` y actualizar `foregroundServiceType="dataSync|microphone"`.
  2. Exponer en `AndroidBridge` de `MainActivity.kt` métodos `acquireCallWakeLock()` y `releaseCallWakeLock()` para evitar que Android corte el audio con la pantalla apagada durante una llamada.
  3. Incrementar versión a `versionCode 12`, `versionName "1.2.0"` en `build.gradle` y actualizar tag `v1.2.0` en `build_apk.yml`.
- **Criterio de terminado:**
  - Diff limpio, sin IPs privadas, y compilación exitosa en GitHub Actions al hacer push.

---

## Orden de Ejecución Sugerido

1. **En paralelo:** Subagente 1 (CDP) + Subagente 2 (PipeWire) + Subagente 4 (UI Frontend).
2. **Secuencial:** Subagente 3 (WebSocket integrando 1 y 2).
3. **Final:** Subagente 5 (Android APK v1.2.0) + pruebas integrales en Wi-Fi y Tailscale + commit/push.
