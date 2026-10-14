#!/usr/bin/env bash
# ==============================================================================
# Script de Instalacion Asistido - TARS AI & Jarvis Assistant
# Sistema Operativo objetivo: Linux (Debian/Ubuntu, Arch, Fedora)
# Regla estricta: Cero emojis en este script y en salidas de consola.
# ==============================================================================

set -eo pipefail

# Colores ANSI para salida en terminal (sin emojis)
CLR_RESET="\033[0m"
CLR_BOLD="\033[1m"
CLR_RED="\033[31m"
CLR_GREEN="\033[32m"
CLR_YELLOW="\033[33m"
CLR_BLUE="\033[34m"
CLR_CYAN="\033[36m"

log_info() {
    echo -e "${CLR_BLUE}[INFO]${CLR_RESET} $1"
}

log_ok() {
    echo -e "${CLR_GREEN}[OK]${CLR_RESET} $1"
}

log_warn() {
    echo -e "${CLR_YELLOW}[ADVERTENCIA]${CLR_RESET} $1"
}

log_error() {
    echo -e "${CLR_RED}[ERROR]${CLR_RESET} $1"
}

log_step() {
    echo -e "\n${CLR_BOLD}${CLR_CYAN}==> [$1] $2${CLR_RESET}"
}

# Resolucion de directorios
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
VENV_DIR="${PROJECT_ROOT}/venv"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
VOSK_DIR="${HOME}/.gemini/models/vosk-model-small-es-0.42"
VOSK_ZIP_URL="https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
CERTS_DIR="${PROJECT_ROOT}/TARS/certs"
CERT_FILE="${CERTS_DIR}/cert.pem"
KEY_FILE="${CERTS_DIR}/key.pem"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="tars-web.service"
SERVICE_TEMPLATE="${PROJECT_ROOT}/systemd/tars-web.service"

# Variables de control de argumentos
AUTO_CONFIRM=false
SKIP_VOSK=false
SKIP_SERVICE=false

print_help() {
    echo "Uso: ./install.sh [OPCIONES]"
    echo ""
    echo "Opciones disponibles:"
    echo "  -y, --yes              Modo no interactivo; asume si a las preguntas confirmables."
    echo "  --skip-vosk            Omite la verificacion y descarga del modelo Vosk."
    echo "  --skip-service         Omite la configuracion del servicio systemd de usuario."
    echo "  -h, --help             Muestra este mensaje de ayuda y termina."
    echo ""
    echo "Ejemplos:"
    echo "  ./install.sh"
    echo "  ./install.sh -y"
    echo "  ./install.sh --skip-vosk"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes)
            AUTO_CONFIRM=true
            shift
            ;;
        --skip-vosk)
            SKIP_VOSK=true
            shift
            ;;
        --skip-service)
            SKIP_SERVICE=true
            shift
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        *)
            log_error "Opcion no reconocida: $1"
            print_help
            exit 1
            ;;
    esac
done

echo "=============================================================================="
echo "          INSTALADOR ASISTIDO - TARS AI & JARVIS ASSISTANT"
echo "=============================================================================="
log_info "Directorio del proyecto: ${PROJECT_ROOT}"

# ------------------------------------------------------------------------------
# PASO 1: Verificacion de dependencias del sistema operativo Linux
# ------------------------------------------------------------------------------
log_step "1/5" "Verificando dependencias del sistema operativo..."

MISSING_SYS_DEPS=()

# 1.1 Python 3
if ! command -v python3 &>/dev/null; then
    MISSING_SYS_DEPS+=("python3")
else
    PY_VER=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
    log_ok "Python 3 detectado (version ${PY_VER})."
fi

# 1.2 Modulo venv de Python
if ! python3 -m venv --help &>/dev/null; then
    MISSING_SYS_DEPS+=("python3-venv")
else
    log_ok "Modulo python3-venv disponible."
fi

# 1.3 ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    MISSING_SYS_DEPS+=("ffmpeg")
else
    log_ok "Herramienta ffmpeg detectada."
fi

# 1.4 Servidor de audio (PulseAudio o PipeWire / WirePlumber)
AUDIO_CLI_FOUND=false
if command -v paplay &>/dev/null; then
    log_ok "Herramienta de audio paplay (pulseaudio-utils) detectada."
    AUDIO_CLI_FOUND=true
fi
if command -v pw-play &>/dev/null || command -v wpctl &>/dev/null; then
    log_ok "Herramienta de audio PipeWire/WirePlumber detectada."
    AUDIO_CLI_FOUND=true
