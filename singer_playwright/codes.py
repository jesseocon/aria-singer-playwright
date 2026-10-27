"""Wait for a sign-in code a vendor emailed, during an aria-runner run.

Some logins email a one-time code (e.g. Okta's email factor). A forwarding rule sends those
emails to Aria's code inbox, and the run's code broker hands the newest code for the login's
inbox address to the tap (aria_runner.codes). From the tap:

    asked = datetime.now(UTC)
    page.click("text=Send code")
    code = wait_for_code("wyndham-okta@codes.aria-ingest.com", after=asked)

Outside a run (no ARIA_CODE_DIR) there is no code inbox, so this raises CodeUnavailable.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime
from pathlib import Path

DIR_ENV = "ARIA_CODE_DIR"


class CodeUnavailable(RuntimeError):
    """No code arrived in time, or this run cannot read the inbox."""


def wait_for_code(address: str, *, after: datetime, timeout_s: float = 180, poll_s: float = 2.0) -> str:
    """The newest code emailed to `address` since `after` (a timezone-aware time). Used once."""
    folder = os.environ.get(DIR_ENV)
    if not folder:
        msg = "no code inbox in this environment (run it through aria-runner)"
        raise CodeUnavailable(msg)
    name = f"code-{secrets.token_hex(6)}"
    request = Path(folder) / f"{name}.request"
    answer = Path(folder) / f"{name}.code"
    partial = request.with_name(request.name + ".part")
    partial.write_text(json.dumps({"address": address, "after": after.isoformat()}))
    os.replace(partial, request)
    deadline = time.monotonic() + timeout_s
    try:
        while time.monotonic() < deadline:
            if answer.exists():
                payload = json.loads(answer.read_text())
                if "error" in payload:
                    raise CodeUnavailable(str(payload["error"]))
                return str(payload["code"])
            time.sleep(poll_s)
    finally:
        request.unlink(missing_ok=True)
        answer.unlink(missing_ok=True)
    msg = f"no code reached {address} within {int(timeout_s)}s"
    raise CodeUnavailable(msg)
