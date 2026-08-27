"""Backup manifests: the durable record of what `docfleet link` changed.

One run writes at most one manifest::

    ~/.docfleet/backup/<repo-id>/<ts>/manifest.json
    ~/.docfleet/backup/<repo-id>/<ts>/<n>/<displaced directory>

Manifest schema::

    {"version": 1, "repo": "<absolute path>", "machine": "laptop",
     "ts": "20260131-101500",
     "items": [{"source": "memory", "target": "/home/u/.agent/memory",
                "mode": "backup|adopt|none",
                "state": "pending|linked|failed|restored|skipped",
                "backup_path": "<absolute path or null>"}]}

States:
    pending  -- the item was started; a crash left it half-applied
    linked   -- the link exists and any displaced data is recorded
    failed   -- the item could not be completed; restore can still undo it
    restored -- the item has been reversed; restore never touches it again
    skipped  -- restore could not reverse the item yet because something new
                occupies the target; a later restore retries it

Only items this run actually changed are recorded. Links that were already
correct are reported but stay out of the manifest, so restoring a run never
removes a link some earlier run installed.

Backups are never deleted automatically.
"""

from __future__ import annotations

from pathlib import Path

from .errors import ConfigError
from .util import backup_root, read_json, repo_id, timestamp, write_json

MANIFEST_FILE = "manifest.json"
MANIFEST_VERSION = 1

STATE_PENDING = "pending"
STATE_LINKED = "linked"
STATE_FAILED = "failed"
STATE_RESTORED = "restored"
STATE_SKIPPED = "skipped"

REVERSIBLE_STATES = (STATE_PENDING, STATE_LINKED, STATE_FAILED, STATE_SKIPPED)


def run_root(repo: Path, machine: str) -> Path:
    """Return the directory holding every manifest for one repo/machine pair."""
    return backup_root() / repo_id(repo, machine)


class Manifest:
    """A lazily created, incrementally saved record of one link run."""

    def __init__(self, path: Path, data: dict) -> None:
        self.path = path
        self.data = data

    @property
    def directory(self) -> Path:
        """Return the run directory that holds this manifest and its backups."""
        return self.path.parent

    @property
    def items(self) -> list[dict]:
        """Return the recorded items in execution order."""
        return self.data["items"]

    @classmethod
    def create(cls, repo: Path, machine: str) -> "Manifest":
        """Create a new run directory with a unique timestamp."""
        root = run_root(repo, machine)
        stamp = timestamp()
        directory = root / stamp
        suffix = 1
        while directory.exists():
            directory = root / f"{stamp}-{suffix}"
            suffix += 1
        directory.mkdir(parents=True)
        data = {
            "version": MANIFEST_VERSION,
            "repo": str(repo),
            "machine": machine,
            "ts": directory.name,
            "items": [],
        }
        manifest = cls(directory / MANIFEST_FILE, data)
        manifest.save()
        return manifest

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        """Load a manifest from disk."""
        data = read_json(path)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ConfigError(f"malformed manifest: {path}")
        return cls(path, data)

    @classmethod
    def find(cls, repo: Path, machine: str, at: str | None = None) -> "Manifest":
        """Load the manifest for timestamp `at`, or the newest one."""
        root = run_root(repo, machine)
        if at:
            path = root / at / MANIFEST_FILE
            if not path.is_file():
                raise ConfigError(f"no manifest for timestamp {at!r} under {root}")
            return cls.load(path)
        candidates = sorted(root.glob(f"*/{MANIFEST_FILE}")) if root.is_dir() else []
        if not candidates:
            raise ConfigError(
                f"no link manifest found for machine {machine!r} under {root}"
            )
        return cls.load(candidates[-1])

    def save(self) -> None:
        """Persist the manifest, overwriting the previous revision."""
        write_json(self.path, self.data)

    def add(
        self,
        source: str,
        target: Path,
        mode: str,
        state: str,
        backup_path: Path | None = None,
    ) -> dict:
        """Append an item and flush the manifest to disk."""
        item = {
            "source": source,
            "target": str(target),
            "mode": mode,
            "state": state,
            "backup_path": str(backup_path) if backup_path else None,
        }
        self.items.append(item)
        self.save()
        return item

    def update(self, item: dict, **changes: object) -> None:
        """Apply changes to an item and flush the manifest to disk."""
        item.update(changes)
        self.save()

    def slot(self, index: int) -> Path:
        """Return the per-item backup directory for item `index`."""
        return self.directory / str(index)
