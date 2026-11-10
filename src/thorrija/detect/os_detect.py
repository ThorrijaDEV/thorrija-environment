"""
Detección de sistema operativo y gestor de paquetes.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OSReport:
    """Resultado de la detección del SO."""
    id: str                    # ej: "arch", "debian", "ubuntu", "fedora", "void"
    name: str                  # nombre legible: "Arch Linux", "Ubuntu 22.04"
    version: str               # versión: "rolling", "22.04", "38"
    version_id: str            # VERSION_ID de /etc/os-release
    pretty_name: str           # PRETTY_NAME completo
    package_manager: str       # "pacman", "apt", "dnf", "xbps", "zypper", "apk", "emerge"
    package_families: tuple    # familias soportadas: ("arch",), ("debian", "ubuntu"), etc.
    is_supported: bool         # True si está en nuestra matriz de compatibilidad
    support_level: str         # "verified" | "assumed" | "unsupported"


class OSDetector:
    """Detecta distribución Linux y gestor de paquetes desde /etc/os-release."""

    # Mapeo ID -> (gestor, familias, nivel_soporte)
    DISTRO_MAP = {
        # Arch family
        "arch": ("pacman", ("arch",), "verified"),
        "manjaro": ("pacman", ("arch",), "assumed"),
        "endeavouros": ("pacman", ("arch",), "assumed"),
        "garuda": ("pacman", ("arch",), "assumed"),
        "artix": ("pacman", ("arch",), "assumed"),
        # Debian family
        "debian": ("apt", ("debian",), "verified"),
        "ubuntu": ("apt", ("debian",), "assumed"),
        "linuxmint": ("apt", ("debian",), "assumed"),
        "pop": ("apt", ("debian",), "assumed"),
        "kali": ("apt", ("debian",), "assumed"),
        "elementary": ("apt", ("debian",), "assumed"),
        "zorin": ("apt", ("debian",), "assumed"),
        # Fedora/RHEL family
        "fedora": ("dnf", ("fedora",), "assumed"),
        "rhel": ("dnf", ("fedora",), "assumed"),
        "centos": ("dnf", ("fedora",), "assumed"),
        "almalinux": ("dnf", ("fedora",), "assumed"),
        "rocky": ("dnf", ("fedora",), "assumed"),
        "nobara": ("dnf", ("fedora",), "assumed"),
        # Void
        "void": ("xbps", ("void",), "assumed"),
        # openSUSE
        "opensuse-tumbleweed": ("zypper", ("opensuse",), "unsupported"),
        "opensuse-leap": ("zypper", ("opensuse",), "unsupported"),
        # Alpine
        "alpine": ("apk", ("alpine",), "unsupported"),
        # Gentoo
        "gentoo": ("emerge", ("gentoo",), "unsupported"),
    }

    SUPPORTED_IDS = {
        "arch", "debian", "ubuntu", "fedora", "void",
        "manjaro", "endeavouros", "linuxmint", "pop", "almalinux", "rocky"
    }

    def __init__(self, os_release_path: str = "/etc/os-release"):
        self.os_release_path = os_release_path

    def detect(self) -> OSReport:
        """Detecta y retorna OSReport completo."""
        data = self._parse_os_release()
        distro_id = data.get("ID", "").lower()
        version_id = data.get("VERSION_ID", "")
        pretty_name = data.get("PRETTY_NAME", distro_id)

        # Normalizar ID (ej: "opensuse-tumbleweed" -> "opensuse")
        normalized_id = self._normalize_id(distro_id)

        pkg_manager, pkg_families, support_level = self.DISTRO_MAP.get(
            normalized_id, ("unknown", (), "unsupported")
        )

        is_supported = normalized_id in self.SUPPORTED_IDS

        return OSReport(
            id=normalized_id,
            name=data.get("NAME", distro_id),
            version=version_id or "rolling",
            version_id=version_id,
            pretty_name=pretty_name,
            package_manager=pkg_manager,
            package_families=pkg_families,
            is_supported=is_supported,
            support_level=support_level,
        )

    def _parse_os_release(self) -> dict:
        """Parsea /etc/os-release (formato key=value, sin dependencias externas)."""
        result = {}
        try:
            with open(self.os_release_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        # Quitar comillas
                        value = value.strip('"').strip("'")
                        result[key] = value
        except (OSError, IOError):
            pass
        return result

    def _normalize_id(self, distro_id: str) -> str:
        """Normaliza IDs compuestos."""
        if distro_id.startswith("opensuse"):
            return "opensuse-tumbleweed" if "tumbleweed" in distro_id else "opensuse-leap"
        return distro_id

    def get_package_families(self) -> tuple:
        """Retorna las familias de paquetes para esta distro."""
        report = self.detect()
        return report.package_families


def detect_os(os_release_path: str = "/etc/os-release") -> OSReport:
    """Función de conveniencia."""
    return OSDetector(os_release_path).detect()