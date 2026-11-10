"""
Tests de integración: flujo completo detect → plan → dry-run.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from thorrija.detect import detect_os, detect_hardware, classify_hardware
from thorrija.catalog import load_catalog
from thorrija.plan import create_plan
from thorrija.state import AuditLog, StateStore, BackupManager


CATALOG_DIR = Path(__file__).parent.parent.parent / "catalog"
FIXTURES_DIR = Path(__file__).parent.parent / "unit" / "fixtures" / "hardware"


def load_fixture_hw(name: str):
    with open(FIXTURES_DIR / f"{name}.json") as f:
        data = json.load(f)
    from thorrija.detect.hw_detect import CPUInfo, MemoryInfo, GPUInfo, DiskInfo, HardwareReport
    return HardwareReport(
        cpu=CPUInfo(**data["cpu"]),
        memory=MemoryInfo(**data["memory"]),
        gpus=[GPUInfo(**g) for g in data["gpus"]],
        disks=[DiskInfo(**d) for d in data["disks"]],
        hostname=data["hostname"],
        kernel=data["kernel"],
        architecture=data["architecture"],
    )


def test_full_flow_minimal_low_end():
    """Flujo completo: hw minimal → low_end → plan con herramientas enabled."""
    hw = load_fixture_hw("hw-minimal")
    os_report = detect_os()
    profile = classify_hardware(hw)
    assert profile == "low_end"

    manifests = load_catalog(str(CATALOG_DIR))
    plan = create_plan(manifests, hw, os_report, profile)

    enabled = plan.get_enabled_entries()
    names = {e.tool.name for e in enabled}
    assert "git" in names
    assert "python" in names
    assert "ollama" not in names  # excluded en low_end

    # Ollama excluido
    excluded = plan.get_excluded_entries()
    excl_names = {e.tool.name for e in excluded}
    assert "ollama" in excl_names


def test_full_flow_standard():
    """Flujo completo: hw standard → standard → plan con herramientas enabled + optional."""
    hw = load_fixture_hw("hw-standard")
    os_report = detect_os()
    profile = classify_hardware(hw)
    assert profile == "standard"

    manifests = load_catalog(str(CATALOG_DIR))
    plan = create_plan(manifests, hw, os_report, profile, include_optional=True)

    enabled = plan.get_enabled_entries()
    names = {e.tool.name for e in enabled}
    assert "git" in names
    assert "python" in names
    assert "ollama" in names  # optional en standard


def test_full_flow_high_end_workstation():
    """Flujo completo: workstation → high_end → plan completo."""
    hw = load_fixture_hw("hw-workstation")
    os_report = detect_os()
    profile = classify_hardware(hw)
    assert profile == "high_end"

    manifests = load_catalog(str(CATALOG_DIR))
    plan = create_plan(manifests, hw, os_report, profile)

    enabled = plan.get_enabled_entries()
    names = {e.tool.name for e in enabled}
    assert "git" in names
    assert "python" in names
    assert "ollama" in names

    # Verificar compatibilidad óptima para ollama
    ollama_entry = next(e for e in plan.entries if e.tool.name == "ollama")
    assert ollama_entry.compatibility.value in ("optimal", "recommended")


def test_full_flow_ai_hardware():
    """Flujo completo: hw AI → high_end → ollama óptimo."""
    hw = load_fixture_hw("hw-ai")
    os_report = detect_os()
    profile = classify_hardware(hw)
    assert profile == "high_end"

    manifests = load_catalog(str(CATALOG_DIR))
    plan = create_plan(manifests, hw, os_report, profile)

    ollama_entry = next(e for e in plan.entries if e.tool.name == "ollama")
    assert ollama_entry.compatibility.value == "optimal"
    # En Arch, ollama usa native -> descarga 0, pero disco > 500
    assert ollama_entry.estimated_disk_mb > 500


def test_audit_log_integration():
    """Integración con AuditLog durante dry-run simulado."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / "log"
        audit = AuditLog(log_dir)
        audit.start_session("integration-test")

        hw = load_fixture_hw("hw-standard")
        os_report = detect_os()
        manifests = load_catalog(str(CATALOG_DIR))
        plan = create_plan(manifests, hw, os_report, "standard")

        # Simular logging de cada herramienta
        for entry in plan.entries:
            if entry.status == "will_install":
                audit.log_action(
                    tool=entry.tool.name,
                    action=f"install_{entry.method}",
                    result="installed" if not plan.dry_run else "pending",
                    method=entry.method,
                    duration_ms=100,
                    verify_command=entry.tool.verify_command,
                    verify_pattern=entry.tool.verify_pattern,
                    verify_ok=True,
                )

        entries = audit.read_session("integration-test")
        assert len(entries) >= 2
        tools = {e["tool"] for e in entries}
        assert "git" in tools
        assert "python" in tools


def test_state_store_integration():
    """Integración con StateStore."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / "state"
        store = StateStore(state_dir)

        hw = load_fixture_hw("hw-standard")
        os_report = detect_os()
        manifests = load_catalog(str(CATALOG_DIR))
        plan = create_plan(manifests, hw, os_report, "standard")

        # Simular guardado de estado tras instalación
        for entry in plan.entries:
            if entry.status == "will_install":
                from thorrija.state import ToolState
                store.set(ToolState(
                    name=entry.tool.name,
                    status="installed",
                    method=entry.method,
                    verify_ok=True,
                ))

        all_states = store.list_all()
        assert len(all_states) >= 2
        assert "git" in all_states
        assert "python" in all_states


def test_backup_manager_integration():
    """Integración con BackupManager (simulado)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_root = Path(tmpdir) / "backups"
        home = Path(tmpdir) / "home" / "user"
        home.mkdir(parents=True)

        # Crear archivos de config simulados
        (home / ".bashrc").write_text("# bashrc original")
        (home / ".config" / "fish" / "config.fish").parent.mkdir(parents=True)
        (home / ".config" / "fish" / "config.fish").write_text("# fish config")

        from thorrija.state import BackupManager
        bm = BackupManager(backup_root)
        bm.start_session()

        # Backup antes de "modificar" dotfiles
        bm.backup_file(home / ".bashrc")
        bm.backup_file(home / ".config" / "fish" / "config.fish")
        bm.save_manifest()

        # Verificar manifiesto
        manifest = json.loads((bm.current_session / "manifest.json").read_text())
        assert len(manifest["files_backed_up"]) == 2


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])