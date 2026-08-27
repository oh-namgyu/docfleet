"""Tests for the layout convention and `docfleet init`."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.conftest import run, run_json, snapshot

EXPECTED_TREE = [
    "README.md",
    "fleet.json",
    "machines",
    "machines/laptop",
    "machines/laptop/docs",
    "machines/laptop/docs/.gitkeep",
    "machines/laptop/machine.json",
    "machines/laptop/memory",
    "machines/laptop/memory/.gitkeep",
    "shared",
    "shared/commands",
    "shared/commands/.gitkeep",
    "shared/standards",
    "shared/standards/.gitkeep",
]


def tree(root: Path) -> list[str]:
    return [name for name, _ in snapshot(root)]


def test_init_new_creates_the_documented_tree(git_repo: Path) -> None:
    assert run("init", "--new", str(git_repo), "--machine", "laptop") == 0
    assert tree(git_repo) == EXPECTED_TREE


def test_init_new_writes_the_fleet_registry(git_repo: Path) -> None:
    run("init", "--new", str(git_repo), "--machine", "laptop")
    fleet = json.loads((git_repo / "fleet.json").read_text(encoding="utf-8"))
    assert fleet["version"] == 1
    assert [entry["name"] for entry in fleet["machines"]] == ["laptop"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", fleet["machines"][0]["created"])


def test_init_new_writes_an_empty_machine_config(git_repo: Path) -> None:
    run("init", "--new", str(git_repo), "--machine", "laptop")
    config = git_repo / "machines" / "laptop" / "machine.json"
    assert json.loads(config.read_text(encoding="utf-8")) == {
        "machine": "laptop",
        "links": [],
    }


def test_init_new_refuses_a_directory_that_is_not_a_git_repo(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert run("init", "--new", str(plain), "--machine", "laptop") == 2
    assert tree(plain) == []


def test_init_new_refuses_a_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert run("init", "--new", str(missing), "--machine", "laptop") == 2
    assert not missing.exists()


@pytest.mark.parametrize("name", ["Laptop", "-desk", "my_machine", "", "office box"])
def test_init_new_rejects_malformed_machine_names(git_repo: Path, name: str) -> None:
    assert run("init", "--new", str(git_repo), f"--machine={name}") == 2
    assert tree(git_repo) == []


def test_init_new_refuses_an_initialised_repository(fleet: Path) -> None:
    assert run("init", "--new", str(fleet), "--machine", "desktop") == 2
    assert tree(fleet) == EXPECTED_TREE


def test_init_join_adds_a_second_machine(fleet: Path) -> None:
    assert run("init", "--join", str(fleet), "--machine", "desktop") == 0
    registry = json.loads((fleet / "fleet.json").read_text(encoding="utf-8"))
    assert [entry["name"] for entry in registry["machines"]] == ["laptop", "desktop"]
    assert (fleet / "machines" / "desktop" / "memory" / ".gitkeep").is_file()
    assert (fleet / "machines" / "laptop" / "memory" / ".gitkeep").is_file()


def test_init_join_rejects_a_duplicate_machine(fleet: Path) -> None:
    assert run("init", "--join", str(fleet), "--machine", "laptop") == 2
    registry = json.loads((fleet / "fleet.json").read_text(encoding="utf-8"))
    assert len(registry["machines"]) == 1


def test_init_join_requires_an_existing_layout(git_repo: Path) -> None:
    assert run("init", "--join", str(git_repo), "--machine", "office") == 2
    assert tree(git_repo) == []


def test_init_json_output(git_repo: Path, capsys: pytest.CaptureFixture) -> None:
    code, payload = run_json(capsys, "init", "--new", str(git_repo), "--machine", "office")
    assert code == 0
    assert payload["command"] == "init"
    assert payload["mode"] == "new"
    assert payload["machine"] == "office"
    assert payload["repo"] == str(git_repo)
    assert "fleet.json" in payload["created"]


def test_error_json_output(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    code, payload = run_json(capsys, "init", "--new", str(tmp_path / "nope"), "--machine", "laptop")
    assert code == 2
    assert payload["exit_code"] == 2
    assert "git init" in payload["error"]


@pytest.mark.parametrize("command", ["start", "close", "doctor", "index"])
def test_later_stage_commands_are_stubs(command: str) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run(command)
    assert excinfo.value.code == 2
