"""Shared fixtures and helpers for the docfleet test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docfleet.cli import main


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the home directory so backups stay inside tmp_path."""
    directory = tmp_path / "home"
    directory.mkdir()
    monkeypatch.setenv("HOME", str(directory))
    monkeypatch.setenv("USERPROFILE", str(directory))
    return directory


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """An empty directory that looks like a git working tree."""
    repo = tmp_path / "fleet"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


@pytest.fixture()
def fleet(git_repo: Path) -> Path:
    """A fleet repository initialised for the machine `laptop`."""
    assert main(["init", "--new", str(git_repo), "--machine", "laptop"]) == 0
    return git_repo


def run(*argv: str) -> int:
    """Invoke the CLI with the given arguments and return the exit code."""
    return main(list(argv))


def run_json(capsys: pytest.CaptureFixture, *argv: str) -> tuple[int, dict]:
    """Invoke the CLI with --json and return the exit code and parsed output."""
    capsys.readouterr()
    code = main(["--json", *argv])
    return code, json.loads(capsys.readouterr().out)


def set_links(repo: Path, machine: str, links: list[dict]) -> None:
    """Replace the links declared by a machine."""
    path = repo / "machines" / machine / "machine.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["links"] = links
    path.write_text(json.dumps(data), encoding="utf-8")


def make_dir(path: Path, **files: str) -> Path:
    """Create a directory holding the given files."""
    path.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (path / name).write_text(content, encoding="utf-8")
    return path


def snapshot(root: Path) -> list[tuple[str, str]]:
    """Describe every path under root: links, directories and file contents."""
    entries: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            kind = f"link:{path.readlink()}"
        elif path.is_dir():
            kind = "dir"
        else:
            kind = f"file:{path.read_text(encoding='utf-8')}"
        entries.append((str(relative), kind))
    return entries


def backup_runs(home_dir: Path) -> list[Path]:
    """Return every manifest directory created so far, oldest first."""
    root = home_dir / ".docfleet" / "backup"
    if not root.is_dir():
        return []
    return sorted(path.parent for path in root.glob("*/*/manifest.json"))


def read_manifest(home_dir: Path, index: int = -1) -> dict:
    """Read one manifest, the newest by default."""
    runs = backup_runs(home_dir)
    return json.loads((runs[index] / "manifest.json").read_text(encoding="utf-8"))
