"""Install, adopt and restore the directory links declared by a machine.

No-data-loss contract:

1. The whole configuration is validated before anything on disk is touched.
   Any violation aborts with exit code 2 and an unchanged filesystem.
2. Real data found at a target is never deleted. It is moved -- into a backup
   directory, or (with --adopt) into the machine folder as the link source --
   and the move is recorded in a manifest before the link is created.
3. A failing item stops the run immediately. Everything completed so far stays
   in the manifest, so `--restore` can always walk the run back.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError
from .layout import KEEP_FILE, machine_config_path, machine_dir
from .manifest import STATE_FAILED, STATE_LINKED, STATE_PENDING, Manifest
from .util import (
    create_dir_link,
    expand_path,
    is_link,
    is_within,
    link_destination,
    read_json,
    stable_path,
)

MODE_NONE = "none"
MODE_BACKUP = "backup"
MODE_ADOPT = "adopt"

ACTION_LINK = "link"
ACTION_SKIP = "skip"

STATE_CURRENT = "current"

EMPTY_SOURCE_ENTRIES = {KEEP_FILE}


@dataclass
class PlannedItem:
    """One validated mapping plus the action decided for it."""

    index: int
    source_rel: str
    source: Path
    target: Path
    mode: str
    action: str
    source_existed: bool = False


def read_links(repo: Path, machine: str) -> list[dict]:
    """Read the `links` list of a machine configuration."""
    config_path = machine_config_path(repo, machine)
    if not config_path.is_file():
        raise ConfigError(
            f"machine {machine!r} is not set up in this repository: "
            f"{config_path} is missing -- run `docfleet init --join`"
        )
    data = read_json(config_path)
    links = data.get("links") if isinstance(data, dict) else None
    if not isinstance(links, list):
        raise ConfigError(f"malformed machine configuration: {config_path}")
    for entry in links:
        if not isinstance(entry, dict) or not isinstance(entry.get("source"), str):
            raise ConfigError(f"each link needs a string 'source': {config_path}")
        if not isinstance(entry.get("target"), str):
            raise ConfigError(f"each link needs a string 'target': {config_path}")
    return links


def _resolve_source(folder: Path, source_rel: str) -> Path:
    if not source_rel or os.path.isabs(source_rel):
        raise ConfigError(
            f"link source must be a path relative to {folder}, got {source_rel!r}"
        )
    source = Path(os.path.normpath(str(folder / source_rel)))
    if not is_within(source, folder) or source == folder:
        raise ConfigError(
            f"link source {source_rel!r} escapes the machine folder {folder}"
        )
    return source


def _resolve_target(raw: str, repo: Path) -> Path:
    target = expand_path(raw)
    if not target.is_absolute():
        raise ConfigError(
            f"link target must be an absolute path (~ allowed), got {raw!r}"
        )
    if is_within(stable_path(target), repo.resolve()):
        raise ConfigError(
            f"link target {raw!r} is inside the repository: a link may not point "
            "at the repository that declares it"
        )
    return target


def _classify(source: Path, target: Path, adopt: bool) -> tuple[str, str]:
    if is_link(target):
        destination = link_destination(target)
        if destination is not None and Path(os.path.abspath(str(destination))) == source:
            return MODE_NONE, ACTION_SKIP
        return MODE_BACKUP, ACTION_LINK
    if target.exists():
        if not target.is_dir():
            raise ConfigError(
                f"target {target} exists and is not a directory: docfleet links "
                "directories only"
            )
        return (MODE_ADOPT if adopt else MODE_BACKUP), ACTION_LINK
    return MODE_NONE, ACTION_LINK


def _check_source(source: Path, source_rel: str, mode: str) -> bool:
    """Validate the source directory; return True when it already exists."""
    if mode == MODE_ADOPT:
        if not source.exists():
            return False
        if not source.is_dir():
            raise ConfigError(f"link source is not a directory: {source}")
        extra = {entry.name for entry in source.iterdir()} - EMPTY_SOURCE_ENTRIES
        if extra:
            raise ConfigError(
                f"cannot adopt into {source}: it already holds content "
                f"({', '.join(sorted(extra))}) -- move it aside or drop --adopt"
            )
        return True
    if not source.is_dir():
        raise ConfigError(
            f"link source {source_rel!r} does not exist: create the directory "
            f"{source} first (docfleet links directories only)"
        )
    return True


def plan(repo: Path, machine: str, adopt: bool = False) -> list[PlannedItem]:
    """Validate the whole configuration and decide what each item needs."""
    folder = machine_dir(repo, machine)
    if not folder.is_dir():
        raise ConfigError(f"machine folder not found: {folder}")
    planned: list[PlannedItem] = []
    seen: dict[str, str] = {}
    for index, entry in enumerate(read_links(repo, machine)):
        source_rel = entry["source"]
        source = _resolve_source(folder, source_rel)
        target = _resolve_target(entry["target"], repo)
        key = str(stable_path(target))
        if key in seen:
            raise ConfigError(
                f"duplicate link target {entry['target']!r} "
                f"(already used by source {seen[key]!r})"
            )
        seen[key] = source_rel
        mode, action = _classify(source, target, adopt)
        existed = _check_source(source, source_rel, mode)
        planned.append(
            PlannedItem(index, source_rel, source, target, mode, action, existed)
        )
    return planned


def _apply(item: PlannedItem, manifest: Manifest, entry: dict) -> None:
    if item.mode == MODE_BACKUP:
        slot = manifest.slot(item.index)
        slot.mkdir(parents=True, exist_ok=True)
        backup_path = slot / item.target.name
        shutil.move(str(item.target), str(backup_path))
        manifest.update(entry, backup_path=str(backup_path))
    elif item.mode == MODE_ADOPT:
        item.source.parent.mkdir(parents=True, exist_ok=True)
        if item.source_existed:
            shutil.rmtree(str(item.source))
        shutil.move(str(item.target), str(item.source))
    item.target.parent.mkdir(parents=True, exist_ok=True)
    create_dir_link(item.source, item.target)


def run_link(repo: Path, machine: str, adopt: bool = False) -> dict:
    """Install every link declared by a machine. Returns a result document."""
    planned = plan(repo, machine, adopt)
    manifest: Manifest | None = None
    items: list[dict] = []
    error: str | None = None
    for item in planned:
        if item.action == ACTION_SKIP:
            items.append(_report(item, STATE_CURRENT, None))
            continue
        if manifest is None:
            manifest = Manifest.create(repo, machine)
        entry = manifest.add(item.source_rel, item.target, item.mode, STATE_PENDING)
        entry["source_existed"] = item.source_existed
        try:
            _apply(item, manifest, entry)
        except OSError as exc:
            manifest.update(entry, state=STATE_FAILED)
            items.append(_report(item, STATE_FAILED, entry.get("backup_path")))
            error = f"{item.source_rel} -> {item.target}: {exc}"
            break
        manifest.update(entry, state=STATE_LINKED)
        items.append(_report(item, STATE_LINKED, entry.get("backup_path")))
    return build_result("link", repo, machine, manifest, items, error, adopt=adopt)


def _report(item: PlannedItem, state: str, backup_path: str | None) -> dict:
    return {
        "source": item.source_rel,
        "target": str(item.target),
        "mode": item.mode,
        "state": state,
        "backup_path": backup_path,
    }


def build_result(
    action: str,
    repo: Path,
    machine: str,
    manifest: Manifest | None,
    items: list[dict],
    error: str | None,
    adopt: bool | None = None,
) -> dict:
    result = {
        "command": "link",
        "action": action,
        "repo": str(repo),
        "machine": machine,
        "manifest": str(manifest.path) if manifest else None,
        "items": items,
        "status": "partial" if error else "ok",
        "error": error,
        "exit_code": 1 if error else 0,
    }
    if adopt is not None:
        result["adopt"] = adopt
    return result
