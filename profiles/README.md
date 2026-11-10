# Perfiles de Hardware — Especificación

Este directorio contiene la definición de perfiles (`profiles/*.toml`) que el clasificador usa para **auto-detectar** el perfil adecuado si el usuario no pasa `--profile`.

## Estructura de un Perfil

```toml
# profiles/standard.toml (ejemplo)
name = "standard"
description = "Equipo de uso general: 4-8 cores, 8-16 GB RAM, GPU opcional"

[thresholds]
# Umbrales para AUTO-clasificación
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

## Perfiles Base (Definidos en FASE 1, implementados en FASE 2)

| Archivo | Perfil | Target |
|---------|--------|--------|
| `low-end.toml` | `low_end` | 2 cores, 2-4 GB RAM, sin GPU, disco limitado |
| `standard.toml` | `standard` | 4-8 cores, 8-16 GB RAM, GPU opcional |
| `high-end.toml` | `high_end` | 16+ GB RAM, CPU moderna, GPU dedicada opcional |
| `minimal.toml` | `minimal` | Solo esenciales: git, python, editor CLI, shell |
| `developer.toml` | `developer` | Alias de `standard` + herramientas de build |
| `cybersecurity.toml` | `cybersecurity` | `standard` + categoría `security` enabled |
| `ai-engineering.toml` | `ai_engineering` | `high_end` + categoría `ai` enabled |
| `full.toml` | `full` | Todo `enabled` (requiere high_end real) |

## Clasificación Automática (Algoritmo)

```python
def classify_hardware(hw: HardwareReport) -> str:
    # Carga todos los profiles/*.toml ordenados por prioridad
    # Evalúa umbrales en orden: low_end → standard → high_end
    # Retorna el primero que matchea TODOS sus umbrales
    # Si ninguno → "standard" (fallback seguro)
```

**Regla**: Un perfil matchea si **TODAS** sus condiciones se cumplen. Ejemplo `high_end`:
- RAM ≥ 16384 MB **Y**
- CPU cores ≥ 8 **Y**
- (GPU dedicada VRAM ≥ 4096 MB **O** CPU cores ≥ 16)

Esto evita clasificar como high_end una máquina con 32 GB RAM pero CPU antigua de 2 cores.

## Personalización

El usuario puede:
1. Crear `~/.config/thorrija/profiles/custom.toml` → se fusiona (override) con los base
2. Pasar `--profile high-end` para forzar (ignora auto-clasificación)
3. Ver perfil detectado con `--detect` (muestra HW + perfil propuesto + umbrales)

## Estado FASE 1

- **Especificación documentada** ✅
- **Archivos `.toml` reales** ❌ (se crean en FASE 2 junto al clasificador)
- Este `README.md` sirve como contrato para la implementación