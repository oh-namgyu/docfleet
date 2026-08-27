"""Error types carrying the docfleet exit-code contract.

Exit codes:
    0 -- success
    1 -- operation-level failure (partial link failure, skipped restore items)
    2 -- environment or configuration error (nothing was modified)
"""

from __future__ import annotations


class DocfleetError(Exception):
    """Base class for errors that map onto a documented exit code."""

    exit_code: int = 2


class ConfigError(DocfleetError):
    """Invalid environment, layout or configuration. Nothing has been changed."""

    exit_code: int = 2


class OperationError(DocfleetError):
    """An operation ran but could not complete every item."""

    exit_code: int = 1
