# Esquema de manifiestos TOML

Este documento define la estructura exacta de un manifiesto en `catalog/<categoría>/<herramienta>.toml`. El validador (`tests/validate_manifests.py`) rechaza cualquier manifiesto que no cumpla.

## Convenciones

- **Requerido**: el campo debe estar presente y tener valor válido
- **Opcional**: puede omitirse; se aplica el default documentado
- **Tipos**: `string`, `integer`, `boolean`, `array[string]`, `table`, `enum`
- **Enum**: solo los valores listados son válidos
- **Regex**: donde se indique, el valor debe matchear el patrón

---

## Estructura raíz

```toml
schema_version = 1

[tool]
[requirements]
[profiles]
[install]
[verify]
[ai_models]          # solo categoría ai
```

---

## Sección `[tool]`

| Campo | Tipo | Req | Default | Restricción |
|-------|------|-----|---------|-------------|
| `name` | string | sí | — | `^[a-z][a-z0-9-]*$` |
| `category` | enum | sí | — | `languages \| development \| editors \| ai \| security \| system` |
| `description` | string | sí | — | 10–500 chars |
| `homepage` | string | no | `""` | URL válida |
| `tags` | array[string] | no | `[]` | Palabras clave para filtrado |

**Ejemplo:**

```toml
[tool]
name = "git"
category = "development"
description = "Distributed version control system"
homepage = "https://git-scm.com/"
tags = ["vcs", "cli", "essential"]
```

---

## Sección `[requirements]`

Recursos necesarios para **instalar** y **ejecutar**.

| Campo | Tipo | Req | Default | Significado |
|-------|------|-----|---------|-------------|
| `ram_run_mb` | integer | no | `100` | RAM mínima para **ejecutar útilmente** (MB) |
| `ram_optimal_mb` | integer | no | `ram_run_mb * 2` | RAM para rendimiento óptimo (MB) |
| `disk_install_mb` | integer | no | `50` | Espacio para instalar (MB) |
| `disk_run_mb` | integer | no | `disk_install_mb` | Espacio adicional en runtime (MB) |
| `gpu` | enum | no | `"none"` | `"none" \| "optional" \| "required"` |
| `cpu_cores_min` | integer | no | `1` | Hilos CPU mínimos |
| `cpu_arch` | array[string] | no | `["x86_64", "aarch64"]` | Arquitecturas soportadas |
| `privileged` | boolean | no | `true` | Instalación nativa requiere sudo |
| `size_class` | enum | no | `"auto"` | `"tiny" (<50MB) \| "small" (<200MB) \| "medium" (<1GB) \| "large" (>=1GB) \| "auto"` |
| `network_required` | boolean | no | `true` | `false` = instalable 100% offline |
| `python_min` | string | no | `""` | Versión mínima Python si aplica |

**Regla de clasificación (usada por el planificador):**

- **Compatible**: método viable + `disk_install_mb` libre
- **Recomendado**: Compatible + RAM libre ≥ `ram_run_mb`
- **Óptimo**: Recomendado + (RAM libre ≥ `ram_optimal_mb` si definido) + (`gpu != "required"` O GPU compatible)

**Ejemplo:**

```toml
[requirements]
ram_run_mb = 8192
ram_optimal_mb = 24576
disk_install_mb = 5000
disk_run_mb = 10000
gpu = "optional"
cpu_cores_min = 4
privileged = false
size_class = "large"
network_required = true
```

---

## Sección `[profiles]`

Controla qué perfiles incluyen la herramienta por defecto. Tres claves **requeridas**.

| Clave | Valores | Significado |
|-------|---------|-------------|
| `low_end` | `enabled \| optional \| excluded` | `enabled` = en plan por defecto; `optional` = solo con `--category`; `excluded` = nunca salvo `--force` |
| `standard` | `enabled \| optional \| excluded` | Idem |
| `high_end` | `enabled \| optional \| excluded` | Idem |

**Ejemplo:**

```toml
[profiles]
low_end = "excluded"
standard = "optional"
high_end = "enabled"
```

---

## Sección `[install]`

