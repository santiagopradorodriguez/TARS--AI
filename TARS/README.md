# TARS - Interfaz de Voz Inteligente

Este directorio contiene el código fuente de TARS, una interfaz de voz avanzada construida sobre Antigravity. TARS implementa un sistema robusto de detección de Wake Word, control Push-to-Talk y un semáforo de privacidad en la bandeja del sistema.

## Características Principales

*   **Detección de Wake Word (Offline):** Utiliza `vosk` para detectar la frase "Hola TARS" en modo manos libres sin depender de la nube.
*   **Semáforo de Privacidad (3 Estados):** 
    *   **Verde (Modo Libre):** Escucha activamente la palabra clave.
    *   **Amarillo (Push-to-Talk):** Desactiva el micrófono continuo y sólo escucha al presionar la tecla F12 (Walkie-Talkie).
    *   **Rojo (Apagado/Killswitch):** Silencia el micrófono a nivel de sistema operativo (`pactl` / `wpctl`) y bloquea cualquier entrada.
*   **Dictado Push-To-Talk (F12):** Integración nativa con teclado para dictar comandos largos y enviarlos automáticamente.
*   **Feedback Acústico Aislado:** Genera tonos puros para confirmar inicio, envío y cancelación de comandos, aislados del reconocimiento de voz mediante `tars_player.py` para evitar que el asistente se escuche a sí mismo.
*   **Filtro Matemático/LaTeX en TTS:** Procesa la sintaxis compleja de respuestas generadas (Markdown y LaTeX) traduciéndolas a expresiones habladas naturales en español (ej. flechas, unidades, fórmulas).
*   **Monitor de WhatsApp:** Intercepta notificaciones de escritorio (como ZapZap) usando DBus y anuncia el nombre del remitente por voz, con un sistema antispam.

## Instalación y Configuración

Los scripts en este directorio están diseñados para operar integrados con la configuración de **Antigravity**. 
Típicamente, estos archivos deben ubicarse en la carpeta `~/.gemini/config/`.

### Dependencias Principales
```bash
pip install vosk sounddevice pynput pystray Pillow edge-tts numpy
sudo apt install pulseaudio-utils wireplumber
```

### Arquitectura de Archivos
*   `tars_wake_word.py`: Demonio principal de reconocimiento continuo.
*   `f12_listener.py`: Monitor global de teclado para Push-to-Talk.
*   `tars_tray.py`: UI de la bandeja del sistema (íconos y menú).
*   `speak_response.py`: Procesamiento de texto y síntesis TTS (Edge-TTS).
*   `tars_player.py`: Reproductor de audio seguro (silencia el mic durante la reproducción).
*   `tars_whatsapp.py`: Monitor de DBus para notificaciones entrantes.
*   `generate_cues.py`: Sintetizador de los efectos de sonido.
