"""
Tests unitarios para detección de HW/SO y clasificación de perfiles.
"""

import json
import sys
from pathlib import Path

# Añadir src al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from thorrija.detect import (
    detect_os, detect_hardware, classify_hardware,
    OSDetector, HardwareDetector, ProfileClassifier,
    HardwareReport, OSReport,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "hardware"


def load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / f"{name}.json") as f:
        return json.load(f)


def test_os_detection_on_current_system():
    """Detección de SO en el sistema actual (debe ser Arch)."""
    report = detect_os()
    assert isinstance(report, OSReport)
    assert report.id in ("arch", "manjaro", "endeavouros")  # Arch family
    assert report.package_manager == "pacman"
    assert "arch" in report.package_families
    assert report.is_supported is True
    assert report.support_level == "verified"


def test_hardware_detection_on_current_system():
    """Detección de HW en el sistema actual."""
    report = detect_hardware()
    assert isinstance(report, HardwareReport)
    assert report.cpu.cores >= 1
    assert report.cpu.threads >= 1
    assert report.memory.total_mb > 0
    assert report.architecture in ("x86_64", "aarch64")
    assert len(report.gpus) >= 1
    assert len(report.disks) >= 1


def test_classify_current_system():
    """Clasificación del sistema actual."""
    hw = detect_hardware()
    profile = classify_hardware(hw)
    assert profile in ("low_end", "standard", "high_end")


def test_fixture_minimal_classifies_low_end():
    """Fixture hw-minimal debe clasificar como low_end."""
    data = load_fixture("hw-minimal")
    # Crear HardwareReport manualmente desde fixture
    from thorrija.detect.hw_detect import CPUInfo, MemoryInfo, GPUInfo, DiskInfo, HardwareReport

    hw = HardwareReport(
        cpu=CPUInfo(**data["cpu"]),
        memory=MemoryInfo(**data["memory"]),
        gpus=[GPUInfo(**g) for g in data["gpus"]],
        disks=[DiskInfo(**d) for d in data["disks"]],
        hostname=data["hostname"],
        kernel=data["kernel"],
        architecture=data["architecture"],
    )

    profile = classify_hardware(hw)
    assert profile == "low_end", f"Esperado low_end, got {profile}"


def test_fixture_integrated_classifies_standard():
    """Fixture hw-integrated debe clasificar como standard."""
    data = load_fixture("hw-integrated")
    from thorrija.detect.hw_detect import CPUInfo, MemoryInfo, GPUInfo, DiskInfo, HardwareReport

    hw = HardwareReport(
        cpu=CPUInfo(**data["cpu"]),
        memory=MemoryInfo(**data["memory"]),
        gpus=[GPUInfo(**g) for g in data["gpus"]],
        disks=[DiskInfo(**d) for d in data["disks"]],
        hostname=data["hostname"],
        kernel=data["kernel"],
        architecture=data["architecture"],
    )

    profile = classify_hardware(hw)
    assert profile == "standard", f"Esperado standard, got {profile}"


def test_fixture_standard_classifies_standard():
    """Fixture hw-standard debe clasificar como standard."""
    data = load_fixture("hw-standard")
    from thorrija.detect.hw_detect import CPUInfo, MemoryInfo, GPUInfo, DiskInfo, HardwareReport

    hw = HardwareReport(
        cpu=CPUInfo(**data["cpu"]),
        memory=MemoryInfo(**data["memory"]),
        gpus=[GPUInfo(**g) for g in data["gpus"]],
        disks=[DiskInfo(**d) for d in data["disks"]],
        hostname=data["hostname"],
        kernel=data["kernel"],
        architecture=data["architecture"],
    )

    profile = classify_hardware(hw)
    assert profile == "standard", f"Esperado standard, got {profile}"


def test_fixture_workstation_classifies_high_end():
    """Fixture hw-workstation debe clasificar como high_end."""
    data = load_fixture("hw-workstation")
    from thorrija.detect.hw_detect import CPUInfo, MemoryInfo, GPUInfo, DiskInfo, HardwareReport

    hw = HardwareReport(
        cpu=CPUInfo(**data["cpu"]),
        memory=MemoryInfo(**data["memory"]),
        gpus=[GPUInfo(**g) for g in data["gpus"]],
        disks=[DiskInfo(**d) for d in data["disks"]],
        hostname=data["hostname"],
        kernel=data["kernel"],
        architecture=data["architecture"],
    )

    profile = classify_hardware(hw)
    assert profile == "high_end", f"Esperado high_end, got {profile}"


def test_fixture_ai_classifies_high_end():
    """Fixture hw-ai debe clasificar como high_end."""
    data = load_fixture("hw-ai")
    from thorrija.detect.hw_detect import CPUInfo, MemoryInfo, GPUInfo, DiskInfo, HardwareReport

    hw = HardwareReport(
        cpu=CPUInfo(**data["cpu"]),
        memory=MemoryInfo(**data["memory"]),
        gpus=[GPUInfo(**g) for g in data["gpus"]],
        disks=[DiskInfo(**d) for d in data["disks"]],
        hostname=data["hostname"],
        kernel=data["kernel"],
        architecture=data["architecture"],
    )

    profile = classify_hardware(hw)
    assert profile == "high_end", f"Esperado high_end, got {profile}"


def test_profile_classifier_explain():
    """Verifica que la explicación de clasificación funciona."""
    data = load_fixture("hw-standard")
    from thorrija.detect.hw_detect import CPUInfo, MemoryInfo, GPUInfo, DiskInfo, HardwareReport

    hw = HardwareReport(
        cpu=CPUInfo(**data["cpu"]),
        memory=MemoryInfo(**data["memory"]),
        gpus=[GPUInfo(**g) for g in data["gpus"]],
        disks=[DiskInfo(**d) for d in data["disks"]],
        hostname=data["hostname"],
        kernel=data["kernel"],
        architecture=data["architecture"],
    )

    classifier = ProfileClassifier()
    explanations = classifier.explain_classification(hw)

    assert "low_end" in explanations
    assert "standard" in explanations
    assert "high_end" in explanations
    for name, info in explanations.items():
        assert "matches" in info
        assert "reasons" in info
        assert isinstance(info["reasons"], list)


def test_forced_profile_override():
    """Forzar perfil ignora auto-clasificación."""
    data = load_fixture("hw-minimal")
    from thorrija.detect.hw_detect import CPUInfo, MemoryInfo, GPUInfo, DiskInfo, HardwareReport

    hw = HardwareReport(
        cpu=CPUInfo(**data["cpu"]),
        memory=MemoryInfo(**data["memory"]),
        gpus=[GPUInfo(**g) for g in data["gpus"]],
        disks=[DiskInfo(**d) for d in data["disks"]],
        hostname=data["hostname"],
        kernel=data["kernel"],
        architecture=data["architecture"],
    )

    # Forzar high_end en hardware minimal
    profile = classify_hardware(hw, profile_name="high_end")
    assert profile == "high_end"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])