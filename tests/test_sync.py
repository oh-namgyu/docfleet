"""Tests for `docfleet start` and `docfleet close` against real git clones."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from docfleet import sync
from tests.conftest import BRANCH, commit_all, git, run, run_json, write_doc


def log(repo: Path) -> list[str]:
    """Return the commit subjects of a repository, newest first."""
    return git(repo, "log", "--format=%s").splitlines()


def rebase_in_progress(repo: Path) -> bool:
    """Return True when git left a rebase half-finished."""
    git_dir = repo / ".git"
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def close(capsys: pytest.CaptureFixture, repo: Path, machine: str) -> tuple[int, dict]:
    """Run `docfleet close` for one machine."""
    return run_json(capsys, "close", "--repo", str(repo), "--machine", machine)


def start(capsys: pytest.CaptureFixture, repo: Path, machine: str) -> tuple[int, dict]:
    """Run `docfleet start` for one machine."""
    return run_json(capsys, "start", "--repo", str(repo), "--machine", machine)


def test_close_publishes_and_start_reports_it(
    laptop: Path, desktop: Path, capsys: pytest.CaptureFixture
) -> None:
    write_doc(laptop, "machines/laptop/docs/plan.md", "a plan\n")
    code, closed = close(capsys, laptop, "laptop")
    assert code == 0
    assert closed["committed"]
    assert "machines/laptop/docs/plan.md" in closed["staged"]

    code, started = start(capsys, desktop, "desktop")
    assert code == 0
    assert [commit["subject"] for commit in started["commits"]] == log(laptop)[:1]
    assert started["areas"] == ["machines/laptop"]
    assert (desktop / "machines/laptop/docs/plan.md").read_text(encoding="utf-8")


def test_close_and_start_print_a_readable_summary(
    laptop: Path, desktop: Path, capsys: pytest.CaptureFixture
) -> None:
    write_doc(laptop, "machines/laptop/docs/plan.md")
    assert run("close", "--repo", str(laptop), "--machine", "laptop") == 0
    assert "committed" in capsys.readouterr().out

    assert run("start", "--repo", str(desktop), "--machine", "desktop") == 0
    output = capsys.readouterr().out
    assert "1 commit(s) from other machines" in output
    assert "areas touched: machines/laptop" in output


def test_close_prints_the_paths_it_refused_to_stage(
    laptop: Path, desktop: Path, capsys: pytest.CaptureFixture
) -> None:
    write_doc(laptop, "machines/desktop/docs/stolen.md")
    assert run("close", "--repo", str(laptop), "--machine", "laptop") == 1
    captured = capsys.readouterr()
    assert "machines/desktop/docs/stolen.md" in captured.out
    assert "nothing was committed" in captured.err


def test_close_uses_the_given_commit_message(
    laptop: Path, capsys: pytest.CaptureFixture
) -> None:
    write_doc(laptop, "shared/standards/style.md")
    code = sync.run_close(laptop, "laptop", "write the style guide")["exit_code"]
    assert code == 0
    assert log(laptop)[0] == "write the style guide"


def test_close_refuses_to_stage_another_machines_folder(
    laptop: Path, desktop: Path, capsys: pytest.CaptureFixture
) -> None:
    before = log(laptop)
    write_doc(laptop, "machines/desktop/docs/stolen.md")
    write_doc(laptop, "machines/laptop/docs/mine.md")
    code, payload = close(capsys, laptop, "laptop")
    assert code == 1
    assert payload["violations"] == ["machines/desktop/docs/stolen.md"]
    assert payload["committed"] is None
    assert log(laptop) == before
    assert git(laptop, "diff", "--cached", "--name-only") == ""
    assert (laptop / "machines/desktop/docs/stolen.md").is_file()


def test_close_with_nothing_to_commit_exits_quietly(
    laptop: Path, capsys: pytest.CaptureFixture
) -> None:
    write_doc(laptop, "machines/laptop/docs/plan.md")
    assert close(capsys, laptop, "laptop")[0] == 0
    before = log(laptop)
    code, payload = close(capsys, laptop, "laptop")
    assert code == 0
    assert payload["committed"] is None
    assert payload["staged"] == []
    assert payload["unpushed"] == 0
    assert log(laptop) == before


def test_close_rebases_over_another_machine(
    laptop: Path, desktop: Path, capsys: pytest.CaptureFixture
) -> None:
    write_doc(laptop, "shared/commands/from-laptop.md")
    assert close(capsys, laptop, "laptop")[0] == 0

    write_doc(desktop, "shared/commands/from-desktop.md")
    code, payload = close(capsys, desktop, "desktop")
    assert code == 0
    assert payload["areas"] == ["shared"]
    assert (desktop / "shared/commands/from-laptop.md").is_file()
    assert (desktop / "shared/commands/from-desktop.md").is_file()
    assert payload["unpushed"] == 0


def test_start_aborts_a_conflicting_rebase_and_keeps_local_content(
    laptop: Path, desktop: Path, capsys: pytest.CaptureFixture
) -> None:
    write_doc(laptop, "shared/commands/note.md", "from laptop\n")
    assert close(capsys, laptop, "laptop")[0] == 0

    write_doc(desktop, "shared/commands/note.md", "from desktop\n")
    commit_all(desktop, "desktop note")
    before = log(desktop)

    code, payload = start(capsys, desktop, "desktop")
    assert code == 1
    assert payload["state"] == "rebase-conflict"
    assert "git rebase --continue" in payload["error"]
    assert not rebase_in_progress(desktop)
    assert log(desktop) == before
    assert (desktop / "shared/commands/note.md").read_text(
        encoding="utf-8"
    ) == "from desktop\n"


def test_start_on_a_detached_head_is_an_environment_error(
    laptop: Path, capsys: pytest.CaptureFixture
) -> None:
    git(laptop, "checkout", "--detach", "HEAD")
    code, payload = start(capsys, laptop, "laptop")
    assert code == 2
    assert payload["state"] == "detached"
    assert "detached" in payload["error"]


def test_start_without_a_remote_is_an_environment_error(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    repo = tmp_path / "solo"
    repo.mkdir()
    git(repo, "init", "--initial-branch", BRANCH)
    git(repo, "config", "user.email", "fleet@example.com")
    git(repo, "config", "user.name", "Fleet Tester")
    assert run_json(capsys, "init", "--new", str(repo), "--machine", "office")[0] == 0
    commit_all(repo, "create fleet")
    code, payload = start(capsys, repo, "office")
    assert code == 2
    assert payload["state"] == "no-remote"


def test_close_survives_a_push_that_lands_after_the_fetch(
    laptop: Path, desktop: Path, capsys: pytest.CaptureFixture
) -> None:
    write_doc(desktop, "machines/desktop/docs/first.md")
    assert close(capsys, desktop, "desktop")[0] == 0

    write_doc(laptop, "machines/laptop/docs/second.md")
    code, payload = close(capsys, laptop, "laptop")
    assert code == 0
    assert payload["areas"] == ["machines/desktop"]
    assert (laptop / "machines/desktop/docs/first.md").is_file()
    assert payload["unpushed"] == 0


def test_close_retries_a_rejected_push_once(
    laptop: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_push = sync.push
    attempts: list[int] = []

    def flaky(repo: Path, state: sync.GitState) -> subprocess.CompletedProcess:
        attempts.append(1)
        if len(attempts) == 1:
            return subprocess.CompletedProcess(
                ["git", "push"], 1, "", "! [rejected] main -> main (fetch first)\n"
            )
        return real_push(repo, state)

    monkeypatch.setattr(sync, "push", flaky)
    write_doc(laptop, "machines/laptop/docs/plan.md")
    code, payload = close(capsys, laptop, "laptop")
    assert code == 0
    assert len(attempts) == 2
    assert payload["unpushed"] == 0


def test_close_reports_a_push_rejected_twice(
    laptop: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_rejected(repo: Path, state: sync.GitState) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(["git", "push"], 1, "", "! [rejected]\n")

    monkeypatch.setattr(sync, "push", always_rejected)
    write_doc(laptop, "machines/laptop/docs/plan.md")
    code, payload = close(capsys, laptop, "laptop")
    assert code == 1
    assert "rejected twice" in payload["error"]
    assert log(laptop)[0].startswith("docfleet close: laptop")
