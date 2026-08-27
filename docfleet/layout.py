"""The docfleet layout convention and the `init` command.

A fleet repository is an ordinary git repository shaped like this::

    fleet.json                    machine registry (repository root)
    README.md                     placeholder created on init when missing
    machines/<name>/machine.json  per-machine link configuration
    machines/<name>/docs/         per-machine documents
    machines/<name>/memory/       per-machine agent memory
    shared/commands/              content shared by every machine
    shared/standards/

`fleet.json` schema::

    {"version": 1,
     "machines": [{"name": "laptop", "created": "2026-01-31"}]}

`machines/<name>/machine.json` schema::

    {"machine": "laptop",
     "links": [{"source": "memory", "target": "~/.agent/memory"}]}

`source` is a directory path relative to the machine folder; `target` is an
absolute path on that machine (a leading ``~`` is expanded). JSON carries no
comments, so this docstring is the schema reference; `links` starts empty.
"""

from __future__ import annotations

import re
from pathlib import Path

from .errors import ConfigError
from .util import is_git_repo, read_json, today_iso, write_json

MACHINES_DIR = "machines"
SHARED_DIR = "shared"
FLEET_FILE = "fleet.json"
MACHINE_FILE = "machine.json"
README_FILE = "README.md"
INDEX_FILE = "INDEX.md"
KEEP_FILE = ".gitkeep"

ROOT_FILES: tuple[str, ...] = (FLEET_FILE, README_FILE, INDEX_FILE)

MACHINE_SUBDIRS: tuple[str, ...] = ("docs", "memory")
SHARED_SUBDIRS: tuple[str, ...] = ("commands", "standards")
FLEET_VERSION = 1

MACHINE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

README_STUB = """# Fleet

Documents and agent memory shared across machines with
[docfleet](https://pypi.org/project/docfleet/).

- `machines/<name>/` -- one folder per machine
- `shared/` -- content every machine uses
- `fleet.json` -- the machine registry
"""


def validate_machine_name(name: str) -> str:
    """Return the machine name, or raise ConfigError when it is malformed."""
    if not MACHINE_NAME_PATTERN.match(name):
        raise ConfigError(
            f"invalid machine name {name!r}: use lowercase letters, digits and "
            "hyphens, starting with a letter or digit (for example: laptop)"
        )
    return name


def writable_prefixes(machine: str) -> tuple[str, ...]:
    """Return the repository path prefixes `machine` is allowed to write."""
    return (f"{MACHINES_DIR}/{machine}/", f"{SHARED_DIR}/")


def is_writable_path(path: str, machine: str) -> bool:
    """Return True when a repository-relative path belongs to a writable area.

    A machine owns `machines/<its own name>/`, every machine shares `shared/`,
    and the root metadata files are common property. Everything else -- above
    all `machines/<another machine>/` -- is read-only for this machine.
    """
    if path in ROOT_FILES:
        return True
    return any(path.startswith(prefix) for prefix in writable_prefixes(machine))


def machine_dir(repo: Path, name: str) -> Path:
    """Return the folder owned by one machine."""
    return repo / MACHINES_DIR / name


def machine_config_path(repo: Path, name: str) -> Path:
    """Return the path of a machine's link configuration file."""
    return machine_dir(repo, name) / MACHINE_FILE


def fleet_path(repo: Path) -> Path:
    """Return the path of the fleet registry."""
    return repo / FLEET_FILE


def has_layout(repo: Path) -> bool:
    """Return True when repo already holds a fleet layout."""
    return fleet_path(repo).is_file() and (repo / MACHINES_DIR).is_dir()


def find_repo(start: Path) -> Path:
    """Search start and its parents for a fleet repository root."""
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if has_layout(candidate):
            return candidate
    raise ConfigError(
        f"no fleet repository found at or above {start}: "
        "pass --repo, or run docfleet init first"
    )


def read_fleet(repo: Path) -> dict:
    """Read and shallow-validate fleet.json."""
    data = read_json(fleet_path(repo))
    if not isinstance(data, dict) or not isinstance(data.get("machines"), list):
        raise ConfigError(f"malformed fleet registry: {fleet_path(repo)}")
    return data


def machine_names(fleet: dict) -> list[str]:
    """Return the registered machine names in registration order."""
    return [str(entry.get("name", "")) for entry in fleet["machines"]]


def _require_git_repo(repo: Path) -> None:
    if not repo.exists():
        raise ConfigError(
            f"directory does not exist: {repo}\n"
            "create it and run `git init` inside it first"
        )
    if not repo.is_dir():
        raise ConfigError(f"not a directory: {repo}")
    if not is_git_repo(repo):
        raise ConfigError(
            f"not a git repository: {repo}\n"
            "run `git init` there first -- docfleet never initialises git for you"
        )


def _touch_keep(directory: Path, created: list[Path]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    keep = directory / KEEP_FILE
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
    created.append(directory)


def _create_machine(repo: Path, name: str, created: list[Path]) -> None:
    folder = machine_dir(repo, name)
    for sub in MACHINE_SUBDIRS:
        _touch_keep(folder / sub, created)
    config = machine_config_path(repo, name)
    if not config.exists():
        write_json(config, {"machine": name, "links": []})
    created.append(config)


def _register_machine(repo: Path, name: str) -> None:
    fleet = read_fleet(repo)
    if name in machine_names(fleet):
        raise ConfigError(
            f"machine {name!r} is already registered in {fleet_path(repo)}"
        )
    fleet["machines"].append({"name": name, "created": today_iso()})
    write_json(fleet_path(repo), fleet)


def init_new(repo: Path, name: str) -> dict:
    """Create a fresh layout in an existing git repository."""
    validate_machine_name(name)
    _require_git_repo(repo)
    if fleet_path(repo).exists():
        raise ConfigError(
            f"{fleet_path(repo)} already exists: use `docfleet init --join` "
            "to add this machine to an existing fleet"
        )
    created: list[Path] = []
    for sub in SHARED_SUBDIRS:
        _touch_keep(repo / SHARED_DIR / sub, created)
    _create_machine(repo, name, created)
    write_json(fleet_path(repo), {"version": FLEET_VERSION, "machines": []})
    created.append(fleet_path(repo))
    readme = repo / README_FILE
    if not readme.exists():
        readme.write_text(README_STUB, encoding="utf-8")
        created.append(readme)
    _register_machine(repo, name)
    return _result("new", repo, name, created)


def init_join(repo: Path, name: str) -> dict:
    """Register an additional machine in an already cloned fleet repository."""
    validate_machine_name(name)
    _require_git_repo(repo)
    if not has_layout(repo):
        raise ConfigError(
            f"no fleet layout in {repo}: expected {FLEET_FILE} and "
            f"{MACHINES_DIR}/ -- clone the fleet repository, or use --new"
        )
    if machine_dir(repo, name).exists():
        raise ConfigError(f"machine folder already exists: {machine_dir(repo, name)}")
    created: list[Path] = []
    _create_machine(repo, name, created)
    _register_machine(repo, name)
    return _result("join", repo, name, created)


def _result(mode: str, repo: Path, name: str, created: list[Path]) -> dict:
    return {
        "command": "init",
        "mode": mode,
        "repo": str(repo),
        "machine": name,
        "created": [str(path.relative_to(repo)) for path in created],
    }