Al menos **un** método. El planificador los evalúa en orden: `native` → `binary_release` → `git_clone` → `script_official` → `pipx` (el primero viable gana).

### 1. `[install.native]` — Paquetes del gestor del SO

Claves por **familia de gestor**. Valor = nombre del paquete u omitido si no existe.

| Clave | Familia | Distros |
|-------|---------|---------|
| `arch` | pacman | Arch, Manjaro, EndeavourOS... |
| `debian` | apt | Debian, Ubuntu, Mint, Pop, Kali... |
| `fedora` | dnf | Fedora, RHEL, CentOS, Alma, Rocky... |
| `void` | xbps | Void Linux |
| `opensuse` | zypper | openSUSE Tumbleweed/Leap |
| `alpine` | apk | Alpine Linux |
| `gentoo` | emerge | Gentoo |

**Regla**: un valor en `debian` solo es válido si el paquete existe con ese nombre en **Debian stable Y Ubuntu LTS actual**. El validador marca como `assumed` lo no verificado. Omite la clave si no existe.

```toml
[install.native]
arch = "git"
debian = "git"
fedora = "git"
void = "git"
opensuse = "git"
alpine = "git"
gentoo = "dev-vcs/git"
```

---

### 2. `[install.binary_release]` — Binario de GitHub Releases

| Campo | Req | Descripción |
|-------|-----|-------------|
| `url_template` | sí | Plantilla con `{version}` y `{arch}` |
| `version` | sí | Versión a instalar (semver sin `v`) |
| `sha256` | sí | Mapa `arch -> hash hex 64 chars`. **Obligatorio**. Sin hash → deshabilitado |
| `archive_type` | no | `"tar.gz" \| "tgz" \| "zip" \| "binary"` — default `"tar.gz"` |
| `binary_name` | no | Ejecutable dentro del archivo (si difiere de `tool.name`) |
| `install_to` | no | Directorio destino — default `"~/.local/bin"` |
| `strip_components` | no | Niveles a quitar al extraer — default `1` |

**Arquitecturas en `sha256`**: `x86_64`, `aarch64`, `armv7`, `riscv64` (las que provea upstream).

```toml
[install.binary_release]
url_template = "https://github.com/ollama/ollama/releases/download/v{version}/ollama-linux-{arch}.tgz"
version = "0.3.12"
sha256 = { x86_64 = "PENDING-VERIFICATION", aarch64 = "PENDING-VERIFICATION" }
archive_type = "tgz"
binary_name = "ollama"
install_to = "~/.local/bin"
```

> **Nota**: En manifiestos de ejemplo los hashes son `PENDING-VERIFICATION`. El validador marca el método como deshabilitado. En Fase 3 se pinnearán hashes reales.

---

### 3. `[install.git_clone]` — Clone + Build

| Campo | Req | Descripción |
|-------|-----|-------------|
| `url` | sí | URL del repo Git |
| `branch` | no | Rama/tag/commit — default `"main"` |
| `build_system` | sí | `"make" \| "cargo" \| "go" \| "cmake" \| "meson" \| "custom"` |
| `build_args` | no | Args extra — default `[]` |
| `binary_path` | sí | Ruta relativa al ejecutable tras build |
| `install_to` | no | Directorio destino — default `"~/.local/bin"` |

```toml
[install.git_clone]
url = "https://github.com/neovim/neovim.git"
branch = "stable"
build_system = "make"
build_args = ["CMAKE_BUILD_TYPE=RelWithDebInfo"]
binary_path = "build/bin/nvim"
install_to = "~/.local/bin"
```

---

### 4. `[install.script_official]` — Script instalador oficial

**Requiere hash pinneado** del script (descargado y verificado antes de ejecutar).

| Campo | Req | Descripción |
|-------|-----|-------------|
| `url` | sí | URL del script |
| `sha256` | sí | Hash SHA-256 del script exacto |
| `args` | no | Argumentos — default `[]` |
| `env` | no | Variables de entorno — default `{}` |

```toml
[install.script_official]
url = "https://install.ghcli.org/install.sh"
sha256 = "PENDING-VERIFICATION"
args = ["-y"]
```

