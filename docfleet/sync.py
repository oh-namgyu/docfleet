"""The `start` and `close` commands: the two ends of a work session.

`start` brings in what the other machines did: fetch, rebase when the upstream
moved ahead, then report the commits and areas that arrived.

`close` publishes this machine's work. It enforces the ownership rule at the
write path: only `machines/<own machine>/`, `shared/` and the root metadata
files are ever staged. A change outside those areas -- above all in another
machine's folder -- stops the run before anything is committed, and there is
no flag to override it.

The order matters. A rebase needs a clean work tree, so `close` commits first,
then rebases the now-clean tree, then pushes. A rejected push (another machine
pushed in between) is retried exactly once after a fresh fetch and rebase.
Neither command ever uses `--force` or `reset --hard`; a rebase that hits a
conflict is aborted, which leaves the local branch exactly as it was.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import OperationError
from .gitops import (
    STATE_NO_REMOTE,
    STATE_REBASE_CONFLICT,
    GitState,
    areas_between,
    changed_paths,
    commits_between,
    git_text,
    message_of,
    read_state,
    require_usable,
    run_git,
    state_error,
)
from .layout import is_writable_path, writable_prefixes
from .util import today_iso

CONFLICT_HELP = (
    "the rebase was aborted, so your branch is exactly as it was before.\n"
    "resolve it by hand:\n"
    "  1. git rebase <upstream>\n"
    "  2. edit the conflicting files, then `git add` them\n"
    "  3. git rebase --continue\n"
    "  4. run docfleet close again"
)


def default_message(machine: str) -> str:
    """Return the commit message used when `-m` is not given."""
    return f"docfleet close: {machine} {today_iso()}"


def fetch(repo: Path, state: GitState) -> None:
    """Fetch the upstream remote, treating an unreachable remote as fatal."""
    remote = state.remote or "origin"
    result = run_git(repo, "fetch", remote)
    if result.returncode != 0:
        raise state_error(
            STATE_NO_REMOTE,
            f"cannot reach remote {remote!r}: {message_of(result)}",
        )


def push(repo: Path, state: GitState) -> subprocess.CompletedProcess[str]:
    """Push the current branch to its upstream branch."""
    remote = state.remote or "origin"
    prefix = f"{remote}/"
    upstream = state.upstream or ""
    branch = upstream[len(prefix) :] if upstream.startswith(prefix) else state.branch
    return run_git(repo, "push", remote, f"HEAD:refs/heads/{branch}")


def rebase_onto_upstream(repo: Path, state: GitState) -> None:
    """Rebase onto the upstream, aborting and reporting on a conflict."""
    result = run_git(repo, "rebase", str(state.upstream))
    if result.returncode == 0:
        return
    run_git(repo, "rebase", "--abort")
    raise OperationError(
        f"rebase onto {state.upstream} hit a conflict: {message_of(result)}\n"
        f"{CONFLICT_HELP}",
        state=STATE_REBASE_CONFLICT,
    )


def _require_no_rebase(state: GitState) -> None:
    if state.state == STATE_REBASE_CONFLICT:
        raise OperationError(
            f"a rebase is already in progress (state: {state.state})\n"
            "finish it with `git rebase --continue`, or undo it with "
            "`git rebase --abort`, then run docfleet again",
            state=state.state,
        )


def _incoming(repo: Path, state: GitState) -> tuple[list[dict], list[str]]:
    """Return the commits and areas the upstream holds and this branch lacks."""
    if not state.needs_rebase or not state.upstream:
        return [], []
    base = git_text(repo, "merge-base", "HEAD", state.upstream).strip()
    return (
        commits_between(repo, base, state.upstream),
        areas_between(repo, base, state.upstream),
    )


def _pull(repo: Path, state: GitState) -> tuple[GitState, list[dict], list[str]]:
    """Fetch, then rebase when the upstream moved ahead."""
    fetch(repo, state)
    state = read_state(repo)
    commits, areas = _incoming(repo, state)
    if state.needs_rebase:
        if state.dirty:
            raise OperationError(
                f"the upstream moved ahead but the work tree has uncommitted "
                f"changes (state: {state.state})\n"
                "run `docfleet close` to commit them, or stash them first",
                state=state.state,
            )
        rebase_onto_upstream(repo, state)
        state = read_state(repo)
    return state, commits, areas


def run_start(repo: Path, machine: str) -> dict:
    """Run `docfleet start`. Returns a result document."""
    state = require_usable(repo)
    _require_no_rebase(state)
    state, commits, areas = _pull(repo, state)
    return {
        "command": "start",
        "repo": str(repo),
        "machine": machine,
        "state": state.state,
        "commits": commits,
        "areas": areas,
        "unpushed": state.ahead,
        "status": "ok",
        "error": None,
        "exit_code": 0,
    }


def _blocked(repo: Path, machine: str, state: GitState, paths: list[str]) -> dict:
    allowed = ", ".join(writable_prefixes(machine))
    return {
        "command": "close",
        "repo": str(repo),
        "machine": machine,
        "state": state.state,
        "violations": paths,
        "staged": [],
        "committed": None,
        "commits": [],
        "areas": [],
        "unpushed": state.ahead,
        "status": "blocked",
        "error": (
            f"{len(paths)} change(s) outside the areas machine {machine!r} owns "
            f"({allowed} and the root metadata files); nothing was committed"
        ),
        "exit_code": 1,
    }


def _stage(repo: Path, paths: list[str]) -> list[str]:
    """Stage exactly the given paths and return what ended up in the index."""
    if paths:
        result = run_git(repo, "add", "--all", "--", *paths)
        if result.returncode != 0:
            raise OperationError(f"could not stage changes: {message_of(result)}")
    staged = git_text(repo, "diff", "--cached", "--name-only").strip()
    return sorted(line for line in staged.splitlines() if line)


def _commit(repo: Path, message: str) -> str:
    result = run_git(repo, "commit", "-m", message)
    if result.returncode != 0:
        raise OperationError(f"commit failed: {message_of(result)}")
    return git_text(repo, "rev-parse", "--short", "HEAD").strip()


def _push_once(repo: Path, state: GitState) -> str | None:
    """Push and return the failure message, or None on success."""
    result = push(repo, state)
    return None if result.returncode == 0 else message_of(result)


def _push_with_retry(repo: Path, state: GitState) -> GitState:
    """Push, retrying once after a fresh fetch and rebase when it is rejected."""
    first = _push_once(repo, state)
    if first is None:
        return read_state(repo)
    state, _, _ = _pull(repo, read_state(repo))
    second = _push_once(repo, state)
    if second is not None:
        raise OperationError(
            f"push was rejected twice: {first}; after fetch and rebase: {second}\n"
            "your commits are safe in the local branch -- push by hand once the "
            "remote settles",
            state=state.state,
        )
    return read_state(repo)


def run_close(repo: Path, machine: str, message: str | None = None) -> dict:
    """Run `docfleet close`. Returns a result document."""
    state = require_usable(repo)
    _require_no_rebase(state)
    changed = changed_paths(repo)
    violations = [path for path in changed if not is_writable_path(path, machine)]
    if violations:
        return _blocked(repo, machine, state, violations)
    staged = _stage(repo, changed)
    committed = _commit(repo, message or default_message(machine)) if staged else None
    state, commits, areas = _pull(repo, read_state(repo))
    state = _push_with_retry(repo, state)
    return {
        "command": "close",
        "repo": str(repo),
        "machine": machine,
        "state": state.state,
        "violations": [],
        "staged": staged,
        "committed": committed,
        "commits": commits,
        "areas": areas,
        "unpushed": state.ahead,
        "status": "ok",
        "error": None,
        "exit_code": 0,
    }
