"""Tests for `docfleet doctor`: one seeded violation per check id, plus --fix."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from docfleet import doctor
from tests.conftest import commit_all, run, run_json, set_links, write_doc


@pytest.fixture()
def fleet_git(laptop: Path) -> Path:
    """A fleet clone with a fresh index and a clean work tree."""
    assert run("index", "--repo", str(laptop)) == 0
    commit_all(laptop, "index")
    return laptop


def settle(repo: Path) -> None:
    """Regenerate the index and commit everything, so only the seed remains."""
    assert run("index", "--repo", str(repo)) == 0
    commit_all(repo, "seed")


def checks(payload: dict) -> set[str]:
    """Return the check ids that fired."""
    return {item["check"] for item in payload["violations"]}


def check_doctor(
    capsys: pytest.CaptureFixture, repo: Path, *extra: str
) -> tuple[int, dict]:
    """Run `docfleet doctor` for the machine `laptop`."""
    return run_json(capsys, "doctor", "--repo", str(repo), "--machine", "laptop", *extra)


def add_machine(repo: Path, name: str, register: bool = True) -> None:
    """Create a machine folder, optionally registering it in fleet.json."""
    write_doc(repo, f"machines/{name}/machine.json", json.dumps({"machine": name}))
    if not register:
        return
    fleet = json.loads((repo / "fleet.json").read_text(encoding="utf-8"))
    fleet["machines"].append({"name": name, "created": "2026-01-31"})
    (repo / "fleet.json").write_text(json.dumps(fleet), encoding="utf-8")


def test_clean_repository_has_no_violations(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 0
    assert payload["violations"] == []
    assert payload["status"] == "ok"


def test_layout_check_reports_a_missing_registry(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    (fleet_git / "fleet.json").unlink()
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_LAYOUT}


def test_layout_check_reports_a_missing_machine_config(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    add_machine(fleet_git, "office")
    (fleet_git / "machines/office/machine.json").unlink()
    settle(fleet_git)
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_LAYOUT}


def test_name_check_reports_an_invalid_machine_name(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    add_machine(fleet_git, "Office")
    settle(fleet_git)
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_NAME}


def test_registry_check_reports_an_unregistered_folder(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    add_machine(fleet_git, "office", register=False)
    settle(fleet_git)
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_REGISTRY}
    assert "not registered" in payload["violations"][0]["message"]


def test_registry_check_reports_a_folder_that_is_missing(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    add_machine(fleet_git, "office")
    shutil.rmtree(fleet_git / "machines/office")
    settle(fleet_git)
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_REGISTRY}


def test_mapping_check_reports_a_source_that_does_not_exist(
    fleet_git: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    set_links(fleet_git, "laptop", [{"source": "gone", "target": str(tmp_path / "x")}])
    commit_all(fleet_git, "declare a link")
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_MAPPING}


def test_link_check_reports_a_link_that_was_removed(
    fleet_git: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    target = tmp_path / "agent" / "memory"
    set_links(fleet_git, "laptop", [{"source": "memory", "target": str(target)}])
    commit_all(fleet_git, "declare a link")
    assert run("link", "--repo", str(fleet_git), "--machine", "laptop") == 0
    target.unlink()
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_LINK}
    assert payload["violations"][0]["path"] == str(target)


def test_link_check_reports_a_link_pointing_elsewhere(
    fleet_git: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    target = tmp_path / "agent" / "memory"
    set_links(fleet_git, "laptop", [{"source": "memory", "target": str(target)}])
    commit_all(fleet_git, "declare a link")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(elsewhere)
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_LINK}
    assert "points at" in payload["violations"][0]["message"]


def test_cross_machine_check_reports_an_edit_in_another_folder(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    add_machine(fleet_git, "desktop")
    settle(fleet_git)
    write_doc(fleet_git, "machines/desktop/memory/notes.md")
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_CROSS}
    assert "machines/desktop" in payload["violations"][0]["message"]


def test_index_check_reports_a_missing_index(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    (fleet_git / "INDEX.md").unlink()
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_INDEX}
    assert "missing" in payload["violations"][0]["message"]


def test_index_check_reports_a_stale_index(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    write_doc(fleet_git, "machines/laptop/docs/plan.md")
    commit_all(fleet_git, "add a document")
    code, payload = check_doctor(capsys, fleet_git)
    assert code == 1
    assert checks(payload) == {doctor.CHECK_INDEX}
    assert "no longer matches" in payload["violations"][0]["message"]


def test_fix_restores_a_link_and_the_index(
    fleet_git: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    target = tmp_path / "agent" / "memory"
    set_links(fleet_git, "laptop", [{"source": "memory", "target": str(target)}])
    assert run("link", "--repo", str(fleet_git), "--machine", "laptop") == 0
    target.unlink()
    (fleet_git / "INDEX.md").unlink()

    code, payload = check_doctor(capsys, fleet_git, "--fix")
    assert code == 0
    assert payload["violations"] == []
    assert {item["check"] for item in payload["fixed"]} == {
        doctor.CHECK_LINK,
        doctor.CHECK_INDEX,
    }
    assert target.is_symlink()
    assert (fleet_git / "INDEX.md").is_file()


def test_fix_leaves_cross_machine_edits_alone(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    add_machine(fleet_git, "desktop")
    settle(fleet_git)
    stray = write_doc(fleet_git, "machines/desktop/memory/notes.md", "not mine\n")

    code, payload = check_doctor(capsys, fleet_git, "--fix")
    assert code == 1
    assert checks(payload) == {doctor.CHECK_CROSS}
    assert payload["fixed"] == []
    assert stray.read_text(encoding="utf-8") == "not mine\n"


def test_doctor_prints_the_check_id_of_every_violation(
    fleet_git: Path, capsys: pytest.CaptureFixture
) -> None:
    (fleet_git / "INDEX.md").unlink()
    assert run("doctor", "--repo", str(fleet_git), "--machine", "laptop") == 1
    assert f"[{doctor.CHECK_INDEX}]" in capsys.readouterr().out


def test_doctor_outside_a_git_repository_is_an_environment_error(
    fleet: Path, capsys: pytest.CaptureFixture
) -> None:
    code, payload = check_doctor(capsys, fleet)
    assert code == 2
    assert "not a git repository" in payload["error"]
