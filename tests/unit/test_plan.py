"""
Tests unitarios para planificador de instalaciones.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from thorrija.detect import detect_hardware, HardwareReport
from thorrija.catalog import load_catalog
from thorrija.plan import create_plan, InstallationPlan, CompatibilityClass


CATALOG_DIR = Path(__file__).parent.parent.parent / "catalog"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "hardware"


def load_fixture(name: str) -> HardwareReport:
    with open(FIXTURES_DIR / f"{name}.json") as f:
        data = json.load(f)
    from thorrija.detect.hw_detect import CPUInfo, MemoryInfo, GPUInfo, DiskInfo
    return HardwareReport(
        cpu=CPUInfo(**data["cpu"]),
        memory=MemoryInfo(**data["memory"]),
        gpus=[GPUInfo(**g) for g in data["gpus"]],
        disks=[DiskInfo(**d) for d in data["disks"]],
        hostname=data["hostname"],
        kernel=data["kernel"],
        architecture=data["architecture"],
    )


def test_create_plan_basic():
    """Creación básica de plan con catálogo completo."""
    manifests = load_catalog(str(CATALOG_DIR))
    hw = detect_hardware()

    from thorrija.detect import detect_os
    os_report = detect_os()

    plan = create_plan(manifests, hw, os_report, "standard")
    assert isinstance(plan, InstallationPlan)
    assert plan.profile == "standard"
    assert len(plan.entries) >= 50  # catálogo completo


def test_plan_minimal_profile_excludes_ollama():
    """Perfil low_end excluye ollama y herramientas pesadas."""
    manifests = load_catalog(str(CATALOG_DIR))
    hw = load_fixture("hw-minimal")

    from thorrija.detect import detect_os
    os_report = detect_os()

    plan = create_plan(manifests, hw, os_report, "low_end")
    enabled = plan.get_enabled_entries()
    names = {e.tool.name for e in enabled}
    assert "ollama" not in names
    assert "git" in names
    assert "python" in names
    # Verificar que solo herramientas enabled en low_end
    for e in enabled:
        assert e.tool.get_profile_status("low_end") == "enabled"


def test_plan_high_end_includes_ollama():
    """Perfil high_end incluye ollama."""
    manifests = load_catalog(str(CATALOG_DIR))
    hw = load_fixture("hw-workstation")

    from thorrija.detect import detect_os
    os_report = detect_os()

    plan = create_plan(manifests, hw, os_report, "high_end")
    enabled = plan.get_enabled_entries()
    names = {e.tool.name for e in enabled}
    assert "ollama" in names
    assert "git" in names
    assert "python" in names


def test_plan_compatibility_classes():
    """Verifica clases de compatibilidad asignadas."""
    manifests = load_catalog(str(CATALOG_DIR))
    hw = load_fixture("hw-standard")

    from thorrija.detect import detect_os
    os_report = detect_os()

    plan = create_plan(manifests, hw, os_report, "standard")

    for entry in plan.entries:
        assert entry.compatibility in CompatibilityClass
        # git y python deberían ser al menos COMPATIBLE
        if entry.tool.name in ("git", "python"):
            assert entry.compatibility != CompatibilityClass.INCOMPATIBLE


def test_plan_ollama_incompatible_on_low_ram():
    """Ollama incompatible en hw con poca RAM."""
    manifests = load_catalog(str(CATALOG_DIR))
    hw = load_fixture("hw-minimal")  # 2 GB RAM

    from thorrija.detect import detect_os
    os_report = detect_os()

    plan = create_plan(manifests, hw, os_report, "standard")
    ollama_entry = next(e for e in plan.entries if e.tool.name == "ollama")
    assert ollama_entry.compatibility == CompatibilityClass.INCOMPATIBLE
    assert any("RAM" in r for r in ollama_entry.incompatibility_reasons)


def test_plan_estimates_resources():
    """Plan estima recursos de descarga y disco."""
    manifests = load_catalog(str(CATALOG_DIR))
    hw = load_fixture("hw-workstation")

    from thorrija.detect import detect_os
    os_report = detect_os()

    plan = create_plan(manifests, hw, os_report, "high_end")

    assert plan.total_disk_mb > 0
    assert plan.total_disk_mb >= sum(e.estimated_disk_mb for e in plan.entries)
    # En Arch, ollama usa native (pacman) -> descarga 0
    # El test verifica que el cálculo de disco funciona


def test_plan_sudo_detection():
    """Detección de operaciones que requieren sudo."""
    manifests = load_catalog(str(CATALOG_DIR))
    hw = detect_hardware()

    from thorrija.detect import detect_os
    os_report = detect_os()

    plan = create_plan(manifests, hw, os_report, "standard")

    # git y python requieren sudo (native, privileged=true)
    sudo_entries = [e for e in plan.entries if e.requires_sudo]
    sudo_names = {e.tool.name for e in sudo_entries}
    assert "git" in sudo_names
    assert "python" in sudo_names

    # ollama no requiere sudo (privileged=false)
    ollama_entry = next(e for e in plan.entries if e.tool.name == "ollama")
    assert ollama_entry.requires_sudo is False


def test_plan_dry_run_flag():
    """Flag dry_run en plan."""
    manifests = load_catalog(str(CATALOG_DIR))
    hw = detect_hardware()

    from thorrija.detect import detect_os
    os_report = detect_os()

    plan = create_plan(manifests, hw, os_report, "standard")
    assert plan.dry_run is True  # default

    # Simular --yes
    plan2 = create_plan(manifests, hw, os_report, "standard")
    plan2.dry_run = False
    assert plan2.dry_run is False


def test_plan_sort_order():
    """Orden del plan: will_install primero, por compatibilidad."""
    manifests = load_catalog(str(CATALOG_DIR))
    hw = load_fixture("hw-workstation")

    from thorrija.detect import detect_os
    os_report = detect_os()

    plan = create_plan(manifests, hw, os_report, "high_end")

    # Verificar orden: will_install antes que optional/excluded
    statuses = [e.status for e in plan.entries]
    # will_install debe aparecer antes que optional/excluded
    first_optional = next((i for i, s in enumerate(statuses) if s == "optional"), len(statuses))
    first_excluded = next((i for i, s in enumerate(statuses) if s == "excluded"), len(statuses))
    last_will_install = max((i for i, s in enumerate(statuses) if s == "will_install"), default=-1)

    assert last_will_install < first_optional
    assert last_will_install < first_excluded


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])