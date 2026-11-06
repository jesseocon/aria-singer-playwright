"""Video of a run's browser, when the person starting the run asked for one.

aria-runner sets ``ARIA_RECORD_VIDEO=1`` for such a run, next to ``ARIA_SCREENSHOT_DIR``. The
browser then records every page; when it closes, each recording is moved into the run's folder
and a notice names it (``code: video``), so the runner uploads it and the console plays it in
the run's log. Without both settings nothing is recorded. Like screenshots, a recording can
show what the vendor's page shows and stays in the deployment's private bucket.
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from singer_playwright import progress
from singer_playwright.screenshots import DIR_ENV

RECORD_ENV = "ARIA_RECORD_VIDEO"
# Small enough to keep a long run's recording to tens of MB, large enough to read a page.
SIZE = {"width": 1280, "height": 800}


def requested() -> bool:
    return os.environ.get(RECORD_ENV, "").strip().lower() in {"1", "true", "yes"} and bool(os.environ.get(DIR_ENV))


def recording_dir() -> Path | None:
    """A scratch folder for Playwright to record into, or None when this run records nothing."""
    if not requested():
        return None
    return Path(tempfile.mkdtemp(prefix="aria-video-"))


def keep(recordings: list[Path], logger: logging.Logger) -> list[str]:
    """Move finished recordings into the run's folder and report each one. Never raises."""
    folder = os.environ.get(DIR_ENV)
    names: list[str] = []
    if not folder:
        return names
    for index, path in enumerate(recordings, start=1):
        try:
            if not path.is_file() or path.stat().st_size == 0:
                continue
            suffix = "" if len(recordings) == 1 else f"-{index}"
            name = f"{datetime.now(UTC):%H%M%S%f}"[:9] + f"-browser{suffix}.webm"
            final = Path(folder) / name
            partial = final.with_name(final.name + ".part")
            _move(path, partial)
            # The runner uploads only complete files, so rename into place once written.
            os.replace(partial, final)
        except Exception:  # noqa: BLE001
            logger.debug("could not keep recording %s", path, exc_info=True)
            continue
        megabytes = final.stat().st_size / 1_000_000
        progress.report(logger, "notice", message=f"Video of the browser ({megabytes:.1f} MB)", code="video", video=name)
        names.append(name)
    return names


def _move(source: Path, target: Path) -> None:
    try:
        os.replace(source, target)
    except OSError:  # another filesystem
        import shutil

        shutil.move(str(source), str(target))