fi
if [ "$AUDIO_CLI_FOUND" = false ]; then
    MISSING_SYS_DEPS+=("pulseaudio-utils / wireplumber")
fi

# 1.5 PortAudio (cabeceras para compilacion de PyAudio / sounddevice)
if ! ldconfig -p 2>/dev/null | grep -q "libportaudio" && [ ! -f /usr/include/portaudio.h ]; then
    log_warn "No se detectaron cabeceras o librerias nativas de PortAudio (portaudio19-dev)."
    log_warn "Son necesarias para que SpeechRecognition acceda al microfono con PyAudio."
    MISSING_SYS_DEPS+=("portaudio19-dev")
else
    log_ok "Libreria nativa de PortAudio detectada."
fi

# 1.6 OpenSSL
if ! command -v openssl &>/dev/null; then
    MISSING_SYS_DEPS+=("openssl")
else
    log_ok "Herramienta openssl detectada."
fi

# 1.7 Herramientas para descarga y descompresion
if ! command -v curl &>/dev/null && ! command -v wget &>/dev/null; then
    MISSING_SYS_DEPS+=("curl o wget")
fi
if ! command -v unzip &>/dev/null; then
    MISSING_SYS_DEPS+=("unzip")
fi

if [ ${#MISSING_SYS_DEPS[@]} -gt 0 ]; then
    echo ""
    log_warn "Se encontraron paquetes o librerias faltantes en el sistema:"
    for dep in "${MISSING_SYS_DEPS[@]}"; do
        echo "  - ${dep}"
    done
    echo ""
    log_info "Comandos sugeridos segun tu distribucion Linux:"
    echo "  [Debian / Ubuntu / Pop!_OS]:"
    echo "    sudo apt update && sudo apt install -y python3-venv python3-dev ffmpeg pulseaudio-utils wireplumber portaudio19-dev libasound2-dev openssl curl wget unzip"
    echo ""
    echo "  [Fedora / RHEL]:"
    echo "    sudo dnf install -y python3-devel ffmpeg-free pulseaudio-utils portaudio-devel openssl curl wget unzip"
    echo ""
    echo "  [Arch Linux / Manjaro]:"
    echo "    sudo pacman -S --needed python ffmpeg pulseaudio-utils portaudio openssl curl wget unzip"
    echo ""

    if [ "$AUTO_CONFIRM" = false ]; then
        read -r -p "Deseas continuar con la instalacion a pesar de las dependencias faltantes? [s/N]: " RESP_CONT
        case "${RESP_CONT}" in
            [sS]|[yY]|[sS][iI])
                log_info "Continuando con la instalacion por indicacion del usuario."
                ;;
            *)
                log_error "Instalacion cancelada. Por favor instala las dependencias de sistema e intenta nuevamente."
                exit 1
                ;;
        esac
    fi
else
    log_ok "Todas las dependencias de sistema requeridas estan presentes."
fi

# ------------------------------------------------------------------------------
# PASO 2: Creacion o verificacion de entorno virtual de Python
# ------------------------------------------------------------------------------
log_step "2/5" "Configurando entorno virtual de Python (venv)..."

if [ -d "${VENV_DIR}" ] && [ -f "${VENV_DIR}/bin/python" ]; then
    log_ok "Entorno virtual existente detectado en: ${VENV_DIR}"
else
    log_info "Creando nuevo entorno virtual en: ${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
    log_ok "Entorno virtual creado exitosamente."
fi

log_info "Actualizando pip, setuptools y wheel..."
"${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel --quiet
log_ok "Herramientas de empaquetado actualizadas."

# ------------------------------------------------------------------------------
# PASO 3: Instalacion de dependencias de Python (requirements.txt)
# ------------------------------------------------------------------------------
log_step "3/5" "Instalando paquetes de Python desde requirements.txt..."

if [ ! -f "${REQUIREMENTS_FILE}" ]; then
    log_error "No se encontro el archivo ${REQUIREMENTS_FILE}."
    exit 1
fi

log_info "Instalando requerimientos en el entorno virtual..."
"${VENV_DIR}/bin/pip" install -r "${REQUIREMENTS_FILE}"
log_ok "Dependencias de Python instaladas correctamente."

# ------------------------------------------------------------------------------
# PASO 4: Descarga y verificacion del modelo liviano Vosk en espanol
# ------------------------------------------------------------------------------
log_step "4/5" "Verificando modelo acustico Vosk en espanol..."

if [ "$SKIP_VOSK" = true ]; then
    log_info "Omitiendo verificacion de modelo Vosk por indicacion (--skip-vosk)."
