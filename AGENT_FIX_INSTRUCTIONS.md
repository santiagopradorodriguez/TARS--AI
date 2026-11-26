# Instrucciones para Agente Razonador: Auditoria Integral, Correccion de Bugs y Seguridad (TARS)

Eres un agente razonador senior especializado en ingenieria de software, Android (Kotlin/Gradle), Python (aiohttp/WebSockets/PipeWire) y ciberseguridad.

Tu objetivo es **auditar por completo todo el codigo fuente** incluido en este archivo ZIP (`TARS/`, `android/`, `.github/workflows/`), **encontrar y corregir absolutamente todos los bugs, errores de compilacion, fallos de funcionamiento, problemas de UX/conexion y vulnerabilidades de seguridad**, dejar la aplicacion **100% funcional de punta a punta**, y devolverme un **archivo ZIP corregido** listo para descomprimir y desplegar.

---

## Areas Criticas a Revisar y Corregir

### 1. Aplicacion Android (`android/`)
- **Compilacion y R8/ProGuard (`build.gradle`, `proguard-rules.pro`):**
  - Verificar que `./gradlew assembleRelease` compile sin errores.
  - Con `minifyEnabled true`, asegurar que exista `android/app/proguard-rules.pro` preservando `@JavascriptInterface` (`AndroidBridge`), clases de ZXing y corutinas para que R8 no rompa el puente JS-Android en tiempo de ejecucion.
- **Conexiones HTTPS / Certificados Locales vs Tailscale (`MainActivity.kt`, `TarsSyncService.kt`, `network_security_config.xml`):**
  - Revisar por que la app puede fallar al conectar por Wi-Fi local (`https://192.168.x.x:8443`) cuando el servidor usa certificado autofirmado y `onReceivedSslError` hace `handler?.cancel()`. Proponer/implementar un mecanismo seguro (por ejemplo, pinning del certificado del QR o flujo claro con certificado Tailscale/local) para que no quede bloqueada sin poder conectar.
- **Escaner de QR y Autenticacion por Token (`MainActivity.kt`, `dialog_settings.xml`, `TarsSyncService.kt`):**
  - Verificar que el boton "Escanear Codigo QR de la PC" funcione al primer inicio y desde Ajustes, pida permiso de camara si hace falta, parsee `https://host:8443/?token=...`, guarde el token y conecte de inmediato.
  - Verificar que `TarsSyncService` envie correctamente `X-TARS-Token` y reciba notificaciones en segundo plano tipo WhatsApp.
- **Modo Llamada y Permisos (`AndroidManifest.xml`, `MainActivity.kt`):**
  - Verificar permisos `CAMERA`, `RECORD_AUDIO`, `POST_NOTIFICATIONS`, `FOREGROUND_SERVICE_MICROPHONE` y el manejo de `acquireCallWakeLock` / `releaseCallWakeLock`.

### 2. Servidor Backend y Puentes (`TARS/tars_web_server.py`, `TARS/tars_voice_bridge.py`, `TARS/tars_qr_dialog.py`)
- **Autenticacion y Sesion:**
  - Verificar que el flujo `?token=...` -> cookie `HttpOnly` funcione tanto en navegador movil como en WebView de Android y en el WebSocket `/ws/voice_call`.
  - Verificar que el QR generado en `tars_qr_dialog.py` y en `/api/connection_mode` contenga el token correcto y no exponga credenciales indebidas en logs.
- **Puente de Modo Llamada (`/ws/voice_call`, `tars_voice_bridge.py`):**
  - Verificar enrutamiento bidireccional de audio PipeWire (`TARS_Phone_Mic_Sink`, `TARS_Antigravity_Out`), limpieza garantizada ante desconexiones, y control CDP multi-ventana por `chat_id` (iniciar, mantener y colgar sin errores `NO_START_BTN` / `NO_END_BTN`).
- **Listeners y Servicios (`f12_listener.py`, `tars_bluetooth_trigger.py`, `tars_tray.py`, `tars_wake_word.py`):**
  - Verificar que todos los scripts funcionen tras el cambio de locks a `$XDG_RUNTIME_DIR/tars/` y sin errores de permisos ni imports rotos.

### 3. Frontend Web (`TARS/web/index.html`, `TARS/web/static/app.js`, `TARS/web/sw.js`)
- Verificar que no haya errores de JavaScript, problemas con CSP (por ejemplo, `AudioWorklet` con `Blob` URL o scripts inline bloqueados por la nueva politica CSP del servidor), ni cache vieja en `sw.js`.
- Verificar que `VoiceCallClient` envie `chat_id` y el token/cookie correctamente al abrir `/ws/voice_call`.

### 4. CI/CD (`.github/workflows/build_apk.yml`)
- Asegurar que el workflow compile el APK Release sin fallos y publique el release correctamente.

---

## Reglas Obligatorias
1. **Cero emojis** en todo el codigo, comentarios, UI y documentacion.
2. **Cero IPs privadas hardcodeadas** (ni locales `192.168.x.x` reales ni IPs de Tailscale reales).
3. **Edicion limpia y funcional:** No dejar codigo roto ni dependencias faltantes.

---

## Entregable Esperado
1. **Archivo ZIP corregido** con la misma estructura de carpetas (`TARS/`, `android/`, `.github/workflows/`), listo para descomprimir sobre el repositorio.
2. Un archivo **`FIX_CHANGELOG.md`** en la raiz del ZIP detallando cada bug, error y problema de seguridad encontrado y como fue corregido.
