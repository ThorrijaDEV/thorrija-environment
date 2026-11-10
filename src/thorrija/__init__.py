"""
Thorrija Environment — Core Package
"""

__version__ = "0.2.0-dev"
__author__ = "thorrija"

# Exportaciones principales para uso interno
from .detect import OSDetector, HardwareDetector, ProfileClassifier
from .catalog import ManifestLoader, ManifestValidator, DependencyResolver
from .plan import InstallationPlanner, DependencyGraph
from .state import AuditLog, BackupManager, ToolState
from .install import InstallationEngine, DriverRegistry

__all__ = [
    "OSDetector",
    "HardwareDetector", 
    "ProfileClassifier",
    "ManifestLoader",
    "ManifestValidator",
    "DependencyResolver",
    "InstallationPlanner",
    "DependencyGraph",
    "AuditLog",
    "BackupManager",
    "ToolState",
    "InstallationEngine",
    "DriverRegistry",
]