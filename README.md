# THORRIJA ENVIRONMENT

Universal, adaptive development environment provisioner for Linux, Windows 11, and macOS (via WSL2).

## Instalación Universal

### Linux / macOS (WSL2) / Windows 11 (PowerShell)

```bash
# Linux / macOS / WSL2
curl -fsSL https://github.com/ThorrijaDEV/thorrija-environment/releases/latest/download/install.sh | bash -s -- --profile standard --yes

# Windows 11 (PowerShell como Administrador)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
irm https://github.com/ThorrijaDEV/thorrija-environment/releases/latest/download/install.ps1 | iex -- --profile standard --yes
```

### Opciones de perfil

| Perfil | Hardware objetivo | Qué instala |
|--------|-------------------|-------------|
| `--profile minimal` | Cualquier hardware | Solo esenciales: git, python, editor CLI, shell |
| `--profile low-end` | 2-4 GB RAM, 2 cores, sin GPU | CLI tools, Python, git, neovim, fish, tools ligeros |
| `--profile standard` | 8-16 GB RAM, 4-8 cores, GPU opcional | Entorno completo desarrollo + contenedores opcionales + IA en CPU |
| `--profile high-end` | 16+ GB RAM, 8+ cores, GPU dedicada | Todo + IA local (Ollama, PyTorch CUDA), modelos locales |

### Opciones útiles

```bash
# Ver qué se instalaría (dry-run)
./install.sh --profile standard --plan

# Solo categoría específica
./install.sh --category ai --yes
./install.sh --category system --yes
./install.sh --category development --yes

# Forzar perfil específico (ignora auto-detección)
./install.sh --profile high-end --yes

# Incluir herramientas opcionales del perfil
./install.sh --profile standard --include-optional --yes

# Solo detectar hardware y perfil sugerido
./install.sh --detect
```

---

## Qué se instala por categoría

### `system` — Sistema base y shell
| Herramienta | Descripción |
|-------------|-------------|
| **fish** | Shell amigable e interactiva |
| **starship** | Prompt rápido y personalizable |
| **tmux** | Multiplexor de terminal |
| **zoxide** | `cd` inteligente que aprende |
| **fzf** | Buscador difuso interactivo |
| **ripgrep (rg)** | Búsqueda rápida tipo grep |
| **fd** | Alternativa rápida a `find` |
| **bat** | `cat` con syntax highlighting |
| **eza** | `ls` moderno con colores y git |
| **btop / htop** | Monitores de recursos |
| **lazygit** | UI de terminal para git |

### `development` — Herramientas de desarrollo
| Herramienta | Descripción |
|-------------|-------------|
| **git** | Control de versiones |
| **gh** | GitHub CLI |
| **cmake / meson / ninja** | Build systems |
| **make / pkgconf** | Build automation |
| **docker / podman** | Contenedores (opcional en standard) |
| **direnv** | Variables de entorno por proyecto |

### `editors` — Editores de código
| Editor | Perfil |
|--------|--------|
| **neovim** | low-end, standard, high-end |
| **helix** | standard, high-end |
| **micro** | low-end, standard, high-end |
| **vscode** | high-end (opcional en standard) |
| **code-server** | high-end (opcional en standard) |

### `languages` — Lenguajes de programación
| Lenguaje | Perfil | Método |
|----------|--------|--------|
| **Python 3.11+** | Todos | Native |
| **Rust (rustup)** | standard, high-end | binary_release |
| **Go** | standard, high-end | Native |
| **Node.js (LTS)** | standard, high-end | Native |
| **Java (OpenJDK 21)** | high-end | Native |
| **Zig** | standard, high-end | Native |
| **Bun** | standard, high-end | binary_release |
| **Deno** | standard, high-end | binary_release |

### `ai` — Inteligencia Artificial / ML
| Herramienta | Perfil | Descripción |
|-------------|--------|-------------|
| **Ollama** | high-end (opt standard) | LLM locales (Llama, Qwen, etc.) |
| **LiteLLM** | standard, high-end | Proxy unificado 100+ LLMs |
| **llama.cpp** | high-end | Inferencia C++ GGUF |
| **whisper.cpp** | high-end | Speech-to-text local |
| **PyTorch** | high-end | Deep learning framework |
| **NumPy / pandas / scikit-learn** | standard, high-end | Cientific computing |

### `security` — Seguridad y auditoría
| Herramienta | Descripción |
|-------------|-------------|
| **nmap** | Escáner de puertos/red |
| **tshark (Wireshark CLI)** | Análisis de paquetes |
| **tcpdump** | Captura de tráfico |
| **openssl / gpg / age** | Criptografía y encriptación |
| **ssh-audit** | Auditoría SSH |
| **lynis** | Auditoría de sistema |

---

## Detección automática

El instalador detecta automáticamente:

| Recurso | Detección |
|---------|-----------|
| **OS** | Linux (Arch, Debian, Ubuntu, Fedora, Void), Windows 11, macOS (WSL2) |
| **CPU** | Modelo, cores físicos/lógicos, vendor, flags |
| **RAM** | Total, disponible, swap |
| **GPU** | Vendor (NVIDIA/AMD/Intel), VRAM, driver, dedicada vs integrada |
| **Disco** | Tamaño, libre, SSD vs HDD |
| **Perfil sugerido** | Basado en RAM, cores, GPU dedicada |

---

## Requisitos

| Plataforma | Requisitos |
|------------|------------|
| **Linux** | Arch, Debian 11+, Ubuntu 20.04+, Fedora 38+, Void — Bash + Python 3.9+ |
| **Windows 11** | PowerShell 5.1+, winget/chocolatey/scoop (auto-instala Python) |
| **macOS** | Solo via WSL2 (Linux nativo) |
| **Común** | Internet para descargas, sudo/admin para paquetes nativos |

---

## Seguridad

- **Hash SHA-256 pinneado** en todos los binarios descargados
- **Sin `curl \| bash`** sin verificación de integridad
- **Sudo/UAC agrupado** y confirmado antes de ejecutar
- **Backups automáticos** antes de modificar dotfiles (`~/.thorrija-backup/`)
- **Log de auditoría** inmutable JSON-lines (`~/.local/share/thorrija/log/`)
- **Modelos IA nunca automáticos** — cada `ollama pull` requiere confirmación

---

## Desinstalación / Auditoría

```bash
# Ver auditoría última ejecución
thorrija --audit

# Ver auditoría en JSON
thorrija --audit --json

# Ver backups disponibles
ls ~/.thorrija-backup/

# Restaurar backup manual
rsync -av ~/.thorrija-backup/20261110-143022/home/ ~/
```

---

## Licencia

MIT — [LICENSE](LICENSE)

---

**Repositorio**: https://github.com/ThorrijaDEV/thorrija-environment  
**Issues**: https://github.com/ThorrijaDEV/thorrija-environment/issues