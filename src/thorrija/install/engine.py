"""
Motor de instalación y registro de drivers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, TYPE_CHECKING
import subprocess
import time
import hashlib

if TYPE_CHECKING:
    from ..plan import ToolPlanEntry
    from ..catalog import ToolManifest
    from ..detect import HardwareReport, OSReport
    from ..state import AuditLog, BackupManager, StateStore


@dataclass
class DriverResult:
    """Resultado de ejecución de un driver."""
    success: bool
    tool_name: str
    method: str
    version: str = ""
    files_changed: List[str] = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    duration_ms: int = 0

    def __post_init__(self):
        if self.files_changed is None:
            self.files_changed = []


class BaseDriver(ABC):
    """Driver base para métodos de instalación."""

    name: str = "base"

    @abstractmethod
    def is_available(self, manifest: "ToolManifest", os_report: "OSReport", hw: "HardwareReport") -> bool:
        """Verifica si el driver puede usarse para esta herramienta en este SO/HW."""
        pass

    @abstractmethod
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
        """Ejecuta la instalación."""
        pass

    def verify(self, manifest: "ToolManifest") -> tuple[bool, str]:
        """Ejecuta verificación post-instalación."""
        if not manifest.verify_command:
            return False, "Sin comando de verificación"

        try:
            start = time.time()
            result = subprocess.run(
                manifest.verify_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=manifest.verify_timeout_sec,
            )
            duration = int((time.time() - start) * 1000)
            output = result.stdout + result.stderr

            if result.returncode != manifest.verify_exit_code:
                return False, f"Exit code {result.returncode} != {manifest.verify_exit_code}"

            import re
            if manifest.verify_pattern and not re.search(manifest.verify_pattern, output):
                return False, f"Patrón '{manifest.verify_pattern}' no encontrado en salida"

            version = ""
            if manifest.version_extract:
                match = re.search(manifest.version_extract, output)
                if match:
                    version = match.group(1)

            return True, version

        except subprocess.TimeoutExpired:
            return False, f"Timeout ({manifest.verify_timeout_sec}s)"
        except Exception as e:
            return False, f"Error verificación: {e}"


class DriverRegistry:
    """Registro de drivers disponibles."""

    def __init__(self):
        self._drivers: Dict[str, BaseDriver] = {}

    def register(self, driver: BaseDriver) -> None:
        self._drivers[driver.name] = driver

    def get(self, name: str) -> Optional[BaseDriver]:
        return self._drivers.get(name)

    def get_all(self) -> List[BaseDriver]:
        return list(self._drivers.values())

    def select_best(
        self,
        manifest: "ToolManifest",
        os_report: "OSReport",
        hw: "HardwareReport",
    ) -> Optional[BaseDriver]:
        """Selecciona mejor driver disponible para el manifiesto."""
        priority = ["native", "binary_release", "git_clone", "script_official", "pipx"]
        for method in priority:
            if method in manifest.install_methods:
                driver = self.get(method)
                if driver and driver.is_available(manifest, os_report, hw):
                    return driver
        return None


# Instancia global
driver_registry = DriverRegistry()


def register_builtin_drivers() -> None:
    """Registra drivers built-in (se importa para activar)."""
    from .drivers import native, binary_release, git_clone, script_official, pipx  # noqa: F401


class InstallationEngine:
    """Orquesta la ejecución de un plan de instalación."""

    def __init__(
        self,
        driver_registry: DriverRegistry,
        audit_log: "AuditLog",
        backup_manager: "BackupManager",
        state_store: "StateStore",
    ):
        self.driver_registry = driver_registry
        self.audit_log = audit_log
        self.backup_manager = backup_manager
        self.state_store = state_store

    def execute_plan(
        self,
        plan: "InstallationPlan",
        continue_on_error: bool = False,
    ) -> List[DriverResult]:
        """Ejecuta todas las entradas del plan en orden."""
        from ..plan import InstallationPlan
        from ..state import AuditLog, BackupManager, StateStore

        results = []

        for entry in plan.entries:
            if entry.status not in ("will_install", "optional"):
                continue

            manifest = entry.tool

            driver = self.driver_registry.select_best(
                manifest, plan.os_report, plan.hw_report
            )

            if not driver:
                result = DriverResult(
                    success=False,
                    tool_name=manifest.name,
                    method=entry.method,
                    error=f"Sin driver disponible para método '{entry.method}'",
                )
                results.append(result)
                self._log_failed(manifest, entry.method, result.error)
                if not continue_on_error:
                    break
                continue

            result = driver.install(
                manifest=manifest,
                os_report=plan.os_report,
                hw=plan.hw_report,
                audit_log=self.audit_log,
                backup_manager=self.backup_manager,
                state_store=self.state_store,
                dry_run=plan.dry_run,
            )
            results.append(result)

            if not result.success:
                if not continue_on_error:
                    break

        return results

    def _log_failed(self, manifest: "ToolManifest", method: str, error: str) -> None:
        self.audit_log.log_action(
            tool=manifest.name,
            action=f"install_{method}",
            result="failed",
            method=method,
            error=error,
            verify_command=manifest.verify_command,
            verify_pattern=manifest.verify_pattern,
        )