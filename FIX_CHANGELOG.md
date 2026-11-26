# Registro Integral de Correcciones — TARS

Este documento detalla todos los bugs, fallos de compilacion, problemas de conectividad y brechas de seguridad detectados y corregidos en el paquete TARS.

## 1. Aplicacion Android

### Compilacion Release y R8
- **Reglas R8 faltantes en `android/app/proguard-rules.pro`:** `build.gradle` tenia `minifyEnabled true` apuntando a `proguard-rules.pro`, pero el archivo no existia y R8 podia ofuscar o eliminar los metodos `@JavascriptInterface` de `AndroidBridge`, las clases de ZXing y las corutinas. Se creo `android/app/proguard-rules.pro` preservando `MainActivity$AndroidBridge`, `TarsTlsPinning`, `com.journeyapps.barcodescanner.**`, `com.google.zxing.**` y `kotlinx.coroutines.**`.

### Conexiones HTTPS Locales y Tailscale mediante Pinning SHA-256
- **Bloqueo total de certificados autofirmados locales en `MainActivity.kt` y `TarsSyncService.kt`:** Tras eliminar los `TrustManager` permisivos, `onReceivedSslError` cancelaba incondicionalmente cualquier certificado local autofirmado y `HttpsURLConnection` rechazaba las consultas locales. Se creo `android/app/src/main/java/com/tars/assistant/TarsTlsPinning.kt` con validacion TLS estandar del sistema para dominios confiables como Tailscale MagicDNS y respaldo seguro por pinning criptografico SHA-256 en tiempo constante contra la huella recibida en el codigo QR.
- **Sondeo de red fallido por endpoint protegido en `MainActivity.kt`:** `testEndpointReachable` consultaba `/api/connection_mode` sin credenciales, recibiendo HTTP 401 y descartando servidores activos. Se redirigio el sondeo al endpoint publico `/api/health` con soporte de TLS pineado y se agrego sondeo TCP al puerto 8443 en `scanSubnetForTars` cuando todavia no hay huella vinculada.
- **Validacion de hosts y normalizacion de URLs en `MainActivity.kt`:** `normalizeUrl` podia lanzar `MalformedURLException` ante entradas malformadas y permitia `http://`. Ahora envuelve el parseo en `try/catch`, fuerza `https://` y valida hosts contra rangos locales RFC 1918, `localhost`, CGNAT de Tailscale y `.ts.net`.

### Escaner QR, Permisos y Ciclo de Vida
- **Permiso de camara faltante al abrir el escaner QR en `MainActivity.kt`:** El boton de escaneo lanzaba ZXing sin solicitar `Manifest.permission.CAMERA`. Se incorporo `cameraPermissionLauncher` y `launchQrScanner` para pedir el permiso antes de abrir la camara, tanto en el primer inicio como desde Ajustes o el dialogo de reconexion.
- **Vinculacion completa por QR en `MainActivity.kt`:** `qrScannerLauncher` ahora extrae `token` y `fp`, valida la huella SHA-256 de 64 caracteres hexadecimales, la guarda junto al token y la URL base, inicia `TarsSyncService` y carga la sesion autenticada de inmediato.
- **Persistencia de cookies en WebView:** Se habilito `CookieManager` con `setAcceptCookie(true)` y `flush()` en `onPageFinished` para preservar la cookie `HttpOnly` de sesion.
- **Crash potencial en Android 14 por Foreground Service en `TarsSyncService.kt`:** El servicio declaraba `dataSync|microphone` en `AndroidManifest.xml`, pero invocaba `startForeground` sin indicar tipo. Se actualizo a `ServiceCompat.startForeground` con `ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC` en API 29 o superior, evitando `SecurityException` cuando aun no se concedio permiso de microfono.
- **Dialogo duplicado y fuga de corutinas en `MainActivity.kt`:** Se limito la sobrecarga obsoleta de `onReceivedError` a API menor a 23 para evitar abrir dos dialogos de error simultaneos, se paso a `SupervisorJob` con cancelacion en `onDestroy` en `MainActivity` y `TarsSyncService`, y se restringio `openExternalIntent` a esquemas `https` y `http`.
- **Limpieza de IPs placeholder y emojis en UI Android:** Se eliminaron los perfiles placeholder rotos y los emojis en `MainActivity.kt`, `activity_main.xml` y `dialog_settings.xml`, dejando el escaneo QR como opcion principal de reconexion.

## 2. Backend Python, Puentes de Voz y Servicios

