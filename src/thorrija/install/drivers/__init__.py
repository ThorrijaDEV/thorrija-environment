"""
Drivers de instalación built-in.
Importar este módulo registra todos los drivers en driver_registry.
"""

from . import native      # noqa: F401
from . import binary_release  # noqa: F401
from . import git_clone   # noqa: F401
from . import script_official  # noqa: F401
from . import pipx        # noqa: F401
from . import windows     # noqa: F401

from ..engine import driver_registry, BaseDriver, DriverResult

__all__ = ["driver_registry", "BaseDriver", "DriverResult"]