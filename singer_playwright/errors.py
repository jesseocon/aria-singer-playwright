"""Framework-specific exceptions."""


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
