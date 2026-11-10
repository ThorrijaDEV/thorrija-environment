"""
Tests unitarios para estado: auditoría, backups, estado de herramientas.
"""

import json
import tempfile
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from thorrija.state import AuditLog, AuditEntry, StateStore, ToolState, BackupManager


def test_audit_log_write_read():
    """Escribe y lee entradas de auditoría."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / "log"
        audit = AuditLog(log_dir)

        session = audit.start_session("test-session")
        assert session.exists()

        audit.log_action(
            tool="git",
            action="install_native",
            result="installed",
            method="native",
            files_changed=["/usr/bin/git"],
            stdout="git version 2.40.0",
            stderr="",
            duration_ms=1000,
            verify_command="git --version",
            verify_pattern="git version",
            verify_ok=True,
        )

        entries = audit.read_session("test-session")
        assert len(entries) == 1
        e = entries[0]
        assert e["tool"] == "git"
        assert e["action"] == "install_native"
        assert e["result"] == "installed"
        assert e["method"] == "native"
        assert e["verify"]["ok"] is True
        assert e["stdout_sha256"] != ""


def test_audit_log_multiple_sessions():
    """Múltiples sesiones de auditoría."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / "log"
        audit = AuditLog(log_dir)

        audit.start_session("session-1")
        audit.log_action(tool="git", action="install", result="installed", method="native")

        audit.start_session("session-2")
        audit.log_action(tool="python", action="install", result="installed", method="native")

        sessions = audit.list_sessions()
        assert len(sessions) == 2
        assert "session-2" in sessions
        assert "session-1" in sessions


def test_state_store_get_set():
    """StateStore guarda y recupera estado."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / "state"
        store = StateStore(state_dir)

        state = ToolState(
            name="git",
            status="installed",
            method="native",
            version="2.40.0",
            installed_at="2026-01-01T00:00:00",
            verify_ok=True,
        )
        store.set(state)

        retrieved = store.get("git")
        assert retrieved is not None
        assert retrieved.name == "git"
        assert retrieved.status == "installed"
        assert retrieved.version == "2.40.0"

        # Update status
        store.update_status("git", "configured", verify_ok=True)
        retrieved = store.get("git")
        assert retrieved.status == "configured"


def test_state_store_list_all():
    """StateStore lista todos los estados."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / "state"
        store = StateStore(state_dir)

        store.set(ToolState(name="git", status="installed", method="native"))
        store.set(ToolState(name="python", status="installed", method="native"))
        store.set(ToolState(name="ollama", status="pending", method="binary_release"))

        all_states = store.list_all()
        assert len(all_states) == 3
        assert set(all_states.keys()) == {"git", "python", "ollama"}


def test_state_store_clear():
    """StateStore limpia estado individual."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / "state"
        store = StateStore(state_dir)

        store.set(ToolState(name="git", status="installed"))
        store.clear("git")
        assert store.get("git") is None


def test_backup_manager_backup_file():
    """BackupManager hace backup de archivo existente."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_root = Path(tmpdir) / "backups"
        source_dir = Path(tmpdir) / "home" / "user"
        source_dir.mkdir(parents=True)

        source_file = source_dir / ".bashrc"
        source_file.write_text("original content")

        bm = BackupManager(backup_root)
        bm.start_session()

        backup_path = bm.backup_file(source_file)
        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.read_text() == "original content"

        # Verificar estructura
        assert "home/user/.bashrc" in str(backup_path.relative_to(bm.current_session))


def test_backup_manager_backup_if_exists():
    """Backup solo si archivo existe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_root = Path(tmpdir) / "backups"
        bm = BackupManager(backup_root)
        bm.start_session()

        nonexistent = Path(tmpdir) / "home" / "user" / ".nonexistent"
        result = bm.backup_if_exists(nonexistent)
        assert result is None


def test_backup_manager_manifest():
    """BackupManager genera manifiesto de sesión."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_root = Path(tmpdir) / "backups"
        source_dir = Path(tmpdir) / "home" / "user"
        source_dir.mkdir(parents=True)

        (source_dir / ".bashrc").write_text("bash config")
        (source_dir / ".config" / "fish" / "config.fish").parent.mkdir(parents=True)
        (source_dir / ".config" / "fish" / "config.fish").write_text("fish config")

        bm = BackupManager(backup_root)
        bm.start_session()
        bm.backup_file(source_dir / ".bashrc")
        bm.backup_file(source_dir / ".config" / "fish" / "config.fish")
        bm.save_manifest()

        manifest_path = bm.current_session / "manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert manifest["timestamp"] == bm.current_session.name
        assert len(manifest["files_backed_up"]) == 2
        orig_paths = {f["original"] for f in manifest["files_backed_up"]}
        assert str(source_dir / ".bashrc") in orig_paths


def test_audit_entry_serialization():
    """AuditEntry se serializa a JSON line correctamente."""
    entry = AuditEntry(
        ts="2026-01-01T00:00:00",
        tool="git",
        action="install_native",
        result="installed",
        method="native",
        files_changed=["/usr/bin/git"],
        stdout_sha256="abc123",
        stderr_sha256="",
        duration_ms=1000,
        verify={"command": "git --version", "pattern": "git version", "ok": True},
    )

    line = entry.to_json_line()
    parsed = json.loads(line)
    assert parsed["tool"] == "git"
    assert parsed["result"] == "installed"
    assert parsed["verify"]["ok"] is True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])