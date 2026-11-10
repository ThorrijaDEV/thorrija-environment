# Bootstrap (`install.sh`)

## Objetivo

`install.sh` es el **único punto de entrada**. Debe:

1. Funcionar en **cualquier Linux** con Bash POSIX-ish (sin `bashisms` innecesarios)
2. Verificar/obtener **Python ≥ 3.9** (piso del motor)
3. Validar **integridad** del código descargado (hash SHA-256)
4. Delegar en el motor Python (`python3 -m thorrija ...`)
5. **Nunca** ejecutar código remoto sin verificación (`curl | bash` prohibido)

---

## Flujo

```
inicio → args --help/--version? → validar entorno → asegurar Python ≥3.9 → obtener/validar código → delegar a motor Python
```

### Validación de entorno

- Bash ≥ 4.0 (`BASH_VERSION`)
- `curl`/`wget`, `tar`, `sha256sum`, `mktemp`, `grep`, `sed`, `awk`
- Directorio temporal escribible (`TMPDIR` o `/tmp`)
- No root (rechaza `EUID == 0`: "No ejecutes como root. Usa usuario normal; sudo se pedirá cuando haga falta")

---

### Python ≥ 3.9 (orden de preferencia)

1. **Ya presente** — `python3 --version` ≥ 3.9 → usar ese
2. **Binario específico** — `python3.11`, `python3.10`, `python3.9` en PATH
3. **Instalar via gestor nativo** (con confirmación) — detecta distro, muestra comando, pide `s/N`, ejecuta con sudo
5. **Fallar con instrucciones** — exit 1 con qué instalar manualmente

**Detección de distro (Bash):**
```bash
. /etc/os-release
case "$ID" in
  arch|manjaro|endeavouros) PKG_CMD="pacman -S --needed --noconfirm python" ;;
  debian|ubuntu|linuxmint|pop) PKG_CMD="apt-get update && apt-get install -y python3 python3-venv" ;;
  fedora|rhel|centos|almalinux|rocky) PKG_CMD="dnf install -y python3" ;;
  void) PKG_CMD="xbps-install -Sy python3" ;;
  *) PKG_CMD="" ;;
esac
```

**Mensaje al usuario:**
```
Python ≥ 3.9 no encontrado.

Se puede instalar automáticamente:
  Comando: sudo pacman -S --needed --noconfirm python
  (Detectado: Arch Linux)

¿Ejecutar con sudo? [s/N]:
```

Si el usuario rechaza o distro desconocida → instrucciones manuales + exit 1.

---

### Obtener y validar código

#### A. GitHub Release (producción)

```bash
REPO="ThorrijaDEV/thorrija-environment"
VERSION="v0.1.0"
TARBALL_URL="https://github.com/${REPO}/releases/download/${VERSION}/thorrija-environment-${VERSION}.tar.gz"
SHA256_EXPECTED="a1b2c3d4e5f6..."  # hardcodeado, actualizado por CI
```

1. Descarga a `$TMPDIR/thorrija-XXXXXX.tar.gz`
2. `sha256sum` → compara con `SHA256_EXPECTED`
3. Match → extrae a `$TMPDIR/thorrija-XXXXXX/`
4. Mismatch → **ABORTA** con error claro y link a releases

#### B. Clone local (`--dev`)

```bash
# Detecta .git y usa código directo (sin descarga, sin hash)
# git clone ... && cd thorrija-environment && ./install.sh --dev
```

---

### Delegar al motor Python

```bash
cd "$EXTRACTED_DIR"
export THORRIJA_BOOTSTRAP=1
exec python3 -m thorrija "$@"
```

El motor recibe `sys.argv[1:]`, `THORRIJA_BOOTSTRAP=1`, CWD con `catalog/`, `profiles/`, `src/`.

---

## Python ausente (resumen)

| Escenario | Resolución |
|-----------|------------|
| Python 3.11+ en PATH | Usar directo (`tomllib` en stdlib) |
| Python 3.9/3.10 en PATH | Usar + `tomli` vendored (`src/thorrija/_vendor/tomli.py`) |
| Solo `python3.11`/`python3.10`/`python3.9` en PATH | Usar ese binario |
| Python < 3.9 o ninguno | Ofrecer instalar via gestor nativo (con confirmación) |
| Usuario rechaza auto-instalación | Instrucciones manuales + exit 1 |
| Distro desconocida | Instrucciones genéricas + exit 1 |
| Sin internet para instalar Python | "Descarga Python de python.org o usa gestor offline" + exit 1 |

**Nota**: `tomli` vendored (~50 KB, MIT) en `src/thorrija/_vendor/tomli.py`. En 3.11+ usa `tomllib`. **Cero deps externas en bootstrap**.

---

## Flags del bootstrap

