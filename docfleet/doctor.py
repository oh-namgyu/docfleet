"""The `doctor` command: a structure lint for a fleet repository.

Every finding carries a stable check id, so scripts can filter on it:

    layout         a required file or folder of the layout is missing
    machine-name   a machine name does not follow the naming rule
    registry       fleet.json and machines/ disagree about which machines exist
    mapping        machine.json declares a link that could never be installed
    link-broken    a declared link is missing, is not a link, or points elsewhere
    cross-machine  uncommitted changes sit in another machine's folder
    index-stale    INDEX.md is missing or no longer matches the layout

doctor reports by default and changes nothing. `--fix` repairs only what can be
regenerated without touching data: it reinstalls links through the ordinary
`docfleet link` machinery and rewrites INDEX.md. Everything else -- above all
cross-machine edits, which are somebody's unsaved work -- stays report-only.
"""

from __future__ import annotations

from pathlib import Path

from .errors import ConfigError
from .gitops import changed_paths, is_work_tree
from .indexer import index_path, is_stale, write_index
from .layout import (
    FLEET_FILE,
    MACHINES_DIR,
    SHARED_DIR,
    fleet_path,
    machine_config_path,
    machine_names,
    read_fleet,
    validate_machine_name,
    writable_prefixes,
)
from .links import plan, run_link
from .util import is_link, link_destination

CHECK_LAYOUT = "layout"
CHECK_NAME = "machine-name"
CHECK_REGISTRY = "registry"
CHECK_MAPPING = "mapping"
CHECK_LINK = "link-broken"
CHECK_CROSS = "cross-machine"
CHECK_INDEX = "index-stale"

CHECKS: tuple[str, ...] = (
    CHECK_LAYOUT,
    CHECK_NAME,
    CHECK_REGISTRY,
    CHECK_MAPPING,
    CHECK_LINK,
    CHECK_CROSS,
    CHECK_INDEX,
)


def _violation(check: str, path: Path | str, message: str) -> dict:
    return {"check": check, "path": str(path), "message": message}


def _machine_dirs(repo: Path) -> list[Path]:
    root = repo / MACHINES_DIR
    if not root.is_dir():
        return []
    return sorted(entry for entry in root.iterdir() if entry.is_dir())


def check_layout(repo: Path) -> list[dict]:
    """Check that the required files and folders of the layout exist."""
    found: list[dict] = []
    if not fleet_path(repo).is_file():
        found.append(
            _violation(
                CHECK_LAYOUT, fleet_path(repo), f"{FLEET_FILE} is missing at the root"
            )
        )
    if not (repo / SHARED_DIR).is_dir():
        found.append(
            _violation(CHECK_LAYOUT, repo / SHARED_DIR, f"{SHARED_DIR}/ is missing")
        )
    if not (repo / MACHINES_DIR).is_dir():
        found.append(
            _violation(CHECK_LAYOUT, repo / MACHINES_DIR, f"{MACHINES_DIR}/ is missing")
        )
    for folder in _machine_dirs(repo):
        config = machine_config_path(repo, folder.name)
        if not config.is_file():
            found.append(
                _violation(
                    CHECK_LAYOUT, config, f"machine {folder.name!r} has no machine.json"
                )
            )
    return found


def check_names(repo: Path) -> list[dict]:
    """Check that every machine name follows the naming rule."""
    found: list[dict] = []
    names = {folder.name: folder for folder in _machine_dirs(repo)}
    for name in machine_names(read_fleet(repo)):
        names.setdefault(name, fleet_path(repo))
    for name, path in sorted(names.items()):
        try:
            validate_machine_name(name)
        except ConfigError as exc:
            found.append(_violation(CHECK_NAME, path, str(exc)))
    return found