else
    if [ -d "${VOSK_DIR}" ] && [ -d "${VOSK_DIR}/am" ]; then
        log_ok "Modelo Vosk encontrado en: ${VOSK_DIR}"
    else
        log_info "El modelo no se encontro en ${VOSK_DIR}."
        DOWNLOAD_VOSK=true
        if [ "$AUTO_CONFIRM" = false ]; then
            read -r -p "Deseas descargar el modelo liviano de Vosk en espanol (~45MB)? [S/n]: " RESP_VOSK
            case "${RESP_VOSK}" in
                [nN]|[nN][oO])
                    DOWNLOAD_VOSK=false
                    log_warn "Descarga de modelo Vosk omitida por el usuario."
                    ;;
                *)
                    DOWNLOAD_VOSK=true
                    ;;
            esac
        fi

        if [ "$DOWNLOAD_VOSK" = true ]; then
            MODELS_PARENT_DIR="$(dirname "${VOSK_DIR}")"
            mkdir -p "${MODELS_PARENT_DIR}"
            TMP_ZIP="/tmp/vosk-model-small-es-0.42.zip"

            log_info "Descargando modelo desde Alphacephei..."
            if command -v curl &>/dev/null; then
                curl -L -o "${TMP_ZIP}" "${VOSK_ZIP_URL}"
            else
                wget -O "${TMP_ZIP}" "${VOSK_ZIP_URL}"
            fi

            log_info "Descomprimiendo modelo en ${MODELS_PARENT_DIR}..."
            unzip -q -o "${TMP_ZIP}" -d "${MODELS_PARENT_DIR}"
            rm -f "${TMP_ZIP}"

            if [ -d "${VOSK_DIR}" ]; then
                log_ok "Modelo Vosk descargado y configurado exitosamente en: ${VOSK_DIR}"
            else
                log_warn "No se pudo verificar la estructura final del modelo Vosk extraido."
            fi
        fi
    fi
fi

# ------------------------------------------------------------------------------
# PASO 5: Certificados SSL autofirmados para el servidor web movil
# ------------------------------------------------------------------------------
log_step "5/5" "Verificando certificados SSL para TARS Mobile WebApp..."

mkdir -p "${CERTS_DIR}"

LOCAL_IP="127.0.0.1"
if command -v ip &>/dev/null; then
    DETECTED_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')
    if [ -n "${DETECTED_IP}" ]; then
        LOCAL_IP="${DETECTED_IP}"
    fi
elif command -v hostname &>/dev/null; then
    DETECTED_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [ -n "${DETECTED_IP}" ]; then
        LOCAL_IP="${DETECTED_IP}"
    fi
fi

TAILSCALE_IP=""
if command -v tailscale &>/dev/null; then
    TS_OUT=$(tailscale ip -4 2>/dev/null || true)
    if [ -n "${TS_OUT}" ]; then
        TAILSCALE_IP=$(echo "${TS_OUT}" | awk '{print $1}')
    fi
fi

GENERATE_SSL=false
if [ ! -f "${CERT_FILE}" ] || [ ! -f "${KEY_FILE}" ]; then
    log_info "No se encontraron certificados SSL previos. Generando nuevo par de claves..."
    GENERATE_SSL=true
else
    log_ok "Certificados SSL encontrados en: ${CERTS_DIR}"
    if [ "$AUTO_CONFIRM" = false ]; then
        read -r -p "Deseas regenerar los certificados SSL con tu IP local actual (${LOCAL_IP})? [s/N]: " RESP_SSL
        case "${RESP_SSL}" in
            [sS]|[yY]|[sS][iI])
                GENERATE_SSL=true
                ;;
            *)
                GENERATE_SSL=false
                ;;
        esac
    fi
fi

if [ "$GENERATE_SSL" = true ]; then
    SAN="subjectAltName=DNS:localhost,IP:127.0.0.1,IP:${LOCAL_IP}"
    if [ -n "${TAILSCALE_IP}" ]; then
        SAN="${SAN},IP:${TAILSCALE_IP}"
        log_info "Incluyendo IP de Tailscale detectada: ${TAILSCALE_IP}"
    fi

    log_info "Generando certificado autofirmado para IP: ${LOCAL_IP}..."
    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout "${KEY_FILE}" \
        -out "${CERT_FILE}" \
        -days 3650 \
        -subj "/CN=${LOCAL_IP}" \
        -addext "${SAN}" >/dev/null 2>&1

    chmod 600 "${KEY_FILE}"
    chmod 644 "${CERT_FILE}"
    log_ok "Certificados SSL generados exitosamente en ${CERTS_DIR}."
fi

