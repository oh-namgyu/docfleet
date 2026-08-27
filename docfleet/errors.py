"""Error types carrying the docfleet exit-code contract.

Exit codes:
    0 -- success
    1 -- operation-level failure (partial link failure, skipped restore items)
    2 -- environment or configuration error (nothing was modified)
"""

from __future__ import annotations


class DocfleetError(Exception):
    """Base class for errors that map onto a documented exit code.

    Extra keyword arguments become `details`, which `--json` output merges
    into the error document (for example the git `state` that caused it).
    """

    exit_code: int = 2

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.details: dict[str, object] = details


class ConfigError(DocfleetError):
    """Invalid environment, layout or configuration. Nothing has been changed."""

    exit_code: int = 2


class OperationError(DocfleetError):
    """An operation ran but could not complete every item."""

    exit_code: int = 1
