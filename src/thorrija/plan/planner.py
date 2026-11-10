"""
Planificador de instalaciones: genera planes legibles y ejecutables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum

from ..catalog import ToolManifest
from ..detect import HardwareReport, OSReport


class CompatibilityClass(Enum):
    """Clase de compatibilidad de una herramienta para el HW/SO actual."""
    COMPATIBLE = "compatible"      # Instalable, pero puede no ejecutar bien
    RECOMMENDED = "recommended"    # Instalable y ejecutable con recursos adecuados
    OPTIMAL = "optimal"            # Recursos sobrados, GPU si aplica
    INCOMPATIBLE = "incompatible"  # No instalable o no viable


@dataclass(frozen=True)
class ToolPlanEntry:
    """Entrada individual en el plan de instalación."""
    tool: ToolManifest
    compatibility: CompatibilityClass
    method: str                    # native, binary_release, git_clone, script_official, pipx
    method_details: Dict[str, Any]
    estimated_download_mb: int
    estimated_disk_mb: int
    requires_sudo: bool
    status: str                    # pending, already_installed, will_install
    warnings: List[str] = field(default_factory=list)
    incompatibility_reasons: List[str] = field(default_factory=list)


@dataclass
class InstallationPlan:
    """Plan completo de instalación."""
    profile: str
    hw_report: HardwareReport
    os_report: OSReport
    entries: List[ToolPlanEntry] = field(default_factory=list)
    total_download_mb: int = 0
    total_disk_mb: int = 0
    requires_sudo: bool = False
    sudo_operations: List[str] = field(default_factory=list)
    dry_run: bool = True
    generated_at: str = ""

    def add_entry(self, entry: ToolPlanEntry) -> None:
        self.entries.append(entry)
        self.total_download_mb += entry.estimated_download_mb
        self.total_disk_mb += entry.estimated_disk_mb
        if entry.requires_sudo:
            self.requires_sudo = True

    def get_enabled_entries(self) -> List[ToolPlanEntry]:
        return [e for e in self.entries if e.status == "will_install"]

    def get_optional_entries(self) -> List[ToolPlanEntry]:
        return [e for e in self.entries if e.status == "optional"]

    def get_excluded_entries(self) -> List[ToolPlanEntry]:
        return [e for e in self.entries if e.status == "excluded"]

    def get_incompatible_entries(self) -> List[ToolPlanEntry]:
        return [e for e in self.entries if e.compatibility == CompatibilityClass.INCOMPATIBLE]


class InstallationPlanner:
    """
    Genera plan de instalación a partir de manifiestos, HW/SO y perfil.
    """

    SIZE_CLASS_DOWNLOAD = {
        "tiny": 10,
        "small": 50,
        "medium": 200,
        "large": 1000,
        "auto": 50,
    }

    def __init__(
        self,
        manifests: List[ToolManifest],
        hw: HardwareReport,
        os_report: OSReport,
        profile: str,
        profile_config: Optional[Any] = None,
    ):
        self.manifests = manifests
        self.hw = hw
        self.os_report = os_report
        self.profile = profile
        self.profile_config = profile_config

    def generate_plan(
        self,
        categories: Optional[List[str]] = None,
        include_optional: bool = False,
        force_excluded: bool = False,
    ) -> InstallationPlan:
        """Genera plan completo."""
        plan = InstallationPlan(
            profile=self.profile,
            hw_report=self.hw,
            os_report=self.os_report,
            generated_at=self._now_iso(),
        )

        # Filtrar manifiestos por categoría
        filtered = self._filter_by_category(categories)

        # Evaluar cada herramienta
        for manifest in filtered:
            entry = self._evaluate_tool(manifest, include_optional, force_excluded)
            plan.add_entry(entry)

        # Ordenar: incompatibles al final, luego por prioridad de perfil
        plan.entries.sort(key=self._plan_sort_key)

        return plan

    def _filter_by_category(self, categories: Optional[List[str]]) -> List[ToolManifest]:
        if not categories or "all" in categories:
            return self.manifests
        return [m for m in self.manifests if m.category in categories]

    def _evaluate_tool(
        self,
        manifest: ToolManifest,
        include_optional: bool,
        force_excluded: bool,
    ) -> ToolPlanEntry:
        """Evalúa una herramienta y genera su entrada de plan."""
        # Verificar perfil
        profile_status = manifest.get_profile_status(self.profile)

        if profile_status == "excluded" and not force_excluded:
            status = "excluded"
        elif profile_status == "optional" and not include_optional:
            status = "optional"
        else:
            status = "will_install"

        # Determinar método de instalación
        method, method_details = self._select_install_method(manifest)

        # Calcular compatibilidad
        compatibility, incomp_reasons = self._classify_compatibility(manifest, method_details)

        # Estimar recursos
        download_mb = self._estimate_download(manifest, method, method_details)
        disk_mb = manifest.disk_install_mb

        # Sudo
        requires_sudo = manifest.privileged and method == "native"

        warnings = []
        if method == "binary_release" and not method_details.get("sha256"):
            warnings.append("Método binary_release deshabilitado: hash no pinneado")
        if method == "script_official" and not method_details.get("sha256"):
            warnings.append("Método script_official deshabilitado: hash no pinneado")
        if download_mb > 200:
            warnings.append(f"Descarga grande (~{download_mb} MB): requiere confirmación explícita")

        return ToolPlanEntry(
            tool=manifest,
            compatibility=compatibility,
            method=method,
            method_details=method_details,
            estimated_download_mb=download_mb,
            estimated_disk_mb=disk_mb,
            requires_sudo=requires_sudo,
            status=status,
            warnings=warnings,
            incompatibility_reasons=incomp_reasons,
        )

    def _select_install_method(self, manifest: ToolManifest) -> tuple[str, Dict]:
        """Selecciona mejor método de instalación para el SO actual."""
        # Prioridad: native > binary_release > git_clone > script_official > pipx
        priority = ["native", "binary_release", "git_clone", "script_official", "pipx"]

        for method in priority:
            if method not in manifest.install_methods:
                continue

            details = manifest.install_methods[method]

            if method == "native":
                # Verificar si hay paquete para familia del SO
                for family in self.os_report.package_families:
                    pkg = details.get(family)
                    if pkg is not None:
                        return method, {"package": pkg, "family": family}

            elif method == "binary_release":
                # Verificar arquitectura y hash
                sha256 = details.get("sha256", {})
                arch = self.hw.architecture
                if arch in sha256:
                    hash_val = sha256[arch]
                    if hash_val.upper() != "PENDING-VERIFICATION":
                        return method, details
                # Sin hash válido -> método deshabilitado
                continue

            elif method in ("git_clone", "script_official", "pipx"):
                # Métodos genéricos, viables si no hay restricciones
                return method, details

        # Fallback: primer método declarado
        for method in manifest.install_methods:
            return method, manifest.install_methods[method]

        return "none", {}

    def _classify_compatibility(
        self,
        manifest: ToolManifest,
        method_details: Dict,
    ) -> tuple[CompatibilityClass, List[str]]:
        """Clasifica compatibilidad: compatible/recommended/optimal/incompatible."""
        reasons = []

        # Sin método viable
        if not method_details:
            return CompatibilityClass.INCOMPATIBLE, ["Sin método de instalación viable para este SO/arquitectura"]

        # Verificar RAM
        ram_available = self.hw.memory.available_mb
        if ram_available < manifest.ram_run_mb:
            reasons.append(f"RAM disponible ({ram_available} MB) < mínima para ejecutar ({manifest.ram_run_mb} MB)")
            return CompatibilityClass.INCOMPATIBLE, reasons

        # Verificar disco
        # (Simplificado: asumimos espacio en /)
        disk_free = self.hw.disks[0].free_mb if self.hw.disks else 0
        if disk_free < manifest.disk_install_mb:
            reasons.append(f"Disco libre ({disk_free} MB) < requerido para instalar ({manifest.disk_install_mb} MB)")
            return CompatibilityClass.INCOMPATIBLE, reasons

        # Verificar GPU si required
        if manifest.gpu == "required":
            has_gpu = any(g.vendor != "none" and g.is_dedicated for g in self.hw.gpus)
            if not has_gpu:
                reasons.append("GPU dedicada requerida pero no detectada")
                return CompatibilityClass.INCOMPATIBLE, reasons

        # Verificar Python mínimo
        if manifest.python_min:
            import sys
            py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
            if self._version_compare(py_version, manifest.python_min) < 0:
                reasons.append(f"Python {py_version} < mínimo requerido {manifest.python_min}")
                return CompatibilityClass.INCOMPATIBLE, reasons

        # Compatible base
        # Recommended: RAM >= ram_run_mb
        if ram_available >= manifest.ram_run_mb:
            # Optimal: RAM >= ram_optimal_mb Y (GPU ok si optional/required)
            ram_optimal = ram_available >= manifest.ram_optimal_mb
            gpu_ok = True
            if manifest.gpu in ("optional", "required"):
                gpu_ok = any(g.vendor != "none" and g.is_dedicated for g in self.hw.gpus)

            if ram_optimal and gpu_ok:
                return CompatibilityClass.OPTIMAL, reasons
            return CompatibilityClass.RECOMMENDED, reasons

        return CompatibilityClass.COMPATIBLE, reasons

    def _estimate_download(self, manifest: ToolManifest, method: str, details: Dict) -> int:
        """Estima MB a descargar."""
        if method == "native":
            return 0  # Paquetes del SO, no contamos descarga
        if method == "binary_release":
            # Estimación por size_class
            return self.SIZE_CLASS_DOWNLOAD.get(manifest.size_class, 50)
        if method == "git_clone":
            return self.SIZE_CLASS_DOWNLOAD.get(manifest.size_class, 100)
        if method == "script_official":
            return 5  # Scripts pequeños
        if method == "pipx":
            return self.SIZE_CLASS_DOWNLOAD.get(manifest.size_class, 20)
        return 0

    def _version_compare(self, v1: str, v2: str) -> int:
        def parse(v):
            return tuple(int(p) for p in v.split(".")[:3])
        t1, t2 = parse(v1), parse(v2)
        return (t1 > t2) - (t1 < t2)

    def _plan_sort_key(self, entry: ToolPlanEntry) -> tuple:
        # Orden: will_install primero, luego optional, excluded, incompatible
        status_order = {"will_install": 0, "optional": 1, "excluded": 2, "pending": 3}
        compat_order = {
            CompatibilityClass.OPTIMAL: 0,
            CompatibilityClass.RECOMMENDED: 1,
            CompatibilityClass.COMPATIBLE: 2,
            CompatibilityClass.INCOMPATIBLE: 3,
        }
        return (
            status_order.get(entry.status, 99),
            compat_order.get(entry.compatibility, 99),
            entry.tool.category,
            entry.tool.name,
        )

    def _now_iso(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()


def create_plan(
    manifests: List[ToolManifest],
    hw: HardwareReport,
    os_report: OSReport,
    profile: str,
    categories: Optional[List[str]] = None,
    include_optional: bool = False,
    force_excluded: bool = False,
) -> InstallationPlan:
    """Función de conveniencia."""
    planner = InstallationPlanner(manifests, hw, os_report, profile)
    return planner.generate_plan(categories, include_optional, force_excluded)