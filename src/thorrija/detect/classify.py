"""
Clasificación de perfiles de hardware (LOW-END, STANDARD, HIGH-END).
Basado en umbrales configurables desde profiles/*.toml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

from .hw_detect import HardwareReport


@dataclass(frozen=True)
class ProfileThresholds:
    """Umbrales para clasificación automática (rangos inclusivos)."""
    ram_min_mb: int = 0                 # RAM mínima para este perfil
    ram_max_mb: int = 2**31 - 1         # RAM máxima para este perfil
    cpu_cores_min: int = 0              # Cores mínimos
    cpu_cores_max: int = 2**31 - 1      # Cores máximos
    gpu_dedicated_vram_min_mb: int = 0  # VRAM mínima GPU dedicada (0 = no requerido)


@dataclass(frozen=True)
class ProfileConfig:
    """Configuración completa de un perfil."""
    name: str
    description: str
    thresholds: ProfileThresholds
    selection: Dict[str, bool]  # include_enabled, include_optional, include_excluded


DEFAULT_THRESHOLDS = ProfileThresholds(
    ram_min_mb=4096,       # 4 GB mínimo para standard
    ram_max_mb=16384,      # 16 GB máximo para standard
    cpu_cores_min=4,
    cpu_cores_max=7,
)

BUILTIN_PROFILES = {
    "low_end": ProfileConfig(
        name="low_end",
        description="Equipos con recursos limitados: 2-4 GB RAM, 2-3 cores, sin GPU dedicada",
        thresholds=ProfileThresholds(
            ram_min_mb=0,
            ram_max_mb=4096,      # <= 4 GB
            cpu_cores_min=0,
            cpu_cores_max=3,      # <= 3 cores
        ),
        selection={"include_enabled": True, "include_optional": False, "include_excluded": False},
    ),
    "standard": ProfileConfig(
        name="standard",
        description="Equipos de uso general: 4-16 GB RAM, 4-7 cores, GPU opcional",
        thresholds=DEFAULT_THRESHOLDS,
        selection={"include_enabled": True, "include_optional": False, "include_excluded": False},
    ),
    "high_end": ProfileConfig(
        name="high_end",
        description="Workstations: 16+ GB RAM, 8+ cores, GPU dedicada recomendada",
        thresholds=ProfileThresholds(
            ram_min_mb=16384,       # >= 16 GB
            ram_max_mb=2**31 - 1,
            cpu_cores_min=8,        # >= 8 cores
            cpu_cores_max=2**31 - 1,
            gpu_dedicated_vram_min_mb=4096,  # GPU dedicada >= 4 GB
        ),
        selection={"include_enabled": True, "include_optional": True, "include_excluded": False},
    ),
    "minimal": ProfileConfig(
        name="minimal",
        description="Solo esenciales: git, python, editor CLI, shell",
        thresholds=DEFAULT_THRESHOLDS,
        selection={"include_enabled": True, "include_optional": False, "include_excluded": False},
    ),
}


class ProfileClassifier:
    """Clasifica hardware en perfiles usando umbrales configurables."""

    def __init__(self, profiles_dir: Optional[str] = None):
        self.profiles_dir = Path(profiles_dir) if profiles_dir else None
        self._custom_profiles: Dict[str, ProfileConfig] = {}
        self._load_custom_profiles()

    def _load_custom_profiles(self) -> None:
        """Carga perfiles personalizados desde profiles_dir."""
        if not self.profiles_dir or not self.profiles_dir.exists():
            return
        if tomllib is None:
            return

        for profile_file in self.profiles_dir.glob("*.toml"):
            try:
                with open(profile_file, "rb") as f:
                    data = tomllib.load(f)
                # Parsear estructura esperada
                name = data.get("name", profile_file.stem)
                desc = data.get("description", "")
                th = data.get("thresholds", {})
                sel = data.get("selection", {})

                thresholds = ProfileThresholds(
                    ram_min_mb=th.get("ram_min_mb", DEFAULT_THRESHOLDS.ram_min_mb),
                    ram_max_mb=th.get("ram_max_mb", DEFAULT_THRESHOLDS.ram_max_mb),
                    cpu_cores_min=th.get("cpu_cores_min", DEFAULT_THRESHOLDS.cpu_cores_min),
                    cpu_cores_max=th.get("cpu_cores_max", DEFAULT_THRESHOLDS.cpu_cores_max),
                    gpu_dedicated_vram_min_mb=th.get("gpu_dedicated_vram_min_mb", DEFAULT_THRESHOLDS.gpu_dedicated_vram_min_mb),
                )
                selection = {
                    "include_enabled": sel.get("include_enabled", True),
                    "include_optional": sel.get("include_optional", False),
                    "include_excluded": sel.get("include_excluded", False),
                }
                self._custom_profiles[name] = ProfileConfig(
                    name=name, description=desc, thresholds=thresholds, selection=selection
                )
            except Exception:
                # Silencioso: perfiles personalizados son opcionales
                pass

    def get_available_profiles(self) -> Dict[str, ProfileConfig]:
        """Retorna todos los perfiles disponibles (builtin + custom)."""
        result = BUILTIN_PROFILES.copy()
        result.update(self._custom_profiles)
        return result

    def classify(self, hw: HardwareReport, profile_name: Optional[str] = None) -> str:
        """
        Clasifica el hardware en un perfil.
        Si profile_name se proporciona, lo usa directamente (forzado).
        Si no, auto-detecta basado en umbrales.
        """
        if profile_name:
            available = self.get_available_profiles()
            if profile_name in available:
                return profile_name
            # Perfil desconocido: advertir pero usar
            return profile_name

        # Auto-clasificación: evaluar perfiles en orden de prioridad
        # Prioridad: high_end > standard > low_end
        for profile_key in ("high_end", "standard", "low_end"):
            profile = self.get_available_profiles().get(profile_key)
            if profile and self._matches_thresholds(hw, profile.thresholds):
                return profile_key

        # Fallback seguro
        return "standard"

    def _matches_thresholds(self, hw: HardwareReport, thresholds: ProfileThresholds) -> bool:
        """Verifica si el hardware está dentro de los rangos del perfil."""
        # RAM
        if not (thresholds.ram_min_mb <= hw.memory.total_mb <= thresholds.ram_max_mb):
            return False

        # CPU cores
        if not (thresholds.cpu_cores_min <= hw.cpu.cores <= thresholds.cpu_cores_max):
            return False

        # GPU dedicada (si el perfil la requiere)
        if thresholds.gpu_dedicated_vram_min_mb > 0:
            has_dedicated_gpu = any(
                gpu.is_dedicated and gpu.vram_mb >= thresholds.gpu_dedicated_vram_min_mb
                for gpu in hw.gpus
                if gpu.vendor != "none"
            )
            if not has_dedicated_gpu:
                return False

        return True

    def get_profile_config(self, profile_name: str) -> Optional[ProfileConfig]:
        """Obtiene configuración completa de un perfil."""
        return self.get_available_profiles().get(profile_name)

    def explain_classification(self, hw: HardwareReport) -> Dict[str, Any]:
        """Explica por qué se clasificó en cada perfil (para debug/--detect)."""
        explanations = {}
        for name, profile in self.get_available_profiles().items():
            matches = self._matches_thresholds(hw, profile.thresholds)
            reasons = []
            th = profile.thresholds

            if hw.memory.total_mb >= th.ram_min_mb:
                reasons.append(f"RAM ({hw.memory.total_mb} MB) >= min ({th.ram_min_mb} MB)")
            else:
                reasons.append(f"RAM ({hw.memory.total_mb} MB) < min ({th.ram_min_mb} MB)")

            if hw.memory.total_mb <= th.ram_max_mb:
                reasons.append(f"RAM ({hw.memory.total_mb} MB) <= max ({th.ram_max_mb} MB)")
            else:
                reasons.append(f"RAM ({hw.memory.total_mb} MB) > max ({th.ram_max_mb} MB)")

            if hw.cpu.cores >= th.cpu_cores_min:
                reasons.append(f"Cores ({hw.cpu.cores}) >= min ({th.cpu_cores_min})")
            else:
                reasons.append(f"Cores ({hw.cpu.cores}) < min ({th.cpu_cores_min})")

            if hw.cpu.cores <= th.cpu_cores_max:
                reasons.append(f"Cores ({hw.cpu.cores}) <= max ({th.cpu_cores_max})")
            else:
                reasons.append(f"Cores ({hw.cpu.cores}) > max ({th.cpu_cores_max})")

            if th.gpu_dedicated_vram_min_mb > 0:
                has_dedicated = any(g.is_dedicated and g.vram_mb >= th.gpu_dedicated_vram_min_mb for g in hw.gpus)
                reasons.append(f"GPU dedicada >= {th.gpu_dedicated_vram_min_mb}MB? {has_dedicated}")

            explanations[name] = {
                "matches": matches,
                "reasons": reasons,
                "thresholds": {
                    "ram_min_mb": th.ram_min_mb,
                    "ram_max_mb": th.ram_max_mb,
                    "cpu_cores_min": th.cpu_cores_min,
                    "cpu_cores_max": th.cpu_cores_max,
                    "gpu_dedicated_vram_min_mb": th.gpu_dedicated_vram_min_mb,
                }
            }

        return explanations


def classify_hardware(hw: HardwareReport, profile_name: Optional[str] = None, profiles_dir: Optional[str] = None) -> str:
    """Función de conveniencia."""
    classifier = ProfileClassifier(profiles_dir)
    return classifier.classify(hw, profile_name)