# Esquema Formal de Manifiestos TOML

Este documento define **exactamente** la estructura de un archivo de manifiesto en `catalog/<categoría>/<herramienta>.toml`. El validador (`tests/validate_manifests.py`) rechaza cualquier manifiesto que no cumpla este esquema.

## Convenciones

- **Requerido**: el campo debe estar presente y tener valor válido
- **Opcional**: puede omitirse; se aplica el default documentado
- **Tipos**: `string`, `integer`, `boolean`, `array[string]`, `table`, `enum`
- **Enum**: solo los valores listados son válidos
- **Regex**: donde se indique, el valor debe matchear el patrón

---

## Estructura Raíz

```toml
schema_version = 1                    # Requerido, integer, debe ser 1

[tool]                                # Requerido, table
[requirements]                        # Opcional, table (defaults abajo)
[profiles]                            # Requerido, table
[install]                             # Requerido, table (al menos 1 método)
[verify]                              # Requerido, table
[ai_models]                           # Opcional, table (solo herramientas AI)
```

---

## Sección `[tool]`

| Campo | Tipo | Req | Default | Restricción |
|-------|------|-----|---------|-------------|
| `name` | string | ✅ | — | `^[a-z][a-z0-9-]*$` (minúsculas, alfanumérico + guión, sin guión inicial) |
| `category` | enum | ✅ | — | `languages \| development \| editors \| ai \| security \| system` |
| `description` | string | ✅ | — | Longitud 10–500 chars |
| `homepage` | string | ❌ | `""` | URL válida (http/https) |
| `tags` | array[string] | ❌ | `[]` | Palabras clave para filtrado |

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

Define los recursos necesarios para **instalar** y **ejecutar** la herramienta.

| Campo | Tipo | Req | Default | Restricción / Semántica |
|-------|------|-----|---------|------------------------|
| `ram_run_mb` | integer | ❌ | `100` | RAM **mínima para ejecutar útilmente** (no solo instalar). En MB. |
| `ram_optimal_mb` | integer | ❌ | `ram_run_mb * 2` | RAM para **rendimiento óptimo**. Si se omite, se calcula. |
| `disk_install_mb` | integer | ❌ | `50` | Espacio en disco **para instalar** (descarga + extracción + instalados). En MB. |
| `disk_run_mb` | integer | ❌ | `disk_install_mb` | Espacio adicional en runtime (caché, datos, modelos). En MB. |
| `gpu` | enum | ❌ | `"none"` | `"none" \| "optional" \| "required"` — afecta clasificación óptimo |
| `cpu_cores_min` | integer | ❌ | `1` | Hilos de CPU mínimos para uso razonable |
| `cpu_arch` | array[string] | ❌ | `["x86_64", "aarch64"]` | Arquitecturas soportadas |
| `privileged` | boolean | ❌ | `true` | `true` = instalación nativa requiere sudo/root |
| `size_class` | enum | ❌ | `"auto"` | `"tiny" (<50MB) \| "small" (<200MB) \| "medium" (<1GB) \| "large" (>=1GB) \| "auto"` — calculado de `disk_install_mb` si "auto" |
| `network_required` | boolean | ❌ | `true` | `false` = instalable 100% offline (solo native con paquetes locales) |
| `python_min` | string | ❌ | `""` | Versión mínima Python si la herramienta la necesita (ej. "3.9") |

**Regla de clasificación (usada por el planificador):**
- **Compatible**: método viable + `disk_install_mb` libre
- **Recomendado**: Compatible + RAM libre ≥ `ram_run_mb`
- **Óptimo**: Recomendado + (RAM libre ≥ `ram_optimal_mb` si definido) + (`gpu != "required"` O GPU compatible detectada)

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

Controla **qué perfiles incluyen esta herramienta por defecto**. Tres claves **requeridas**.

| Clave | Tipo | Valores Válidos | Significado |
|-------|------|-----------------|-------------|
| `low_end` | enum | `enabled \| optional \| excluded` | `enabled` = en plan por defecto; `optional` = solo si usuario pide `--category`; `excluded` = nunca salvo `--force` |
| `standard` | enum | `enabled \| optional \| excluded` | Idem |
| `high_end` | enum | `enabled \| optional \| excluded` | Idem |

**Ejemplo:**
```toml
[profiles]
low_end = "excluded"
standard = "optional"
high_end = "enabled"
```

---

## Sección `[install]`

**Al menos uno** de los siguientes subtablas debe estar presente. Cada una define un **método de instalación**. El planificador los evalúa en orden de preferencia: `native` → `binary_release` → `git_clone` → `script_official` → `pipx` (el primero viable gana).

### 1. `[install.native]` — Paquetes del gestor del SO

Claves por **familia de gestor** (no por distro individual). Valor = nombre del paquete **o** `null` si no existe en esa familia.

