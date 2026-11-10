# THORRIJA ENVIRONMENT

Universal, adaptive, hardware-agnostic development environment provisioner for Linux.

## Phase Status

| Phase | Description | Status | Date |
|-------|-------------|--------|------|
| 0 | Audit & Research | ✅ Complete | 2026-11-10 |
| 1 | Formal Specification | ✅ Complete | 2026-11-10 |
| 2 | Core Implementation | ⏳ Pending | — |
| 3 | Modular Catalog | ⏳ Pending | — |
| 4 | Offline/SSD Distribution | ⏳ Pending | — |
| 5 | Final Validation | ⏳ Pending | — |

## Overview

Thorrija Environment is a **manifest-driven** provisioning system that:

1. **Detects** OS, hardware, and resources (no assumptions, cascading fallbacks)
2. **Classifies** the machine into a profile (LOW-END / STANDARD / HIGH-END) with configurable thresholds
3. **Selects** tools from a modular catalog via declarative TOML manifests
4. **Generates** a human-reviewable installation plan with resource estimates
5. **Installs** via idempotent drivers (native packages, binary releases, git, scripts, pipx)
6. **Audits** real outcomes (command presence + output pattern, not exit codes)

## Quick Start (Future)

```bash
# From GitHub (Phase 1+ only)
curl -fsSL https://github.com/ThorrijaDEV/thorrija-environment/releases/latest/download/install.sh | bash -s -- --detect
./install.sh --profile standard --plan
./install.sh --profile standard --yes
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — System design, data flow, module boundaries
- [Manifests](docs/MANIFESTS.md) — TOML schema, classification semantics, profiles
- [Security](docs/SECURITY.md) — Threat model, sudo policy, hash pinning, backups
- [Compatibility](docs/COMPATIBILITY.md) — Distro × tool matrix, verified/assumed/unsupported
- [Bootstrap](docs/BOOTSTRAP.md) — install.sh spec, Python fallback strategies

## Catalog Structure

```
catalog/
├── languages/      # Python, Rust, Go, Java, JS/TS, C/C++
├── development/    # Git, GitHub CLI, CMake, Make, Docker, Podman
├── editors/        # Neovim, VS Code, OpenCode, terminals
├── ai/             # Ollama, LiteLLM, PyTorch, NumPy, scikit-learn
├── security/       # Nmap, Wireshark, analysis tools
└── system/         # Fish, Starship, tmux, fonts, dotfiles (chezmoi)
```

## Profiles

| Profile | Target Hardware | Philosophy |
|---------|-----------------|------------|
| `low-end` | 2 cores, 2–4 GB RAM, no GPU, limited disk | CLI-only, minimal services, no local AI |
| `standard` | 4–8 cores, 8–16 GB RAM, optional GPU | Full dev environment, optional containers, CPU AI |
| `high-end` | 16+ GB RAM, modern CPU, optional dedicated GPU | AI frameworks, Ollama, PyTorch/CUDA, local models |

Profiles are **configurable** — thresholds live in `profiles/*.toml`, not hardcoded.

## Distribution

**This phase: GitHub-only.** The installer downloads manifests and the engine from GitHub releases. Offline/SSD mode is designed for (architecture allows it) but not implemented.

## Requirements

- Linux (Arch, Debian, Ubuntu, Fedora, Void — others via generic drivers)
- Bash + Python ≥ 3.9 (bootstrap handles missing Python)
- Internet access for GitHub downloads
- sudo for native package installs (grouped, shown, confirmed)

## License

MIT — see LICENSE (to be added in Phase 2).