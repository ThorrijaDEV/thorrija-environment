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

# Importar validador principal
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from thorrija.catalog.validator import ManifestValidator, ValidationResult

REPO_ROOT = Path(__file__).parent.parent
CATALOG_DIR = REPO_ROOT / "catalog"
MANIFESTS_DOC = REPO_ROOT / "docs" / "MANIFESTS.md"

VALID_CATEGORIES = {"languages", "development", "editors", "ai", "security", "system"}


def parse_toml_string(content: str, source: str) -> dict[str, Any]:
    try:
        return tomllib.loads(content)
    except Exception as e:
        from thorrija.catalog.validator import ValidationError
        raise ValidationError(source, f"TOML parse error: {e}")


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


def validate_doc_toml_blocks() -> list:
    """Valida bloques TOML en MANIFESTS.md."""
    errors = []
    if not MANIFESTS_DOC.exists():
        from thorrija.catalog.validator import ValidationError
        errors.append(ValidationError(str(MANIFESTS_DOC.relative_to(REPO_ROOT)), "Archivo no encontrado"))
        return errors

    blocks = extract_toml_blocks(MANIFESTS_DOC)
    for i, (block, line) in enumerate(blocks):
        try:
            parse_toml_string(block, f"{MANIFESTS_DOC.relative_to(REPO_ROOT)}:line{line}")
        except Exception as e:
            from thorrija.catalog.validator import ValidationError
            errors.append(ValidationError(str(MANIFESTS_DOC.relative_to(REPO_ROOT)), f"Bloque TOML línea {line}: {e}"))
    return errors


def validate_cross_references() -> list:
    """Verifica referencias entre docs (archivos mencionados existen)."""
    from thorrija.catalog.validator import ValidationError
    errors = []
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
            if ref not in content and Path(ref).name not in content:
                errors.append(ValidationError(doc_path, f"Referencia esperada no encontrada: {ref}"))

    return errors


def main() -> int:
    all_errors = []
    warnings = []

    print("🔍 Validando manifiestos en catalog/...")
    manifest_files = list(CATALOG_DIR.rglob("*.toml"))
    if not manifest_files:
        from thorrija.catalog.validator import ValidationError
        all_errors.append(ValidationError("catalog/", "No se encontraron manifiestos .toml"))

    validator = ManifestValidator()
    results = validator.validate_all(CATALOG_DIR)

    for result in results:
        if not result.valid:
            all_errors.extend([type('obj', (object,), {'file': result.file, 'message': err, 'path': ''})() for err in result.errors])
        for warn in result.warnings:
            warnings.append(warn)

    print(f"  {len(manifest_files)} archivos, {len([e for e in all_errors if 'catalog' in e.file])} errores")

    print("🔍 Validando bloques TOML en docs/MANIFESTS.md...")
    doc_errors = validate_doc_toml_blocks()
    all_errors.extend(doc_errors)
    print(f"  {len(doc_errors)} errores")

    print("🔍 Validando referencias cruzadas...")
    ref_errors = validate_cross_references()
    all_errors.extend(ref_errors)
    print(f"  {len(ref_errors)} errores")

    print("\n" + "=" * 60)
    if warnings:
        print("⚠️  WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
        print()

    if all_errors:
        print("❌ FALLOS DE VALIDACIÓN:")
        for e in all_errors:
            print(f"  - {e.file}{':' + e.path + ' ' if e.path else ' '}{e.message}")
        print(f"\nTotal: {len(all_errors)} errores, {len(warnings)} warnings")
        return 1
    else:
        print("✅ TODAS LAS VALIDACIONES PASARON")
        if warnings:
            print(f"({len(warnings)} warnings informativos)")
        return 0


if __name__ == "__main__":
    sys.exit(main())