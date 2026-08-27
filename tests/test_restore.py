"""Tests for `docfleet link --restore`."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.conftest import (
    backup_runs,
    make_dir,
    read_manifest,
    run,
    run_json,
    set_links,
    snapshot,
)


@pytest.fixture()
def linked(fleet: Path, tmp_path: Path) -> Path:
    """A machine whose memory link displaced a real directory."""
    target = make_dir(tmp_path / "agent" / "memory", notes="local notes")
    set_links(fleet, "laptop", [{"source": "memory", "target": str(target)}])
    return target


def test_restore_returns_the_previous_state_exactly(
    fleet: Path, tmp_path: Path, linked: Path
) -> None:
    agent = tmp_path / "agent"
    before = snapshot(agent)
    assert run("link", "--repo", str(fleet), "--machine", "laptop") == 0
    assert snapshot(agent) != before
    assert run("link", "--repo", str(fleet), "--machine", "laptop", "--restore") == 0
    assert snapshot(agent) == before


def test_restore_marks_items_and_is_idempotent(
    fleet: Path, tmp_path: Path, home: Path, linked: Path
) -> None:
    run("link", "--repo", str(fleet), "--machine", "laptop")
    run("link", "--repo", str(fleet), "--machine", "laptop", "--restore")
    assert read_manifest(home)["items"][0]["state"] == "restored"
    before = snapshot(tmp_path / "agent")
    assert run("link", "--repo", str(fleet), "--machine", "laptop", "--restore") == 0
    assert snapshot(tmp_path / "agent") == before


def test_restore_removes_a_link_that_displaced_nothing(
    fleet: Path, tmp_path: Path
) -> None:
    target = tmp_path / "agent" / "memory"
    set_links(fleet, "laptop", [{"source": "memory", "target": str(target)}])
    run("link", "--repo", str(fleet), "--machine", "laptop")
    assert run("link", "--repo", str(fleet), "--machine", "laptop", "--restore") == 0
    assert not target.exists()
    assert (fleet / "machines" / "laptop" / "memory" / ".gitkeep").is_file()


def test_restore_skips_a_target_taken_over_by_new_data(
    fleet: Path, home: Path, linked: Path, capsys: pytest.CaptureFixture
) -> None:
    run("link", "--repo", str(fleet), "--machine", "laptop")
    backup = Path(read_manifest(home)["items"][0]["backup_path"])
    linked.unlink()
    make_dir(linked, fresh="written after linking")

    code, payload = run_json(
        capsys, "link", "--repo", str(fleet), "--machine", "laptop", "--restore"
    )
    assert code == 1
    assert payload["status"] == "partial"
    assert [item["state"] for item in payload["items"]] == ["skipped"]
    assert (linked / "fresh").read_text(encoding="utf-8") == "written after linking"
    assert (backup / "notes").read_text(encoding="utf-8") == "local notes"


def test_a_skipped_item_is_retried_by_a_later_restore(
    fleet: Path, home: Path, linked: Path
) -> None:
    run("link", "--repo", str(fleet), "--machine", "laptop")
    linked.unlink()
    make_dir(linked, fresh="written after linking")
    assert run("link", "--repo", str(fleet), "--machine", "laptop", "--restore") == 1
    shutil.rmtree(linked)
    assert run("link", "--repo", str(fleet), "--machine", "laptop", "--restore") == 0
    assert (linked / "notes").read_text(encoding="utf-8") == "local notes"
    assert read_manifest(home)["items"][0]["state"] == "restored"


def test_restore_reverses_an_adopted_directory(
    fleet: Path, tmp_path: Path, linked: Path
) -> None:
    agent = tmp_path / "agent"
    before = snapshot(agent)
    assert run("link", "--repo", str(fleet), "--machine", "laptop", "--adopt") == 0
    assert run("link", "--repo", str(fleet), "--machine", "laptop", "--restore") == 0
    assert snapshot(agent) == before
    source = fleet / "machines" / "laptop" / "memory"
    assert (source / ".gitkeep").is_file()
    assert not (source / "notes").exists()


def test_restore_at_selects_an_older_run(
    fleet: Path, tmp_path: Path, home: Path, linked: Path
) -> None:
    run("link", "--repo", str(fleet), "--machine", "laptop")
    first = read_manifest(home)["ts"]
    docs_target = make_dir(tmp_path / "agent" / "docs", page="local page")
    set_links(
        fleet,
        "laptop",
        [
            {"source": "memory", "target": str(linked)},
            {"source": "docs", "target": str(docs_target)},
        ],
    )
    run("link", "--repo", str(fleet), "--machine", "laptop")
    assert len(backup_runs(home)) == 2

    assert (
        run(
            "link",
            "--repo",
            str(fleet),
            "--machine",
            "laptop",
            "--restore",
            "--at",
            first,
        )
        == 0
    )
    assert (linked / "notes").read_text(encoding="utf-8") == "local notes"
    assert docs_target.is_symlink()


def test_restore_without_a_manifest_is_a_configuration_error(fleet: Path) -> None:
    assert run("link", "--repo", str(fleet), "--machine", "laptop", "--restore") == 2


def test_at_requires_restore(fleet: Path) -> None:
    assert (
        run("link", "--repo", str(fleet), "--machine", "laptop", "--at", "20260101-000000")
        == 2
    )
