#!/usr/bin/env python3
"""
Calcula hashes SHA-256 reales para binary_release en manifiestos.
Uso: python3 scripts/calculate_hashes.py [--dry-run] [--only NAME]
"""

from __future__ import annotations

import hashlib
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

CATALOG_DIR = Path(__file__).parent.parent / "catalog"

ARCH_MAP = {
    "x86_64": ["x86_64", "amd64"],
    "aarch64": ["aarch64", "arm64"],
}

def download_file(url: str, timeout: int = 30) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ThorrijaEnvironment/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        return None

def calculate_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def resolve_url_template(template: str, version: str, arch: str) -> Optional[str]:
    arch_variants = ARCH_MAP.get(arch, [arch])
    for variant in arch_variants:
        url = template.format(version=version, arch=variant)
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "ThorrijaEnvironment/0.1")
            with urllib.request.urlopen(req, timeout=10):
                return url
        except Exception:
            continue
    return template.format(version=version, arch=arch_variants[0])

def process_one_manifest(manifest_path: Path) -> List[tuple]:
    """Procesa un manifiesto y retorna lista de (arch, hash) calculados."""
    content = manifest_path.read_text(encoding="utf-8")
    
    match = re.search(r'\[install\.binary_release\]\n(.*?)(?:\n\[|\Z)', content, re.DOTALL)
    if not match:
        return []
    
    section = match.group(1)
    
    ver_match = re.search(r'version\s*=\s*"([^"]+)"', section)
    if not ver_match:
        return []
    version = ver_match.group(1)
    
    url_match = re.search(r'url_template\s*=\s*"([^"]+)"', section)
    if not url_match:
        return []
    url_template = url_match.group(1)
    
    sha256_match = re.search(r'sha256\s*=\s*\{([^}]+)\}', section, re.DOTALL)
    current_hashes = {}
    if sha256_match:
        for line in sha256_match.group(1).split(','):
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                current_hashes[k.strip()] = v.strip().strip('"')
    
    results = []
    for arch in ["x86_64", "aarch64"]:
        if arch in current_hashes and current_hashes[arch].upper() != "PENDING-VERIFICATION":
            continue
        
        url = resolve_url_template(url_template, version, arch)
        if not url:
            continue
            
        print(f"  Descargando {manifest_path.name} [{arch}]: {url}")
        data = download_file(url)
        if data:
            hash_val = hashlib.sha256(data).hexdigest()
            results.append((arch, hash_val))
    
    return results

def main():
    dry_run = "--dry-run" in sys.argv
    only_tool = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only_tool = sys.argv[idx + 1]
    
    if dry_run:
        print("=== MODO DRY-RUN ===")
    else:
        print("=== MODO ESCRITURA ===")
    
    manifests = list(Path(CATALOG_DIR).rglob("*.toml"))
    print(f"Encontrados {len(manifests)} manifiestos")
    
    targets = []
    for manifest_path in manifests:
        content = manifest_path.read_text(encoding="utf-8")
        if "PENDING-VERIFICATION" not in content:
            continue
        if only_tool and manifest_path.stem != only_tool:
            continue
        targets.append(manifest_path)
    
    print(f"Procesando {len(targets)} manifiestos con PENDING-VERIFICATION")
    
    total_updated = 0
    
    # Procesar en paralelo (máx 3 concurrentes para no saturar)
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_path = {executor.submit(process_one_manifest, p): p for p in targets}
        
        for future in as_completed(future_to_path):
            manifest_path = future_to_path[future]
            try:
                results = future.result()
                if results:
                    print(f"\n{manifest_path.name}:")
                    for arch, hash_val in results:
                        print(f"  {arch}: {hash_val}")
                    
                    if not dry_run:
                        # Actualizar archivo
                        content = manifest_path.read_text(encoding="utf-8")
                        for arch, hash_val in results:
                            old = f'{arch} = "PENDING-VERIFICATION"'
                            new = f'{arch} = "{hash_val}"'
                            content = content.replace(old, new)
                        manifest_path.write_text(content, encoding="utf-8")
                        total_updated += 1
                        print(f"  ✓ Actualizado")
            except Exception as e:
                print(f"  Error: {e}")
    
    print(f"\n=== Resumen ===")
    if dry_run:
        print("Dry-run completado. Ejecuta sin --dry-run para aplicar.")
    else:
        print(f"Manifiestos actualizados: {total_updated}")

if __name__ == "__main__":
    main()