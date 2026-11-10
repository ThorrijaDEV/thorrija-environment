#!/usr/bin/env bash
# install.sh — Thorrija Environment Bootstrap
# Version: 0.2.0-dev
# SHA256 del tarball release: ACTUALIZAR_EN_CI

set -euo pipefail

# --- Configuración inmutable (actualizada por CI en cada release) ---
REPO="ThorrijaDEV/thorrija-environment"
RELEASE_VERSION="latest"
SHA256_EXPECTED="PENDING_RELEASE_HASH"
BOOTSTRAP_VERSION="0.2.0-dev"
# --- Fin Config ---

readonly REPO RELEASE_VERSION SHA256_EXPECTED BOOTSTRAP_VERSION

# Colores para output (solo si stdout es TTY)
if [[ -t 1 ]]; then
    readonly C_RESET='\033[0m' C_BOLD='\033[1m' C_RED='\033[31m' C_GREEN='\033[32m' C_YELLOW='\033[33m' C_BLUE='\033[34m' C_CYAN='\033[36m'
else
    readonly C_RESET='' C_BOLD='' C_RED='' C_GREEN='' C_YELLOW='' C_BLUE='' C_CYAN=''
fi

log_info()  { printf "${C_BLUE}[INFO]${C_RESET} %s\n" "$*"; }
log_ok()    { printf "${C_GREEN}[OK]${C_RESET} %s\n" "$*"; }
log_warn()  { printf "${C_YELLOW}[WARN]${C_RESET} %s\n" "$*"; }
log_error() { printf "${C_RED}[ERROR]${C_RESET} %s\n" "$*" >&2; }
log_debug() { [[ "${THORRIJA_DEBUG:-0}" == "1" ]] && printf "${C_CYAN}[DEBUG]${C_RESET} %s\n" "$*"; }

usage() {
    cat <<'EOF'
Thorrija Environment — Bootstrap Installer

Uso: ./install.sh [OPCIONES_BOOTSTRAP] -- [OPCIONES_MOTOR]

Opciones del bootstrap:
  -h, --help           Muestra esta ayuda
  -V, --version        Versión del bootstrap
      --dev            Modo desarrollo (usa código local, sin descarga)
      --verify-only    Solo verifica hash del tarball (modo release)
      --python PATH    Forzar binario Python específico
      --no-python-check Saltar verificación versión Python (peligroso)
      --debug          Activar logs de debug

Todas las demás opciones se pasan al motor Python.
Ejemplos:
  ./install.sh -- --detect
  ./install.sh -- --profile standard --plan
  ./install.sh -- --profile standard --yes
EOF
}

# --- Parseo args bootstrap ---
BOOTSTRAP_ARGS=()
ENGINE_ARGS=()
PASSTHROUGH=0
FORCE_PYTHON=""
SKIP_PYTHON_CHECK=0
DEV_MODE=0
VERIFY_ONLY=0

for arg in "$@"; do
    if [[ $PASSTHROUGH -eq 1 ]]; then
        ENGINE_ARGS+=("$arg")
    elif [[ "$arg" == "--" ]]; then
        PASSTHROUGH=1
    elif [[ "$arg" =~ ^(--help|-h)$ ]]; then
        usage; exit 0
    elif [[ "$arg" =~ ^(--version|-V)$ ]]; then
        echo "thorrija-bootstrap $BOOTSTRAP_VERSION"; exit 0
    elif [[ "$arg" == "--dev" ]]; then
        DEV_MODE=1
    elif [[ "$arg" == "--verify-only" ]]; then
        VERIFY_ONLY=1
    elif [[ "$arg" == "--python" ]]; then
        FORCE_PYTHON="${2:-}"; shift
        [[ -z "$FORCE_PYTHON" ]] && { log_error "--python requiere argumento"; exit 1; }
    elif [[ "$arg" == "--no-python-check" ]]; then
        SKIP_PYTHON_CHECK=1
    elif [[ "$arg" == "--debug" ]]; then
        export THORRIJA_DEBUG=1
    else
        ENGINE_ARGS+=("$arg")
    fi
done

# --- Validaciones iniciales ---
[[ $EUID -eq 0 ]] && { log_error "No ejecutes como root. Usa usuario normal; sudo se pedirá cuando haga falta."; exit 1; }

