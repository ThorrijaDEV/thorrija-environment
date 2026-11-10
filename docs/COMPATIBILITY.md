# Matriz de Compatibilidad

## Política de Estados

Cada combinación **Distro × Herramienta × Método** tiene uno de tres estados:

| Estado | Significado | Criterio |
|--------|-------------|----------|
| **verified** | Probado **realmente** en la distro indicada, instalación + verificación exitosa | Ejecución documentada en CI/test real, log disponible |
| **assumed** | Razonablemente compatible (paquete existe con mismo nombre, binario multi-arch disponible), **PERO no probado aún** | Conocimiento estándar + manifiesto declara compatibilidad; válido para planificar, requiere confirmación usuario |
| **unsupported** | Incompatible conocido, sin método viable, o roto | Documentado con razón |

**Regla de oro**: Nada se marca `verified` sin ejecución real. `assumed` es el default honesto para "debería funcionar".

---

## Matriz Distro × Soporte General (Nivel SO)

| Distro | Versión Mínima | Gestor | Estado Base | Notas |
|--------|----------------|--------|-------------|-------|
| **Arch Linux** | Rolling (actual) | pacman | **verified** | Distro de desarrollo del autor; todo testeado aquí primero |
| **Debian** | 11 (bullseye) | apt | assumed | Testing en VM planeado FASE 3 |
| **Ubuntu** | 20.04 LTS | apt | assumed | Paquetes a menudo más nuevos que Debian; mismo nombre suele funcionar |
| **Fedora** | 38 | dnf | assumed | Nombres de paquetes a veces difieren (ej. `python3` vs `python3.11`) |
| **Void Linux** | Rolling (actual) | xbps | assumed | Nombres pueden diferir significativamente (ej. `python3.11` en vez de `python3`) |
| openSUSE Tumbleweed | Rolling | zypper | unsupported | No planeado en FASE 1-3; PRs bienvenidos |
| Alpine Linux | 3.18+ | apk | unsupported | Musl libc rompe binarios glibc; solo native/git_clone |
| Gentoo | Rolling | emerge | unsupported | Source-based; solo git_clone/native con USE flags |
| NixOS | 23.11+ | nix | unsupported | Paradigma distinto; fuera de alcance (chezmoi + home-manager recomendado) |

> **Nota**: "assumed" significa que el **manifiesto puede declarar** `debian = "paquete"` y el planificador lo considerará compatible, pero el plan **mostrará** `(assumed)` junto a esa herramienta. El usuario decide.

---

## Matriz Herramienta × Distro (Ejemplos Representativos)

Esta tabla se expandirá en FASE 3 con cada categoría. Hoy solo muestra los **tres manifiestos de ejemplo** de FASE 1.

### `catalog/development/git.toml`

| Distro | Método | Paquete/Release | Estado | Verificado |
|--------|--------|-----------------|--------|------------|
| Arch | native | `git` | verified | ✅ (host actual) |
| Debian 11/12 | native | `git` | assumed | Nombre idéntico en repos oficiales |
| Ubuntu 20.04/22.04/24.04 | native | `git` | assumed | Idem |
| Fedora 38+ | native | `git` | assumed | Idem |
| Void | native | `git` | assumed | `xbps-query -Rs git` confirma |

### `catalog/languages/python.toml`

| Distro | Método | Paquete | Estado | Notas |
|--------|--------|---------|--------|-------|
| Arch | native | `python` | verified | ✅ (host actual: Python 3.13) |
| Debian 11 | native | `python3` | assumed | Paquete `python3` = 3.9 en bullseye |
| Debian 12 | native | `python3` | assumed | Paquete `python3` = 3.11 en bookworm |
| Ubuntu 20.04 | native | `python3` | assumed | Python 3.8 (EOL) — **requiere python_min 3.9** → incompatible real |
| Ubuntu 22.04/24.04 | native | `python3` | assumed | Python 3.10/3.12 — OK |
| Fedora 38+ | native | `python3` | assumed | Python 3.11/3.12 — OK |
| Void | native | `python3.11` / `python3.12` | **assumed (nombre difiere)** | Void usa `python3.11`, `python3.12` como paquetes separados; manifiesto debe decidir cuál |

> **Decisión para Void**: En FASE 1 el manifiesto usa `void = "python3.11"` (asumido). En FASE 3 se verificará y se documentará el nombre exacto.

### `catalog/ai/ollama.toml`

| Distro | Método | Detalle | Estado | Notas |
|--------|--------|---------|--------|-------|
| Arch | native | `ollama` (extra/ollama) | **verified** | Existe en repos oficiales Arch (extra) |
| Arch | binary_release | GitHub releases | assumed | Funciona pero native preferido |
| Debian/Ubuntu | native | `null` | unsupported | No hay paquete `ollama` en repos oficiales Debian/Ubuntu |
| Debian/Ubuntu | binary_release | GitHub releases | assumed | Binario oficial Linux x86_64/aarch64; hash pendiente |
| Fedora | native | `null` | unsupported | No en repos oficiales Fedora (COPR existe, no oficial) |
| Fedora | binary_release | GitHub releases | assumed | Idem |
| Void | native | `null` | unsupported | No en repos oficiales Void |
| Void | binary_release | GitHub releases | assumed | Idem |

> **Clave**: Para Ollama, **solo Arch tiene `verified` vía native**. El resto depende de `binary_release` con hash pinneado (FASE 3).

---

## Particularidades por Distro (Para Autores de Manifiestos)

