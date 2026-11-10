#!/usr/bin/env python3
"""
Calcula hashes SHA-256 reales para binary_release en manifiestos.
Uso: python3 scripts/calculate_hashes.py [--dry-run]
"""

from __future__ import annotations

import hashlib
import re
import sys
import urllib.request
from pathlib import Path
from typing import Dict, Optional

CATALOG_DIR = Path(__file__).parent.parent / "catalog"

ARCH_MAP = {
    "x86_64": ["x86_64", "amd64"],
    "aarch64": ["aarch64", "arm64"],
}

def download_file(url: str) -> Optional[bytes]:
    """Descarga archivo y retorna bytes."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ThorrijaEnvironment/0.1"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except Exception as e:
        print(f"  Error descargando {url}: {e}")
        return None

def calculate_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def resolve_url_template(template: str, version: str, arch: str) -> str:
    """Resuelve plantilla con version y arch."""
    # Mapear arch a variantes comunes
    arch_variants = ARCH_MAP.get(arch, [arch])
    for variant in arch_variants:
        url = template.format(version=version, arch=variant)
        # Probar si existe (HEAD request)
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "ThorrijaEnvironment/0.1")
            with urllib.request.urlopen(req, timeout=10):
                return url
        except Exception:
            continue
    # Fallback: primera variante
    return template.format(version=version, arch=arch_variants[0])

def process_manifest(manifest_path: Path, dry_run: bool = True) -> Dict[str, str]:
    """Procesa un manifiesto y retorna hashes calculados."""
    content = manifest_path.read_text(encoding="utf-8")
    
    # Extraer binary_release section
    match = re.search(r'\[install\.binary_release\]\n(.*?)(?:\n\[|\Z)', content, re.DOTALL)
    if not match:
        return {}
    
    section = match.group(1)
    
    # Extraer version
    ver_match = re.search(r'version\s*=\s*"([^"]+)"', section)
    if not ver_match:
        return {}
    version = ver_match.group(1)
    
    # Extraer url_template
    url_match = re.search(r'url_template\s*=\s*"([^"]+)"', section)
    if not url_match:
        return {}
    url_template = url_match.group(1)
    
    # Extraer sha256 actual
    sha256_match = re.search(r'sha256\s*=\s*\{([^}]+)\}', section, re.DOTALL)
    current_hashes = {}
    if sha256_match:
        for line in sha256_match.group(1).split(','):
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                current_hashes[k.strip()] = v.strip().strip('"')
    
    new_hashes = {}
    for arch in ["x86_64", "aarch64"]:
        if arch in current_hashes and current_hashes[arch].upper() != "PENDING-VERIFICATION":
            print(f"  {arch}: ya tiene hash real, saltando")
            new_hashes[arch] = current_hashes[arch]
            continue
        
        url = resolve_url_template(url_template, version, arch)
        print(f"  Descargando {arch}: {url}")
        data = download_file(url)
        if data:
            hash_val = calculate_sha256(data)
            print(f"  {arch}: {hash_val}")
            new_hashes[arch] = hash_val
        else:
            print(f"  {arch}: FALLÓ descarga")
            if arch in current_hashes:
                new_hashes[arch] = current_hashes[arch]
    
    if not dry_run and new_hashes:
        # Actualizar archivo
        new_sha256_str = ", ".join(f'{k} = "{v}"' for k, v in new_hashes.items())
        new_section = re.sub(
            r'sha256\s*=\s*\{[^}]+\}',
            f'sha256 = {{ {new_sha256_str} }}',
            section
        )
        new_content = content.replace(match.group(0), f"[install.binary_release]\n{new_section}")
        manifest_path.write_text(new_content, encoding="utf-8")
        print(f"  ✓ Actualizado {manifest_path}")
    
    return new_hashes

def main():
    dry_run = "--dry-run" in sys.argv
    
    if dry_run:
        print("=== MODO DRY-RUN (no modifica archivos) ===")
    else:
        print("=== MODO ESCRITURA (modifica manifiestos) ===")
    
    manifests = list(Path(CATALOG_DIR).rglob("*.toml"))
    print(f"Encontrados {len(manifests)} manifiestos")
    
    total_updated = 0
    for manifest_path in manifests:
        content = manifest_path.read_text(encoding="utf-8")
        if "PENDING-VERIFICATION" not in content:
            continue
        
        print(f"\nProcesando: {manifest_path.relative_to(Path.cwd())}")
        hashes = process_manifest(manifest_path, dry_run)
        if hashes and not dry_run:
            total_updated += 1
    
    print(f"\n=== Resumen ===")
    if dry_run:
        print("Dry-run completado. Ejecuta sin --dry-run para aplicar cambios.")
    else:
        print(f"Manifiestos actualizados: {total_updated}")

if __name__ == "__main__":
    main()