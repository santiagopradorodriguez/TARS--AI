#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$HOME/.config/tars" ] && [ ! -d "$HOME/.gemini/config" ]; then
    CONFIG_DIR="$HOME/.config/tars"
else
    CONFIG_DIR="$HOME/.gemini/config"
fi

echo "Actualizando TARS desde $REPO_DIR/TARS hacia $CONFIG_DIR..."
mkdir -p "$CONFIG_DIR/web/static" "$CONFIG_DIR/web/media"

cp "$REPO_DIR/TARS/tars_web_server.py" "$CONFIG_DIR/tars_web_server.py"
cp "$REPO_DIR/TARS/speak_response.py" "$CONFIG_DIR/speak_response.py" 2>/dev/null || true
cp "$REPO_DIR/TARS/tars_voice_engine.py" "$CONFIG_DIR/tars_voice_engine.py" 2>/dev/null || true
cp "$REPO_DIR/TARS/zapzap_listener.py" "$CONFIG_DIR/zapzap_listener.py" 2>/dev/null || true
cp "$REPO_DIR/TARS/tars_player.py" "$CONFIG_DIR/tars_player.py" 2>/dev/null || true
cp -r "$REPO_DIR/TARS/cues_puck" "$CONFIG_DIR/" 2>/dev/null || true
cp "$REPO_DIR/TARS/"*.wav "$CONFIG_DIR/" 2>/dev/null || true
if [ -f "$REPO_DIR/TARS/dormir_hasta_las_8.sh" ]; then
    chmod +x "$REPO_DIR/TARS/dormir_hasta_las_8.sh"
    cp "$REPO_DIR/TARS/dormir_hasta_las_8.sh" "$CONFIG_DIR/dormir_hasta_las_8.sh"
    cp "$REPO_DIR/TARS/dormir_hasta_las_8.sh" "$HOME/dormir_hasta_las_8.sh"
fi
cp "$REPO_DIR/TARS/web/index.html" "$CONFIG_DIR/web/index.html"
cp "$REPO_DIR/TARS/web/sw.js" "$CONFIG_DIR/web/sw.js" 2>/dev/null || true
cp "$REPO_DIR/TARS/web/manifest.json" "$CONFIG_DIR/web/manifest.json" 2>/dev/null || true
cp -r "$REPO_DIR/TARS/web/static/." "$CONFIG_DIR/web/static/"

if sudo -n iptables -t nat -L PREROUTING -n 2>/dev/null | grep -q "8443"; then
    true
else
    sudo -n iptables -t nat -A PREROUTING -p tcp --dport 443 -j REDIRECT --to-ports 8443 2>/dev/null || true
    sudo -n iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 8080 2>/dev/null || true
    sudo -n iptables -t nat -A OUTPUT -p tcp -d 127.0.0.1 --dport 443 -j REDIRECT --to-ports 8443 2>/dev/null || true
fi

if systemctl --user list-unit-files | grep -q "tars-web.service"; then
    echo "Reiniciando servicio tars-web.service..."
    systemctl --user reset-failed tars-web.service 2>/dev/null || true
    systemctl --user restart tars-web.service
    systemctl --user is-active tars-web.service
fi

if systemctl --user list-unit-files | grep -q "zapzap-voice-notifier.service"; then
    echo "Reiniciando servicio zapzap-voice-notifier.service..."
    systemctl --user reset-failed zapzap-voice-notifier.service 2>/dev/null || true
    systemctl --user restart zapzap-voice-notifier.service
    systemctl --user is-active zapzap-voice-notifier.service
fi

if systemctl --user list-unit-files | grep -q "tars-tunnel.service"; then
    systemctl --user stop tars-tunnel.service 2>/dev/null || true
    systemctl --user disable tars-tunnel.service 2>/dev/null || true
fi

echo "TARS actualizado y en linea."