command -v curl >/dev/null || command -v wget >/dev/null || { log_error "Se requiere curl o wget"; exit 1; }
command -v tar >/dev/null || { log_error "Se requiere tar"; exit 1; }
command -v sha256sum >/dev/null || { log_error "Se requiere sha256sum"; exit 1; }
command -v mktemp >/dev/null || { log_error "Se requiere mktemp"; exit 1; }

# --- Etapa 1: Asegurar Python ≥ 3.9 ---
find_python() {
    local candidates=()
    [[ -n "$FORCE_PYTHON" ]] && candidates+=("$FORCE_PYTHON")
    candidates+=(python3 python3.13 python3.12 python3.11 python3.10 python3.9)

    for py in "${candidates[@]}"; do
        if command -v "$py" >/dev/null 2>&1; then
            local version
            version=$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null) || continue
            local major minor
            IFS=. read -r major minor <<<"$version"
            if [[ $major -gt 3 ]] || [[ $major -eq 3 && $minor -ge 9 ]]; then
                echo "$py"
                return 0
            fi
            log_debug "Python $py versión $version < 3.9, descartado"
        fi
    done
    return 1
}

PYTHON_BIN=""
if [[ $SKIP_PYTHON_CHECK -eq 1 ]]; then
    PYTHON_BIN=$(command -v python3 || command -v python3.11 || command -v python3.10 || command -v python3.9 || true)
    [[ -z "$PYTHON_BIN" ]] && { log_error "No se encontró python3"; exit 1; }
    log_warn "Saltando verificación de versión Python (--no-python-check)"
else
    log_info "Buscando Python ≥ 3.9..."
    PYTHON_BIN=$(find_python) || true
fi

if [[ -z "$PYTHON_BIN" ]]; then
    log_warn "Python ≥ 3.9 no encontrado en PATH."
    # Detectar distro para ofrecer instalación
    . /etc/os-release 2>/dev/null || { ID="unknown"; }
    PKG_CMD=""
    case "$ID" in
        arch|manjaro|endeavouros) PKG_CMD="pacman -S --needed --noconfirm python" ;;
        debian|ubuntu|linuxmint|pop) PKG_CMD="apt-get update && apt-get install -y python3 python3-venv" ;;
        fedora|rhel|centos|almalinux|rocky) PKG_CMD="dnf install -y python3" ;;
        void) PKG_CMD="xbps-install -Sy python3" ;;
        *) PKG_CMD="" ;;
    esac

    if [[ -n "$PKG_CMD" ]]; then
        echo
        log_info "Se puede instalar automáticamente con el gestor de tu distro:"
        echo "  Comando: sudo $PKG_CMD"
        echo "  (Detectado: ${PRETTY_NAME:-$ID})"
        echo
        read -rp "¿Ejecutar este comando con sudo? [s/N]: " confirm
        if [[ "${confirm,,}" =~ ^(s|y)$ ]]; then
            log_info "Instalando Python..."
            eval "sudo $PKG_CMD" || { log_error "Falló la instalación de Python"; exit 1; }
            PYTHON_BIN=$(find_python) || { log_error "Python instalado pero no detectable"; exit 1; }
            log_ok "Python disponible: $($PYTHON_BIN --version)"
        else
            log_error "Instalación cancelada por el usuario."
            echo
            echo "Instala manualmente uno de:"
            echo "  Arch:      sudo pacman -S python"
            echo "  Debian/Ub: sudo apt-get install python3.11"
            echo "  Fedora:    sudo dnf install python3.11"
            echo "  Void:      sudo xbps-install -Sy python3.11"
            exit 1
        fi
    else
        log_error "Distro no reconocida para auto-instalación."
        echo "Instala Python ≥ 3.9 manualmente y reintenta."
        exit 1
    fi
fi

log_ok "Python detectado: $($PYTHON_BIN --version)"

# Verificar que tomllib/tomli está disponible (o lo vendorearemos)
if ! "$PYTHON_BIN" -c "import tomllib" 2>/dev/null && ! "$PYTHON_BIN" -c "import tomli" 2>/dev/null; then
    log_warn "tomllib/tomli no disponible en Python del sistema; se usará vendor incluido"
fi

# --- Etapa 2: Obtener código fuente ---
WORKDIR=""
CLEANUP=()

cleanup() {
    for item in "${CLEANUP[@]}"; do
        [[ -e "$item" ]] && rm -rf "$item"
    done
}
trap cleanup EXIT

