"""
Motor de instalación y drivers.
"""

from .engine import (
    InstallationEngine,
    DriverRegistry,
    BaseDriver,
    DriverResult,
    driver_registry,
    register_builtin_drivers,
)
from .drivers import native, binary_release, git_clone, script_official, pipx

# Registrar drivers al importar
register_builtin_drivers()

__all__ = [
    "InstallationEngine",
    "DriverRegistry",
    "BaseDriver",
    "DriverResult",
    "driver_registry",
    "register_builtin_drivers",
]