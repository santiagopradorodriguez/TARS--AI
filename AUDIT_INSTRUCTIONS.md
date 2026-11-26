# Instrucciones de Auditoria de Ciberseguridad - TARS (Jarvis-Assistant)

Eres un agente razonador especializado en seguridad informatica. Tu tarea es analizar todo el codigo fuente contenido en este archivo comprimido (`TARS/`, `android/`, `.github/workflows/`) para identificar cualquier vulnerabilidad, hueco de seguridad, exposicion de datos o mala practica a nivel de ciberseguridad.

## Alcance de la Auditoria
1. **Servidor Web y WebSockets (`TARS/tars_web_server.py`, `TARS/tars_voice_bridge.py`):**
   - Autenticacion, autorizacion y control de acceso en endpoints HTTP/HTTPS y WebSockets (`/ws/voice_call`, `/api/*`).
   - Inyeccion de comandos (`subprocess`, `os.system`), inyeccion de JavaScript via CDP (`eval_in_antigravity`), path traversal en descarga/subida de archivos (`/api/download`, `/api/audio`).
   - Exposicion en interfaces de red (`0.0.0.0`), manejo de CORS, certificados TLS/SSL y cabeceras de seguridad.
   - Manejo de procesos en segundo plano, locks, condiciones de carrera y denegacion de servicio (DoS).

2. **Servicios del Sistema y Listeners (`TARS/f12_listener.py`, `TARS/tars_bluetooth_trigger.py`, `TARS/tars_wake_word.py`, `TARS/tars_tray.py`):**
   - Privilegios excesivos (servicios corriendo como `root`), ejecucion de subprocesos con `su` o shell, manejo de archivos temporales en `/tmp/`.

3. **Frontend Web (`TARS/web/index.html`, `TARS/web/static/app.js`, `TARS/web/sw.js`):**
   - XSS (Cross-Site Scripting) al renderizar mensajes, markdown o respuestas de la IA.
   - Almacenamiento inseguro en `localStorage`, Service Workers o WebPush.

4. **Aplicacion Android (`android/app/src/main/java/com/tars/assistant/*.kt`, `AndroidManifest.xml`, `build.gradle`):**
   - `WebView` con `setJavaScriptEnabled(true)` y `AndroidBridge` (`@JavascriptInterface`): riesgos de ejecucion remota o abuso desde paginas externas.
   - Validacion de certificados SSL/TLS (`TrustManager` permisivo / `HostnameVerifier` que acepta todo).
   - Permisos en `AndroidManifest.xml`, `usesCleartextTraffic="true"`, almacenamiento en `SharedPreferences` y firma del APK.

## Formato de Salida Esperado
Para cada hallazgo, reporta:
- **Severidad:** Critica / Alta / Media / Baja
- **Archivo y linea aproximada**
- **Descripcion del hueco y vector de ataque**
- **Remediacion concreta recomendada**
