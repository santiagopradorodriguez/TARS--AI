# Plan de Implementacion - Agente 4: Backend Proxy Domotica y Telemetria

## Objetivo
Implementar en `TARS/tars_web_server.py` los endpoints de proxy HTTPS para las luces Tuya (evitando el bloqueo por contenido mixto en navegadores móviles) y un endpoint de telemetría del sistema para alimentar las métricas en vivo del HUD.

## Archivos Afectados
- `TARS/tars_web_server.py`
- `actualizar_tars.sh`

## Reglas Obligatorias
- Cero emojis en cualquier respuesta, log o mensaje.
- Mantener intactas todas las rutas existentes (`/api/sync`, `/api/chats`, `/api/switch_chat`, `/api/chat_history`, etc.).
- Las peticiones proxy no deben bloquear el bucle de eventos de `asyncio` (usar `asyncio.to_thread` o cliente HTTP asíncrono).

---

## Tareas Especificas de Backend

### 1. Proxy Seguro HTTPS para Domotica Tuya (Puerto 8080)
Debido a que la PWA móvil se sirve bajo HTTPS (puerto 8443), cualquier llamada directa desde JavaScript a `http://192.168.0.x:8080` es bloqueada por las políticas de seguridad del navegador móvil (Mixed Content: HTTPS no permite peticiones HTTP inseguras en red local).

Solución a implementar en `tars_web_server.py`:
```python
async def proxy_tuya_request(endpoint: str, payload: dict) -> dict:
    import urllib.request
    import json
    tuya_url = f"http://127.0.0.1:8080{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        tuya_url,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"success": False, "error": f"Error comunicando con luces_tuya en 8080: {e}"}

async def handle_tuya_power(request):
    data = await request.json()
    res = await asyncio.to_thread(proxy_tuya_request, "/power", data)
    return web.json_response(res)

async def handle_tuya_color(request):
    data = await request.json()
    res = await asyncio.to_thread(proxy_tuya_request, "/color", data)
    return web.json_response(res)

async def handle_tuya_brightness(request):
    data = await request.json()
    res = await asyncio.to_thread(proxy_tuya_request, "/brightness", data)
    return web.json_response(res)
```

Rutas a registrar en la aplicación web (`app.router.add_post`):
- `POST /api/tuya/power` -> `handle_tuya_power`
- `POST /api/tuya/color` -> `handle_tuya_color`
- `POST /api/tuya/brightness` -> `handle_tuya_brightness`

### 2. Endpoint de Telemetria de Hardware (`/api/system_stats`)
Implementar una función liviana para obtener métricas reales de la máquina:
```python
def get_linux_system_stats():
    stats = {"cpu_pct": 0, "ram_used_mb": 0, "ram_total_mb": 0, "cpu_temp": None}
    try:
        # Memoria desde /proc/meminfo
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        mem = {}
        for l in lines:
            parts = l.split(":")
            if len(parts) == 2:
                mem[parts[0].strip()] = int(parts[1].strip().split()[0])
        total_kb = mem.get("MemTotal", 0)
        avail_kb = mem.get("MemAvailable", 0)
        stats["ram_total_mb"] = total_kb // 1024
        stats["ram_used_mb"] = (total_kb - avail_kb) // 1024
    except Exception:
        pass

    try:
        # Temperatura desde /sys/class/thermal
        for p in ["/sys/class/thermal/thermal_zone0/temp", "/sys/class/hwmon/hwmon0/temp1_input"]:
            if os.path.exists(p):
                with open(p, "r") as f:
                    stats["cpu_temp"] = round(int(f.read().strip()) / 1000.0, 1)
                break
    except Exception:
        pass

    return stats

async def handle_system_stats(request):
    stats = await asyncio.to_thread(get_linux_system_stats)
    return web.json_response(stats)
```
Ruta a registrar:
- `GET /api/system_stats` -> `handle_system_stats`

### 3. Despliegue en Produccion y Verificacion
- Una vez aplicadas las modificaciones en `TARS/tars_web_server.py`:
  1. Ejecutar `./actualizar_tars.sh` para copiar archivos a `~/.gemini/config/`.
  2. Verificar que `systemctl --user is-active tars-web.service` devuelva `active`.
  3. Comprobar que una petición `curl -k https://127.0.0.1:8443/api/system_stats` devuelva el JSON de métricas.

---

## Verificacion de Integridad
1. Probar `curl -k -X POST https://127.0.0.1:8443/api/tuya/power -H "Content-Type: application/json" -d '{"state":true}'` cuando `luces_tuya/app.py` esté levantado en el puerto 8080.
2. Confirmar que el servicio web de TARS responda en HTTPS sin caídas.
