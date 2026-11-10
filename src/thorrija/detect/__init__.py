"""
Detección de sistema operativo, hardware y clasificación de perfiles.
"""

from .os_detect import OSDetector, OSReport, detect_os
from .hw_detect import (
    HardwareDetector, HardwareReport,
    CPUInfo, MemoryInfo, GPUInfo, DiskInfo,
    detect_hardware,
)
from .classify import (
    ProfileClassifier, ProfileConfig, ProfileThresholds,
    BUILTIN_PROFILES, DEFAULT_THRESHOLDS,
    classify_hardware,
)

__all__ = [
    "OSDetector", "OSReport", "detect_os",
    "HardwareDetector", "HardwareReport",
    "CPUInfo", "MemoryInfo", "GPUInfo", "DiskInfo", "detect_hardware",
    "ProfileClassifier", "ProfileConfig", "ProfileThresholds",
    "BUILTIN_PROFILES", "DEFAULT_THRESHOLDS", "classify_hardware",
]