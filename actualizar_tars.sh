#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.gemini/config"

echo "🔄 Actualizando TARS desde $REPO_DIR/TARS hacia $CONFIG_DIR..."
mkdir -p "$CONFIG_DIR/web/static" "$CONFIG_DIR/web/media"

cp "$REPO_DIR/TARS/tars_web_server.py" "$CONFIG_DIR/tars_web_server.py"
cp "$REPO_DIR/TARS/speak_response.py" "$CONFIG_DIR/speak_response.py" 2>/dev/null || true
cp "$REPO_DIR/TARS/tars_voice_engine.py" "$CONFIG_DIR/tars_voice_engine.py" 2>/dev/null || true
if [ -f "$REPO_DIR/TARS/dormir_hasta_las_8.sh" ]; then
    chmod +x "$REPO_DIR/TARS/dormir_hasta_las_8.sh"
    cp "$REPO_DIR/TARS/dormir_hasta_las_8.sh" "$CONFIG_DIR/dormir_hasta_las_8.sh"
    cp "$REPO_DIR/TARS/dormir_hasta_las_8.sh" "$HOME/dormir_hasta_las_8.sh"
fi
cp "$REPO_DIR/TARS/web/index.html" "$CONFIG_DIR/web/index.html"
cp "$REPO_DIR/TARS/web/sw.js" "$CONFIG_DIR/web/sw.js" 2>/dev/null || true
cp "$REPO_DIR/TARS/web/manifest.json" "$CONFIG_DIR/web/manifest.json" 2>/dev/null || true
cp "$REPO_DIR/TARS/web/static/app.js" "$CONFIG_DIR/web/static/app.js"
cp "$REPO_DIR/TARS/web/static/style.css" "$CONFIG_DIR/web/static/style.css"

if systemctl --user list-unit-files | grep -q "tars-web.service"; then
    echo "🚀 Reiniciando servicio tars-web.service..."
    systemctl --user reset-failed tars-web.service 2>/dev/null || true
    systemctl --user restart tars-web.service
    systemctl --user is-active tars-web.service
fi

echo "✅ ¡TARS actualizado y en línea!"
