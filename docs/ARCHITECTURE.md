# Arquitectura de Thorrija Environment

## Visión General

Thorrija Environment es un **provisionador declarativo** que transforma un Linux "crudo" en un entorno de desarrollo completo, adaptado al hardware real. La arquitectura sigue el principio: **detectar → planificar → confirmar → ejecutar → auditar**.

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐     ┌────────────┐
│  Bootstrap  │────▶│  Detección   │────▶│  Clasif.    │────▶│  Planificador│────▶│  Motor de  │
│  (Bash)     │     │  OS + HW     │     │  Perfil     │     │  + Resolvedor│     │  Instalación│
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘     └────────────┘
                                                                                          │
                                                                                          ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐     ┌────────────┐
│  Auditoría  │◀────│  Verificación│◀────│  Drivers    │◀────│  Estado +    │◀────│  Log       │
│  Post-Inst. │     │  Real        │     │  Idempot.   │     │  Backups     │     │  JSON-lines│
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘     └────────────┘
```

## Módulos Principales (src/thorrija/)

| Módulo | Responsabilidad | Archivos Clave |
|--------|-----------------|----------------|
| `detect/` | Detección OS, hardware, clasificación de perfil | `os_detect.py`, `hw_detect.py`, `classify.py` |
| `catalog/` | Carga, validación y resolución de manifiestos TOML | `loader.py`, `validator.py`, `resolver.py` |
| `plan/` | Generación de plan humano, resolución de dependencias | `planner.py`, `depgraph.py` |
| `install/` | Motor + drivers de instalación | `engine.py`, `drivers/{native,binary_release,git_clone,script_official,pipx}.py` |
| `state/` | Log JSON-lines, backups, estado por herramienta | `audit.py`, `backup.py`, `tool_state.py` |
| `ui/` | CLI: --detect, --plan, --profile, --category, --audit, --update | `cli.py`, `formatters.py` |

## Flujo de Datos

1. **Entrada**: Flags CLI + catálogo local (descargado de GitHub) + perfil solicitado/auto
2. **Detección**: `HardwareReport` (RAM, CPU, GPU, disco, arquitectura) + `OSReport` (distro, versión, gestor de paquetes)
3. **Clasificación**: `Profile` (low_end/standard/high_end) via umbrales en `profiles/*.toml`
4. **Catálogo**: Lista de `ToolManifest` filtrados por categoría/perfil + compatibilidad
5. **Resolución**: Grafo de dependencias → `InstallPlan` (orden topológico, conflictos, alternativas)
6. **Plan Humano**: Tabla con herramienta, método, recursos, estado (compatible/recomendado/óptimo), requiere sudo, bytes a descargar
7. **Confirmación**: Usuario revisa y aprueba (`--yes` para no interactivo)
8. **Ejecución**: Drivers en orden, cada uno idempotente, registrando en `state/`
9. **Verificación**: Cada herramienta ejecutando su `[verify].command` y matcheando `pattern`
10. **Auditoría**: Reporte final + log completo en `~/.local/share/thorrija/log/`

## Semántica de Clases de Compatibilidad

**NUNCA** confundir "instalable" con "ejecutable correctamente".

| Clase | Definición Técnica | Uso en Plan |
|-------|-------------------|-------------|
| **Compatible** | Existe al menos un método de instalación viable Y `disk_install_mb` disponible | Se instala si el usuario lo pide explícitamente |
| **Recomendado** | Compatible + RAM disponible ≥ `ram_run_mb` (o `ram_optimal_mb` si existe) | Instalación por defecto en perfiles que lo marcan `enabled` |
| **Óptimo** | Recomendado + RAM ≥ `ram_optimal_mb` (si definido) + condición GPU satisfecha | Marcado como "óptimo"; el plan puede sugerir actualizar hardware si no se alcanza |

Los umbrales `ram_run_mb` / `ram_optimal_mb` viven en el **manifiesto** de cada herramienta. La clasificación de perfil (LOW-END/STANDARD/HIGH-END) vive en `profiles/*.toml` y controla qué herramientas se *ofrecen* por defecto (`enabled`/`optional`/`excluded`).

## Catálogo y Manifiestos

- Un archivo TOML por herramienta en `catalog/<categoría>/<nombre>.toml`
- Esquema formal en [MANIFESTS.md](MANIFESTS.md)
- Categorías: `languages`, `development`, `editors`, `ai`, `security`, `system`
- Cada manifiesto declara sus propios requisitos, métodos de instalación, verificación

## Drivers de Instalación

| Driver | Descripción | Idempotencia | Cuándo Usar |
|--------|-------------|--------------|-------------|
| `native` | Gestor de paquetes del SO (pacman/apt/dnf/xbps) | Verifica paquete instalado + versión | Primera opción siempre que exista paquete oficial |
| `binary_release` | Descarga tarball/binario de GitHub Releases + SHA-256 | Verifica hash + extracción + symlink | Sin paquete nativo, releases oficiales con hash |
| `git_clone` | Clone superficial + build (make/cargo/go build) | Verifica repo + commit + artefacto | Solo cuando no hay release binario |
| `script_official` | Script instalador oficial **con hash pinneado** | Verifica hash + ejecuta + verifica resultado | Solo como último recurso, hash obligatorio |
| `pipx` | `pipx install <paquete>` | Verifica `pipx list` + versión | Herramientas Python CLI distribuidas en PyPI |

**Regla de seguridad**: `binary_release` y `script_official` **requieren** `sha256` en el manifiesto. Sin hash → método **deshabilitado** (el planificador lo reporta como "inseguro: hash no pinneado").

## Estado y Recuperación

- **Log**: JSON-lines en `~/.local/share/thorrija/log/<timestamp>.jsonl`
  - Cada entrada: `{ts, tool, action, result, files_changed[], stdout_sha256, stderr_sha256}`
- **Estado por herramienta**: `~/.local/share/thorrija/state/<tool>.json`
  - `{status: "pending|installed|configured|failed", method, version, installed_at, verify_ok}`
- **Backups**: `~/.thorrija-backup/<YYYYMMDD-HHMMSS>/` antes de tocar cualquier archivo existente (dotfiles, configs)
- **Reanudación**: `--resume` lee el estado y continúa desde la primera herramienta `pending` o `failed` (solo si es seguro: sin cambios destructivos pendientes)
- **Detección de instalación parcial**: `--audit` compara estado declarado vs verificación real de cada herramienta

## Testing por Fases

| Fase | Qué se Prueba | Fixtures de Hardware (simulados) |
|------|---------------|-----------------------------------|
| 2 (Núcleo) | Detección, clasificación, carga manifiestos, planificador, dry-run | 5 perfiles (ver abajo) |
| 3 (Catálogo) | Cada categoría: instalación real + verificación + idempotencia | Mismos 5 perfiles + matrix distros |
| 5 (Final) | Integración completa, recovery, offline-design-ready | Hardware real + VMs |

### 5 Perfiles de Hardware de Referencia (simulados en tests)

| Perfil | RAM | CPU | GPU | Disco | Uso |
|--------|-----|-----|-----|-------|-----|
| `hw-minimal` | 2 GB | 2 cores | none | 20 GB HDD | LOW-END baseline |
| `hw-integrated` | 4 GB | 4 cores | Intel UHD / AMD Vega | 64 GB SSD | STANDARD low |
| `hw-standard` | 8 GB | 6 cores | none | 128 GB SSD | STANDARD typical |
| `hw-workstation` | 16 GB | 12 cores | NVIDIA RTX 3060 (12 GB) | 512 GB NVMe | HIGH-END |
| `hw-ai` | 32 GB | 16 cores | NVIDIA RTX 4090 (24 GB) | 1 TB NVMe | HIGH-END AI |

Los tests **no** inventan resultados: cada fixture alimenta al motor de detección y se verifica que la clasificación y el plan coinciden con lo esperado documentado.

## Puerta Abierta a Modo Offline / SSD (Fase 4)

La arquitectura **no implementa** modo offline en esta fase, pero está diseñada para ello:

- Catálogo y manifiestos son archivos estáticos → copiables a SSD
- Drivers `native` requieren red; `binary_release`/`git_clone` pueden usar caché local
- `install.sh --offline` futuro: leerá `offline/manifests/` + `offline/cache/` y reportará qué dependencias faltan
- **Nunca** fingirá instalación completa si faltan componentes

## Decisiones Arquitectónicas Clave (ADR Resumido)

| Decisión | Alternativa Descartada | Justificación |
|----------|------------------------|---------------|
| Bootstrap Bash + motor Python stdlib | Todo en Bash / Todo en Rust / Nix | Bash universal para arranque; Python 3.9+ en todas las distros objetivo; stdlib = cero deps de bootstrap |
| TOML para manifiestos | YAML (requiere PyYAML) / JSON (verbose) | `tomllib` en stdlib desde Python 3.11; `tomli` de 1 archivo para 3.9/3.10; sin deps externas |
| Perfiles configurables (TOML) | Hardcoded en código | Umbrales de RAM/CPU/GPU cambian; equipos modestos evolucionan; separa política de mecanismo |
| Verificación por comando+pattern | Exit code del instalador | Exit code 0 ≠ herramienta funciona (ej. servicio no arranca, binario en PATH roto) |
| Sin curl\|bash sin hash | Scripts remotos "convenientes" | Supply chain security; hash pinneado = integridad verificable |

## Estado de Implementación (Honesto)

| Componente | Estado | Notas |
|------------|--------|-------|
| Especificación (FASE 1) | ✅ Completa | Este documento + MANIFESTS.md + SECURITY.md + COMPATIBILITY.md + BOOTSTRAP.md |
| Bootstrap `install.sh` | ❌ No implementado | Fase 2 |
| Detección OS/HW | ❌ No implementado | Fase 2 |
| Clasificador de perfiles | ❌ No implementado | Fase 2 |
| Cargador/validador manifiestos | ❌ No implementado | Fase 2 |
| Planificador + resolvedor | ❌ No implementado | Fase 2 |
| Drivers de instalación | ❌ No implementado | Fase 2 |
| Estado + auditoría + backups | ❌ No implementado | Fase 2 |
| CLI completa | ❌ No implementado | Fase 2 |
| Catálogo completo (6 categorías) | ❌ No implementado | Fase 3 (oleadas) |
| Modo offline/SSD | ❌ No implementado | Fase 4 (diseñado, no codificado) |
| Tests de integración 5 perfiles | ❌ No implementado | Fase 2/3/5 |

**Ningún componente marcado ✅ tiene código ejecutable.** Solo documentación y manifiestos de ejemplo validados.