def check_registry(repo: Path) -> list[dict]:
    """Check that fleet.json and the machines/ folders agree, both ways."""
    registered = set(machine_names(read_fleet(repo)))
    on_disk = {folder.name for folder in _machine_dirs(repo)}
    found = [
        _violation(
            CHECK_REGISTRY,
            repo / MACHINES_DIR / name,
            f"machine {name!r} is registered in {FLEET_FILE} but has no folder",
        )
        for name in sorted(registered - on_disk)
    ]
    found.extend(
        _violation(
            CHECK_REGISTRY,
            repo / MACHINES_DIR / name,
            f"folder {MACHINES_DIR}/{name}/ is not registered in {FLEET_FILE}",
        )
        for name in sorted(on_disk - registered)
    )
    return found


def check_links(repo: Path, machine: str) -> list[dict]:
    """Check this machine's declared links against what is on disk."""
    try:
        planned = plan(repo, machine)
    except ConfigError as exc:
        return [_violation(CHECK_MAPPING, machine_config_path(repo, machine), str(exc))]
    found: list[dict] = []
    for item in planned:
        destination = link_destination(item.target)
        if not is_link(item.target):
            reason = "exists but is not a link" if item.target.exists() else "is missing"
            found.append(
                _violation(
                    CHECK_LINK, item.target, f"link for {item.source_rel!r} {reason}"
                )
            )
        elif destination is None or Path(destination).resolve() != item.source.resolve():
            found.append(
                _violation(
                    CHECK_LINK,
                    item.target,
                    f"link for {item.source_rel!r} points at {destination} "
                    f"instead of {item.source}",
                )
            )
    return found


def check_cross_machine(repo: Path, machine: str) -> list[dict]:
    """Check that no uncommitted change sits in another machine's folder."""
    own = writable_prefixes(machine)[0]
    prefix = f"{MACHINES_DIR}/"
    return [
        _violation(
            CHECK_CROSS,
            repo / path,
            f"uncommitted change in another machine's folder: {path}",
        )
        for path in changed_paths(repo)
        if path.startswith(prefix) and not path.startswith(own)
    ]


def check_index(repo: Path) -> list[dict]:
    """Check that INDEX.md exists and matches freshly generated content."""
    path = index_path(repo)
    if not path.is_file():
        return [_violation(CHECK_INDEX, path, "INDEX.md is missing")]
    if is_stale(repo):
        return [
            _violation(
                CHECK_INDEX,
                path,
                "INDEX.md no longer matches the layout: run `docfleet index`",
            )
        ]
    return []


def collect(repo: Path, machine: str) -> list[dict]:
    """Run every check and return the violations found, in check order."""
    if not is_work_tree(repo):
        raise ConfigError(
            f"not a git repository: {repo} -- docfleet doctor reads git status"
        )
    found = check_layout(repo)
    if not fleet_path(repo).is_file():
        return found
    found.extend(check_names(repo))
    found.extend(check_registry(repo))
    found.extend(check_links(repo, machine))
    found.extend(check_cross_machine(repo, machine))
    found.extend(check_index(repo))
    return found


def _repair(repo: Path, machine: str, violations: list[dict]) -> list[dict]:
    """Repair the regenerable findings only. Returns what was repaired."""
    fixed: list[dict] = []
    if any(item["check"] == CHECK_LINK for item in violations):
        result = run_link(repo, machine)
        fixed.extend(
            {"check": CHECK_LINK, "path": item["target"], "action": item["state"]}
            for item in result["items"]
        )
    if any(item["check"] == CHECK_INDEX for item in violations):
        write_index(repo)
        fixed.append(
            {"check": CHECK_INDEX, "path": str(index_path(repo)), "action": "written"}
        )
    return fixed


def run_doctor(repo: Path, machine: str, fix: bool = False) -> dict:
    """Run `docfleet doctor`. Returns a result document."""
    violations = collect(repo, machine)
    fixed: list[dict] = []
    if fix and violations:
        fixed = _repair(repo, machine, violations)
        violations = collect(repo, machine)
    return {
        "command": "doctor",
        "repo": str(repo),
        "machine": machine,
        "checks": list(CHECKS),
        "violations": violations,
        "fixed": fixed,
        "status": "violations" if violations else "ok",
        "error": f"{len(violations)} violation(s) found" if violations else None,
        "exit_code": 1 if violations else 0,
    }