### Debian / Ubuntu
- Mismos nombres de paquete **la mayoría de las veces**
- Ubuntu a veces tiene versiones más nuevas (PPA no considerado — solo repos oficiales)
- `python3` en Ubuntu 20.04 = 3.8 → **incompatible con `python_min = "3.9"`** → el planificador lo marcará incompatible aunque el paquete exista

### Fedora
- Nombres suelen coincidir con Arch (`git`, `python3`, `rust`, `go`, `nodejs`)
- `dnf` maneja dependencias bien; `privileged = true` estándar

### Void Linux
- **Nombres frecuentemente distintos**: `python3.11`, `python3.12`, `nodejs-20`, `rust-1.75`, `go-1.21`
- `xbps-query -Rs <nombre>` es la fuente de verdad
- Rolling pero conservador; a veces versiones más viejas que Arch

### Arch Linux
- `pacman` nombres canónicos (`python` = 3.x actual, `git`, `rust`, `go`, `nodejs`)
- `extra/ollama` existe (verificado)
- AUR **no usado** por el core (solo native = repos oficiales). Usuario puede añadir AUR via manifiesto personal.

---

## Arquitecturas de CPU

| Arquitectura | Estado General | Notas |
|--------------|----------------|-------|
| `x86_64` (amd64) | **verified** | Arquitectura de desarrollo y test principal |
| `aarch64` (arm64) | assumed | Binarios GitHub Releases suelen existir; native packages en Debian/Ubuntu/Fedora/Arch ARM |
| `armv7` (armhf) | unsupported | No planeado; PRs bienvenidos |
| `riscv64` | unsupported | Emergente; solo si upstream provee binarios |

**Regla en manifiestos**: `cpu_arch` en `[requirements]` lista arquitecturas soportadas. El planificador filtra automáticamente.

---

## GPU / CUDA

| Vendor | Detección | Estado | Notas |
|--------|-----------|--------|-------|
| NVIDIA (propietario) | `nvidia-smi` + `/proc/driver/nvidia/version` | assumed | Requiere driver instalado; CUDA version detectable |
| AMD (ROCm) | `rocminfo` + `/sys/class/drm/` | unsupported | FASE 3+ |
| Intel (Arc/integrado) | `intel_gpu_top` + `/sys/class/drm/` | unsupported | FASE 3+ |
| Apple Silicon (Metal) | `system_profiler` | unsupported | Solo macOS (fuera de alcance Linux) |

**En manifiestos**: `gpu = "required"` → herramienta solo `compatible`/`recomendado`/`optimo` si GPU detectada coincide. `gpu = "optional"` → GPU mejora clasificación a óptimo si presente.

---

## Cómo Cambia el Estado (Workflow FASE 3)

1. **Escritura de manifiesto** → estado inicial `assumed` para distros no Arch
2. **Test en VM/CI** (GitHub Actions matrix: Arch, Debian, Ubuntu, Fedora, Void) → instala + verifica
3. **Si pasa**: PR actualiza `COMPATIBILITY.md` → `verified` + fecha + link a run CI
4. **Si falla**: Manifiesto corregido (cambia paquete, añade método, marca `unsupported`) → volver a 1

**Ningún manifiesto se fusiona a `main` sin al menos `assumed` documentado y `verified` en Arch**.

---

## Reporte de Compatibilidad (Generado por `--audit --compat`)

```text
COMPATIBILITY REPORT - Thorrija Environment
Generated: 2026-11-10 14:30:22
Host: Arch Linux (verified)

Tool                    | Method         | Arch     | Debian   | Ubuntu   | Fedora   | Void
------------------------|----------------|----------|----------|----------|----------|--------
git                     | native         | verified | assumed  | assumed  | assumed  | assumed
python                  | native         | verified | assumed* | assumed* | assumed  | assumed†
ollama                  | native         | verified | unsup.   | unsup.   | unsup.   | unsup.
ollama                  | binary_release | assumed  | assumed  | assumed  | assumed  | assumed

* Ubuntu 20.04: python3=3.8 < python_min=3.9 → incompatible real
† Void: paquete python3.11 asumido; requiere verificación nombre exacto
```

Este reporte lo genera el motor leyendo `COMPATIBILITY.md` (formato máquina en `docs/compatibility.json` futuro) + resultados de verificación real.

---

## Limitaciones Actuales (FASE 1)

- Solo **Arch** tiene estado `verified` real (host del autor)
- Todas las demás distros: `assumed` basado en conocimiento de nombres de paquetes públicos
- **No hay CI matrix** todavía (FASE 2+)
- Void Linux: nombres de paquetes Python/Node/Rust **no confirmados** — marcados `assumed` con nota
- Ubuntu 20.04: Python 3.8 → incompatible con piso 3.9 del proyecto
- GPU/ROCm/CUDA: detección no implementada → todo `assumed`/`unsupported`

---

## Decisiones Pendientes

| Tema | Decisión Necesaria |
|------|-------------------|
| Ubuntu 20.04 EOL (abril 2025) | ¿Soportar como mínimo o subir a 22.04? |
| Fedora EOL rápido (13 meses) | ¿Versión mínima fija o "última + 1 anterior"? |
| AUR en Arch | ¿Permitir `aur` como familia en `install.native`? (Riesgo: no auditado) |
| Flatpak / Snap / AppImage | ¿Drivers adicionales? (Actualmente solo native/binary/git/pipx/script) |
| Windows (WSL2) | ¿Cuándo y cómo? (Arquitectura lo permite, no prioridad) |