| Clave | Familia | Distros Cubiertas |
|-------|---------|-------------------|
| `arch` | pacman | Arch, Manjaro, EndeavourOS, Garuda... |
| `debian` | apt | Debian, Ubuntu, Linux Mint, Pop!_OS, Kali... |
| `fedora` | dnf | Fedora, RHEL, CentOS Stream, AlmaLinux, Rocky... |
| `void` | xbps | Void Linux |
| `opensuse` | zypper | openSUSE (Tumbleweed/Leap) |
| `alpine` | apk | Alpine Linux |
| `gentoo` | emerge | Gentoo |

**Regla crítica**: Un valor no-`null` en `debian` **solo es válido** si el paquete existe con ese nombre exacto en **Debian stable Y Ubuntu LTS actual**. El validador marca como `assumed` cualquier entrada no verificada (ver COMPATIBILITY.md). Usa `null` si el nombre difiere o no existe.

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

### 2. `[install.binary_release]` — Binario de GitHub Releases (u otro)

| Campo | Tipo | Req | Descripción |
|-------|------|-----|-------------|
| `url_template` | string | ✅ | Plantilla con `{version}` y `{arch}`. Ej: `https://github.com/owner/repo/releases/download/v{version}/tool-{version}-{arch}.tar.gz` |
| `version` | string | ✅ | Versión a instalar (semver sin prefijo `v`) |
| `sha256` | table | ✅ | Mapa `arch -> hash hex 64 chars`. **Obligatorio**. Sin hash → método deshabilitado. |
| `archive_type` | enum | ❌ | `"tar.gz" \| "tgz" \| "zip" \| "binary"` — default `"tar.gz"` |
| `binary_name` | string | ❌ | Nombre del ejecutable dentro del archivo (si difiere de `tool.name`) |
| `install_to` | string | ❌ | Directorio destino — default `"~/.local/bin"` |
| `strip_components` | integer | ❌ | Niveles de directorio a quitar al extraer — default `1` |

**Arquitecturas soportadas en `sha256`**: `x86_64`, `aarch64`, `armv7`, `riscv64` (las que provea el upstream).

```toml
[install.binary_release]
url_template = "https://github.com/ollama/ollama/releases/download/v{version}/ollama-linux-{arch}.tgz"
version = "0.3.12"
sha256 = { x86_64 = "PENDING-VERIFICATION", aarch64 = "PENDING-VERIFICATION" }
archive_type = "tgz"
binary_name = "ollama"
install_to = "~/.local/bin"
```

> ⚠️ **Nota**: En manifiestos de ejemplo (FASE 1) los hashes son `PENDING-VERIFICATION`. El validador lo detecta y marca el método como **deshabilitado**. En FASE 3 se pinnearán hashes reales tras verificación.

### 3. `[install.git_clone]` — Clone + Build