if [[ $DEV_MODE -eq 1 ]]; then
    # Modo desarrollo: usar código local (donde está este script)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -d "$SCRIPT_DIR/src/thorrija" && -d "$SCRIPT_DIR/catalog" ]]; then
        WORKDIR="$SCRIPT_DIR"
        log_info "Modo desarrollo: usando código local en $WORKDIR"
    else
        log_error "--dev requiere ejecutarse desde la raíz del repo clonado (con src/ y catalog/)"
        exit 1
    fi
else
    # Modo release: descargar y verificar tarball
    TMPDIR=$(mktemp -d -t thorrija-XXXXXX)
    CLEANUP+=("$TMPDIR")
    TARBALL="$TMPDIR/thorrija.tar.gz"

    if [[ "$RELEASE_VERSION" == "latest" ]]; then
        # Resolver latest via GitHub API
        log_info "Resolviendo última versión desde GitHub..."
        LATEST_URL="https://api.github.com/repos/$REPO/releases/latest"
        RELEASE_JSON=$(curl -fsSL "$LATEST_URL" 2>/dev/null) || { log_error "No se pudo obtener release info de GitHub"; exit 1; }
        TAG=$(echo "$RELEASE_JSON" | grep -o '"tag_name": *"[^"]*"' | cut -d'"' -f4)
        [[ -z "$TAG" ]] && { log_error "No se pudo parsear tag_name de GitHub API"; exit 1; }
        RELEASE_VERSION="$TAG"
        log_info "Última versión: $RELEASE_VERSION"
    fi

    TARBALL_URL="https://github.com/${REPO}/releases/download/${RELEASE_VERSION}/thorrija-environment-${RELEASE_VERSION}.tar.gz"
    log_info "Descargando $TARBALL_URL ..."
    if command -v curl >/dev/null; then
        curl -fsSL -o "$TARBALL" "$TARBALL_URL" || { log_error "Falló descarga con curl"; exit 1; }
    else
        wget -q -O "$TARBALL" "$TARBALL_URL" || { log_error "Falló descarga con wget"; exit 1; }
    fi

    if [[ $VERIFY_ONLY -eq 1 ]]; then
        ACTUAL_SHA=$(sha256sum "$TARBALL" | cut -d' ' -f1)
        echo "SHA256 actual: $ACTUAL_SHA"
        echo "SHA256 esperado: $SHA256_EXPECTED"
        [[ "$ACTUAL_SHA" == "$SHA256_EXPECTED" ]] && { log_ok "Hash verificado"; exit 0; } || { log_error "Hash NO coincide"; exit 1; }
    fi

    if [[ "$SHA256_EXPECTED" != "PENDING_RELEASE_HASH" ]]; then
        log_info "Verificando integridad (SHA-256)..."
        ACTUAL_SHA=$(sha256sum "$TARBALL" | cut -d' ' -f1)
        if [[ "$ACTUAL_SHA" != "$SHA256_EXPECTED" ]]; then
            log_error "Integridad del instalador comprometida."
            echo "  Hash esperado: $SHA256_EXPECTED"
            echo "  Hash real:     $ACTUAL_SHA"
            echo "No continúes. Descarga manualmente desde:"
            echo "https://github.com/$REPO/releases"
            exit 1
        fi
        log_ok "Hash verificado correctamente"
    else
        log_warn "SHA256_EXPECTED no configurado (build de desarrollo). Saltando verificación de integridad."
    fi

    log_info "Extrayendo..."
    EXTRACT_DIR="$TMPDIR/thorrija-extracted"
    mkdir -p "$EXTRACT_DIR"
    tar -xzf "$TARBALL" -C "$EXTRACT_DIR" --strip-components=1 || { log_error "Falló extracción"; exit 1; }

    # Verificar estructura esperada
    [[ -d "$EXTRACT_DIR/src/thorrija" && -d "$EXTRACT_DIR/catalog" ]] || { log_error "Estructura de release inválida"; exit 1; }

    WORKDIR="$EXTRACT_DIR"
    log_ok "Código fuente listo en $WORKDIR"
fi

# --- Etapa 3: Delegar al motor Python ---
cd "$WORKDIR"
export THORRIJA_BOOTSTRAP=1
export THORRIJA_WORKDIR="$WORKDIR"

log_info "Iniciando motor Python..."
exec "$PYTHON_BIN" -m thorrija "${ENGINE_ARGS[@]}"