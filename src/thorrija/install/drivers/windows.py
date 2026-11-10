"""
Drivers de instalación para Windows: winget, chocolatey, scoop.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import List, Optional, TYPE_CHECKING

from ..engine import BaseDriver, DriverResult, driver_registry

if TYPE_CHECKING:
    from ..catalog import ToolManifest
    from ..detect import HardwareReport
    from ..detect.windows import WindowsOSReport
    from ..state import AuditLog, BackupManager, StateStore


class WingetDriver(BaseDriver):
    """Driver para Windows Package Manager (winget)."""

    name = "winget"

    def is_available(
        self,
        manifest: "ToolManifest",
        os_report: "WindowsOSReport",
        hw: "HardwareReport",
    ) -> bool:
        if "winget" not in os_report.package_managers:
            return False
        details = manifest.install_methods.get("winget", {})
        return "id" in details or "name" in details

    def _get_package_id(self, manifest: "ToolManifest") -> Optional[str]:
        details = manifest.install_methods.get("winget", {})
        return details.get("id") or details.get("name")

    def install(
        self,
        manifest: "ToolManifest",
        os_report: "WindowsOSReport",
        hw: "HardwareReport",
        audit_log: "AuditLog",
        backup_manager: "BackupManager",
        state_store: "StateStore",
        dry_run: bool = True,
    ) -> DriverResult:
        start = time.time()
        tool_name = manifest.name

        package_id = self._get_package_id(manifest)
        if not package_id:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="winget: 'id' o 'name' requerido en manifest",
            )

        # Verificar si ya está instalado
        if self._is_installed(package_id):
            state_store.update_status(tool_name, "already_installed", method=self.name)
            audit_log.log_action(
                tool=tool_name,
                action="install_winget",
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

        # Instalar via winget
        cmd = ["winget", "install", "--id", package_id, "--silent", "--accept-source-agreements", "--accept-package-agreements"]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            duration = int((time.time() - start) * 1000)

            if result.returncode != 0:
                error_msg = result.stderr[-500:] if result.stderr else "Error desconocido"
                state_store.update_status(tool_name, "failed", method=self.name)
                audit_log.log_action(
                    tool=tool_name,
                    action="install_winget",
                    result="failed",
                    method=self.name,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    duration_ms=duration,
                    error=error_msg,
                )
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    stderr=result.stderr,
                    error=error_msg,
                    duration_ms=duration,
                )

            if self._is_installed(package_id):
                state_store.update_status(tool_name, "installed", method=self.name)
                audit_log.log_action(
                    tool=tool_name,
                    action="install_winget",
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
            else:
                state_store.update_status(tool_name, "failed", method=self.name)
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error="Paquete instalado pero no detectado",
                    duration_ms=duration,
                )

        except subprocess.TimeoutExpired:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="Timeout instalación winget (300s)",
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

    def _is_installed(self, package_id: str) -> bool:
        try:
            result = subprocess.run(
                ["winget", "list", "--id", package_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0 and package_id.lower() in result.stdout.lower()
        except Exception:
            return False


class ChocolateyDriver(BaseDriver):
    """Driver para Chocolatey."""

    name = "chocolatey"

    def is_available(
        self,
        manifest: "ToolManifest",
        os_report: "WindowsOSReport",
        hw: "HardwareReport",
    ) -> bool:
        if "chocolatey" not in os_report.package_managers:
            return False
        details = manifest.install_methods.get("chocolatey", {})
        return "package" in details

    def _get_package_name(self, manifest: "ToolManifest") -> Optional[str]:
        details = manifest.install_methods.get("chocolatey", {})
        return details.get("package")

    def _is_installed(self, package: str) -> bool:
        try:
            result = subprocess.run(
                ["choco", "list", "--local-only", "--exact", package],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0 and package.lower() in result.stdout.lower()
        except Exception:
            return False

    def install(
        self,
        manifest: "ToolManifest",
        os_report: "WindowsOSReport",
        hw: "HardwareReport",
        audit_log: "AuditLog",
        backup_manager: "BackupManager",
        state_store: "StateStore",
        dry_run: bool = True,
    ) -> DriverResult:
        start = time.time()
        tool_name = manifest.name

        package = self._get_package_name(manifest)
        if not package:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="chocolatey: 'package' requerido",
            )

        if self._is_installed(package):
            state_store.update_status(tool_name, "already_installed", method=self.name)
            audit_log.log_action(
                tool=tool_name,
                action="install_chocolatey",
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

        cmd = ["choco", "install", package, "-y", "--no-progress"]

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
                    action="install_chocolatey",
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
                    stderr=result.stderr,
                    error=result.stderr[-500:],
                    duration_ms=duration,
                )

            if self._is_installed(package):
                state_store.update_status(tool_name, "installed", method=self.name)
                audit_log.log_action(
                    tool=tool_name,
                    action="install_chocolatey",
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
            else:
                state_store.update_status(tool_name, "failed", method=self.name)
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error="Paquete instalado pero no detectado",
                    duration_ms=duration,
                )

        except subprocess.TimeoutExpired:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="Timeout chocolatey (300s)",
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


class ScoopDriver(BaseDriver):
    """Driver para Scoop."""

    name = "scoop"

    def is_available(
        self,
        manifest: "ToolManifest",
        os_report: "WindowsOSReport",
        hw: "HardwareReport",
    ) -> bool:
        if "scoop" not in os_report.package_managers:
            return False
        details = manifest.install_methods.get("scoop", {})
        return "package" in details

    def _get_package_name(self, manifest: "ToolManifest") -> Optional[str]:
        details = manifest.install_methods.get("scoop", {})
        return details.get("package")

    def _is_installed(self, package: str) -> bool:
        try:
            result = subprocess.run(
                ["scoop", "list", "--local-only"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0 and package.lower() in result.stdout.lower()
        except Exception:
            return False

    def install(
        self,
        manifest: "ToolManifest",
        os_report: "WindowsOSReport",
        hw: "HardwareReport",
        audit_log: "AuditLog",
        backup_manager: "BackupManager",
        state_store: "StateStore",
        dry_run: bool = True,
    ) -> DriverResult:
        start = time.time()
        tool_name = manifest.name

        package = self._get_package_name(manifest)
        if not package:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="scoop: 'package' requerido",
            )

        if self._is_installed(package):
            state_store.update_status(tool_name, "already_installed", method=self.name)
            audit_log.log_action(
                tool=tool_name,
                action="install_scoop",
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

        cmd = ["scoop", "install", package]

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
                    action="install_scoop",
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
                action="install_scoop",
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
                error="Timeout scoop (300s)",
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


# Registrar drivers
driver_registry.register(WingetDriver())
driver_registry.register(ChocolateyDriver())
driver_registry.register(ScoopDriver())