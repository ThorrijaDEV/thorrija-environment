# Thorrija Environment

Universal, adaptive, hardware-agnostic development environment provisioner for Linux.

## Estado del proyecto

| Fase | Descripción | Estado |
|------|-------------|--------|
| 0 | Auditoría e investigación | Completada |
| 1 | Especificación formal | Completada |
| 2 | Implementación del núcleo | Completada |
| 3 | Catálogo modular | Completada |
| 4 | Distribución offline/SSD | Pendiente |
| 5 | Validación final | Pendiente |

Última actualización: 2026-11-10

## Qué hace

Thorrija Environment es un provisionador **basado en manifiestos** que:

1. **Detecta** el sistema operativo, hardware y recursos (sin asumir, con fallbacks en cascada)
2. **Clasifica** la máquina en un perfil (LOW-END / STANDARD / HIGH-END) con umbrales configurables
3. **Selecciona** herramientas de un catálogo modular mediante manifiestos TOML declarativos
4. **Genera** un plan de instalación revisable por el usuario, con estimación de recursos
5. **Instala** mediante drivers idempotentes (paquetes nativos, binarios, git, scripts, pipx)
6. **Audita** resultados reales (comando presente + patrón de salida, no solo código de salida)

## Inicio rápido (cuando esté listo)

```bash
# Desde GitHub
curl -fsSL https://github.com/ThorrijaDEV/thorrija-environment/releases/latest/download/install.sh | bash -s -- --detect
./install.sh --profile standard --plan
./install.sh --profile standard --yes
```

## Documentación

- [Arquitectura](docs/ARCHITECTURE.md) — Diseño del sistema, flujo de datos, límites de módulos
- [Manifiestos](docs/MANIFESTS.md) — Esquema TOML, semántica de clasificación, perfiles
- [Seguridad](docs/SECURITY.md) — Modelo de amenazas, política sudo, hash pinning, backups
- [Compatibilidad](docs/COMPATIBILITY.md) — Matriz distro × herramienta, verified/assumed/unsupported
- [Bootstrap](docs/BOOTSTRAP.md) — Especificación de install.sh, estrategias de fallback Python

## Estructura del catálogo

```
catalog/
├── languages/      # Python, Rust, Go, Java, JS/TS, C/C++
├── development/    # Git, GitHub CLI, CMake, Make, Docker, Podman
├── editors/        # Neovim, VS Code, OpenCode, terminales
├── ai/             # Ollama, LiteLLM, PyTorch, NumPy, scikit-learn
├── security/       # Nmap, Wireshark, herramientas de análisis
└── system/         # Fish, Starship, tmux, fuentes, dotfiles (chezmoi)
```

## Perfiles

| Perfil | Hardware objetivo | Filosofía |
|--------|-------------------|-----------|
| `low-end` | 2 cores, 2–4 GB RAM, sin GPU, disco limitado | Solo CLI, servicios mínimos, sin IA local |
| `standard` | 4–8 cores, 8–16 GB RAM, GPU opcional | Entorno de desarrollo completo, contenedores opcionales, IA en CPU |
| `high-end` | 16+ GB RAM, CPU moderna, GPU dedicada opcional | Frameworks de IA, Ollama, PyTorch/CUDA, modelos locales |

Los perfiles son **configurables** — los umbrales viven en `profiles/*.toml`, no en código.

## Distribución

**Esta fase: solo GitHub.** El instalador descarga manifiestos y motor desde GitHub releases. El modo offline/SSD está diseñado (la arquitectura lo permite) pero no implementado.

## Requisitos

- Linux (Arch, Debian, Ubuntu, Fedora, Void — otros vía drivers genéricos)
- Bash + Python ≥ 3.9 (el bootstrap gestiona Python ausente)
- Acceso a Internet para descargas de GitHub
- sudo para instalaciones nativas (agrupadas, mostradas, confirmadas)

## Licencia

MIT — ver LICENSE (pendiente).