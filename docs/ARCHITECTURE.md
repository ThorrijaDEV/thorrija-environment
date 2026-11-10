# Arquitectura

## Visión general

Thorrija Environment es un provisionador declarativo: toma un Linux base y lo convierte en un entorno de desarrollo completo, adaptado al hardware real. El flujo es simple: **detectar → planificar → confirmar → ejecutar → auditar**.

```
Bootstrap (Bash) → Detección OS/HW → Clasificación → Planificador → Motor de instalación
                                                        ↓
                                              Auditoría ← Verificación ← Drivers ← Estado/Backups
```

## Módulos principales

```
src/thorrija/
├── detect/     # OS, hardware, clasificación de perfiles
├── catalog/    # Carga, validación, resolución de manifiestos TOML
├── plan/       # Planificador + grafo de dependencias
├── install/    # Motor + 5 drivers (native, binary, git, script, pipx)
├── state/      # Log JSON-lines, backups, estado por herramienta
└── ui/         # CLI + formateadores
```

## Flujo de datos

1. **Entrada**: flags CLI + catálogo local + perfil (auto o forzado)
2. **Detección**: `HardwareReport` (RAM, CPU, GPU, disco, arch) + `OSReport` (distro, versión, gestor paquetes)
3. **Clasificación**: `Profile` (low_end/standard/high_end) via umbrales en `profiles/*.toml`
4. **Catálogo**: `ToolManifest` filtrados por categoría/perfil + compatibilidad
5. **Resolución**: grafo de dependencias → `InstallPlan` (orden topológico, conflictos, alternativas)
6. **Plan legible**: tabla con herramienta, método, recursos, clase de compatibilidad, sudo, bytes a descargar
7. **Confirmación**: usuario revisa y aprueba (`--yes` para no interactivo)
8. **Ejecución**: drivers en orden, idempotentes, registran en `state/`
9. **Verificación**: cada tool ejecuta su `[verify].command` y matchea `pattern`
10. **Auditoría**: reporte final + log completo en `~/.local/share/thorrija/log/`

## Clases de compatibilidad

No confundir "instalable" con "ejecutable bien".

| Clase | Definición | Uso en plan |
|-------|------------|-------------|
| **Compatible** | Método viable + espacio en disco | Solo si el usuario lo pide explícitamente |
| **Recomendado** | Compatible + RAM ≥ `ram_run_mb` | Por defecto en perfiles `enabled` |
| **Óptimo** | Recomendado + RAM ≥ `ram_optimal_mb` + GPU si aplica | Marcado como "óptimo" |

Los umbrales (`ram_run_mb`, `ram_optimal_mb`) viven en el **manifiesto** de cada herramienta. La clasificación de perfil (low_end/standard/high_end) vive en `profiles/*.toml` y controla qué herramientas se ofrecen por defecto (`enabled`/`optional`/`excluded`).

## Catálogo y manifiestos

- Un archivo TOML por herramienta en `catalog/<categoría>/<nombre>.toml`
## Documentación relacionada

- [Esquema de manifiestos](MANIFESTS.md) — Esquema TOML formal
- [Seguridad](SECURITY.md) — Modelo de amenazas, política sudo, hash pinning, backups
- [Compatibilidad](COMPATIBILITY.md) — Matriz distro × herramienta, verified/assumed/unsupported
- [Bootstrap](BOOTSTRAP.md) — Especificación de install.sh, estrategias de fallback Python
- Categorías: `languages`, `development`, `editors`, `ai`, `security`, `system`
- Cada manifiesto declara sus requisitos, métodos de instalación, verificación

## Drivers de instalación

| Driver | Descripción | Idempotencia | Cuándo usar |
|--------|-------------|--------------|-------------|
| `native` | Gestor de paquetes del SO (pacman/apt/dnf/xbps) | Paquete instalado + versión | Primera opción si hay paquete oficial |
| `binary_release` | Tarball/binario de GitHub Releases + SHA-256 | Hash + extracción + symlink | Sin paquete nativo, releases con hash |
| `git_clone` | Clone superficial + build (make/cargo/go) | Repo + commit + artefacto | Solo sin release binario |
| `script_official` | Script oficial **con hash pinneado** | Hash + ejecución + verificación | Último recurso, hash obligatorio |
| `pipx` | `pipx install <paquete>` | `pipx list` + versión | Herramientas Python CLI en PyPI |

