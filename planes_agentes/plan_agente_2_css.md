# Plan de Implementacion - Agente 2: Estilos Dark HUD Militar y Animaciones

## Objetivo
Desarrollar y consolidar la hoja de estilos `TARS/web/static/style.css` para dotar a la Super App de una estética táctica de laboratorio (Dark HUD militar), soporte completo para las 4 vistas modulares, animación del osciloscopio canvas y navegación táctil inferior (dock).

## Archivo Afectado
- `TARS/web/static/style.css`

## Reglas Obligatorias
- Cero emojis en cualquier elemento gráfico o decorativo.
- Paleta oscura estricta: fondo `#0a0a0c`, paneles `#111318` con bordes tenues de `1px solid rgba(255, 255, 255, 0.08)`.
- Acentos tácticos: Cian `#00e5ff` (estado nominal), Ámbar `#e5a93c` (advertencia y cron), Rojo `#ff3b30` (grabación y alerta).
- Tipografía monoespaciada para telemetría, lecturas y cronómetros.

---

## Secciones y Reglas CSS a Implementar

### 1. Variables Globales y Reset Táctico
```css
:root {
    --bg-main: #0a0a0c;
    --bg-panel: #111318;
    --bg-panel-hover: #161922;
    --bg-card: rgba(255, 255, 255, 0.03);
    --border-subtle: 1px solid rgba(255, 255, 255, 0.08);
    --border-accent: 1px solid rgba(0, 229, 255, 0.35);
    --cyan: #00e5ff;
    --cyan-dim: rgba(0, 229, 255, 0.15);
    --amber: #e5a93c;
    --amber-dim: rgba(229, 169, 60, 0.15);
    --red: #ff3b30;
    --red-dim: rgba(255, 59, 48, 0.15);
    --text-primary: #e6edf3;
    --text-muted: #8b949e;
    --font-mono: 'JetBrains Mono', 'Fira Code', 'SF Mono', monospace;
}
```

### 2. Estructura de Vistas Modulares
```css
.hud-module-view {
    display: none;
    flex: 1;
    flex-direction: column;
    overflow-y: auto;
    padding: 12px 14px 76px 14px; /* Margen inferior para que el dock no tape contenido */
    box-sizing: border-box;
}

.hud-module-view.active {
    display: flex;
}
```

### 3. Encabezado Táctico y Reactor Canvas
- Centrado del canvas osciloscopio:
  - Ancho 220px, alto 42px, fondo transparente con borde tenue y bordes redondeados (`border-radius: 6px`).
- Lectura de estado `.core-readout-wrap`:
  - `font-family: var(--font-mono)`, `font-size: 0.72rem`, `letter-spacing: 1.5px`, `text-transform: uppercase`.
  - Punto de pulso (`#hud-status-dot`):
    - `.online`: verde/cian fijo con pulso sutil.
    - `.alert`: rojo con pulso rápido durante captura de voz.
    - `.busy`: ámbar durante procesamiento o inferencia.

### 4. Barra de Audio Flotante (`#audio-control-bar`)
- Barra fija o flotante con `background: rgba(17, 19, 24, 0.95)`, `border: var(--border-accent)`, `border-radius: 10px`, `padding: 8px 14px`.
- Botones de control de voz (`#audio-pause-btn`, `#audio-stop-btn`) con transiciones suaves y efecto de pulsación táctil (`transform: scale(0.95)`).

### 5. Modulo 2 - Estilos de Domótica y Luces Tuya
- Tarjetas tácticas de control: fondo `var(--bg-panel)`, borde `var(--border-subtle)`, esquinas de 8px.
- Botones de encendido y apagado rápido (`#tuya-power-on-btn` con brillo tenue cian, `#tuya-power-off-btn` con borde rojo).
- Slider de brillo táctico (`#tuya-brightness-slider`):
  - Track delgado (4px), color de fondo `#21262d`.
  - Thumb circular de 18px color `var(--cyan)` con sombra de neón tenue.
- Selector de color y muestras (`.swatch-btn`):
  - Botones circulares o cuadrados redondeados de 32px con borde de 1px.
- Tarjetas de perfiles (`.tuya-preset-card`):
  - Grid de 2 columnas.
  - Estado `.active` resaltado con borde `var(--cyan)` y fondo `var(--cyan-dim)`.
- Consola de telemetría domótica (`#tuya-telemetry-log`):
  - Aspecto de terminal: fondo `#050507`, borde `var(--border-subtle)`, `font-family: var(--font-mono)`, color `#7ee787`, altura 120px, scroll vertical suave.

### 6. Modulo 3 - Estilos de Agenda y Temporizadores
- Tarjetas de lista (`.hud-list-item`):
  - Flex horizontal con información a la izquierda y acción a la derecha.
  - Indicador de cuenta regresiva (`.timer-countdown-readout`): `font-family: var(--font-mono)`, color `var(--amber)`, `font-weight: 700`, `font-size: 1.05rem`.
- Badges de estado: `ACTIVE`, `EXPIRADO` en formato monospace compacto.
- Botones de eliminación (`.hud-btn-sm`) con estilo minimalista (`border: var(--border-subtle)`, color `#ff7b72`).

### 7. Modulo 4 - Estilos de Telemetria y Nodos Multi-PC
- Grilla de métricas de red: 2 columnas con tarjetas de datos clave (RTT, Nodo, Sincronización, Audio).
- Gráfico de barras de latencia (`#latency-bars-wrapper`):
  - Contenedor flex con alineación al fondo (`align-items: flex-end`), altura 40px, gap de 3px.
  - Elemento `.latency-bar`: ancho 6px, fondo `var(--cyan)`, borde superior redondeado de 2px, con cambio dinámico a `var(--amber)` en valores superiores a 250ms.
- Lista de tarjetas de PC: indicador de estado con dot online/offline, botón `DIRECTO` y badge de nodo activo.

### 8. Dock Tactico Inferior (`.hud-dock`)
- Posición fija en la base:
  ```css
  .hud-dock {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      height: 62px;
      background: rgba(10, 10, 12, 0.94);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border-top: 1px solid rgba(255, 255, 255, 0.09);
      display: flex;
      justify-content: space-around;
      align-items: center;
      z-index: 1000;
      padding: 0 6px;
      box-sizing: border-box;
  }
  ```
- Botón `.dock-tab`:
  - Flex vertical (icono SVG arriba, etiqueta de texto abajo).
  - Texto en monospace compacto (`font-size: 0.65rem`, `letter-spacing: 1px`, `color: var(--text-muted)`).
  - Estado `.active`: color de texto e icono en `var(--cyan)`, con una línea superior brillante (`box-shadow: 0 -2px 0 var(--cyan)` o pseudo-elemento `::before`).

### 9. Animaciones
- `@keyframes spin` para spinners de carga (`Cambiando chats, por favor espere...`).
- `@keyframes pulse-core` para latidos del reactor.

---

## Verificacion de Integridad
1. Comprobar que ninguna regla rompa el scroll ni oculte el input de texto en el chat.
2. Auditar que el padding inferior de las vistas sea suficiente para no quedar tapado por el dock.
3. Verificar que las fuentes y colores mantengan contraste legible en pantalla de teléfono al sol.
