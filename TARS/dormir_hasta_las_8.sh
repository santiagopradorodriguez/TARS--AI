#!/usr/bin/env bash
# Suspende la PC en RAM (modo mem) y la despierta automáticamente a la hora indicada (por defecto 08:00),
# asegurando que Antigravity IDE y TARS estén abiertos al despertar.

WAKE_TIME="${1:-08:00}"
NOW=$(date +%s)
TARGET=$(date -d "today $WAKE_TIME" +%s)

if [ "$TARGET" -le "$NOW" ]; then
    TARGET=$(date -d "tomorrow $WAKE_TIME" +%s)
fi

SECS=$((TARGET - NOW))
WAKE_HUMAN=$(date -d "@$TARGET" "+%Y-%m-%d %H:%M:%S")

ensure_antigravity() {
    export DISPLAY="${DISPLAY:-:0}"
    export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
    if ! pgrep -f "Antigravity-x64/antigravity" >/dev/null 2>&1 && ! pgrep -x "antigravity" >/dev/null 2>&1; then
        if [ -x "$HOME/Descargas/Antigravity-x64/antigravity" ]; then
            nohup "$HOME/Descargas/Antigravity-x64/antigravity" >/dev/null 2>&1 &
        elif [ -x "/usr/share/antigravity/antigravity" ]; then
            nohup /usr/share/antigravity/antigravity --remote-debugging-port=9223 >/dev/null 2>&1 &
        elif command -v antigravity >/dev/null 2>&1; then
            nohup antigravity --remote-debugging-port=9223 >/dev/null 2>&1 &
        fi
    fi
}

echo "🌙 Asegurando que Antigravity esté abierto antes de suspender..."
ensure_antigravity

echo "⏰ Suspendiendo PC por $SECS segundos (despertará a las $WAKE_HUMAN)..."
sudo -n rtcwake -m mem -s "$SECS"

# Al despertar a las 08:00 AM:
sleep 4
echo "☀️ PC despierta ($(date)). Verificando Antigravity y TARS..."
ensure_antigravity
systemctl --user start tars-web.service 2>/dev/null || true
