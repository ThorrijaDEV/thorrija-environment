"""
Driver pipx: instala paquetes Python CLI via pipx.
"""

from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING

from ..engine import BaseDriver, DriverResult, driver_registry

if TYPE_CHECKING:
    from ..catalog import ToolManifest
    from ..detect import HardwareReport, OSReport
    from ..state import AuditLog, BackupManager, StateStore


class PipxDriver(BaseDriver):
    """Driver para instalación vía pipx."""

    name = "pipx"

    def is_available(
        self,
        manifest: "ToolManifest",
        os_report: "OSReport",
        hw: "HardwareReport",
    ) -> bool:
        try:
            subprocess.run(["pipx", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

        details = manifest.install_methods.get("pipx", {})
        return "package" in details

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

        details = manifest.install_methods.get("pipx", {})
        package = details.get("package", "")
        version = details.get("version", "")
        python_version = details.get("python", "")

        if not package:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="pipx: package requerido",
            )

        try:
            result = subprocess.run(
                ["pipx", "list", "--short"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if package in result.stdout:
                state_store.update_status(tool_name, "already_installed", method=self.name)
                audit_log.log_action(
                    tool=tool_name,
                    action="install_pipx",
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
        except Exception:
            pass

        if dry_run:
            state_store.update_status(tool_name, "pending", method=self.name)
            return DriverResult(
                success=True,
                tool_name=tool_name,
                method=self.name,
                duration_ms=int((time.time() - start) * 1000),
            )

        pkg_spec = f"{package}=={version}" if version else package
        cmd = ["pipx", "install", pkg_spec]
        if python_version:
            cmd.extend(["--python", python_version])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            duration = int((time.time() - start) * 1000)

            if result.returncode != 0:
                state_store.update_status(tool_name, "failed", method=self.name)
                audit_log.log_action(
                    tool=tool_name,
                    action="install_pipx",
                    result="failed",
                    method=self.name,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    duration_ms=duration,
                    error=result.stderr[-500:],
                )
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    error=result.stderr[-500:],
                    duration_ms=duration,
                )

            state_store.update_status(tool_name, "installed", method=self.name)
            audit_log.log_action(
                tool=tool_name,
                action="install_pipx",
                result="installed",
                method=self.name,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration,
                verify_command=manifest.verify_command,
                verify_pattern=manifest.verify_pattern,
            )
            return DriverResult(
                success=True,
                tool_name=tool_name,
                method=self.name,
                duration_ms=duration,
            )

        except subprocess.TimeoutExpired:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="pipx install timeout (300s)",
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error=f"Excepción: {e}",
                duration_ms=int((time.time() - start) * 1000),
            )


# Registrar driver
driver_registry.register(PipxDriver())