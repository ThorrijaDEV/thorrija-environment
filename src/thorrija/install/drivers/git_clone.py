"""
Driver git_clone: clona repositorio y compila.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from ..engine import BaseDriver, DriverResult, driver_registry

if TYPE_CHECKING:
    from ..catalog import ToolManifest
    from ..detect import HardwareReport, OSReport
    from ..state import AuditLog, BackupManager, StateStore


BUILD_COMMANDS = {
    "make": ["make", "-j$(nproc)"],
    "cargo": ["cargo", "build", "--release"],
    "go": ["go", "build"],
    "cmake": ["cmake", "-B", "build", "-DCMAKE_BUILD_TYPE=Release", "&&", "cmake", "--build", "build", "--parallel"],
    "meson": ["meson", "setup", "build", "--buildtype=release", "&&", "ninja", "-C", "build"],
    "custom": [],  # Se usa build_args
}


class GitCloneDriver(BaseDriver):
    """Driver para instalación vía git clone + build."""

    name = "git_clone"

    def is_available(
        self,
        manifest: "ToolManifest",
        os_report: "OSReport",
        hw: "HardwareReport",
    ) -> bool:
        details = manifest.install_methods.get("git_clone", {})
        url = details.get("url", "")
        build_system = details.get("build_system", "")
        return bool(url and build_system)

    def _get_build_cmd(self, build_system: str, build_args: List[str]) -> List[str]:
        if build_system in BUILD_COMMANDS:
            base = BUILD_COMMANDS[build_system]
            if build_system == "custom":
                return build_args if build_args else ["echo", "No build command specified"]
            return base + build_args
        return build_args if build_args else ["echo", "Unknown build system"]

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

        details = manifest.install_methods.get("git_clone", {})
        url = details.get("url", "")
        branch = details.get("branch", "main")
        build_system = details.get("build_system", "")
        build_args = details.get("build_args", [])
        binary_path_rel = details.get("binary_path", "")
        install_to = details.get("install_to", "~/.local/bin")

        if not url or not build_system or not binary_path_rel:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="Configuración git_clone incompleta (url, build_system, binary_path requeridos)",
            )

        install_dir = Path(install_to).expanduser()
        install_dir.mkdir(parents=True, exist_ok=True)
        binary_dest = install_dir / Path(binary_path_rel).name

        # Verificar si ya existe y coincide commit (opcional)
        if binary_dest.exists():
            state_store.update_status(tool_name, "already_installed", method=self.name)
            audit_log.log_action(
                tool=tool_name,
                action="install_git",
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

        # Clonar y compilar en temp
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_dir = tmpdir_path / "repo"

            # Git clone
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", "--branch", branch, url, str(repo_dir)],
                    check=True,
                    capture_output=True,
                    timeout=120,
                )
            except subprocess.CalledProcessError as e:
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error=f"Git clone falló: {e.stderr.decode() if e.stderr else e}",
                    duration_ms=int((time.time() - start) * 1000),
                )
            except subprocess.TimeoutExpired:
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error="Git clone timeout (120s)",
                    duration_ms=int((time.time() - start) * 1000),
                )

            # Build
            build_cmd = self._get_build_cmd(build_system, build_args)
            try:
                # Ejecutar en directorio del repo
                cmd_str = " ".join(build_cmd)
                result = subprocess.run(
                    cmd_str,
                    shell=True,
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10 min para build
                )
                if result.returncode != 0:
                    return DriverResult(
                        success=False,
                        tool_name=tool_name,
                        method=self.name,
                        error=f"Build falló: {result.stderr[-500:]}",
                        stdout=result.stdout,
                        stderr=result.stderr,
                        duration_ms=int((time.time() - start) * 1000),
                    )
            except subprocess.TimeoutExpired:
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error="Build timeout (600s)",
                    duration_ms=int((time.time() - start) * 1000),
                )
            except Exception as e:
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error=f"Excepción en build: {e}",
                    duration_ms=int((time.time() - start) * 1000),
                )

            # Encontrar binario
            binary_src = repo_dir / binary_path_rel
            if not binary_src.exists():
                # Buscar recursivamente
                found = None
                for root, dirs, files in os.walk(repo_dir):
                    for f in files:
                        if f == Path(binary_path_rel).name:
                            found = Path(root) / f
                            break
                    if found:
                        break
                binary_src = found

            if not binary_src or not binary_src.exists():
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error=f"Binario no encontrado tras build: {binary_path_rel}",
                    duration_ms=int((time.time() - start) * 1000),
                )

            # Copiar a destino
            try:
                shutil.copy2(binary_src, binary_dest)
                binary_dest.chmod(0o755)
            except Exception as e:
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error=f"Error copiando binario: {e}",
                    duration_ms=int((time.time() - start) * 1000),
                )

        # Verificar
        if binary_dest.exists():
            state_store.update_status(tool_name, "installed", method=self.name)
            audit_log.log_action(
                tool=tool_name,
                action="install_git",
                result="installed",
                method=self.name,
                files_changed=[str(binary_dest)],
                verify_command=manifest.verify_command,
                verify_pattern=manifest.verify_pattern,
            )
            return DriverResult(
                success=True,
                tool_name=tool_name,
                method=self.name,
                files_changed=[str(binary_dest)],
                duration_ms=int((time.time() - start) * 1000),
            )

        return DriverResult(
            success=False,
            tool_name=tool_name,
            method=self.name,
            error="Binario copiado pero no verificado",
            duration_ms=int((time.time() - start) * 1000),
        )


# Registrar driver
driver_registry.register(GitCloneDriver())