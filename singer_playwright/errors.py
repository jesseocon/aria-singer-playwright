"""Framework-specific exceptions."""


class TransientError(Exception):
    """A failure that usually clears up on its own: a rate limit, a vendor outage.

    Raise it (or any exception with ``retryable = True``) once a tap's own retries have run
    out. The stream's error event then says ``"retryable": true``, and aria-runner queues
    the run again later instead of treating the failure as permanent.
    """

    retryable = True


class SessionInvalidError(Exception):
    """Raised when storage_state is missing or the session probe fails."""


class ReAuthRequiredError(SessionInvalidError):
    """Raised when the site redirected to login — manual re-auth is required."""

    def __init__(self, message: str | None = None) -> None:
        default = (
            "Session expired or missing. Run `python -m singer_playwright auth` "
            "to sign in manually, then retry."
        )
        super().__init__(message or default)
