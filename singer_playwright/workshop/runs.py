"""Workshop run directories and artifact persistence."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def default_runs_root() -> Path:
    return Path.cwd() / "workshop-runs"


def default_session_dir() -> Path:
    return Path.cwd() / ".workshop"


def new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def create_run_dir(root: Path | None = None, run_id: str | None = None) -> tuple[Path, str]:
    run_id = run_id or new_run_id()
    run_dir = (root or default_runs_root()) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "steps").mkdir(exist_ok=True)
    return run_dir, run_id


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_step_artifact(run_dir: Path, step_number: int, name: str, payload: Any) -> Path:
    path = run_dir / "steps" / f"{step_number:03d}-{name}.json"
    write_json(path, payload)
    return path


def write_session_file(
    *,
    host: str,
    port: int,
    pid: int,
    run_id: str,
    run_dir: str,
    storage_state_path: str,
) -> Path:
    session_dir = default_session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / "session.json"
    write_json(
        session_path,
        {
            "host": host,
            "port": port,
            "pid": pid,
            "run_id": run_id,
            "run_dir": run_dir,
            "storage_state_path": storage_state_path,
            "started_at": datetime.now(UTC).isoformat(),
        },
    )
    return session_path


def load_session_file() -> dict[str, Any]:
    session_path = default_session_dir() / "session.json"
    if not session_path.is_file():
        msg = (
            "No workshop session found. Start one with:\n"
            "  uv run python -m singer_playwright workshop start --storage-state storage_state.json"
        )
        raise FileNotFoundError(msg)
    return read_json(session_path)


def clear_session_file() -> None:
    session_path = default_session_dir() / "session.json"
    if session_path.is_file():
        session_path.unlink()
