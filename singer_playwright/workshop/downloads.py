"""Capture file downloads (CSV/Excel exports) triggered in workshop pages."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "download"


def sniff_format(head: bytes) -> str:
    if head.startswith(ZIP_MAGIC):
        return "zip"
    if head.startswith(OLE_MAGIC):
        return "ole"
    if head.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        return "text"
    sample = head[:2048]
    if not sample or b"\x00" in sample:
        return "binary"
    return "text"


def text_preview(data: bytes, max_chars: int) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16", errors="replace")
    else:
        text = data.decode("utf-8-sig", errors="replace")
    return text[:max_chars]


class DownloadRecorder:
    """Saves every download from any page in the context to ``<run_dir>/downloads``.

    Download events only arrive while the daemon is inside a Playwright call, so
    events are queued and saved on the next ``flush`` rather than in the handler.
    """

    def __init__(self, out_dir: Path, *, preview_chars: int = 1500) -> None:
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(out_dir, 0o700)
        self.log_path = out_dir / "downloads.jsonl"
        self.preview_chars = preview_chars
        self.entries: list[dict[str, Any]] = []
        self.seq = 0
        self._pending: list[Any] = []

    def attach(self, context: Any) -> None:  # noqa: ANN401
        for page in context.pages:
            self._watch_page(page)
        context.on("page", self._watch_page)

    def _watch_page(self, page: Any) -> None:  # noqa: ANN401
        page.on("download", self._on_download)

    def _on_download(self, download: Any) -> None:  # noqa: ANN401
        self._pending.append(download)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def flush(self) -> list[dict[str, Any]]:
        saved = []
        while self._pending:
            saved.append(self._save(self._pending.pop(0)))
        return saved

    def wait_for_next(self, page: Any, *, timeout_ms: int, name: str | None = None) -> dict[str, Any]:  # noqa: ANN401
        """Block until a queued download exists, then save it (optionally renamed)."""
        deadline = time.time() + timeout_ms / 1000
        while not self._pending:
            if time.time() >= deadline:
                msg = f"No download started within {timeout_ms} ms"
                raise TimeoutError(msg)
            page.wait_for_timeout(250)
        return self._save(self._pending.pop(0), name=name)

    def _save(self, download: Any, *, name: str | None = None) -> dict[str, Any]:  # noqa: ANN401
        self.seq += 1
        seq = self.seq
        suggested = str(download.suggested_filename or "download")
        filename = _safe_name(name) if name else _safe_name(suggested)
        if not Path(filename).suffix and Path(suggested).suffix:
            filename += Path(suggested).suffix
        path = self.out_dir / f"{seq:03d}-{filename}"

        entry: dict[str, Any] = {
            "seq": seq,
            "at": _now(),
            "url": download.url,
            "suggested_filename": suggested,
            "path": str(path),
        }
        failure = download.failure()
        if failure:
            entry["failure"] = failure
        else:
            download.save_as(str(path))
            os.chmod(path, 0o600)
            data = path.read_bytes()
            fmt = sniff_format(data[:4096])
            entry["bytes"] = len(data)
            entry["format"] = fmt
            if fmt == "text":
                entry["preview"] = text_preview(data, self.preview_chars)

        self.entries.append(entry)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")
        return entry

    def list(self) -> dict[str, Any]:
        self.flush()
        return {"count": len(self.entries), "dir": str(self.out_dir), "downloads": self.entries}
