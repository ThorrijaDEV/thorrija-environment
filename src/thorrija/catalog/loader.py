"""
Carga y parseo de manifiestos TOML desde el catálogo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

from ..detect import HardwareReport, OSReport


@dataclass(frozen=True)
class ToolManifest:
    """Manifiesto de una herramienta parseado y validado."""
    # [tool]
    name: str
    category: str
    description: str
    homepage: str = ""
    tags: tuple = ()

    # [requirements]
    ram_run_mb: int = 100
    ram_optimal_mb: int = 200
    disk_install_mb: int = 50
    disk_run_mb: int = 50
    gpu: str = "none"                    # none | optional | required
    cpu_cores_min: int = 1
    cpu_arch: tuple = ("x86_64", "aarch64")
    privileged: bool = True
    size_class: str = "auto"             # tiny | small | medium | large | auto
    network_required: bool = True
    python_min: str = ""

    # [profiles]
    profiles: Dict[str, str] = field(default_factory=dict)  # low_end, standard, high_end -> enabled|optional|excluded

    # [install] - métodos disponibles
    install_methods: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # [verify]
    verify_command: str = ""
    verify_pattern: str = ""
    verify_exit_code: int = 0
    verify_timeout_sec: int = 10
    version_extract: str = ""

    # [ai_models]
    ai_automatic: bool = False
    ai_default_models: tuple = ()
    ai_requires_confirmation: bool = True

    # Metadatos internos
    source_path: str = ""
    schema_version: int = 1

    # Propiedades computadas
    @property
    def is_ai_tool(self) -> bool:
        return self.category == "ai"

    def get_profile_status(self, profile: str) -> str:
        """Retorna enabled|optional|excluded para un perfil."""
        return self.profiles.get(profile, "excluded")

    def is_enabled_for_profile(self, profile: str) -> bool:
        return self.get_profile_status(profile) == "enabled"

    def is_optional_for_profile(self, profile: str) -> bool:
        return self.get_profile_status(profile) == "optional"

    def is_excluded_for_profile(self, profile: str) -> bool:
        return self.get_profile_status(profile) == "excluded"


class ManifestLoader:
    """Carga manifiestos desde directorio de catálogo."""

    VALID_CATEGORIES = {"languages", "development", "editors", "ai", "security", "system"}
    VALID_PROFILE_VALUES = {"enabled", "optional", "excluded"}
    VALID_GPU_VALUES = {"none", "optional", "required"}
    VALID_SIZE_CLASSES = {"tiny", "small", "medium", "large", "auto"}
    VALID_INSTALL_METHODS = {"native", "binary_release", "git_clone", "script_official", "pipx"}

    def __init__(self, catalog_root: str):
        self.catalog_root = Path(catalog_root)
        self._cache: Dict[str, ToolManifest] = {}

    def load_all(self) -> List[ToolManifest]:
        """Carga todos los manifiestos válidos del catálogo."""
        manifests = []
        if not self.catalog_root.exists():
            return manifests

        for category_dir in self.catalog_root.iterdir():
            if not category_dir.is_dir():
                continue
            if category_dir.name not in self.VALID_CATEGORIES:
                continue

            for toml_file in category_dir.glob("*.toml"):
                try:
                    manifest = self.load_manifest(toml_file)
                    if manifest:
                        manifests.append(manifest)
                except Exception:
                    # Silencioso: manifiestos inválidos se ignoran (validador los reportará)
                    pass

        return manifests

    def load_manifest(self, path: Path) -> Optional[ToolManifest]:
        """Carga y parsea un manifiesto individual."""
        if path in self._cache:
            return self._cache[path]

        if tomllib is None:
            raise RuntimeError("tomllib/tomli no disponible")

        with open(path, "rb") as f:
            data = tomllib.load(f)

        manifest = self._parse_manifest(data, str(path))
        self._cache[path] = manifest
        return manifest

    def _parse_manifest(self, data: Dict[str, Any], source_path: str) -> ToolManifest:
        """Parsea diccionario TOML a ToolManifest."""
        # [tool]
        tool = data.get("tool", {})
        name = tool.get("name", "")
        category = tool.get("category", "")
        description = tool.get("description", "")
        homepage = tool.get("homepage", "")
        tags = tuple(tool.get("tags", []))

        # [requirements]
        req = data.get("requirements", {})
        ram_run = req.get("ram_run_mb", 100)
        ram_optimal = req.get("ram_optimal_mb", ram_run * 2)
        disk_install = req.get("disk_install_mb", 50)
        disk_run = req.get("disk_run_mb", disk_install)
        gpu = req.get("gpu", "none")
        cpu_cores_min = req.get("cpu_cores_min", 1)
        cpu_arch = tuple(req.get("cpu_arch", ["x86_64", "aarch64"]))
        privileged = req.get("privileged", True)
        size_class = req.get("size_class", "auto")
        network_required = req.get("network_required", True)
        python_min = req.get("python_min", "")

        # [profiles]
        profiles = data.get("profiles", {})
        profile_dict = {
            "low_end": profiles.get("low_end", "excluded"),
            "standard": profiles.get("standard", "excluded"),
            "high_end": profiles.get("high_end", "excluded"),
        }

        # [install]
        install_methods = {}
        install = data.get("install", {})
        for method in self.VALID_INSTALL_METHODS:
            if method in install:
                install_methods[method] = install[method]

        # [verify]
        verify = data.get("verify", {})
        verify_command = verify.get("command", "")
        verify_pattern = verify.get("pattern", "")
        verify_exit_code = verify.get("exit_code", 0)
        verify_timeout_sec = verify.get("timeout_sec", 10)
        version_extract = verify.get("version_extract", "")

        # [ai_models]
        ai = data.get("ai_models", {})
        ai_automatic = ai.get("automatic", False)
        ai_default_models = tuple(ai.get("default_models", []))
        ai_requires_confirmation = ai.get("requires_confirmation", True)

        schema_version = data.get("schema_version", 1)

        return ToolManifest(
            name=name,
            category=category,
            description=description,
            homepage=homepage,
            tags=tags,
            ram_run_mb=ram_run,
            ram_optimal_mb=ram_optimal,
            disk_install_mb=disk_install,
            disk_run_mb=disk_run,
            gpu=gpu,
            cpu_cores_min=cpu_cores_min,
            cpu_arch=cpu_arch,
            privileged=privileged,
            size_class=size_class,
            network_required=network_required,
            python_min=python_min,
            profiles=profile_dict,
            install_methods=install_methods,
            verify_command=verify_command,
            verify_pattern=verify_pattern,
            verify_exit_code=verify_exit_code,
            verify_timeout_sec=verify_timeout_sec,
            version_extract=version_extract,
            ai_automatic=ai_automatic,
            ai_default_models=ai_default_models,
            ai_requires_confirmation=ai_requires_confirmation,
            source_path=source_path,
            schema_version=schema_version,
        )

    def filter_by_category(self, manifests: List[ToolManifest], category: str) -> List[ToolManifest]:
        """Filtra manifiestos por categoría."""
        if category == "all":
            return manifests
        return [m for m in manifests if m.category == category]

    def filter_by_profile(self, manifests: List[ToolManifest], profile: str) -> List[ToolManifest]:
        """Filtra manifiestos que aplican al perfil (enabled u optional)."""
        return [
            m for m in manifests
            if m.get_profile_status(profile) in ("enabled", "optional")
        ]

    def filter_compatible(
        self,
        manifests: List[ToolManifest],
        hw: HardwareReport,
        os_report: OSReport,
    ) -> List[ToolManifest]:
        """Filtra manifiestos compatibles con HW/SO actual."""
        compatible = []
        for m in manifests:
            if self._is_compatible(m, hw, os_report):
                compatible.append(m)
        return compatible

    def _is_compatible(self, manifest: ToolManifest, hw: HardwareReport, os_report: OSReport) -> bool:
        """Verifica compatibilidad básica (arquitectura, SO, método de instalación)."""
        # Arquitectura
        if hw.architecture not in manifest.cpu_arch:
            return False

        # Python mínimo
        if manifest.python_min:
            import sys
            py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
            if self._version_compare(py_version, manifest.python_min) < 0:
                return False

        # Al menos un método de instalación viable
        if not self._has_viable_method(manifest, os_report):
            return False

        return True

    def _has_viable_method(self, manifest: ToolManifest, os_report: OSReport) -> bool:
        """Verifica si hay al menos un método de instalación viable para este SO."""
        for method_name, method_data in manifest.install_methods.items():
            if method_name == "native":
                # Verificar si hay paquete para la familia del SO
                for family in os_report.package_families:
                    if family in method_data and method_data[family] is not None:
                        return True
            elif method_name == "binary_release":
                # Verificar arquitectura soportada
                sha256 = method_data.get("sha256", {})
                if hw.architecture in sha256:
                    return True
            elif method_name in ("git_clone", "script_official", "pipx"):
                # Estos son genéricos, viables si no hay restricciones
                return True
        return False

    def _version_compare(self, v1: str, v2: str) -> int:
        """Compara versiones semver simples. Retorna -1, 0, 1."""
        def parse(v: str):
            parts = v.split(".")
            return tuple(int(p) for p in parts[:3])

        t1, t2 = parse(v1), parse(v2)
        if t1 < t2:
            return -1
        elif t1 > t2:
            return 1
        return 0


def load_catalog(catalog_root: str) -> List[ToolManifest]:
    """Función de conveniencia."""
    return ManifestLoader(catalog_root).load_all()