**Regla de seguridad**: `binary_release` y `script_official` **requieren** `sha256` en el manifiesto. Sin hash → método deshabilitado (el planificador lo reporta como "inseguro: hash no pinneado").

## Estado y recuperación

- **Log**: JSON-lines en `~/.local/share/thorrija/log/<timestamp>.jsonl`
  - Cada entrada: `{ts, tool, action, result, files_changed[], stdout_sha256, stderr_sha256}`
- **Estado por herramienta**: `~/.local/share/thorrija/state/<tool>.json`
  - `{status: "pending|installed|configured|failed", method, version, installed_at, verify_ok}`
- **Backups**: `~/.thorrija-backup/<YYYYMMDD-HHMMSS>/` antes de tocar archivos existentes (dotfiles, configs)
- **Reanudación**: `--resume` continúa desde la primera tool `pending` o `failed` (si es seguro)
- **Detección de instalación parcial**: `--audit` compara estado declarado vs verificación real

## Testing por fases

| Fase | Qué se prueba | Fixtures de hardware |
|------|---------------|---------------------|
| 2 (Núcleo) | Detección, clasificación, manifiestos, planificador, dry-run | 5 perfiles |
| 3 (Catálogo) | Instalación real + verificación + idempotencia | 5 perfiles + matrix distros |
| 5 (Final) | Integración completa, recovery, offline-ready | Hardware real + VMs |

### 5 perfiles de hardware de referencia

| Perfil | RAM | CPU | GPU | Disco | Uso |
|--------|-----|-----|-----|-------|-----|
| `hw-minimal` | 2 GB | 2 cores | none | 20 GB HDD | LOW-END baseline |
| `hw-integrated` | 4 GB | 4 cores | Intel UHD / AMD Vega | 64 GB SSD | STANDARD low |
| `hw-standard` | 8 GB | 6 cores | none | 128 GB SSD | STANDARD typical |
| `hw-workstation` | 16 GB | 12 cores | NVIDIA RTX 3060 (12 GB) | 512 GB NVMe | HIGH-END |
| `hw-ai` | 32 GB | 16 cores | NVIDIA RTX 4090 (24 GB) | 1 TB NVMe | HIGH-END AI |

Los tests alimentan fixtures al motor de detección y verifican que la clasificación y el plan coinciden con lo esperado.

## Modo offline / SSD (Fase 4)

La arquitectura **no implementa** modo offline aún, pero está diseñada para ello:

- Catálogo y manifiestos son archivos estáticos → copiables a SSD
- Drivers `native` requieren red; `binary_release`/`git_clone` pueden usar caché local
- `install.sh --offline` futuro: leerá `offline/manifests/` + `offline/cache/` y reportará qué falta
- **Nunca** finge instalación completa si faltan componentes

## Decisiones arquitectónicas clave

| Decisión | Alternativa descartada | Por qué |
|----------|------------------------|---------|
| Bootstrap Bash + motor Python stdlib | Todo en Bash / Rust / Nix | Bash universal; Python 3.9+ en todas las distros; stdlib = cero deps bootstrap |
| TOML para manifiestos | YAML (PyYAML) / JSON (verbose) | `tomllib` en stdlib desde 3.11; `tomli` de 1 archivo para 3.9/3.10 |
| Perfiles configurables (TOML) | Hardcoded en código | Umbrales cambian; equipos modestos evolucionan; separa política de mecanismo |
| Verificación por comando+pattern | Exit code del instalador | Exit code 0 ≠ herramienta funciona (servicio no arranca, binario roto en PATH) |
| Sin `curl \| bash` sin hash | Scripts remotos "convenientes" | Supply chain security; hash pinneado = integridad verificable |

## Estado de implementación

| Componente | Estado |
|------------|--------|
| Especificación (Fase 1) | Completa |
| Bootstrap `install.sh` | Completado |
| Detección OS/HW | Completado |
| Clasificador de perfiles | Completado |
| Cargador/validador manifiestos | Completado |
| Planificador + resolvedor | Completado |
| Drivers de instalación | Completados (5) |
| Estado + auditoría + backups | Completado |
| CLI completa | Completada |
| Catálogo completo (6 categorías) | Completado (51 herramientas) |
| Modo offline/SSD | Diseñado, no implementado |
| Tests de integración 5 perfiles | Completados |

El código es ejecutable y validado. La documentación refleja lo que existe.