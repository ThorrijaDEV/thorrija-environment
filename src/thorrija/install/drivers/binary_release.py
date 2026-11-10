"""
Driver binary_release: descarga binarios de GitHub Releases con verificación SHA-256.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from ..engine import BaseDriver, DriverResult, driver_registry

if TYPE_CHECKING:
    from ..catalog import ToolManifest
    from ..detect import HardwareReport, OSReport
    from ..state import AuditLog, BackupManager, StateStore


ARCH_MAP = {
    "x86_64": ["x86_64", "amd64"],
    "aarch64": ["aarch64", "arm64"],
    "armv7": ["armv7", "armhf"],
    "riscv64": ["riscv64"],
}


class BinaryReleaseDriver(BaseDriver):
    """Driver para instalación vía binarios de releases."""

    name = "binary_release"

    def is_available(
        self,
        manifest: "ToolManifest",
        os_report: "OSReport",
        hw: "HardwareReport",
    ) -> bool:
        details = manifest.install_methods.get("binary_release", {})
        sha256 = details.get("sha256", {})

        # Requerir hash válido (no PENDING-VERIFICATION)
        arch = hw.architecture
        for mapped_arch in ARCH_MAP.get(arch, [arch]):
            hash_val = sha256.get(mapped_arch)
            if hash_val and hash_val.upper() != "PENDING-VERIFICATION":
                return True
        return False

    def _resolve_arch(self, hw_arch: str, sha256: dict) -> Optional[str]:
        """Resuelve arquitectura a clave en sha256."""
        for mapped in ARCH_MAP.get(hw_arch, [hw_arch]):
            if mapped in sha256:
                return mapped
        return None

    def _download_file(self, url: str, dest: Path) -> tuple[bool, str, str]:
        """Descarga archivo con urllib. Retorna (success, stdout, stderr)."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ThorrijaEnvironment/0.2"})
            with urllib.request.urlopen(req, timeout=60) as response, open(dest, "wb") as out:
                shutil.copyfileobj(response, out)
            return True, "", ""
        except Exception as e:
            return False, "", str(e)

    def _verify_hash(self, path: Path, expected: str) -> bool:
        """Verifica SHA-256 del archivo."""
        try:
            with open(path, "rb") as f:
                actual = hashlib.sha256(f.read()).hexdigest()
            return actual.lower() == expected.lower()
        except Exception:
            return False

    def _extract_archive(self, archive: Path, dest_dir: Path, strip: int = 1) -> List[str]:
        """Extrae archivo y retorna lista de archivos extraídos."""
        extracted = []
        try:
            if archive.suffix in (".tgz", ".tar.gz", ".tar"):
                import tarfile
                with tarfile.open(archive, "r:*") as tf:
                    members = tf.getmembers()
                    for member in members:
                        # Ajustar path con strip_components
                        parts = member.name.split("/")
                        if len(parts) > strip:
                            member.name = "/".join(parts[strip:])
                            tf.extract(member, dest_dir)
                            extracted.append(str(dest_dir / member.name))
            elif archive.suffix == ".zip":
                import zipfile
                with zipfile.ZipFile(archive, "r") as zf:
                    for member in zf.namelist():
                        parts = member.split("/")
                        if len(parts) > strip:
                            new_name = "/".join(parts[strip:])
                            zf.extract(member, dest_dir)
                            # Renombrar si strip > 0
                            old_path = dest_dir / member
                            new_path = dest_dir / new_name
                            if old_path != new_path and old_path.exists():
                                old_path.rename(new_path)
                            extracted.append(str(new_path))
        except Exception:
            pass
        return extracted

    def _find_binary(self, extract_dir: Path, binary_name: str) -> Optional[Path]:
        """Busca el binario en el directorio extraído."""
        # Búsqueda directa
        direct = extract_dir / binary_name
        if direct.exists():
            return direct

        # Búsqueda recursiva
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                if f == binary_name or f.endswith(f"/{binary_name}"):
                    return Path(root) / f
        return None

    def install(
        self,
        manifest: "ToolManifest",
        os_report: "OSReport",
        hw: "HardwareReport",
        audit_log: "AuditLog",
        backup_manager: "BackupManager",
        state_store: "StateStore",
        dry_run: bool = True,
    ) -> DriverResult:
        start = time.time()
        tool_name = manifest.name

        details = manifest.install_methods.get("binary_release", {})
        url_template = details.get("url_template", "")
        version = details.get("version", "")
        sha256_map = details.get("sha256", {})
        binary_name = details.get("binary_name", tool_name)
        install_to = details.get("install_to", "~/.local/bin")
        strip_components = details.get("strip_components", 1)

        if not url_template or not version:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="Configuración binary_release incompleta",
            )

        # Resolver arquitectura
        arch_key = self._resolve_arch(hw.architecture, sha256_map)
        if not arch_key:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error=f"Arquitectura {hw.architecture} no soportada en release",
            )

        expected_hash = sha256_map[arch_key]
        if expected_hash.upper() == "PENDING-VERIFICATION":
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="Hash no pinneado (PENDING-VERIFICATION) - método deshabilitado por seguridad",
            )

        # Construir URL
        url = url_template.format(version=version, arch=arch_key)
        install_dir = Path(install_to).expanduser()
        install_dir.mkdir(parents=True, exist_ok=True)
        binary_path = install_dir / binary_name

        # Verificar si ya existe y coincide hash
        if binary_path.exists() and self._verify_hash(binary_path, expected_hash):
            state_store.update_status(tool_name, "already_installed", method=self.name)
            audit_log.log_action(
                tool=tool_name,
                action="install_binary",
                result="already_installed",
                method=self.name,
                verify_command=manifest.verify_command,
                verify_pattern=manifest.verify_pattern,
            )
            return DriverResult(
                success=True,
                tool_name=tool_name,
                method=self.name,
                duration_ms=int((time.time() - start) * 1000),
            )

        if dry_run:
            state_store.update_status(tool_name, "pending", method=self.name)
            return DriverResult(
                success=True,
                tool_name=tool_name,
                method=self.name,
                duration_ms=int((time.time() - start) * 1000),
            )

        # Descargar a temp
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            archive_path = tmpdir_path / f"{tool_name}-{version}.tar.gz"

            # Descargar
            success, _, err = self._download_file(url, archive_path)
            if not success:
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error=f"Descarga fallida: {err}",
                    duration_ms=int((time.time() - start) * 1000),
                )

            # Verificar hash
            if not self._verify_hash(archive_path, expected_hash):
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error=f"Hash SHA-256 no coincide. Esperado: {expected_hash}",
                    duration_ms=int((time.time() - start) * 1000),
                )

            # Extraer
            extract_dir = tmpdir_path / "extracted"
            extract_dir.mkdir()
            self._extract_archive(archive_path, extract_dir, strip_components)

            # Encontrar binario
            binary = self._find_binary(extract_dir, binary_name)
            if not binary:
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error=f"Binario '{binary_name}' no encontrado en archivo",
                    duration_ms=int((time.time() - start) * 1000),
                )

            # Instalar (copiar a destino)
            try:
                shutil.copy2(binary, binary_path)
                binary_path.chmod(0o755)
            except Exception as e:
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error=f"Error copiando binario: {e}",
                    duration_ms=int((time.time() - start) * 1000),
                )

        # Verificar instalación final
        if binary_path.exists() and self._verify_hash(binary_path, expected_hash):
            state_store.update_status(tool_name, "installed", method=self.name)
            audit_log.log_action(
                tool=tool_name,
                action="install_binary",
                result="installed",
                method=self.name,
                files_changed=[str(binary_path)],
                verify_command=manifest.verify_command,
                verify_pattern=manifest.verify_pattern,
            )
            return DriverResult(
                success=True,
                tool_name=tool_name,
                method=self.name,
                files_changed=[str(binary_path)],
                duration_ms=int((time.time() - start) * 1000),
            )

        return DriverResult(
            success=False,
            tool_name=tool_name,
            method=self.name,
            error="Instalación completada pero verificación final falló",
            duration_ms=int((time.time() - start) * 1000),
        )


# Registrar driver
driver_registry.register(BinaryReleaseDriver())