| Flag | Descripción |
|------|-------------|
| `--help`, `-h` | Ayuda del bootstrap y sale |
| `--version`, `-V` | Versión del bootstrap y sale |
| `--dev` | Modo desarrollo: código local (detecta `.git`), sin descarga/hash |
| `--offline` | No implementado — reservado Fase 4; sale 1 |
| `--verify-only` | Solo verifica hash del tarball (modo release) y sale |
| `--python PATH` | Fuerza binario Python específico |
| `--no-python-check` | Peligroso: salta verificación versión (solo testing) |

**El resto** (`--detect`, `--profile`, `--plan`, `--category`, `--yes`, `--audit`, `--update`, `--resume`, etc.) **se pasan tal cual al motor**. El bootstrap no los parsea.

---

## Seguridad

| Medida | Implementación |
|--------|----------------|
| Hash hardcodeado | `SHA256_EXPECTED="..."` en script; CI lo actualiza por release |
| Sin `curl \| bash` | Descarga → verifica hash → extrae → ejecuta Python local |
| Sin root | Rechaza `EUID == 0` al inicio |
| Temporal seguro | `mktemp -d` permisos 700; limpieza en `trap` |
| Args passthrough | `"$@"` sin eval ni manipulación |
| Env vars | Solo `THORRIJA_BOOTSTRAP=1` + `TMPDIR` respetado |

---

## Auto-update (`--update`) — Futuro (Fase 2+)

```bash
./install.sh --update
# 1. GitHub API: latest release tag
# 2. Compara con versión actual (hardcodeada)
# 3. Si hay nueva: descarga NUEVO install.sh a temp
# 4. Verifica hash del NUEVO script (hash en release notes / asset aparte)
# 5. OK → reemplaza install.sh actual (backup .bak)
# 6. Ejecuta nuevo script con mismos args
```

**Fase 1**: `--update` no implementado; motor Python tendrá su `--update` para catálogo/manifiestos.

---

## Testing (Fase 2)

| Test | Descripción |
|------|-------------|
| `test_bootstrap_python_detection.sh` | Matrix: Python 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, none |
| `test_bootstrap_hash_verification.sh` | Hash correcto / incorrecto / corrupto |
| `test_bootstrap_distro_detection.sh` | /etc/os-release para Arch, Debian, Ubuntu, Fedora, Void, desconocido |
| `test_bootstrap_args_passthrough.sh` | Flags varios pasados al motor intactos |
| `test_bootstrap_root_rejection.sh` | EUID=0 → rechazo claro |
| `test_bootstrap_dev_mode.sh` | Ejecución desde repo clonado (`.git` presente) |

---

## Esqueleto mínimo

```bash
#!/usr/bin/env bash
# install.sh — Thorrija Environment Bootstrap
# Version: 0.1.0-dev
# SHA256 del tarball release: ACTUALIZAR_EN_CI

set -euo pipefail

REPO="ThorrijaDEV/thorrija-environment"
RELEASE_VERSION="latest"
SHA256_EXPECTED="PENDING_RELEASE_HASH"  # CI lo reemplaza

usage() {
  cat <<'EOF'
Thorrija Environment — Bootstrap Installer

Uso: ./install.sh [OPCIONES_BOOTSTRAP] -- [OPCIONES_MOTOR]

Opciones del bootstrap:
  -h, --help           Muestra esta ayuda
  -V, --version        Versión del bootstrap
      --dev            Modo desarrollo (código local, sin descarga)
      --verify-only    Solo verifica hash del tarball (modo release)
      --python PATH    Forzar binario Python
      --no-python-check Saltar verificación versión Python (peligroso)

Todas las demás opciones se pasan al motor Python.
Ejemplos:
  ./install.sh -- --detect
  ./install.sh -- --profile standard --plan
  ./install.sh -- --profile standard --yes
EOF
}

BOOTSTRAP_ARGS=()
ENGINE_ARGS=()
PASSTHROUGH=0
for arg in "$@"; do
  if [[ $PASSTHROUGH -eq 1 ]]; then
    ENGINE_ARGS+=("$arg")
  elif [[ "$arg" == "--" ]]; then
    PASSTHROUGH=1
  elif [[ "$arg" =~ ^(--help|-h|--version|-V|--dev|--verify-only|--python|--no-python-check)$ ]]; then
    BOOTSTRAP_ARGS+=("$arg")
  else
    ENGINE_ARGS+=("$arg")
  fi
done

# ... etapas 0-3 ...

exec python3 -m thorrija "${ENGINE_ARGS[@]}"
```

---

## Decisiones Pendientes

| Tema | Opciones | Notas |
|------|----------|-------|
| Vendoring `tomli` | `_vendor/tomli.py` vs `pip install --target` | Single file = más simple, cero deps |
| Auto-update bootstrap | `--update` en bootstrap vs solo motor | Bootstrap auto-update = UX superior pero más complejo |
| Soporte `uv` / `pipx` | `uv run --python 3.11 -m thorrija`? | Podría simplificar detección Python |
| Windows (WSL2) | Bootstrap `.ps1` paralelo? | Fase 4+ |
| Firmas cosign | Verificar firma del tarball además de hash | Fase 2+ con sigstore |