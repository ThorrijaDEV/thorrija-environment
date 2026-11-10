"""
Detección de Windows OS y hardware.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Optional

from .os_detect import OSReport
from .hw_detect import HardwareReport, CPUInfo, MemoryInfo, GPUInfo, DiskInfo


@dataclass(frozen=True)
class WindowsOSReport:
    """Resultado de detección de Windows."""
    version: str              # ej: "10.0.19045"
    build: str                # ej: "19045"
    edition: str              # ej: "Pro", "Home", "Enterprise"
    product_name: str         # ej: "Windows 11 Pro"
    architecture: str         # "x86_64" o "arm64"
    is_windows_11: bool
    package_managers: List[str]  # ej: ["winget", "chocolatey", "scoop"]
    support_level: str        # "verified" | "assumed" | "unsupported"


class WindowsOSDetector:
    """Detecta versión y edición de Windows."""

    def detect(self) -> WindowsOSReport:
        # Usar platform module y WMI/PowerShell
        version = platform.version()
        build = platform.win32_ver()[2] if hasattr(platform, 'win32_ver') else ""
        
        # Obtener info detallada via PowerShell
        ps_info = self._get_windows_info_ps()
        
        edition = ps_info.get("Edition", "Unknown")
        product_name = ps_info.get("ProductName", "Windows")
        
        # Detectar Windows 11
        is_win11 = self._is_windows_11(build, product_name)
        
        # Detectar gestores de paquetes disponibles
        pkg_managers = self._detect_package_managers()
        
        arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
        
        return WindowsOSReport(
            version=version,
            build=build,
            edition=edition,
            product_name=product_name,
            architecture=arch,
            is_windows_11=is_win11,
            package_managers=pkg_managers,
            support_level="verified",
        )

    def _get_windows_info_ps(self) -> dict:
        """Obtiene info de Windows via PowerShell."""
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance -ClassName Win32_OperatingSystem | "
                "Select-Object Caption, Version, BuildNumber, OperatingSystemSKU | "
                "ConvertTo-Json -Compress"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                return {
                    "ProductName": data.get("Caption", "Windows"),
                    "Version": data.get("Version", ""),
                    "BuildNumber": data.get("BuildNumber", ""),
                    "Edition": self._sku_to_edition(data.get("OperatingSystemSKU", 0)),
                }
        except Exception:
            pass
        return {}

    def _sku_to_edition(self, sku: int) -> str:
        """Convierte SKU numérico a nombre de edición."""
        sku_map = {
            48: "Pro", 49: "Pro N", 72: "Enterprise", 73: "Enterprise N",
            100: "Education", 101: "Education N", 121: "Pro for Workstations",
            161: "Pro Single Language", 10: "Home", 11: "Home N",
        }
        return sku_map.get(sku, "Unknown")

    def _is_windows_11(self, build: str, product_name: str) -> bool:
        try:
            return int(build) >= 22000 or "11" in product_name
        except Exception:
            return False

    def _detect_package_managers(self) -> List[str]:
        """Detecta qué gestores de paquetes están disponibles."""
        managers = []
        
        # winget (incluido en Windows 10 1809+ / Windows 11)
        try:
            subprocess.run(["winget", "--version"], capture_output=True, timeout=5, check=True)
            managers.append("winget")
        except Exception:
            pass
        
        # Chocolatey
        try:
            subprocess.run(["choco", "--version"], capture_output=True, timeout=5, check=True)
            managers.append("chocolatey")
        except Exception:
            pass
        
        # Scoop
        try:
            subprocess.run(["scoop", "--version"], capture_output=True, timeout=5, check=True)
            managers.append("scoop")
        except Exception:
            pass
        
        return managers


class WindowsHardwareDetector:
    """Detecta hardware en Windows via WMI/PowerShell."""

    def detect(self) -> HardwareReport:
        cpu = self._get_cpu_ps()
        memory = self._get_memory_ps()
        gpus = self._get_gpus_ps()
        disks = self._get_disks_ps()
        
        return HardwareReport(
            cpu=cpu,
            memory=memory,
            gpus=gpus,
            disks=disks,
            hostname=platform.node(),
            kernel=platform.version(),
            architecture="arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64",
        )

    def _get_cpu_ps(self) -> CPUInfo:
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance -ClassName Win32_Processor | "
                "Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, Manufacturer, Architecture | "
                "ConvertTo-Json -Compress"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if isinstance(data, list):
                    data = data[0]
                return CPUInfo(
                    model=data.get("Name", "Unknown"),
                    cores=int(data.get("NumberOfCores", 1)),
                    threads=int(data.get("NumberOfLogicalProcessors", 1)),
                    architecture="x86_64",  # Windows CPU arch
                    vendor=data.get("Manufacturer", "unknown").lower(),
                    flags=[],
                )
        except Exception:
            pass
        return CPUInfo(model="Unknown", cores=1, threads=1, architecture="x86_64", vendor="unknown")

    def _get_memory_ps(self) -> MemoryInfo:
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance -ClassName Win32_OperatingSystem | "
                "Select-Object TotalVisibleMemorySize, FreePhysicalMemory, TotalVirtualMemorySize, FreeVirtualMemory | "
                "ConvertTo-Json -Compress"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                # Valores en KB, convertir a MB
                total_kb = int(data.get("TotalVisibleMemorySize", 0))
                free_kb = int(data.get("FreePhysicalMemory", 0))
                swap_total_kb = int(data.get("TotalVirtualMemorySize", 0))
                swap_free_kb = int(data.get("FreeVirtualMemory", 0))
                return MemoryInfo(
                    total_mb=total_kb // 1024,
                    available_mb=free_kb // 1024,
                    swap_total_mb=swap_total_kb // 1024,
                    swap_free_mb=swap_free_kb // 1024,
                )
        except Exception:
            pass
        return MemoryInfo(total_mb=0, available_mb=0, swap_total_mb=0, swap_free_mb=0)

    def _get_gpus_ps(self) -> List[GPUInfo]:
        gpus = []
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance -ClassName Win32_VideoController | "
                "Select-Object Name, AdapterRAM, DriverVersion, VideoProcessor | "
                "ConvertTo-Json -Compress"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if not isinstance(data, list):
                    data = [data]
                for gpu_data in data:
                    name = gpu_data.get("Name", "Unknown")
                    vram_bytes = int(gpu_data.get("AdapterRAM", 0) or 0)
                    vram_mb = vram_bytes // (1024 * 1024) if vram_bytes else 0
                    driver = gpu_data.get("DriverVersion", "")
                    
                    # Determinar vendor
                    name_lower = name.lower()
                    if "nvidia" in name_lower or "geforce" in name_lower or "quadro" in name_lower or "rtx" in name_lower or "gtx" in name_lower:
                        vendor = "nvidia"
                        is_dedicated = True
                    elif "amd" in name_lower or "radeon" in name_lower:
                        vendor = "amd"
                        is_dedicated = "integrated" not in name_lower
                    elif "intel" in name_lower or "uhd" in name_lower or "iris" in name_lower or "hd graphics" in name_lower:
                        vendor = "intel"
                        is_dedicated = False
                    else:
                        vendor = "unknown"
                        is_dedicated = False
                    
                    gpus.append(GPUInfo(
                        vendor=vendor,
                        model=name,
                        vram_mb=vram_mb,
                        driver=driver,
                        is_dedicated=is_dedicated,
                    ))
        except Exception:
            pass
        
        if not gpus:
            gpus.append(GPUInfo(vendor="none", model="No GPU detected"))
        return gpus

    def _get_disks_ps(self) -> List[DiskInfo]:
        disks = []
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance -ClassName Win32_LogicalDisk | "
                "Where-Object {$_.DriveType -eq 3} | "
                "Select-Object DeviceID, Size, FreeSpace, MediaType | "
                "ConvertTo-Json -Compress"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if not isinstance(data, list):
                    data = [data]
                for disk_data in data:
                    path = disk_data.get("DeviceID", "C:")
                    size_bytes = int(disk_data.get("Size", 0) or 0)
                    free_bytes = int(disk_data.get("FreeSpace", 0) or 0)
                    media_type = disk_data.get("MediaType", "")
                    is_ssd = "ssd" in str(media_type).lower() or "solid state" in str(media_type).lower()
                    
                    disks.append(DiskInfo(
                        path=path,
                        total_mb=size_bytes // (1024 * 1024) if size_bytes else 0,
                        free_mb=free_bytes // (1024 * 1024) if free_bytes else 0,
                        is_ssd=is_ssd,
                    ))
        except Exception:
            pass
        
        if not disks:
            disks.append(DiskInfo(path="C:", total_mb=0, free_mb=0))
        return disks


def detect_windows_os() -> WindowsOSReport:
    return WindowsOSDetector().detect()

def detect_windows_hardware() -> HardwareReport:
    return WindowsHardwareDetector().detect()