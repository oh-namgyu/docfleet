"""Small shared helpers: JSON files, timestamps, git facts and directory links."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .errors import ConfigError

TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"


def read_json(path: Path) -> Any:
    """Read a JSON document, raising ConfigError on missing or malformed files."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"malformed JSON in {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    """Write a JSON document with a trailing newline, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=False)
        handle.write("\n")


def today_iso() -> str:
    """Return the current local date as YYYY-MM-DD."""
    return date.today().isoformat()


def timestamp() -> str:
    """Return a filesystem-safe local timestamp (YYYYMMDD-HHMMSS)."""
    return datetime.now().strftime(TIMESTAMP_FORMAT)


def is_git_repo(path: Path) -> bool:
    """Return True when path is the root of a git working tree."""
    return (path / ".git").exists()


def git_origin(path: Path) -> str | None:
    """Return the origin remote URL of a repository, or None when unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    url = result.stdout.strip()
    return url or None


def repo_id(repo: Path, machine: str) -> str:
    """Return a stable 12-char id for a (repository, machine) pair."""
    key = git_origin(repo) or str(repo.resolve())
    digest = hashlib.sha256(f"{key}\n{machine}".encode("utf-8")).hexdigest()
    return digest[:12]


def backup_root() -> Path:
    """Return the root directory holding backups and manifests."""
    return Path(os.path.expanduser("~")) / ".docfleet" / "backup"


def expand_path(raw: str) -> Path:
    """Expand a user-supplied path (~ allowed) without resolving symlinks."""
    return Path(os.path.expanduser(raw))


def stable_path(path: Path) -> Path:
    """Resolve a path's parent only, so an existing link at path stays visible."""
    parent = path.parent
    try:
        real_parent = Path(os.path.realpath(str(parent)))
    except OSError:
        real_parent = parent
    return real_parent / path.name


def is_within(path: Path, parent: Path) -> bool:
    """Return True when path is parent itself or lives underneath it."""
    return path == parent or parent in path.parents


def is_link(path: Path) -> bool:
    """Return True for symlinks and (on Windows) directory junctions."""
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction is None:
        return False
    try:
        return bool(is_junction(str(path)))
    except OSError:
        return False


def link_destination(path: Path) -> Path | None:
    """Return the destination of a link, or None when path is not a link."""
    if not is_link(path):
        return None
    try:
        return Path(os.readlink(str(path)))
    except OSError:
        return None


def create_dir_link(source: Path, target: Path) -> None:
    """Create a directory link at target pointing to source.

    Windows uses a directory junction so that no elevated privilege is needed,
    falling back to a symlink when junctions are unavailable.
    """
    if os.name == "nt":
        try:
            import _winapi  # noqa: PLC0415 -- platform-specific import

            _winapi.CreateJunction(str(source), str(target))
            return
        except (ImportError, AttributeError, OSError):
            pass
    os.symlink(str(source), str(target), target_is_directory=True)


def remove_link(path: Path) -> None:
    """Remove a link without touching the directory it points at."""
    try:
        os.unlink(str(path))
    except OSError:
        os.rmdir(str(path))  # Windows junctions are removed as directories
