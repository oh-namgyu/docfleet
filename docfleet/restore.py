"""Reverse a link run from its manifest, newest run first.

Restore walks items in reverse order: it removes the link, then moves the
displaced data back into place. If something new occupies the target position,
the item is skipped and reported instead -- nothing is ever deleted to make
room. Restored items are marked in the manifest, so re-running is a no-op.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .layout import KEEP_FILE, machine_dir
from .links import MODE_ADOPT, MODE_BACKUP, build_result
from .manifest import (
    REVERSIBLE_STATES,
    STATE_RESTORED,
    STATE_SKIPPED,
    Manifest,
)
from .util import is_link, remove_link


def _put_back(manifest: Manifest, item: dict, target: Path) -> None:
    if item["mode"] == MODE_BACKUP and item.get("backup_path"):
        backup = Path(item["backup_path"])
        if backup.exists():
            shutil.move(str(backup), str(target))
    elif item["mode"] == MODE_ADOPT:
        folder = machine_dir(Path(manifest.data["repo"]), manifest.data["machine"])
        source = folder / item["source"]
        if source.exists():
            shutil.move(str(source), str(target))
            if item.get("source_existed"):
                source.mkdir(parents=True, exist_ok=True)
                (source / KEEP_FILE).write_text("", encoding="utf-8")


def _restore_item(manifest: Manifest, item: dict) -> str:
    target = Path(item["target"])
    if target.exists() and not is_link(target):
        manifest.update(item, state=STATE_SKIPPED)
        return STATE_SKIPPED
    if is_link(target):
        remove_link(target)
    _put_back(manifest, item, target)
    manifest.update(item, state=STATE_RESTORED)
    return STATE_RESTORED


def run_restore(repo: Path, machine: str, at: str | None = None) -> dict:
    """Reverse the newest link run, or the run identified by timestamp `at`."""
    manifest = Manifest.find(repo, machine, at)
    items: list[dict] = []
    skipped = 0
    for entry in reversed(manifest.items):
        if entry["state"] not in REVERSIBLE_STATES:
            continue
        state = _restore_item(manifest, entry)
        skipped += int(state == STATE_SKIPPED)
        items.append(
            {
                "source": entry["source"],
                "target": entry["target"],
                "mode": entry["mode"],
                "state": state,
                "backup_path": entry.get("backup_path"),
            }
        )
    error = (
        f"{skipped} item(s) skipped: something new occupies the target position"
        if skipped
        else None
    )
    return build_result("restore", repo, machine, manifest, items, error)
