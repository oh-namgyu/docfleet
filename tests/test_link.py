"""Tests for `docfleet link`, including --adopt and the no-data-loss contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from docfleet import links
from docfleet.util import create_dir_link, is_link
from tests.conftest import (
    backup_runs,
    make_dir,
    read_manifest,
    run,
    run_json,
    set_links,
    snapshot,
)


def link_memory(fleet: Path, target: Path) -> None:
    set_links(fleet, "laptop", [{"source": "memory", "target": str(target)}])


def test_link_creates_a_directory_link(fleet: Path, tmp_path: Path) -> None:
    target = tmp_path / "agent" / "memory"
    link_memory(fleet, target)
    assert run("link", "--repo", str(fleet), "--machine", "laptop") == 0
    assert is_link(target)
    assert target.resolve() == (fleet / "machines" / "laptop" / "memory").resolve()
    assert (target / ".gitkeep").is_file()


def test_link_expands_a_home_relative_target(fleet: Path, home: Path) -> None:
    set_links(fleet, "laptop", [{"source": "memory", "target": "~/.agent/memory"}])
    assert run("link", "--repo", str(fleet), "--machine", "laptop") == 0
    assert is_link(home / ".agent" / "memory")


def test_link_is_idempotent(fleet: Path, tmp_path: Path, home: Path) -> None:
    target = tmp_path / "agent" / "memory"
    link_memory(fleet, target)
    assert run("link", "--repo", str(fleet), "--machine", "laptop") == 0
    first = snapshot(tmp_path / "agent")
    assert run("link", "--repo", str(fleet), "--machine", "laptop") == 0
    assert snapshot(tmp_path / "agent") == first
    assert len(backup_runs(home)) == 1


def test_link_reports_an_already_correct_link_as_current(
    fleet: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    link_memory(fleet, tmp_path / "agent" / "memory")
    run("link", "--repo", str(fleet), "--machine", "laptop")
    code, payload = run_json(capsys, "link", "--repo", str(fleet), "--machine", "laptop")
    assert code == 0
    assert [item["state"] for item in payload["items"]] == ["current"]
    assert payload["manifest"] is None


def test_link_backs_up_an_existing_directory(
    fleet: Path, tmp_path: Path, home: Path
) -> None:
    target = make_dir(tmp_path / "agent" / "memory", notes="local notes")
    link_memory(fleet, target)
    assert run("link", "--repo", str(fleet), "--machine", "laptop") == 0
    assert is_link(target)
    manifest = read_manifest(home)
    assert manifest["machine"] == "laptop"
    assert manifest["repo"] == str(fleet)
    item = manifest["items"][0]
    assert item["mode"] == "backup"
    assert item["state"] == "linked"
    assert item["target"] == str(target)
    backup = Path(item["backup_path"])
    assert backup.name == "memory"
    assert (backup / "notes").read_text(encoding="utf-8") == "local notes"


def test_link_backs_up_a_stale_link(fleet: Path, tmp_path: Path, home: Path) -> None:
    elsewhere = make_dir(tmp_path / "elsewhere")
    target = tmp_path / "agent" / "memory"
    target.parent.mkdir(parents=True)
    create_dir_link(elsewhere, target)
    link_memory(fleet, target)
    assert run("link", "--repo", str(fleet), "--machine", "laptop") == 0
    assert target.resolve() == (fleet / "machines" / "laptop" / "memory").resolve()
    assert read_manifest(home)["items"][0]["mode"] == "backup"


def test_adopt_moves_the_existing_directory_into_the_repository(
    fleet: Path, tmp_path: Path, home: Path
) -> None:
    target = make_dir(tmp_path / "agent" / "memory", notes="local notes")
    link_memory(fleet, target)
    assert run("link", "--repo", str(fleet), "--machine", "laptop", "--adopt") == 0
    source = fleet / "machines" / "laptop" / "memory"
    assert (source / "notes").read_text(encoding="utf-8") == "local notes"
    assert not (source / ".gitkeep").exists()
    assert is_link(target)
    assert (target / "notes").is_file()
    item = read_manifest(home)["items"][0]
    assert item["mode"] == "adopt"
    assert item["state"] == "linked"
    assert item["backup_path"] is None


def test_adopt_refuses_to_overwrite_a_populated_source(
    fleet: Path, tmp_path: Path, home: Path
) -> None:
    (fleet / "machines" / "laptop" / "memory" / "kept.md").write_text("x", "utf-8")
    target = make_dir(tmp_path / "agent" / "memory", notes="local notes")
    link_memory(fleet, target)
    assert run("link", "--repo", str(fleet), "--machine", "laptop", "--adopt") == 2
    assert not is_link(target)
    assert (target / "notes").is_file()
    assert backup_runs(home) == []


def test_link_without_declarations_succeeds(fleet: Path, home: Path) -> None:
    assert run("link", "--repo", str(fleet), "--machine", "laptop") == 0
    assert backup_runs(home) == []


def test_link_finds_the_repository_and_machine_by_itself(
    fleet: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "agent" / "memory"
    link_memory(fleet, target)
    monkeypatch.chdir(fleet / "machines" / "laptop")
    assert run("link") == 0
    assert is_link(target)


@pytest.mark.parametrize(
    "links",
    [
        pytest.param([{"source": "memory", "target": "relative/path"}], id="relative"),
        pytest.param([{"source": "memory", "target": "REPO/inside"}], id="in-repo"),
        pytest.param(
            [
                {"source": "memory", "target": "TMP/agent/one"},
                {"source": "docs", "target": "TMP/agent/one"},
            ],
            id="duplicate-target",
        ),
        pytest.param([{"source": "absent", "target": "TMP/agent/one"}], id="no-source"),
        pytest.param([{"source": "../..", "target": "TMP/agent/one"}], id="escape"),
        pytest.param([{"source": "memory", "target": "TMP/file.txt"}], id="file-target"),
    ],
)
def test_invalid_configurations_change_nothing(
    fleet: Path, tmp_path: Path, home: Path, links: list[dict]
) -> None:
    (tmp_path / "file.txt").write_text("keep me", encoding="utf-8")
    resolved = [
        {
            "source": link["source"],
            "target": link["target"]
            .replace("REPO", str(fleet))
            .replace("TMP", str(tmp_path)),
        }
        for link in links
    ]
    set_links(fleet, "laptop", resolved)
    before = snapshot(tmp_path)
    assert run("link", "--repo", str(fleet), "--machine", "laptop") == 2
    assert snapshot(tmp_path) == before
    assert backup_runs(home) == []


def test_a_failing_item_stops_the_run_and_is_recorded(
    fleet: Path, tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "agent" / "memory"
    second = make_dir(tmp_path / "agent" / "docs", page="local page")
    set_links(
        fleet,
        "laptop",
        [
            {"source": "memory", "target": str(first)},
            {"source": "docs", "target": str(second)},
        ],
    )
    calls: list[Path] = []

    def flaky(source: Path, target: Path) -> None:
        calls.append(target)
        if len(calls) > 1:
            raise OSError("simulated link failure")
        create_dir_link(source, target)

    monkeypatch.setattr(links, "create_dir_link", flaky)
    assert run("link", "--repo", str(fleet), "--machine", "laptop") == 1

    items = read_manifest(home)["items"]
    assert [item["state"] for item in items] == ["linked", "failed"]
    assert is_link(first)
    assert not second.exists()
    backup = Path(items[1]["backup_path"])
    assert (backup / "page").read_text(encoding="utf-8") == "local page"


def test_link_json_output(
    fleet: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    target = tmp_path / "agent" / "memory"
    link_memory(fleet, target)
    code, payload = run_json(capsys, "link", "--repo", str(fleet), "--machine", "laptop")
    assert code == 0
    assert payload["command"] == "link"
    assert payload["action"] == "link"
    assert payload["adopt"] is False
    assert payload["status"] == "ok"
    assert payload["error"] is None
    assert payload["items"] == [
        {
            "source": "memory",
            "target": str(target),
            "mode": "none",
            "state": "linked",
            "backup_path": None,
        }
    ]
