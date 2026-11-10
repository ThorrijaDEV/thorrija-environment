"""
Driver script_official: ejecuta script instalador oficial con hash verificado.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

from ..engine import BaseDriver, DriverResult, driver_registry

if TYPE_CHECKING:
    from ..catalog import ToolManifest
    from ..detect import HardwareReport, OSReport
    from ..state import AuditLog, BackupManager, StateStore


class ScriptOfficialDriver(BaseDriver):
    """Driver para scripts instaladores oficiales."""

    name = "script_official"

    def is_available(
        self,
        manifest: "ToolManifest",
        os_report: "OSReport",
        hw: "HardwareReport",
    ) -> bool:
        details = manifest.install_methods.get("script_official", {})
        sha256 = details.get("sha256", "")
        return bool(sha256 and sha256.upper() != "PENDING-VERIFICATION")

    def _download_script(self, url: str, dest: Path) -> tuple[bool, str]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ThorrijaEnvironment/0.2"})
            with urllib.request.urlopen(req, timeout=30) as response, open(dest, "wb") as out:
                out.write(response.read())
            return True, ""
        except Exception as e:
            return False, str(e)

    def _verify_hash(self, path: Path, expected: str) -> bool:
        try:
            with open(path, "rb") as f:
                actual = hashlib.sha256(f.read()).hexdigest()
            return actual.lower() == expected.lower()
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

        details = manifest.install_methods.get("script_official", {})
        url = details.get("url", "")
        expected_hash = details.get("sha256", "")
        args = details.get("args", [])
        env_vars = details.get("env", {})

        if not url or not expected_hash:
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="Configuración script_official incompleta (url, sha256 requeridos)",
            )

        if expected_hash.upper() == "PENDING-VERIFICATION":
            return DriverResult(
                success=False,
                tool_name=tool_name,
                method=self.name,
                error="Hash no pinneado (PENDING-VERIFICATION) - método deshabilitado por seguridad",
            )

        if dry_run:
            state_store.update_status(tool_name, "pending", method=self.name)
            return DriverResult(
                success=True,
                tool_name=tool_name,
                method=self.name,
                duration_ms=int((time.time() - start) * 1000),
            )

        # Descargar y verificar
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "install.sh"

            success, err = self._download_script(url, script_path)
            if not success:
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error=f"Descarga fallida: {err}",
                    duration_ms=int((time.time() - start) * 1000),
                )

            if not self._verify_hash(script_path, expected_hash):
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error=f"Hash SHA-256 no coincide. Esperado: {expected_hash}",
                    duration_ms=int((time.time() - start) * 1000),
                )

            # Ejecutar script
            script_path.chmod(0o755)
            cmd = [str(script_path)] + args

            env = os.environ.copy()
            env.update(env_vars)

            try:
                result = subprocess.run(
                    cmd,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                duration = int((time.time() - start) * 1000)

                if result.returncode != 0:
                    state_store.update_status(tool_name, "failed", method=self.name)
                    audit_log.log_action(
                        tool=tool_name,
                        action="install_script",
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
                    action="install_script",
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
                    stdout=result.stdout,
                    stderr=result.stderr,
                    duration_ms=duration,
                )

            except subprocess.TimeoutExpired:
                return DriverResult(
                    success=False,
                    tool_name=tool_name,
                    method=self.name,
                    error="Script timeout (300s)",
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
driver_registry.register(ScriptOfficialDriver())