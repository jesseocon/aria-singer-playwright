"""RFC 6238 time-based one-time passwords (the 6-digit authenticator codes)."""

from __future__ import annotations

import base64
import hmac
import struct
import time

STEP_SECONDS = 30


def _key(secret: str) -> bytes:
    """Authenticator secrets are base32, often shown in groups with spaces."""
    cleaned = secret.replace(" ", "").replace("-", "").upper()
    if not cleaned:
        msg = "TOTP secret is empty"
        raise ValueError(msg)
    padded = cleaned + "=" * (-len(cleaned) % 8)
    try:
        return base64.b32decode(padded)
    except ValueError as exc:
        msg = "TOTP secret is not valid base32"
        raise ValueError(msg) from exc


def totp(
    secret: str,
    *,
    at: float | None = None,
    digits: int = 6,
    step: int = STEP_SECONDS,
    digest: str = "sha1",
) -> str:
    counter = int((time.time() if at is None else at) // step)
    mac = hmac.new(_key(secret), struct.pack(">Q", counter), digest).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def fresh_totp(secret: str, *, min_seconds_left: int = 5) -> str:
    """A code with time left to type it; waits for the next window when close to expiry."""
    left = STEP_SECONDS - time.time() % STEP_SECONDS
    if left < min_seconds_left:
        time.sleep(left + 0.5)
    return totp(secret)