> Sin `sha256` → método deshabilitado (inseguro).

---

### 5. `[install.pipx]` — Paquete Python via pipx

| Campo | Req | Descripción |
|-------|-----|-------------|
| `package` | sí | Nombre en PyPI (con `[extras]` opcional) |
| `version` | no | Versión fija — default `latest` |
| `python` | no | Versión Python — default `""` (sistema) |

```toml
[install.pipx]
package = "ansible"
version = "9.0.0"
python = "3.9"
```

---

## Sección `[verify]`

**Requerida**. Cómo verifica que la herramienta **realmente funciona**.

| Campo | Req | Descripción |
|-------|-----|-------------|
| `command` | sí | Comando a ejecutar (`"git --version"`) |
| `pattern` | sí | Regex en stdout/stderr combinado (`"git version"`) |
| `exit_code` | no | Código esperado — default `0` |
| `timeout_sec` | no | Timeout — default `10` |
| `version_extract` | no | Regex con grupo para extraer versión (`"git version (\S+)"`) |

La verificación se ejecuta **después** de instalar y **antes** de marcar `installed`. Si falla, estado → `failed` y el plan se detiene (salvo `--continue-on-error`).

```toml
[verify]
command = "git --version"
pattern = "git version"
version_extract = "git version (\\S+)"
```

---

## Sección `[ai_models]` (solo categoría `ai`)

| Campo | Req | Default | Descripción |
|-------|-----|---------|-------------|
| `automatic` | no | `false` | **Nunca** `true` por defecto |
| `default_models` | no | `[]` | Modelos sugeridos (solo docs) |
| `requires_confirmation` | no | `true` | Cada pull pide confirmación |

```toml
[ai_models]
automatic = false
default_models = ["llama3.2:3b", "nomic-embed-text"]
requires_confirmation = true
```

---

## Esquema de perfiles (`profiles/*.toml`)

```toml
name = "standard"
description = "Equipo de uso general: 4-8 cores, 8-16 GB RAM, GPU opcional"

[thresholds]
ram_low_end_max_mb = 6144
ram_high_end_min_mb = 16384
cpu_cores_low_end_max = 3
cpu_cores_high_end_min = 8
gpu_dedicated_vram_min_mb = 4096

[selection]
include_enabled = true
include_optional = false
include_excluded = false
```

El motor (`classify.py`) usa estos umbrales para proponer un perfil si no pasas `--profile`. Siempre puedes forzar otro.

---

## Validación (reglas inquebrantables)

El script `tests/validate_manifests.py` aplica:

1. `schema_version == 1` (integer)
2. `[tool].name` matchea `^[a-z][a-z0-9-]*$`
3. `[tool].category` ∈ enum válido
4. `[profiles]` tiene exactamente `low_end`, `standard`, `high_end` con valores ∈ `{enabled,optional,excluded}`
5. `[install]` tiene ≥ 1 subtabla de método
6. `[verify]` tiene `command` y `pattern` (strings no vacíos)
7. `[install.binary_release]` → `sha256` table con ≥ 1 entrada (si no → warning: deshabilitado)
8. `[install.script_official]` → `sha256` string (si no → warning: deshabilitado)
9. `[install.native]`: valor no-null en `debian`/`ubuntu` → marcado `assumed` en reporte
10. `ram_run_mb` > 0, `disk_install_mb` > 0
11. Parseable por `tomllib` / `tomli` sin errores
12. Bloques TOML en `MANIFESTS.md` (```toml) también parseables

---

## Ejemplos de referencia

| Archivo | Categoría | Notas |
|---------|-----------|-------|
| `catalog/development/git.toml` | development | Native en todas las familias, `enabled` en todos los perfiles |
| `catalog/languages/python.toml` | languages | Native + detección preexistente, `enabled` en todos |
| `catalog/ai/ollama.toml` | ai | Binary release (hash pending), `excluded` en low_end, `optional` en standard, `enabled` en high_end |

Estos tres manifiestos cumplen el esquema al 100% y son validados por `tests/validate_manifests.py`.