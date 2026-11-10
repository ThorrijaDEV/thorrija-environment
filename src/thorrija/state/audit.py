"""
Gestión de estado: log de auditoría, backups, estado por herramienta.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import threading


@dataclass
class AuditEntry:
    """Entrada individual en el log de auditoría."""
    ts: str
    tool: str
    action: str
    result: str
    method: str
    files_changed: List[str] = field(default_factory=list)
    stdout_sha256: str = ""
    stderr_sha256: str = ""
    duration_ms: int = 0
    verify: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class AuditLog:
    """Log de auditoría inmutable (JSON Lines)."""

    def __init__(self, log_dir: Optional[Path] = None):
        if log_dir is None:
            log_dir = Path.home() / ".local" / "share" / "thorrija" / "log"
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_log: Optional[Path] = None
        self._lock = threading.Lock()

    def start_session(self, session_id: Optional[str] = None) -> Path:
        """Inicia nueva sesión de log."""
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.current_log = self.log_dir / f"{session_id}.jsonl"
        # Crear archivo vacío
        self.current_log.touch()
        return self.current_log

    def log(self, entry: AuditEntry) -> None:
        """Escribe entrada al log actual."""
        if self.current_log is None:
            self.start_session()
        with self._lock:
            with open(self.current_log, "a", encoding="utf-8") as f:
                f.write(entry.to_json_line() + "\n")

    def log_action(
        self,
        tool: str,
        action: str,
        result: str,
        method: str,
        files_changed: Optional[List[str]] = None,
        stdout: str = "",
        stderr: str = "",
        duration_ms: int = 0,
        verify_ok: bool = False,
        verify_command: str = "",
        verify_pattern: str = "",
        error: str = "",
    ) -> None:
        """Helper para loguear acción típica."""
        import hashlib
        entry = AuditEntry(
            ts=datetime.now().isoformat(),
            tool=tool,
            action=action,
            result=result,
            method=method,
            files_changed=files_changed or [],
            stdout_sha256=hashlib.sha256(stdout.encode()).hexdigest() if stdout else "",
            stderr_sha256=hashlib.sha256(stderr.encode()).hexdigest() if stderr else "",
            duration_ms=duration_ms,
            verify={
                "command": verify_command,
                "pattern": verify_pattern,
                "ok": verify_ok,
            } if verify_command else {},
            error=error,
        )
        self.log(entry)

    def read_session(self, session_id: str) -> List[Dict]:
        """Lee todas las entradas de una sesión."""
        log_file = self.log_dir / f"{session_id}.jsonl"
        if not log_file.exists():
            return []
        entries = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def list_sessions(self) -> List[str]:
        """Lista IDs de sesiones disponibles."""
        sessions = []
        for f in self.log_dir.glob("*.jsonl"):
            sessions.append(f.stem)
        return sorted(sessions, reverse=True)


@dataclass
class ToolState:
    """Estado persistente de una herramienta."""
    name: str
    status: str = "pending"          # pending, installed, configured, failed, skipped
    method: str = ""
    version: str = ""
    installed_at: str = ""
    verify_ok: bool = False
    verify_output: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "ToolState":
        return cls(**data)


class StateStore:
    """Almacén de estado por herramienta (JSON por herramienta)."""

    def __init__(self, state_dir: Optional[Path] = None):
        if state_dir is None:
            state_dir = Path.home() / ".local" / "share" / "thorrija" / "state"
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, tool_name: str) -> Path:
        return self.state_dir / f"{tool_name}.json"

    def get(self, tool_name: str) -> Optional[ToolState]:
        path = self._path(tool_name)
        if not path.exists():
            return None
        with self._lock:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        return ToolState.from_dict(data)

    def set(self, state: ToolState) -> None:
        path = self._path(state.name)
        with self._lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)

    def update_status(self, tool_name: str, status: str, **kwargs) -> None:
        state = self.get(tool_name) or ToolState(name=tool_name)
        state.status = status
        for k, v in kwargs.items():
            if hasattr(state, k):
                setattr(state, k, v)
        self.set(state)

    def list_all(self) -> Dict[str, ToolState]:
        states = {}
        for f in self.state_dir.glob("*.json"):
            tool = f.stem
            state = self.get(tool)
            if state:
                states[tool] = state
        return states

    def clear(self, tool_name: str) -> None:
        path = self._path(tool_name)
        if path.exists():
            path.unlink()


class BackupManager:
    """Gestiona backups de archivos antes de modificarlos."""

    def __init__(self, backup_root: Optional[Path] = None):
        if backup_root is None:
            backup_root = Path.home() / ".thorrija-backup"
        self.backup_root = backup_root
        self.current_session: Optional[Path] = None
        self._backed_up: Dict[str, Path] = {}  # original -> backup

    def start_session(self) -> Path:
        """Inicia sesión de backup."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.current_session = self.backup_root / timestamp
        self.current_session.mkdir(parents=True, exist_ok=True)
        return self.current_session

    def backup_file(self, source: Path) -> Optional[Path]:
        """Hace backup de un archivo si existe y no está ya backupeado."""
        if not source.exists():
            return None

        source = source.resolve()
        if source in self._backed_up:
            return self._backed_up[source]

        if self.current_session is None:
            self.start_session()

        # Ruta relativa preservando estructura
        try:
            rel = source.relative_to(Path.home())
            dest = self.current_session / "home" / rel
        except ValueError:
            # Fuera de home (ej. /etc)
            rel = source.relative_to("/")
            dest = self.current_session / "root" / rel

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        self._backed_up[source] = dest
        return dest

    def backup_if_exists(self, source: Path) -> Optional[Path]:
        """Backup solo si el archivo existe."""
        if source.exists():
            return self.backup_file(source)
        return None

    def get_session_manifest(self) -> Dict:
        """Genera manifiesto de la sesión actual."""
        if not self.current_session:
            return {}

        files = []
        for orig, backup in self._backed_up.items():
            files.append({
                "original": str(orig),
                "backup": str(backup.relative_to(self.current_session)),
            })

        return {
            "timestamp": self.current_session.name,
            "session_dir": str(self.current_session),
            "files_backed_up": files,
        }

    def save_manifest(self) -> None:
        """Guarda manifiesto en la sesión."""
        if self.current_session:
            manifest = self.get_session_manifest()
            manifest_path = self.current_session / "manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

    def list_sessions(self) -> List[Path]:
        return sorted([p for p in self.backup_root.iterdir() if p.is_dir()], reverse=True)