### Autenticacion, Cookies, Middleware y Logs en `TARS/tars_web_server.py`
- **Error de headers tras `WebSocketResponse.prepare()` en `security_middleware`:** Al finalizar `/ws/voice_call`, el middleware intentaba escribir cabeceras HTTP sobre una respuesta WebSocket ya preparada. Se resguardo la mutacion de cookies y headers con `if not resp.prepared:`.
- **Persistencia de cookie `tars_token`:** Se agrego `max_age` de 30 dias a la cookie `HttpOnly; Secure; SameSite=Strict` para evitar cierres de sesion al reiniciar el navegador o WebView.
- **Huella TLS en QR y proteccion de credenciales en logs:** Se implemento `get_cert_sha256_fingerprint` y se incluyo `&fp=<sha256>` en `/api/connection_mode` y en el QR de consola. En `print_connection_qr` se dejo de imprimir el token en texto plano en stdout y se eliminaron los mensajes obsoletos que mencionaban HTTP 8080.
- **Permisos de clave privada en `tailscale cert`:** Se aplico `os.chmod(KEY_FILE, 0o600)` tambien cuando el certificado es emitido por Tailscale.

### Modo Llamada y Control CDP Multi-Ventana
- **Propagacion incompleta de `chat_id` en `TARS/tars_web_server.py`:** `antigravity_voice_call_start` y `antigravity_voice_call_stop` consultaban `antigravity_voice_call_status()` sin pasar `target_chat_id`, lo que podia sondear otra ventana en escenarios multi-ventana. Se corrigio la propagacion en ambas funciones y en los endpoints HTTP `/api/voice_call/status`, `/api/voice_call/start` y `/api/voice_call/stop`.
- **Seleccion robusta de target CDP en `_find_antigravity_voice_ws_url`:** Al coincidir un `target_chat_id`, ahora se verifica primero que la pagina contenga los controles de Voice Mode antes de devolverla, evitando errores `NO_START_BTN` y `NO_END_BTN`.
- **Notificacion de errores en `/ws/voice_call`:** Si `antigravity_voice_call_start` falla, el servidor envia un mensaje JSON `{"type": "error", "error": ...}` al cliente WebSocket y evita marcar `voice_started` en falso positivo.
- **Prevencion de deadlock de `stderr` y cierre rapido en `TARS/tars_voice_bridge.py`:** `pacat` y `parec` abrian `stderr=PIPE` sin lectura, con riesgo de bloqueo al llenarse el buffer. Se redirigio `stderr` a `DEVNULL` y se registro `_async_parec_proc` para terminarlo de inmediato en `teardown()`.

### Dialogo QR, Notificaciones y Scripts Auxiliares
- **QR seguro y sin token visible en `TARS/tars_qr_dialog.py`:** Se unifico la lectura de configuracion mediante `tars_rutas.directorio_config_tars()`, se embebio `&fp=<sha256>` en el QR, se oculto el token de las etiquetas de texto en pantalla y se reemplazo el usuario por defecto por `getpass.getuser()`.
- **Eliminacion de topic publico residual en `TARS/speak_response.py`:** Se quito el endpoint hardcodeado `https://ntfy.sh/tars_santiago_a03`; ahora `ntfy` solo se invoca si esta definida la variable de entorno `TARS_NTFY_TOPIC`.
- **Eliminacion de IP privada de prueba de ruta y emojis:** Se reemplazo el destino UDP de descubrimiento de interfaz local por `8.8.8.8:80` en `tars_web_server.py` y `tars_qr_dialog.py`, y se eliminaron todos los emojis de `tars_live_commander.py`, `dormir_hasta_las_8.sh` y `TARS/README.md`.

## 3. Frontend Web y Service Worker

- **Compatibilidad de `AudioWorklet` con CSP estricto:** `TARS/web/static/app.js` cargaba `VoiceCallPcmProcessor` mediante un `Blob` URL que quedaba bloqueado por `script-src 'self'`. Se extrajo el procesador a `TARS/web/static/voice_call_worklet.js`, se agrego `worker-src 'self'` a la CSP del servidor y se cargo como modulo estatico.
- **Limpieza de credenciales en barra de direcciones:** `TARS/web/static/app.js` ahora limpia los parametros `token` y `fp` de `window.location` mediante `history.replaceState` apenas carga la pagina.
- **Sincronizacion de cache y proteccion en `TARS/web/sw.js` y `TARS/web/index.html`:** Se alineo la version de assets a `v8.2` incluyendo `voice_call_worklet.js`, se excluyeron URLs con `token=` o `fp=` de la cache del Service Worker, y se eliminaron emojis y ejemplos de IP privada en `app.js` e `index.html`.

## 4. CI/CD

- **Limpieza garantizada del keystore en `.github/workflows/build_apk.yml`:** Se agrego `set -euo pipefail` y `trap 'rm -f "$TARS_KEYSTORE_PATH"' EXIT` para asegurar la eliminacion del archivo keystore incluso si falla Gradle.
