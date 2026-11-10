# Tests — Validación Documental

Este directorio contiene herramientas de validación de la **especificación** (FASE 1), no del motor de instalación.

## `validate_manifests.py`

Valida:
1. **Esquema de manifiestos** — Todos los `catalog/**/*.toml` cumplen `docs/MANIFESTS.md`
2. **Ejemplos en documentación** — Bloques ```toml en `MANIFESTS.md` son TOML válido
3. **Referencias cruzadas** — Docs mencionan archivos que existen
3. **Placeholders detectados** — `PENDING-VERIFICATION` en hashes → warning (método deshabilitado)

### Uso

```bash
# Desde la raíz del repo
python3 tests/validate_manifests.py

# Exit codes:
#  0 = todo OK
#  1 = errores de validación
```

### Salida Esperada (FASE 1)

```
🔍 Validando manifiestos en catalog/...
  3 archivos, 0 errores
🔍 Validando bloques TOML en docs/MANIFESTS.md...
  0 errores
🔍 Validando referencias cruzadas...
  0 errores

============================================================
⚠️  WARNINGS:
  - catalog/ai/ollama.toml: binary_release.sha256.x86_64 = PENDING-VERIFICATION (método deshabilitado hasta pinnear hash real)
  - catalog/ai/ollama.toml: binary_release.sha256.aarch64 = PENDING-VERIFICATION (método deshabilitado hasta pinnear hash real)

✅ TODAS LAS VALIDACIONES PASARON
(2 warnings informativos)
```

Los **warnings son esperados y correctos** en FASE 1: los hashes de Ollama se pinnearán en FASE 3 tras verificación real. El validador los detecta y reporta, pero no son errores.

## Tests Futuros (FASE 2+)

| Archivo | Qué Prueba |
|---------|------------|
| `test_detect.py` | Detección OS/HW con fixtures de 5 perfiles |
| `test_classify.py` | Clasificación de perfiles con umbrales |
| `test_plan.py` | Planificador: dependencias, conflictos, orden |
| `test_drivers/` | Cada driver: native, binary_release, git_clone, script_official, pipx |
| `test_idempotency.py` | Segunda ejecución = already_installed |
| `test_recovery.py` | `--resume` tras fallo parcial |
| `test_audit.py` | `--audit` detecta instalaciones parciales |

## Fixtures de Hardware (Para FASE 2)

Simulados via variables de entorno / mocks en `tests/fixtures/hardware/`:

| Fixture | RAM | CPU | GPU | Disco | Perfil Esperado |
|---------|-----|-----|-----|-------|-----------------|
| `hw-minimal.json` | 2 GB | 2 cores | none | 20 GB HDD | low_end |
| `hw-integrated.json` | 4 GB | 4 cores | Intel UHD | 64 GB SSD | standard |
| `hw-standard.json` | 8 GB | 6 cores | none | 128 GB SSD | standard |
| `hw-workstation.json` | 16 GB | 12 cores | RTX 3060 12GB | 512 GB NVMe | high_end |
| `hw-ai.json` | 32 GB | 16 cores | RTX 4090 24GB | 1 TB NVMe | high_end |