# ------------------------------------------------------------------------------
# SERVICIO SYSTEMD DE USUARIO (tars-web.service)
# ------------------------------------------------------------------------------
echo ""
echo "------------------------------------------------------------------------------"
echo " CONFIGURACION DEL SERVICIO SYSTEMD DE USUARIO (tars-web.service)"
echo "------------------------------------------------------------------------------"

if [ "$SKIP_SERVICE" = true ]; then
    log_info "Instalacion de servicio systemd omitida (--skip-service)."
else
    INSTALL_SERVICE=false
    if [ "$AUTO_CONFIRM" = true ]; then
        INSTALL_SERVICE=true
    else
        read -r -p "Deseas configurar e instalar el servicio systemd de usuario para tars-web? [s/N]: " RESP_SRV
        case "${RESP_SRV}" in
            [sS]|[yY]|[sS][iI])
                INSTALL_SERVICE=true
                ;;
            *)
                INSTALL_SERVICE=false
                ;;
        esac
    fi

    if [ "$INSTALL_SERVICE" = true ]; then
        mkdir -p "${SYSTEMD_USER_DIR}"
        TARGET_SERVICE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}"

        cat <<EOF > "${TARGET_SERVICE}"
[Unit]
Description=TARS Mobile WebApp Server
After=network.target

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=${PROJECT_ROOT}/TARS
ExecStart=${VENV_DIR}/bin/python -u ${PROJECT_ROOT}/TARS/tars_web_server.py
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

        log_ok "Archivo de servicio creado en: ${TARGET_SERVICE}"

        if command -v systemctl &>/dev/null; then
            systemctl --user daemon-reload
            log_ok "systemctl --user daemon-reload ejecutado."

            START_NOW=false
            if [ "$AUTO_CONFIRM" = false ]; then
                read -r -p "Deseas habilitar e iniciar el servicio tars-web.service ahora mismo? [s/N]: " RESP_START
                case "${RESP_START}" in
                    [sS]|[yY]|[sS][iI])
                        START_NOW=true
                        ;;
                    *)
                        START_NOW=false
                        ;;
                esac
            fi

            if [ "$START_NOW" = true ]; then
                systemctl --user enable "${SERVICE_NAME}"
                systemctl --user restart "${SERVICE_NAME}"
                log_ok "Servicio ${SERVICE_NAME} habilitado e iniciado."
                log_info "Estado del servicio:"
                systemctl --user status "${SERVICE_NAME}" --no-pager || true
            else
                log_info "Para activar e iniciar el servicio manualmente en el futuro:"
                echo "  systemctl --user enable ${SERVICE_NAME}"
                echo "  systemctl --user start ${SERVICE_NAME}"
            fi
        else
            log_warn "systemctl no disponible en esta sesion. Copiado el archivo a ${TARGET_SERVICE}."
        fi
    else
        log_info "Instalacion automatica del servicio omitida."
        echo "Si deseas instalarlo manualmente:"
        echo "  1. Copia el archivo ${SERVICE_TEMPLATE} a ~/.config/systemd/user/"
        echo "  2. Ajusta las rutas a tu entorno virtual y repositorio."
        echo "  3. Ejecuta: systemctl --user daemon-reload && systemctl --user enable --now tars-web.service"
    fi
fi

# ------------------------------------------------------------------------------
# RESUMEN Y FINALIZACION
# ------------------------------------------------------------------------------
echo ""
echo "=============================================================================="
echo "          INSTALACION COMPLETADA EXITOSAMENTE"
echo "=============================================================================="
echo ""
echo "Para comenzar a utilizar el proyecto:"
echo ""
echo "1. Activar el entorno virtual:"
echo "   source ${VENV_DIR}/bin/activate"
echo ""
echo "2. Ejecutar la interfaz grafica principal de Jarvis:"
echo "   python ${PROJECT_ROOT}/jarvis_gui.py"
echo ""
echo "3. Ejecutar el servidor web movil de TARS (manualmente):"
echo "   python ${PROJECT_ROOT}/TARS/tars_web_server.py"
echo ""
echo "4. Administrar el servicio en segundo plano (si fue instalado):"
echo "   systemctl --user status tars-web.service"
echo "   systemctl --user restart tars-web.service"
echo "   systemctl --user stop tars-web.service"
echo ""
echo "5. Direccion de acceso web movil (con SSL):"
echo "   https://${LOCAL_IP}:8443"
if [ -n "${TAILSCALE_IP}" ]; then
    echo "   https://${TAILSCALE_IP}:8443 (Tailscale)"
fi
echo ""
echo "=============================================================================="
