# Seguridad

## Principios

1. **Cero secretos en el repo** — Ni tokens, contraseñas, claves SSH, ni hashes de contraseñas. Los secretos viven en el entorno del usuario (keyring, variables de entorno, archivos locales fuera del repo).
2. **Sin `curl | bash` sin verificación** — Todo código remoto debe tener hash SHA-256 pinneado en el manifiesto. El motor **rechaza** ejecutar scripts o binarios sin hash verificado.
3. **Sudo mínimo, agrupado, confirmado** — El motor recopila todas las operaciones que requieren privilegios, las muestra **antes** de ejecutar, y pide confirmación única. No hay `sudo` disperso ni silencioso.
4. **Backups antes de tocar** — Cualquier escritura sobre archivos existentes del usuario (dotfiles, configs, `~/.config`, `~/.local`) genera backup automático en `~/.thorrija-backup/<YYYYMMDD-HHMMSS>/` con estructura espejo.
5. **Idempotencia real** — Cada driver verifica estado actual antes de actuar. `already_installed` / `installed` / `configured` / `failed`. No "reinstalar por si acaso".
6. **Auditoría completa** — Log JSON-lines inmutable en `~/.local/share/thorrija/log/`. Cada operación: timestamp, herramienta, acción, resultado, archivos modificados, hashes de stdout/stderr.
7. **Verificación de resultado real** — La instalación no se da por buena por exit code 0. Se ejecuta `[verify].command` y se matchea `[verify].pattern` contra la salida real.
8. **Descargas grandes = consentimiento explícito** — Herramientas con `size_class ∈ {medium, large}` o `disk_install_mb > 200` exigen `--yes` o confirmación interactiva.
9. **Modelos de IA nunca automáticos** — `[ai_models].automatic = false` hardcodeado en manifiestos. Cada `ollama pull` / `litellm download` requiere acción de usuario.
10. **Integridad del propio instalador** — Bootstrap verifica checksum del repo clonado / tarball descargado antes de delegar al motor Python.

---

## Modelo de amenazas (STRIDE)

| Amenaza | Mitigación |
|---------|------------|
| **Spoofing** (falso instalador) | Bootstrap verifica hash SHA-256 del tarball de release de GitHub antes de extraer. Releases firmados por GitHub (sigstore/cosign en Fase 2+). |
| **Tampering** (manifiesto modificado) | Catálogo versionado en Git; `git log` + tags firmados. Validador rechaza manifiestos con campos inválidos. |
| **Repudiation** (no saber qué pasó) | Log JSON-lines inmutable + backups con timestamp. `--audit` reconstruye historia completa. |
| **Information Disclosure** (secretos en log) | **Nunca** se loguean: contraseñas, tokens, claves, variables de entorno sensibles. Sanitización automática (API keys, JWT, AWS keys, etc.). |
| **Denial of Service** (instalación rota) | Idempotencia + estado por herramienta + `--resume` + `--audit` detectan instalaciones parciales. Rollback manual via backups. |
| **Elevation of Privilege** (sudo abusivo) | Sudo solo para: (a) gestor de paquetes nativo, (b) escribir en `/usr/local`, `/opt`, `/etc`. **Nunca** para modificar `$HOME`. Operaciones en `$HOME` usan permisos de usuario. |

---

## Política de Sudo

| Operación | Sudo | Cómo se maneja |
|-----------|------|----------------|
| `pacman -S`, `apt install`, `dnf install`, `xbps-install` | Sí | Agrupadas en una llamada por gestor; mostradas al usuario con comando exacto |
| `mkdir -p /usr/local/bin` + `cp` binario | Sí | Agrupada; muestra ruta destino |
| `systemctl enable/start` (servicios systemd) | Sí | Solo si el manifiesto declara `service: true` (raro); agrupado |
| Escribir en `~/.local/bin`, `~/.config`, `~/.bashrc` | No | Permisos de usuario; backup previo |
| `pipx install` | No | Usuario (pipx gestiona su directorio) |
| `git clone` + `make install` (prefix=$HOME/.local) | No | Usuario |

**El usuario ve ANTES de confirmar:**

```
OPERACIONES QUE REQUIEREN SUDO (3 comandos):
  1. pacman -S --needed --noconfirm git python rust
  2. mkdir -p /usr/local/bin && cp ollama /usr/local/bin/ollama
  3. systemctl enable --now ollama.service

¿Continuar? [s/N]:
```

---

## Hash Pinning

| Método | Hash | Qué se verifica |
|--------|------|-----------------|
| `binary_release` | `sha256` table (por arch) | Hash del **archivo descargado** antes de extraer |
| `script_official` | `sha256` string | Hash del **script exacto** descargado antes de ejecutar |
| `git_clone` | Commit SHA en `branch` (opcional) | Si `branch` = commit SHA (40 hex), verifica `git rev-parse HEAD` tras clone |
| `native` | — | Confianza en repos oficiales + claves del gestor |

**Si falta hash**: El método se marca `disabled: true` en el plan con razón `"inseguro: hash no pinneado"`. El usuario puede forzar con `--unsafe-allow-unverified` (solo interactivo, nunca en `--yes`).

---

## Backups y restauración

**Directorio**: `~/.thorrija-backup/<YYYYMMDD-HHMMSS>/`

