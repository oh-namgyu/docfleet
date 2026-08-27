"""Shared fixtures and helpers for the docfleet test suite."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from docfleet.cli import main
from docfleet.util import is_link, link_destination

BRANCH = "main"


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


def git(cwd: Path, *args: str) -> str:
    """Run a git command that must succeed and return its stdout."""
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"git {' '.join(args)}: {result.stderr}"
    return result.stdout


def _configure(repo: Path) -> None:
    git(repo, "config", "user.email", "fleet@example.com")
    git(repo, "config", "user.name", "Fleet Tester")
    git(repo, "config", "commit.gpgsign", "false")


def commit_all(repo: Path, message: str) -> str:
    """Stage everything in a test repository and commit it."""
    git(repo, "add", "--all")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


def clone(origin: Path, destination: Path) -> Path:
    """Clone the shared origin and give the clone a committer identity."""
    git(destination.parent, "clone", str(origin), str(destination))
    _configure(destination)
    if subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        check=False,
    ).returncode:
        git(destination, "symbolic-ref", "HEAD", f"refs/heads/{BRANCH}")
    return destination


@pytest.fixture()
def origin(tmp_path: Path) -> Path:
    """A bare repository standing in for the shared remote."""
    path = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "--initial-branch", BRANCH, str(path))
    return path


@pytest.fixture()
def laptop(tmp_path: Path, origin: Path) -> Path:
    """A clone that created the fleet and pushed it, acting as machine `laptop`."""
    repo = clone(origin, tmp_path / "laptop")
    assert main(["init", "--new", str(repo), "--machine", "laptop"]) == 0
    commit_all(repo, "create fleet")
    git(repo, "push", "--set-upstream", "origin", BRANCH)
    return repo


@pytest.fixture()
def desktop(tmp_path: Path, origin: Path, laptop: Path) -> Path:
    """A second clone joined to the same fleet as machine `desktop`."""
    repo = clone(origin, tmp_path / "desktop")
    assert main(["init", "--join", str(repo), "--machine", "desktop"]) == 0
    commit_all(repo, "join desktop")
    git(repo, "push", "origin", BRANCH)
    git(laptop, "pull", "--rebase")
    return repo


def write_doc(repo: Path, relative: str, content: str = "note\n") -> Path:
    """Write a file inside the repository, creating parent directories."""
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


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
    """Describe every path under root: links, directories and file contents.

    A link is described by its destination and never descended into, so a
    POSIX symlink and a Windows junction produce the same shape of report.
    """
    entries: list[tuple[str, str]] = []
    links: set[Path] = set()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts or links.intersection(path.parents):
            continue
        if is_link(path):
            links.add(path)
            kind = f"link:{link_destination(path)}"
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