| Campo | Tipo | Req | Descripción |
|-------|------|-----|-------------|
| `url` | string | ✅ | URL del repo Git (https:// o git@) |
| `branch` | string | ❌ | Rama/tag/commit — default `"main"` |
| `build_system` | enum | ✅ | `"make" \| "cargo" \| "go" \| "cmake" \| "meson" \| "custom"` |
| `build_args` | array[string] | ❌ | Argumentos extra al build — default `[]` |
| `binary_path` | string | ✅ | Ruta relativa al ejecutable tras build |
| `install_to` | string | ❌ | Directorio destino — default `"~/.local/bin"` |

```toml
[install.git_clone]
url = "https://github.com/neovim/neovim.git"
branch = "stable"
build_system = "make"
build_args = ["CMAKE_BUILD_TYPE=RelWithDebInfo"]
binary_path = "build/bin/nvim"
install_to = "~/.local/bin"
```

### 4. `[install.script_official]` — Script Instalador Oficial

**Requiere hash pinneado del script** (descargado y verificado antes de ejecutar).

| Campo | Tipo | Req | Descripción |
|-------|------|-----|-------------|
| `url` | string | ✅ | URL del script (raw GitHub, sitio oficial) |
| `sha256` | string | ✅ | Hash SHA-256 del script **exacto** a ejecutar |
| `args` | array[string] | ❌ | Argumentos al script — default `[]` |
| `env` | table | ❌ | Variables de entorno — default `{}` |

```toml
[install.script_official]
url = "https://install.ghcli.org/install.sh"
sha256 = "PENDING-VERIFICATION"
args = ["-y"]
```

> Sin `sha256` → método **deshabilitado** (inseguro).

### 5. `[install.pipx]` — Paquete Python via pipx

| Campo | Tipo | Req | Descripción |
|-------|------|-----|-------------|
| `package` | string | ✅ | Nombre en PyPI (puede incluir `[extras]`) |
| `version` | string | ❌ | Versión fija — default `latest` |
| `python` | string | ❌ | Versión Python requerida — default `""` (usa default del sistema) |

```toml
[install.pipx]
package = "ansible"
version = "9.0.0"
python = "3.9"
```

---

## Sección `[verify]`

**Requerida**. Define cómo el motor verifica que la herramienta **realmente funciona** tras la instalación.

| Campo | Tipo | Req | Descripción |
|-------|------|-----|-------------|
| `command` | string | ✅ | Comando a ejecutar (ej. `"git --version"`) |
| `pattern` | string | ✅ | Regex que debe matchear en stdout/stderr combinado (ej. `"git version"`) |
| `exit_code` | integer | ❌ | Código de salida esperado — default `0` |
| `timeout_sec` | integer | ❌ | Timeout — default `10` |
| `version_extract` | string | ❌ | Regex con grupo capturador para extraer versión (ej. `"git version (\\S+)"`) |

**Importante**: La verificación se ejecuta **después** de la instalación y **antes** de marcar la herramienta como `installed`. Si falla, el estado pasa a `failed` y el plan se detiene (salvo `--continue-on-error`).

```toml
[verify]
command = "git --version"
pattern = "git version"
version_extract = "git version (\\S+)"
```

---

## Sección `[ai_models]` (Solo Categoría `ai`)

Controla descarga de modelos para herramientas de IA (Ollama, LiteLLM, etc.).

| Campo | Tipo | Req | Default | Descripción |
|-------|------|-----|---------|-------------|
| `automatic` | boolean | ❌ | `false` | `true` = descargar modelos por defecto — **NUNCA** `true` por defecto en este proyecto |
| `default_models` | array[string] | ❌ | `[]` | Lista de modelos sugeridos (solo documentación, no se instalan solos) |
| `requires_confirmation` | boolean | ❌ | `true` | Cada pull de modelo pide confirmación explícita |

```toml
[ai_models]
automatic = false
default_models = ["llama3.2:3b", "nomic-embed-text"]
requires_confirmation = true
```

---

## Esquema de Perfiles (`profiles/*.toml`)

Archivos en `profiles/` definen los **umbrales de clasificación** y selección por defecto.

```toml
# profiles/standard.toml (ejemplo)
name = "standard"
description = "Equipo de uso general: 4-8 cores, 8-16 GB RAM, GPU opcional"

[thresholds]
# Umbrales para AUTO-clasificación (si usuario no pasa --profile)
ram_low_end_max_mb = 6144        # ≤ 6 GB → low_end
ram_high_end_min_mb = 16384      # ≥ 16 GB → high_end
cpu_cores_low_end_max = 3        # ≤ 3 cores → low_end
cpu_cores_high_end_min = 8       # ≥ 8 cores → high_end
gpu_dedicated_vram_min_mb = 4096 # GPU dedicada ≥ 4 GB → high_end (si RAM también califica)

[selection]
# Qué herramientas incluir por defecto según su [profiles] en el manifiesto
include_enabled = true
include_optional = false
include_excluded = false
```

El motor de clasificación (`classify.py`) usa estos umbrales para proponer un perfil si el usuario no especifica `--profile`. El usuario siempre puede forzar otro.

---

## Validación (Reglas del Validador)

El script `tests/validate_manifests.py` aplica estas reglas **inquebrantables**:

1. **schema_version == 1** (integer)
2. `[tool].name` matchea `^[a-z][a-z0-9-]*$`
3. `[tool].category` ∈ enum válido
4. `[profiles]` tiene exactamente las 3 claves `low_end`, `standard`, `high_end` con valores ∈ `{enabled,optional,excluded}`
5. `[install]` tiene ≥ 1 subtabla de método
6. `[verify]` tiene `command` y `pattern` (strings no vacíos)
7. Si `[install.binary_release]` existe → `sha256` table presente con ≥ 1 entrada (si no → warning: método deshabilitado)
8. Si `[install.script_official]` existe → `sha256` string presente (si no → warning: método deshabilitado)
9. `[install.native]`: cualquier valor no-null en `debian`/`ubuntu` → marcado `assumed` en reporte (no error, pero visible)
10. `ram_run_mb` > 0, `disk_install_mb` > 0
11. Archivo parseable por `tomllib` / `tomli` sin errores
12. Bloques TOML en `MANIFESTS.md` (cercados ```toml) también parseables

---

## Ejemplos de Referencia (en este repo)

| Archivo | Categoría | Notas |
|---------|-----------|-------|
| `catalog/development/git.toml` | development | Native en todas las familias, `enabled` en todos los perfiles |
| `catalog/languages/python.toml` | languages | Native + detección preexistente, `enabled` en todos |
| `catalog/ai/ollama.toml` | ai | Binary release (hash pending), `excluded` en low_end, `optional` en standard, `enabled` en high_end |

Estos tres manifiestos **cumplen el esquema al 100%** y son validados por `tests/validate_manifests.py`.