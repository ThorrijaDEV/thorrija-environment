"""
Driver nativo: gestores de paquetes del sistema (pacman, apt, dnf, xbps, zypper, apk, emerge).
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import List, Optional, TYPE_CHECKING

from ..engine import BaseDriver, DriverResult, driver_registry

if TYPE_CHECKING:
    from ..catalog import ToolManifest
    from ..detect import HardwareReport, OSReport
    from ..state import AuditLog, BackupManager, StateStore


# Comandos por gestor
PKG_COMMANDS = {
    "pacman": {
        "install": "pacman -S --needed --noconfirm",
        "check": "pacman -Q",
    },
    "apt": {
        "install": "apt-get update && apt-get install -y",
        "check": "dpkg -l",
    },
    "dnf": {
        "install": "dnf install -y",
        "check": "rpm -q",
    },
    "xbps": {
        "install": "xbps-install -Sy",
        "check": "xbps-query -l",
    },
    "zypper": {
        "install": "zypper --non-interactive install",
        "check": "rpm -q",
    },
    "apk": {
        "install": "apk add",
        "check": "apk info -e",
    },
    "emerge": {
        "install": "emerge --quiet",
        "check": "equery list",
    },
}


class NativeDriver(BaseDriver):
    """Driver para instalación vía gestor de paquetes nativo."""

    name = "native"

    def is_available(
        self,
        manifest: "ToolManifest",
        os_report: "OSReport",
        hw: "HardwareReport",
    ) -> bool:
        # Verificar que hay paquete para la familia del SO
        native_data = manifest.install_methods.get("native", {})
        for family in os_report.package_families:
            pkg = native_data.get(family)
            if pkg is not None and pkg != "":
                return True
        return False

    def _get_package_name(self, manifest: "ToolManifest", os_report: "OSReport") -> Optional[str]:
        native_data = manifest.install_methods.get("native", {})
        for family in os_report.package_families:
            pkg = native_data.get(family)
            if pkg is not None and pkg != "":
                return pkg
        return None

    def _get_pkg_manager(self, os_report: "OSReport") -> Optional[str]:
        pm = os_report.package_manager
        return pm if pm in PKG_COMMANDS else None

    def _is_installed(self, pkg_manager: str, package: str) -> bool:
        """Verifica si paquete ya está instalado."""
        check_cmd = PKG_COMMANDS[pkg_manager]["check"]
        try:
            result = subprocess.run(
                f"{check_cmd} {package}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

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

        pkg_manager = self._get_pkg_manager(os_report)
        if not pkg_manager:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error=f"Gestor de paquetes no soportado: {os_report.package_manager}",
            )

        package = self._get_package_name(manifest, os_report)
        if not package:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error=f"Sin paquete definido para {os_report.id}",
            )

        # Verificar si ya está instalado
        if self._is_installed(pkg_manager, package):
            state_store.update_status(tool_name, "already_installed", method=self.name)
            audit_log.log_action(
                tool=tool_name,
                action="install_native",
                result="already_installed",
                method=self.name,
                verify_command=manifest.verify_command,
                verify_pattern=manifest.verify_pattern,
            )
            return DriverResult(
                success=True,
                tool_name=tool_name,
                method="already_installed",
                version="",
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

        # Instalar
        install_cmd = PKG_COMMANDS[pkg_manager]["install"]
        sudo_password = os.environ.get("THORRIJA_SUDO_PASSWORD")
        cmd = f"sudo -S {install_cmd} {package}"

        try:
            # Usar input para pasar password a sudo -S (más seguro que pipe en shell)
            sudo_input = (sudo_password + "\n") if sudo_password else "\n"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
                input=sudo_input,
            )
            duration = int((time.time() - start) * 1000)

            if result.returncode != 0:
                error_msg = result.stderr[-500:] if result.stderr else "Error desconocido"
                state_store.update_status(tool_name, "failed", method=self.name)
                audit_log.log_action(
                    tool=tool_name,
                    action="install_native",
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

            # Verificar instalación
            if self._is_installed(pkg_manager, package):
                state_store.update_status(tool_name, "installed", method=self.name)
                audit_log.log_action(
                    tool=tool_name,
                    action="install_native",
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
                    error="Paquete instalado pero no detectado como instalado",
                    duration_ms=duration,
                )

        except subprocess.TimeoutExpired:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="Timeout instalación (300s)",
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
driver_registry.register(NativeDriver())