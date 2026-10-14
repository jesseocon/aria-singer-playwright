"""Localhost HTTP daemon for persistent Playwright workshop sessions."""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from singer_playwright.workshop.observe import clear_workshop_scripts_cache

from singer_playwright.workshop.recipe import RecipeExtract
from singer_playwright.workshop.runs import clear_session_file, write_session_file
from singer_playwright.workshop.session_state import WorkshopSessionState


class WorkshopDaemon:
    def __init__(
        self,
        *,
        storage_state_path: str,
        headless: bool = True,
        host: str = "127.0.0.1",
        port: int = 0,
        run_id: str = "",
        capture_types: tuple[str, ...] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.session = WorkshopSessionState(
            storage_state_path=storage_state_path,
            headless=headless,
            run_id=run_id,
        )
        if capture_types:
            self.session.capture_types = capture_types
        self.httpd: HTTPServer | None = None

    def start(self) -> dict[str, Any]:
        start_info = self.session.start()
        handler = _build_handler(self.session)
        self.httpd = HTTPServer((self.host, self.port), handler)
        actual_host, actual_port = self.httpd.server_address
        self.host = actual_host
        self.port = actual_port
        project_root = str(Path.cwd().resolve())
        os.environ.setdefault("MELTANO_PROJECT_ROOT", project_root)
        session_path = write_session_file(
            host=self.host,
            port=self.port,
            pid=os.getpid(),
            run_id=self.session.run_id,
            run_dir=str(self.session.run_dir),
            storage_state_path=self.session.storage_state_path,
            project_root=project_root,
        )
        return {
            "ok": True,
            "host": self.host,
            "port": self.port,
            "pid": os.getpid(),
            "run_id": self.session.run_id,
            "run_dir": str(self.session.run_dir),
            "session_file": str(session_path),
            **start_info,
        }

    def serve_forever(self) -> None:
        if self.httpd is None:
            msg = "Daemon not started"
            raise RuntimeError(msg)
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        self.session.stop()
        clear_session_file(pid=os.getpid())


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:  # noqa: ANN401
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    data = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(data, dict):
        msg = "Request body must be a JSON object"
        raise ValueError(msg)
    return data


def _build_handler(session: WorkshopSessionState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "run_id": session.run_id,
                        "run_dir": str(session.run_dir),
                    },
                )
                return
            _json_response(self, 404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = _read_json(self)
                if self.path == "/observe":
                    result = session.observe(
                        frame_index=payload.get("frame_index"),
                        frame_url_pattern=payload.get("frame_url_pattern"),
                        label=str(payload.get("label") or "current"),
                    )
                    _json_response(self, 200, {"ok": True, "result": result})
                    return

                if self.path == "/goto":
                    result = session.goto(
                        str(payload["url"]),
                        wait_until=str(payload.get("wait_until") or "domcontentloaded"),
                    )
                    _json_response(self, 200, {"ok": True, "result": result})
                    return

                if self.path == "/act":
                    params = payload.get("params")
                    if not isinstance(params, dict):
                        params = {k: v for k, v in payload.items() if k != "action"}
                    result = session.act(str(payload["action"]), **params)
                    _json_response(self, 200, {"ok": True, "result": result})
                    return

                if self.path == "/extract":
                    result = session.extract(
                        str(payload.get("extract_type") or payload.get("type") or "table"),
                        selector=payload.get("selector"),
                        frame_index=payload.get("frame_index"),
                        frame_url_pattern=payload.get("frame_url_pattern"),
                        limit=int(payload.get("limit") or 50),
                    )
                    _json_response(self, 200, {"ok": True, "result": result})
                    return

                if self.path == "/screenshot":
                    result = session.screenshot(name=str(payload.get("name") or "screenshot"))
                    _json_response(self, 200, {"ok": True, "result": result})
                    return

                if self.path == "/recipe/save":
                    extract = RecipeExtract.from_dict(payload.get("extract") or {})
                    result = session.save_recipe(
                        brief_dict=dict(payload.get("brief") or {}),
                        extract=extract,
                        sample_records=list(payload.get("sample_records") or []),
                        output_path=payload.get("output_path"),
                    )
                    _json_response(self, 200, {"ok": True, "result": result})
                    return

                if self.path == "/network/mark":
                    result = session.network_mark(str(payload["label"]))
                    _json_response(self, 200, {"ok": True, "result": result})
                    return

                if self.path == "/network/catalog":
                    result = session.network_catalog(
                        since_mark=payload.get("since_mark"),
                        host_pattern=payload.get("host_pattern"),
                    )
                    _json_response(self, 200, {"ok": True, "result": result})
                    return

                if self.path == "/network/show":
                    result = session.network_show(
                        int(payload["seq"]),
                        preview_chars=int(payload.get("preview_chars", 2000)),
                    )
                    _json_response(self, 200, {"ok": True, "result": result})
                    return

                if self.path == "/network/replay":
                    result = session.network_replay(
                        int(payload["seq"]),
                        query=payload.get("query"),
                        json_patch=payload.get("json_patch"),
                        body=payload.get("body"),
                        url=payload.get("url"),
                        method=payload.get("method"),
                        preview_chars=int(payload.get("preview_chars", 1000)),
                    )
                    _json_response(self, 200, {"ok": True, "result": result})
                    return

                if self.path == "/stop":
                    session.stop()
                    clear_session_file(pid=os.getpid())
                    _json_response(self, 200, {"ok": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return

                _json_response(self, 404, {"ok": False, "error": "not found"})
            except Exception as exc:  # noqa: BLE001
                _json_response(self, 500, {"ok": False, "error": str(exc)})

    return Handler


def run_daemon(
    *,
    storage_state_path: str,
    headless: bool = True,
    host: str = "127.0.0.1",
    port: int = 18742,
    detach: bool = False,
    capture_types: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if detach:
        pid = os.fork()
        if pid > 0:
            return {"ok": True, "detached": True, "pid": pid}
        os.setsid()

    clear_workshop_scripts_cache()
    daemon = WorkshopDaemon(
        storage_state_path=storage_state_path,
        headless=headless,
        host=host,
        port=port,
        capture_types=capture_types,
    )

    def handle_signal(_signum: int, _frame: object) -> None:
        # Runs on the serve_forever thread, so httpd.shutdown() here would deadlock.
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    info = daemon.start()
    print(json.dumps(info), flush=True)
    try:
        daemon.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if daemon.httpd is not None:
            daemon.httpd.server_close()
            daemon.httpd = None
        daemon.session.stop()
        clear_session_file(pid=os.getpid())
    if detach:
        sys.exit(0)
    return info
