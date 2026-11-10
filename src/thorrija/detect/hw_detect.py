"""
Detección de hardware (CPU, RAM, GPU, disco).
Sin dependencias externas, solo /proc, /sys y comandos estándar.
"""

from __future__ import annotations

import os
import re
import subprocess
import shutil
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass(frozen=True)
class CPUInfo:
    model: str
    cores: int
    threads: int
    architecture: str
    vendor: str
    flags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class MemoryInfo:
    total_mb: int
    available_mb: int
    swap_total_mb: int
    swap_free_mb: int


@dataclass(frozen=True)
class GPUInfo:
    vendor: str                    # "nvidia", "amd", "intel", "unknown"
    model: str
    vram_mb: int = 0
    driver: str = ""
    is_dedicated: bool = False
    cuda_version: str = ""


@dataclass(frozen=True)
class DiskInfo:
    path: str
    total_mb: int
    free_mb: int
    is_ssd: bool = False
    filesystem: str = ""


@dataclass(frozen=True)
class HardwareReport:
    cpu: CPUInfo
    memory: MemoryInfo
    gpus: List[GPUInfo]
    disks: List[DiskInfo]
    hostname: str
    kernel: str
    architecture: str  # x86_64, aarch64, etc.


class HardwareDetector:
    """Detecta hardware sin requerir root ni herramientas específicas."""

    def __init__(self):
        self._cpu_cache: Optional[CPUInfo] = None
        self._memory_cache: Optional[MemoryInfo] = None
        self._gpu_cache: Optional[List[GPUInfo]] = None
        self._disk_cache: Optional[List[DiskInfo]] = None

    def detect(self) -> HardwareReport:
        """Detecta todo el hardware y retorna reporte completo."""
        return HardwareReport(
            cpu=self.get_cpu(),
            memory=self.get_memory(),
            gpus=self.get_gpus(),
            disks=self.get_disks(),
            hostname=self._get_hostname(),
            kernel=self._get_kernel(),
            architecture=self._get_architecture(),
        )

    def get_cpu(self) -> CPUInfo:
        if self._cpu_cache:
            return self._cpu_cache

        model = "Unknown"
        cores = 1
        threads = 1
        vendor = "unknown"
        flags = []
        architecture = self._get_architecture()

        # Leer /proc/cpuinfo
        try:
            with open("/proc/cpuinfo", "r") as f:
                content = f.read()
        except (OSError, IOError):
            pass
        else:
            # Contar procesadores lógicos
            threads = content.count("processor\t:")
            if threads == 0:
                threads = 1

            # Modelo (primera ocurrencia)
            for line in content.splitlines():
                if line.startswith("model name\t:"):
                    model = line.split(":", 1)[1].strip()
                    break
                elif line.startswith("Model\t\t:"):
                    model = line.split(":", 1)[1].strip()
                    break

            # Vendor
            for line in content.splitlines():
                if line.startswith("vendor_id\t:"):
                    vendor = line.split(":", 1)[1].strip().lower()
                    break

            # Flags (primera CPU)
            for line in content.splitlines():
                if line.startswith("flags\t\t:"):
                    flags = line.split(":", 1)[1].strip().split()
                    break

            # Cores físicos: intentar vía /sys o smt
            cores = self._count_physical_cores(threads)

        self._cpu_cache = CPUInfo(
            model=model,
            cores=cores,
            threads=threads,
            architecture=architecture,
            vendor=vendor,
            flags=flags,
        )
        return self._cpu_cache

    def _count_physical_cores(self, logical_threads: int) -> int:
        """Intenta determinar cores físicos."""
        # Método 1: /sys/devices/system/cpu/cpu*/topology/core_id
        core_ids = set()
        try:
            for cpu_dir in os.listdir("/sys/devices/system/cpu/"):
                if cpu_dir.startswith("cpu") and cpu_dir[3:].isdigit():
                    core_id_path = f"/sys/devices/system/cpu/{cpu_dir}/topology/core_id"
                    if os.path.exists(core_id_path):
                        with open(core_id_path) as f:
                            core_ids.add(f.read().strip())
        except (OSError, IOError):
            pass

        if core_ids:
            return len(core_ids)

        # Método 2: si hay hyperthreading, cores = threads / 2
        # Detectar HT via flags
        cpu = self.get_cpu()  # recursion guard: solo flags
        if "ht" in cpu.flags:
            return max(1, logical_threads // 2)

        return logical_threads

    def get_memory(self) -> MemoryInfo:
        if self._memory_cache:
            return self._memory_cache

        meminfo = {}
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        # val formato: "  123456 kB"
                        val = val.strip().split()[0]
                        meminfo[key] = int(val)
        except (OSError, IOError, ValueError):
            pass

        total_kb = meminfo.get("MemTotal", 0)
        available_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        swap_total_kb = meminfo.get("SwapTotal", 0)
        swap_free_kb = meminfo.get("SwapFree", 0)

        self._memory_cache = MemoryInfo(
            total_mb=total_kb // 1024,
            available_mb=available_kb // 1024,
            swap_total_mb=swap_total_kb // 1024,
            swap_free_mb=swap_free_kb // 1024,
        )
        return self._memory_cache

    def get_gpus(self) -> List[GPUInfo]:
        if self._gpu_cache is not None:
            return self._gpu_cache

        gpus = []

        # 1. Intentar lspci (más fiable)
        gpus.extend(self._detect_gpus_lspci())

        # 2. Fallback: /sys/class/drm
        if not gpus:
            gpus.extend(self._detect_gpus_sysfs())

        # 3. NVIDIA específico: nvidia-smi
        nvidia_gpus = self._detect_nvidia_smi()
        if nvidia_gpus:
            # Reemplazar/mergear con detección lspci
            gpus = self._merge_gpus(gpus, nvidia_gpus)

        self._gpu_cache = gpus if gpus else [GPUInfo(vendor="none", model="No GPU detected")]
        return self._gpu_cache

    def _detect_gpus_lspci(self) -> List[GPUInfo]:
        """Detecta GPUs vía lspci -nn."""
        gpus = []
        try:
            # -nn = mostrar IDs numéricos
            out = subprocess.run(
                ["lspci", "-nn", "-d", "::0300", "-d", "::0302", "-d", "::0380"],
                capture_output=True, text=True, timeout=5
            )
            if out.returncode != 0:
                return gpus

            for line in out.stdout.strip().splitlines():
                # Formato: 01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA106 [RTX 3060] [10de:2504] (rev a1)
                gpu = self._parse_lspci_line(line)
                if gpu:
                    gpus.append(gpu)
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            pass
        return gpus

    def _parse_lspci_line(self, line: str) -> Optional[GPUInfo]:
        """Parsea una línea de lspci para extraer vendor/model."""
        # Buscar patrón [vendor:device]
        match = re.search(r"\[([0-9a-f]{4}):([0-9a-f]{4})\]", line)
        if not match:
            return None

        vendor_id, device_id = match.groups()

        # Mapear vendor IDs conocidos
        vendor_map = {
            "10de": "nvidia",
            "1002": "amd",      # ATI/AMD
            "8086": "intel",
            "1af4": "virtio",   # VirtIO GPU
        }
        vendor = vendor_map.get(vendor_id, "unknown")

        # Extraer nombre del modelo (texto entre corchetes finales o antes de vendor ID)
        model = "Unknown GPU"
        # Intentar extraer nombre legible
        parts = line.split("]:")
        if len(parts) > 1:
            model = parts[-1].strip()
        else:
            model = line.split(":")[-1].strip()

        # Determinar si es dedicada (heurística: NVIDIA/AMD discretas vs Intel integrada)
        is_dedicated = vendor in ("nvidia", "amd") and "integrated" not in model.lower()

        return GPUInfo(
            vendor=vendor,
            model=model,
            is_dedicated=is_dedicated,
        )

    def _detect_gpus_sysfs(self) -> List[GPUInfo]:
        """Fallback: /sys/class/drm/card*/device/uevent"""
        gpus = []
        try:
            drm_path = "/sys/class/drm"
            if not os.path.isdir(drm_path):
                return gpus

            for card in os.listdir(drm_path):
                if not card.startswith("card"):
                    continue
                uevent_path = os.path.join(drm_path, card, "device", "uevent")
                if not os.path.exists(uevent_path):
                    continue

                props = {}
                with open(uevent_path) as f:
                    for line in f:
                        if "=" in line:
                            k, v = line.strip().split("=", 1)
                            props[k] = v

                vendor_id = props.get("PCI_ID", "").split(":")[0] if "PCI_ID" in props else ""
                vendor_map = {"10de": "nvidia", "1002": "amd", "8086": "intel"}
                vendor = vendor_map.get(vendor_id, "unknown")

                gpus.append(GPUInfo(
                    vendor=vendor,
                    model=props.get("PCI_SUBSYSTEM_NAME", f"GPU {card}"),
                    is_dedicated=vendor in ("nvidia", "amd"),
                ))
        except (OSError, IOError):
            pass
        return gpus

    def _detect_nvidia_smi(self) -> List[GPUInfo]:
        """Detecta GPUs NVIDIA con nvidia-smi (si está disponible)."""
        gpus = []
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if out.returncode != 0:
                return gpus

            for line in out.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    name, vram_mb, driver = parts[0], parts[1], parts[2]
                    gpus.append(GPUInfo(
                        vendor="nvidia",
                        model=name,
                        vram_mb=int(vram_mb) if vram_mb.isdigit() else 0,
                        driver=driver,
                        is_dedicated=True,
                    ))
        except (subprocess.SubprocessError, FileNotFoundError, OSError, ValueError):
            pass
        return gpus

    def _merge_gpus(self, lspci_gpus: List[GPUInfo], nvidia_gpus: List[GPUInfo]) -> List[GPUInfo]:
        """Mergea detecciones: nvidia-smi tiene más info (VRAM, driver)."""
        merged = []
        for ngpu in nvidia_gpus:
            # Buscar match en lspci
            match = next((g for g in lspci_gpus if g.vendor == "nvidia" and g.model in ngpu.model), None)
            if match:
                merged.append(GPUInfo(
                    vendor="nvidia",
                    model=ngpu.model,
                    vram_mb=ngpu.vram_mb,
                    driver=ngpu.driver,
                    is_dedicated=True,
                ))
            else:
                merged.append(ngpu)

        # Añadir GPUs no-NVIDIA de lspci
        for g in lspci_gpus:
            if g.vendor != "nvidia":
                merged.append(g)

        return merged

    def get_disks(self) -> List[DiskInfo]:
        if self._disk_cache is not None:
            return self._disk_cache

        disks = []
        try:
            # Usar shutil.disk_usage para puntos de montaje relevantes
            for mount_point in ["/", "/home", "/var", "/tmp"]:
                try:
                    usage = shutil.disk_usage(mount_point)
                    # Detectar SSD via /sys/block
                    is_ssd = self._is_ssd_mount(mount_point)
                    disks.append(DiskInfo(
                        path=mount_point,
                        total_mb=usage.total // (1024 * 1024),
                        free_mb=usage.free // (1024 * 1024),
                        is_ssd=is_ssd,
                    ))
                except (OSError, FileNotFoundError):
                    continue
        except Exception:
            pass

        self._disk_cache = disks if disks else [DiskInfo(path="/", total_mb=0, free_mb=0)]
        return self._disk_cache

    def _is_ssd_mount(self, mount_point: str) -> bool:
        """Intenta detectar si el montaje está en SSD."""
        try:
            # Encontrar dispositivo de bloque para el mount point
            out = subprocess.run(
                ["findmnt", "-n", "-o", "SOURCE", mount_point],
                capture_output=True, text=True, timeout=3
            )
            if out.returncode != 0:
                return False

            device = out.stdout.strip()
            # Ej: /dev/nvme0n1p1 -> nvme0n1, /dev/sda1 -> sda
            base = os.path.basename(device)
            # Quitar número de partición final
            base = re.sub(r'p?\d+$', '', base)

            rotational_path = f"/sys/block/{base}/queue/rotational"
            if os.path.exists(rotational_path):
                with open(rotational_path) as f:
                    return f.read().strip() == "0"
        except Exception:
            pass
        return False

    def _get_hostname(self) -> str:
        try:
            return os.uname().nodename
        except Exception:
            return "unknown"

    def _get_kernel(self) -> str:
        try:
            return os.uname().release
        except Exception:
            return "unknown"

    def _get_architecture(self) -> str:
        try:
            return os.uname().machine
        except Exception:
            return "unknown"


def detect_hardware() -> HardwareReport:
    """Función de conveniencia."""
    return HardwareDetector().detect()