**Qué se backupea** (antes de primera escritura):
- Dotfiles objetivo: `~/.bashrc`, `~/.config/fish/`, `~/.config/nvim/`, etc.
- Cualquier archivo que el motor vaya a **sobrescribir** (detectado por `state.backup_paths`)
- Configs de sistema si se tocan (raro): `/etc/environment.d/`, `/etc/profile.d/`

**Estructura:**
```
~/.thorrija-backup/20261110-143022/
├── home/
│   ├── .bashrc
│   └── .config/
│       └── fish/
│           └── config.fish
└── manifest.json  # {timestamp, tools_affected, files_backed_up[]}
```

**Restauración manual:**
```bash
ls ~/.thorrija-backup/
rsync -av ~/.thorrija-backup/20261110-143022/home/ ~/
```

---

## Log de Auditoría (JSON-Lines)

**Ubicación**: `~/.local/share/thorrija/log/<YYYYMMDD-HHMMSS>.jsonl`

**Entrada típica:**
```json
{"ts":"2026-11-10T14:30:22.123Z","tool":"git","action":"install_native","result":"installed","method":"native","files_changed":["/usr/bin/git"],"stdout_sha256":"a1b2c3...","stderr_sha256":"","duration_ms":4500,"verify":{"command":"git --version","pattern":"git version","ok":true}}
{"ts":"2026-11-10T14:30:27.456Z","tool":"ollama","action":"install_binary","result":"failed","method":"binary_release","files_changed":[],"stdout_sha256":"","stderr_sha256":"d4e5f6...","duration_ms":12000,"error":"sha256 mismatch: expected abc..., got def...","verify":{"ok":false}}
```

**Campos**: `ts`, `tool`, `action`, `result`, `method`, `files_changed`, `stdout_sha256`, `stderr_sha256`, `duration_ms`. `verify` presente si acción = install/configure.

**Uso de `--audit`:**
```bash
thorrija --audit                    # Resumen de última ejecución
thorrija --audit --json             # JSON completo
thorrija --audit --tool git         # Detalle de una herramienta
thorrija --audit --since 2026-11-01 # Filtrar por fecha
```

---

## Operaciones PROHIBIDAS en el Core

El motor **nunca** debe:

1. Ejecutar `curl ... | bash` o `wget ... | sh` sin hash verificado
2. Ejecutar `sudo` para escribir en `$HOME` o subdirectorios
3. Sobrescribir archivo existente sin backup previo registrado
4. Loguear secrets (sanitizador obligatorio en `state/audit.py`)
5. Descargar >200 MB sin consentimiento explícito (`--yes` o prompt)
6. Instalar modelos de IA (Ollama, HuggingFace, etc.) sin acción del usuario
7. Modificar `/etc`, `/usr`, `/opt` fuera de gestor nativo (salvo `/usr/local/bin` para binarios `binary_release` con confirmación)
8. Ejecutar código descargado sin verificación de integridad (hash + opcionalmente firma)
9. Asumir que exit code 0 = éxito (siempre verificación `[verify]`)
10. Continuar tras fallo de verificación sin `--continue-on-error`

---

## Sanitización de Logs

Antes de escribir en el log, el motor pasa stdout/stderr por:

```python
SECRET_PATTERNS = [
    r'(?i)(api[_-]?key|apikey|token|secret|password|passwd)\s*[:=]\s*\S+',
    r'gh[ps]_[a-zA-Z0-9]{36,}',           # GitHub tokens
    r'aws_access_key_id\s*=\s*[A-Z0-9]{20}',
    r'aws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{40}',
    r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',  # JWT
    r'(?i)bearer\s+[A-Za-z0-9_-]{20,}',
]
```

Cada match se reemplaza por `***REDACTED***` **antes** de hashear y loguear.

---

## Verificación de Integridad del Instalador (Bootstrap)

`install.sh` debe:

1. Descargar tarball: `https://github.com/ThorrijaDEV/thorrija-environment/releases/download/vX.Y.Z/thorrija-environment-vX.Y.Z.tar.gz`
2. Verificar SHA-256 contra valor **hardcodeado en el script** (actualizado en cada release)
3. Solo si hash OK → extraer a directorio temporal → ejecutar `python3 -m thorrija ...`
4. Si hash falla → abortar: "Integridad del instalador comprometida. Descarga manual desde GitHub."

---

## Decisiones Pendientes

| Tema | Opciones | Actual |
|------|----------|--------|
| Firma de releases | cosign/sigstore, GPG, GitHub attestations | Pendiente — Fase 2 |
| Sandboxing de drivers | bubblewrap, systemd-run, sin sandbox | Pendiente — Fase 2 |
| Rate limiting GitHub API | Token personal, GitHub App, sin token | Pendiente — Fase 2 |
| Notificaciones de seguridad | Email, webhook, solo log local | Pendiente — Fase 5 |

---

## Checklist por Release

- [ ] Todos los `binary_release`/`script_official` tienen hashes reales (no `PENDING-VERIFICATION`)
- [ ] Validador rechaza manifiestos sin hash en esos métodos
- [ ] `install.sh` tiene hash del release hardcodeado y verificado
- [ ] Sanitizador de logs probado con patrones de secretos reales
- [ ] Backups creados y restaurables en prueba de integración
- [ ] `--audit` reporta correctamente instalaciones parciales
- [ ] Sudo agrupado y mostrado antes de confirmar (test visual)
- [ ] Modelos de IA: `[ai_models].automatic = false` en todos los manifiestos `ai`
- [ ] Descargas >200 MB exigen `--yes` (test automatizado)