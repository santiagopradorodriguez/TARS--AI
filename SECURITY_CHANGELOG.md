# Registro de Correcciones de Seguridad — TARS

Este paquete contiene el codigo fuente de TARS corregido tras la auditoria de backend y ciberseguridad, cubriendo los 21 hallazgos identificados.

## Resumen de cambios aplicados

### 1. Backend Web, WebSockets y Puentes de IA
- **F-01 (`TARS/tars_web_server.py`):** Autenticacion obligatoria en `security_middleware` y `/ws/voice_call` con token criptografico de 256 bits (`Authorization: Bearer`, `X-TARS-Token`, cookie `HttpOnly; Secure; SameSite=Strict` al abrir el QR o `?token=`), validado con `hmac.compare_digest`. Se elimino el listener HTTP 8080 y se restringio CORS a origenes HTTPS propios.
- **F-02 (`TARS/tars_web_server.py`):** Chroot estricto en `GET /api/download` limitado a `MEDIA_DIR`, `UPLOADS_DIR` y `TARS_ALLOWED_DOWNLOAD_DIRS`, bloqueo de ZIP recursivo de directorios y sanitizacion RFC 5987 de `Content-Disposition`.
- **F-03 (`TARS/tars_web_server.py`):** Eliminacion del topic publico hardcodeado `tars_santiago_a03`; `ntfy` solo se activa si se define `TARS_NTFY_TOPIC`. Permisos `0600` para `vapid_keys.json` y `tars_auth_token`.
- **F-04 (`TARS/tars_live_commander.py`):** Eliminacion de `shell=True`; reemplazado por herramienta `ejecutar_accion` con lista blanca estricta (`abrir_url` solo `https://` y controles `playerctl` con `shell=False`).
- **F-05 (`TARS/tars_web_server.py`):** Serializacion con `json.dumps` y `CSS.escape` en `eval_in_antigravity` de `switch_antigravity_chat`.
- **F-06 (`TARS/tars_web_server.py`):** Allowlist de nodos Tailscale `100.64.0.0/10` y `.ts.net` en `/api/add_pc`, `/api/select_pc` y proxy remoto, con verificacion TLS estandar y `TARS_CA_BUNDLE` opcional.
- **F-07 (`TARS/tars_web_server.py`):** Tope de subida de 20 MB por archivo y `ffmpeg` endurecido con `-protocol_whitelist file,pipe` y `timeout=15`.
- **F-08 y F-09 (`TARS/tars_web_server.py`):** Redireccion segura sin Open Redirect ni CRLF en `_handle_dual_8443`, `TLSv1_2` minimo, `chmod 600` en `key.pem`, validez autofirmada de 365 dias y headers CSP, HSTS, X-Frame-Options, X-Content-Type-Options y Referrer-Policy.

### 2. Servicios del Sistema, Listeners y Scripts Shell
- **F-10 (`TARS/tars_bluetooth_trigger.py`):** Eliminado `su - santiago -c ...` y agregado filtrado de MAC autorizada via `TARS_BT_ALLOWED_MAC`.
- **F-11 (`TARS/dormir_hasta_las_8.sh`):** CDP ligado a `127.0.0.1`, validacion estricta de `WAKE_TIME` y `SECS` e invocacion de `/usr/sbin/rtcwake`.
- **F-12 y F-13 (`TARS/tars_rutas.py`, `f12_listener.py`, `tars_wake_word.py`, `tars_tray.py`, `tars_player.py`, `speak_response.py`, `tars_opencode_lector.py`, `zapzap_listener.py`, `tars_whatsapp.py`):** Locks y audios movidos a `$XDG_RUNTIME_DIR/tars/` con permisos `0700`, eliminacion de `os.system` y paso seguro de `wav` por `sys.argv[1]` a Whisper.

### 3. Frontend Web y Service Worker
- **F-14 y F-16 (`TARS/web/static/app.js`):** Escape con `escapeHtml` en todas las asignaciones `innerHTML` vulnerables y validacion HTTPS al guardar en `localStorage`.
- **F-15 (`TARS/web/sw.js`):** Exclusion de `/media/` de la cache persistente y validacion de mismo origen en `clients.openWindow`.

### 4. Aplicacion Android y CI/CD
- **F-17 (`MainActivity.kt`, `TarsSyncService.kt`):** Eliminados `handler?.proceed()`, `X509TrustManager` vacios y `HostnameVerifier` permisivos.
- **F-18 y F-19 (`MainActivity.kt`):** Validacion estricta de hosts con regex, control de origen en `onPermissionRequest` para microfono y bloqueo de Intent Redirection.
- **F-20 (`android/app/build.gradle`, `.github/workflows/build_apk.yml`):** Eliminadas credenciales `tars123456` y keystore efimero; firma persistente desde GitHub Secrets, R8 activado, firma v1 desactivada y Actions pineadas a commit SHA.
- **F-21 (`AndroidManifest.xml`, `res/xml/network_security_config.xml`, `MainActivity.kt`):** `allowBackup="false"`, `usesCleartextTraffic="false"`, `allowFileAccess=false`, `MIXED_CONTENT_NEVER_ALLOW` y timeout de 10 minutos para `PARTIAL_WAKE_LOCK`.
