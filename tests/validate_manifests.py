#!/usr/bin/env python3
"""
Validación documental de manifiestos TOML y referencias cruzadas.

Este script NO es el motor de instalación. Es una herramienta de CI/calidad
que verifica:
1. Todos los manifiestos en catalog/**/*.toml cumplen el esquema formal
2. Bloques TOML en docs/MANIFESTS.md son parseables
3. Referencias cruzadas entre docs existen
4. No hay placeholders que parezcan funcionales (PENDING-VERIFICATION detectado)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Python 3.9+: tomllib en stdlib; fallback a tomli si existe
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        print("ERROR: Se requiere Python 3.11+ (tomllib) o paquete 'tomli' instalado")
        sys.exit(1)

# ── Configuración ──────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
CATALOG_DIR = REPO_ROOT / "catalog"
MANIFESTS_DOC = REPO_ROOT / "docs" / "MANIFESTS.md"

VALID_CATEGORIES = {"languages", "development", "editors", "ai", "security", "system"}
VALID_PROFILE_VALUES = {"enabled", "optional", "excluded"}
VALID_GPU_VALUES = {"none", "optional", "required"}
VALID_SIZE_CLASSES = {"tiny", "small", "medium", "large", "auto"}
VALID_INSTALL_METHODS = {"native", "binary_release", "git_clone", "script_official", "pipx"}
NATIVE_PKG_FAMILIES = {"arch", "debian", "fedora", "void", "opensuse", "alpine", "gentoo"}

NAME_REGEX = re.compile(r"^[a-z][a-z0-9-]*$")
SEMVER_REGEX = re.compile(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?(?:\+[a-zA-Z0-9.-]+)?$")
URL_REGEX = re.compile(r"^https?://")

# ── Utilidades ─────────────────────────────────────────────────────────────

class ValidationError(Exception):
    def __init__(self, file: str, message: str, path: str = ""):
        self.file = file
        self.message = message
        self.path = path
        super().__init__(f"{file}{':' + path + ' ' if path else ' '}{message}")

def parse_toml_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except Exception as e:
        raise ValidationError(str(path), f"TOML parse error: {e}")

def parse_toml_string(content: str, source: str) -> dict[str, Any]:
    try:
        return tomllib.loads(content)
    except Exception as e:
        raise ValidationError(source, f"TOML parse error: {e}")

# ── Validadores de Esquema ─────────────────────────────────────────────────

def validate_tool_section(data: dict, file: str) -> list[ValidationError]:
    errors = []
    tool = data.get("tool")
    if not tool or not isinstance(tool, dict):
        errors.append(ValidationError(file, "Sección [tool] requerida y debe ser tabla"))
        return errors

    # name
    name = tool.get("name")
    if not name or not isinstance(name, str):
        errors.append(ValidationError(file, "[tool].name: requerido, string"))
    elif not NAME_REGEX.match(name):
        errors.append(ValidationError(file, f"[tool].name: '{name}' no matchea ^[a-z][a-z0-9-]*$"))

    # category
    cat = tool.get("category")
    if not cat or not isinstance(cat, str):
        errors.append(ValidationError(file, "[tool].category: requerido, string"))
    elif cat not in VALID_CATEGORIES:
        errors.append(ValidationError(file, f"[tool].category: '{cat}' inválido. Válidos: {sorted(VALID_CATEGORIES)}"))

    # description
    desc = tool.get("description")
    if not desc or not isinstance(desc, str):
        errors.append(ValidationError(file, "[tool].description: requerido, string"))
    elif len(desc) < 10 or len(desc) > 500:
        errors.append(ValidationError(file, "[tool].description: longitud 10-500 chars"))

    # homepage (opcional)
    homepage = tool.get("homepage", "")
    if homepage and not URL_REGEX.match(homepage):
        errors.append(ValidationError(file, f"[tool].homepage: '{homepage}' no es URL válida"))

    # tags (opcional)
    tags = tool.get("tags", [])
    if tags and not (isinstance(tags, list) and all(isinstance(t, str) for t in tags)):
        errors.append(ValidationError(file, "[tool].tags: debe ser array de strings"))

    return errors

def validate_requirements(data: dict, file: str) -> list[ValidationError]:
    errors = []
    req = data.get("requirements", {})
    if not isinstance(req, dict):
        errors.append(ValidationError(file, "[requirements]: debe ser tabla"))
        return errors

    # ram_run_mb
    ram_run = req.get("ram_run_mb", 100)
    if not isinstance(ram_run, int) or ram_run <= 0:
        errors.append(ValidationError(file, "[requirements].ram_run_mb: entero > 0"))

    # ram_optimal_mb
    ram_opt = req.get("ram_optimal_mb", ram_run * 2)
    if not isinstance(ram_opt, int) or ram_opt <= 0:
        errors.append(ValidationError(file, "[requirements].ram_optimal_mb: entero > 0"))

    # disk_install_mb
    disk_inst = req.get("disk_install_mb", 50)
    if not isinstance(disk_inst, int) or disk_inst <= 0:
        errors.append(ValidationError(file, "[requirements].disk_install_mb: entero > 0"))

    # disk_run_mb
    disk_run = req.get("disk_run_mb", disk_inst)
    if not isinstance(disk_run, int) or disk_run <= 0:
        errors.append(ValidationError(file, "[requirements].disk_run_mb: entero > 0"))

    # gpu
    gpu = req.get("gpu", "none")
    if gpu not in VALID_GPU_VALUES:
        errors.append(ValidationError(file, f"[requirements].gpu: '{gpu}' inválido. Válidos: {sorted(VALID_GPU_VALUES)}"))

    # cpu_cores_min
    cpu_min = req.get("cpu_cores_min", 1)
    if not isinstance(cpu_min, int) or cpu_min < 1:
        errors.append(ValidationError(file, "[requirements].cpu_cores_min: entero >= 1"))

    # cpu_arch
    cpu_arch = req.get("cpu_arch", ["x86_64", "aarch64"])
    if not isinstance(cpu_arch, list) or not all(isinstance(a, str) for a in cpu_arch):
        errors.append(ValidationError(file, "[requirements].cpu_arch: array de strings"))

    # privileged
    priv = req.get("privileged", True)
    if not isinstance(priv, bool):
        errors.append(ValidationError(file, "[requirements].privileged: boolean"))

    # size_class
    size_cls = req.get("size_class", "auto")
    if size_cls not in VALID_SIZE_CLASSES:
        errors.append(ValidationError(file, f"[requirements].size_class: '{size_cls}' inválido. Válidos: {sorted(VALID_SIZE_CLASSES)}"))

    # network_required
    net = req.get("network_required", True)
    if not isinstance(net, bool):
        errors.append(ValidationError(file, "[requirements].network_required: boolean"))

    # python_min
    py_min = req.get("python_min", "")
    if py_min and not isinstance(py_min, str):
        errors.append(ValidationError(file, "[requirements].python_min: string"))

    return errors

def validate_profiles(data: dict, file: str) -> list[ValidationError]:
    errors = []
    profiles = data.get("profiles")
    if not profiles or not isinstance(profiles, dict):
        errors.append(ValidationError(file, "[profiles]: requerido, tabla"))
        return errors

    for key in ("low_end", "standard", "high_end"):
        val = profiles.get(key)
        if val is None:
            errors.append(ValidationError(file, f"[profiles].{key}: requerido"))
        elif val not in VALID_PROFILE_VALUES:
            errors.append(ValidationError(file, f"[profiles].{key}: '{val}' inválido. Válidos: {sorted(VALID_PROFILE_VALUES)}"))

    # No claves extra
    extra = set(profiles.keys()) - {"low_end", "standard", "high_end"}
    if extra:
        errors.append(ValidationError(file, f"[profiles]: claves extra no permitidas: {sorted(extra)}"))

    return errors

def validate_install(data: dict, file: str) -> list[ValidationError]:
    errors = []
    install = data.get("install")
    if not install or not isinstance(install, dict):
        errors.append(ValidationError(file, "[install]: requerido, tabla con al menos un método"))
        return errors

    methods_present = set(install.keys()) & VALID_INSTALL_METHODS
    if not methods_present:
        errors.append(ValidationError(file, f"[install]: debe tener al menos uno de {sorted(VALID_INSTALL_METHODS)}"))

    # Validar cada método presente
    for method in methods_present:
        mdata = install[method]
        if not isinstance(mdata, dict):
            errors.append(ValidationError(file, f"[install.{method}]: debe ser tabla"))
            continue

        if method == "native":
            # Al menos una familia con valor no-null
            families_present = set(mdata.keys()) & NATIVE_PKG_FAMILIES
            if not families_present:
                errors.append(ValidationError(file, "[install.native]: debe tener al menos una familia (arch, debian, fedora, void, opensuse, alpine, gentoo)"))
            for fam, pkg in mdata.items():
                if fam in NATIVE_PKG_FAMILIES:
                    if pkg is not None and not isinstance(pkg, str):
                        errors.append(ValidationError(file, f"[install.native].{fam}: string o null"))
                else:
                    errors.append(ValidationError(file, f"[install.native].{fam}: familia no reconocida"))

        elif method == "binary_release":
            # Campos requeridos
            for field in ("url_template", "version", "sha256"):
                if field not in mdata:
                    errors.append(ValidationError(file, f"[install.binary_release].{field}: requerido"))
            # sha256 debe ser tabla con al menos una entrada
            sha256 = mdata.get("sha256", {})
            if not isinstance(sha256, dict) or not sha256:
                errors.append(ValidationError(file, "[install.binary_release].sha256: tabla requerida con ≥1 entrada (arch -> hash)"))
            else:
                for arch, hash_val in sha256.items():
                    if not isinstance(hash_val, str):
                        errors.append(ValidationError(file, f"[install.binary_release].sha256.{arch}: string requerido"))
                    elif hash_val.upper() == "PENDING-VERIFICATION":
                        # Valor especial FASE 1: hash pendiente de pinnear real
                        # Se acepta como TOML válido; warning se reporta aparte
                        pass
                    elif len(hash_val) != 64 or not all(c in "0123456789abcdef" for c in hash_val.lower()):
                        errors.append(ValidationError(file, f"[install.binary_release].sha256.{arch}: hash hex de 64 chars requerido (o 'PENDING-VERIFICATION')"))
            # version formato semver
            ver = mdata.get("version", "")
            if ver and not SEMVER_REGEX.match(ver):
                errors.append(ValidationError(file, f"[install.binary_release].version: '{ver}' no es semver válido"))

        elif method == "git_clone":
            for field in ("url", "build_system", "binary_path"):
                if field not in mdata:
                    errors.append(ValidationError(file, f"[install.git_clone].{field}: requerido"))
            build_sys = mdata.get("build_system", "")
            if build_sys not in {"make", "cargo", "go", "cmake", "meson", "custom"}:
                errors.append(ValidationError(file, f"[install.git_clone].build_system: '{build_sys}' inválido"))

        elif method == "script_official":
            for field in ("url", "sha256"):
                if field not in mdata:
                    errors.append(ValidationError(file, f"[install.script_official].{field}: requerido"))
            sha = mdata.get("sha256", "")
            if sha and (not isinstance(sha, str) or len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha.lower())):
                errors.append(ValidationError(file, "[install.script_official].sha256: hash hex de 64 chars requerido"))
            if sha.upper() == "PENDING-VERIFICATION":
                pass  # warning

        elif method == "pipx":
            if "package" not in mdata:
                errors.append(ValidationError(file, "[install.pipx].package: requerido"))
            pkg = mdata.get("package", "")
            if pkg and not isinstance(pkg, str):
                errors.append(ValidationError(file, "[install.pipx].package: string"))

    return errors

def verify_section(data: dict, file: str) -> list[ValidationError]:
    errors = []
    verify = data.get("verify")
    if not verify or not isinstance(verify, dict):
        errors.append(ValidationError(file, "[verify]: requerido, tabla"))
        return errors

    for field in ("command", "pattern"):
        val = verify.get(field)
        if not val or not isinstance(val, str):
            errors.append(ValidationError(file, f"[verify].{field}: requerido, string no vacío"))

    exit_code = verify.get("exit_code", 0)
    if not isinstance(exit_code, int):
        errors.append(ValidationError(file, "[verify].exit_code: entero"))

    timeout = verify.get("timeout_sec", 10)
    if not isinstance(timeout, int) or timeout <= 0:
        errors.append(ValidationError(file, "[verify].timeout_sec: entero > 0"))

    return errors

def validate_ai_models(data: dict, file: str) -> list[ValidationError]:
    errors = []
    ai = data.get("ai_models")
    if ai is None:
        return errors  # opcional
    if not isinstance(ai, dict):
        errors.append(ValidationError(file, "[ai_models]: debe ser tabla"))
        return errors

    auto = ai.get("automatic", False)
    if not isinstance(auto, bool):
        errors.append(ValidationError(file, "[ai_models].automatic: boolean"))

    # Regla de proyecto: automatic NUNCA true por defecto
    if auto is True:
        errors.append(ValidationError(file, "[ai_models].automatic: MUST BE false (proyecto prohíbe descarga automática de modelos)"))

    models = ai.get("default_models", [])
    if models and not (isinstance(models, list) and all(isinstance(m, str) for m in models)):
        errors.append(ValidationError(file, "[ai_models].default_models: array de strings"))

    req_conf = ai.get("requires_confirmation", True)
    if not isinstance(req_conf, bool):
        errors.append(ValidationError(file, "[ai_models].requires_confirmation: boolean"))

    return errors

def validate_manifest_file(path: Path) -> list[ValidationError]:
    """Valida un archivo de manifiesto completo."""
    errors = []
    rel = path.relative_to(REPO_ROOT)
    data = parse_toml_file(path)

    # schema_version
    sv = data.get("schema_version")
    if sv != 1:
        errors.append(ValidationError(str(rel), f"schema_version: debe ser 1 (encontrado: {sv})"))

    # Secciones
    errors.extend(validate_tool_section(data, str(rel)))
    errors.extend(validate_requirements(data, str(rel)))
    errors.extend(validate_profiles(data, str(rel)))
    errors.extend(validate_install(data, str(rel)))
    errors.extend(verify_section(data, str(rel)))
    errors.extend(validate_ai_models(data, str(rel)))

    # Coherencia: name en [tool] debe coincidir con nombre de archivo (sin .toml)
    tool_name = data.get("tool", {}).get("name")
    file_stem = path.stem
    if tool_name and tool_name != file_stem:
        errors.append(ValidationError(str(rel), f"[tool].name ('{tool_name}') != nombre de archivo ('{file_stem}')"))

    return errors

# ── Validación de Docs ─────────────────────────────────────────────────────

def extract_toml_blocks(markdown_path: Path) -> list[tuple[str, int]]:
    """Extrae bloques ```toml ... ``` del markdown. Retorna (contenido, línea_inicio)."""
    content = markdown_path.read_text(encoding="utf-8")
    blocks = []
    pattern = re.compile(r"```toml\n(.*?)\n```", re.DOTALL)
    for match in pattern.finditer(content):
        block_content = match.group(1)
        line_no = content[:match.start()].count("\n") + 1
        blocks.append((block_content, line_no))
    return blocks

def validate_doc_toml_blocks() -> list[ValidationError]:
    errors = []
    if not MANIFESTS_DOC.exists():
        errors.append(ValidationError(str(MANIFESTS_DOC.relative_to(REPO_ROOT)), "Archivo no encontrado"))
        return errors

    blocks = extract_toml_blocks(MANIFESTS_DOC)
    for i, (block, line) in enumerate(blocks):
        try:
            parse_toml_string(block, f"{MANIFESTS_DOC.relative_to(REPO_ROOT)}:line{line}")
        except ValidationError as e:
            errors.append(e)
    return errors

def validate_cross_references() -> list[ValidationError]:
    """Verifica referencias entre docs (archivos mencionados existen)."""
    errors = []
    # Mapa de referencias esperadas: doc -> lista de archivos que debe mencionar/existir
    expected_refs = {
        "docs/ARCHITECTURE.md": [
            "docs/MANIFESTS.md",
            "docs/SECURITY.md",
            "docs/COMPATIBILITY.md",
            "docs/BOOTSTRAP.md",
        ],
        "docs/MANIFESTS.md": [
            "catalog/development/git.toml",
            "catalog/languages/python.toml",
            "catalog/ai/ollama.toml",
        ],
        "docs/SECURITY.md": [],
        "docs/COMPATIBILITY.md": [
            "catalog/development/git.toml",
            "catalog/languages/python.toml",
            "catalog/ai/ollama.toml",
        ],
        "docs/BOOTSTRAP.md": [],
    }

    for doc_path, refs in expected_refs.items():
        full_doc = REPO_ROOT / doc_path
        if not full_doc.exists():
            errors.append(ValidationError(doc_path, "Documento referenciado no existe"))
            continue
        content = full_doc.read_text(encoding="utf-8")
        for ref in refs:
            # Buscar referencia al archivo (ruta relativa o nombre)
            if ref not in content and Path(ref).name not in content:
                errors.append(ValidationError(doc_path, f"Referencia esperada no encontrada: {ref}"))

    return errors

# ── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    all_errors: list[ValidationError] = []
    warnings: list[str] = []

    print("🔍 Validando manifiestos en catalog/...")
    manifest_files = list(CATALOG_DIR.rglob("*.toml"))
    if not manifest_files:
        all_errors.append(ValidationError("catalog/", "No se encontraron manifiestos .toml"))

    for mf in manifest_files:
        try:
            errs = validate_manifest_file(mf)
            all_errors.extend(errs)
            # Warnings para placeholders
            data = parse_toml_file(mf)
            install = data.get("install", {})
            if "binary_release" in install:
                sha256 = install["binary_release"].get("sha256", {})
                for arch, h in sha256.items():
                    if h.upper() == "PENDING-VERIFICATION":
                        warnings.append(f"{mf.relative_to(REPO_ROOT)}: binary_release.sha256.{arch} = PENDING-VERIFICATION (método deshabilitado hasta pinnear hash real)")
            if "script_official" in install:
                sha = install["script_official"].get("sha256", "")
                if sha.upper() == "PENDING-VERIFICATION":
                    warnings.append(f"{mf.relative_to(REPO_ROOT)}: script_official.sha256 = PENDING-VERIFICATION (método deshabilitado hasta pinnear hash real)")
        except ValidationError as e:
            all_errors.append(e)

    print(f"  {len(manifest_files)} archivos, {len([e for e in all_errors if 'catalog' in e.file])} errores")

    print("🔍 Validando bloques TOML en docs/MANIFESTS.md...")
    doc_errors = validate_doc_toml_blocks()
    all_errors.extend(doc_errors)
    print(f"  {len(doc_errors)} errores")

    print("🔍 Validando referencias cruzadas...")
    ref_errors = validate_cross_references()
    all_errors.extend(ref_errors)
    print(f"  {len(ref_errors)} errores")

    # Reporte
    print("\n" + "=" * 60)
    if warnings:
        print("⚠️  WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
        print()

    if all_errors:
        print("❌ FALLOS DE VALIDACIÓN:")
        for e in all_errors:
            print(f"  - {e}")
        print(f"\nTotal: {len(all_errors)} errores, {len(warnings)} warnings")
        return 1
    else:
        print("✅ TODAS LAS VALIDACIONES PASARON")
        if warnings:
            print(f"({len(warnings)} warnings informativos)")
        return 0

if __name__ == "__main__":
    sys.exit(main())