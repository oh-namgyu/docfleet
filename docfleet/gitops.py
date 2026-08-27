"""Git plumbing shared by `sync` and `doctor`.

Every call goes through :func:`run_git`, which invokes the git executable
directly (never through a shell) and never uses `--force` or `reset --hard`.

Working-tree states reported by :func:`read_state`::

    not-a-repo       the directory is not inside a git working tree
    detached         HEAD does not point at a branch
    rebase-conflict  a rebase is in progress and waits for a resolution
    no-remote        no upstream branch, or the remote cannot be reached
    diverged         local and upstream both hold commits the other lacks
    behind           the upstream holds commits this branch lacks
    ahead            this branch holds commits the upstream lacks
    dirty            in sync with the upstream, but the work tree has changes
    clean            in sync with the upstream and nothing to commit

`not-a-repo`, `detached` and `no-remote` are environment errors: they abort
with exit code 2 and carry the state name in the message and in `--json`.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

GIT_TIMEOUT = 120

STATE_CLEAN = "clean"
STATE_AHEAD = "ahead"
STATE_BEHIND = "behind"
STATE_DIVERGED = "diverged"
STATE_REBASE_CONFLICT = "rebase-conflict"
STATE_DETACHED = "detached"
STATE_NO_REMOTE = "no-remote"
STATE_NOT_A_REPO = "not-a-repo"
STATE_DIRTY = "dirty"

ENVIRONMENT_STATES = (STATE_NOT_A_REPO, STATE_DETACHED, STATE_NO_REMOTE)
BEHIND_STATES = (STATE_BEHIND, STATE_DIVERGED)


class GitStateError(ConfigError):
    """An environment error naming the git state that caused it."""


def state_error(state: str, message: str) -> GitStateError:
    """Build an environment error that carries `state` into --json output."""
    return GitStateError(f"{message} (state: {state})", state=state)


@dataclass(frozen=True)
class GitState:
    """A snapshot of one working tree relative to its upstream branch."""

    state: str
    branch: str | None = None
    remote: str | None = None
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    dirty: bool = False

    @property
    def is_environment_error(self) -> bool:
        """Return True when this state means docfleet cannot operate at all."""
        return self.state in ENVIRONMENT_STATES

    @property
    def needs_rebase(self) -> bool:
        """Return True when the upstream holds commits this branch lacks."""
        return self.state in BEHIND_STATES


def run_git(
    repo: Path, *args: str, timeout: int = GIT_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    """Run one git command in `repo` and return the completed process."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ConfigError("git executable not found: install git first") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfigError(f"git {' '.join(args)} could not run: {exc}") from exc


def git_text(repo: Path, *args: str) -> str:
    """Run a git command that must succeed and return its stdout."""
    result = run_git(repo, *args)
    if result.returncode != 0:
        raise ConfigError(f"git {' '.join(args)} failed: {message_of(result)}")
    return result.stdout


def message_of(result: subprocess.CompletedProcess[str]) -> str:
    """Return the most useful line of a failed git command."""
    text = (result.stderr or result.stdout).strip()
    return text.splitlines()[-1] if text else f"exit code {result.returncode}"


def is_work_tree(repo: Path) -> bool:
    """Return True when `repo` sits inside a git working tree."""
    result = run_git(repo, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def rebase_in_progress(repo: Path) -> bool:
    """Return True when a rebase is waiting for the user to resolve it."""
    result = run_git(repo, "rev-parse", "--git-dir")
    if result.returncode != 0:
        return False
    git_dir = Path(result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def _status_paths(repo: Path, extra: list[str]) -> list[str]:
    tokens = git_text(repo, "status", "--porcelain", "-z", *extra).split("\0")
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if len(token) < 4:
            continue
        code, path = token[:2], token[3:]
        paths.append(path)
        if ("R" in code or "C" in code) and index < len(tokens):
            paths.append(tokens[index])
            index += 1
    return paths


def changed_paths(repo: Path) -> list[str]:
    """Return every path with staged, unstaged or untracked changes.

    Porcelain collapses a fully-untracked directory to a single "dir/" entry
    (e.g. "machines/" in a repo with no commits yet), which hides which
    machine the files belong to. Such entries are expanded to their
    individual paths so ownership checks stay accurate.
    """
    expanded: set[str] = set()
    for path in _status_paths(repo, []):
        if path.endswith("/"):
            expanded.update(_status_paths(repo, ["-uall", "--", path]) or [path])
        else:
            expanded.add(path)
    return sorted(expanded)


def _divergence(repo: Path, upstream: str) -> tuple[int, int]:
    counts = git_text(repo, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
    behind, _, ahead = counts.strip().partition("\t")
    return int(ahead or 0), int(behind or 0)


def read_state(repo: Path) -> GitState:
    """Classify the working tree at `repo`. Never modifies anything."""
    if not is_work_tree(repo):
        return GitState(STATE_NOT_A_REPO)
    branch_result = run_git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch_result.returncode != 0:
        return GitState(STATE_DETACHED)
    branch = branch_result.stdout.strip()
    upstream_result = run_git(
        repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    dirty = bool(changed_paths(repo))
    if upstream_result.returncode != 0:
        return GitState(STATE_NO_REMOTE, branch=branch, dirty=dirty)
    upstream = upstream_result.stdout.strip()
    remote = run_git(repo, "config", "--get", f"branch.{branch}.remote").stdout.strip()
    if rebase_in_progress(repo):
        state = STATE_REBASE_CONFLICT
        ahead = behind = 0
    else:
        ahead, behind = _divergence(repo, upstream)
        if ahead and behind:
            state = STATE_DIVERGED
        elif behind:
            state = STATE_BEHIND
        elif ahead:
            state = STATE_AHEAD
        else:
            state = STATE_DIRTY if dirty else STATE_CLEAN
    return GitState(
        state=state,
        branch=branch,
        remote=remote or None,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        dirty=dirty,
    )


def require_usable(repo: Path) -> GitState:
    """Read the state and abort with exit code 2 when git cannot be used."""
    state = read_state(repo)
    if state.state == STATE_NOT_A_REPO:
        raise state_error(state.state, f"not a git repository: {repo}")
    if state.state == STATE_DETACHED:
        raise state_error(
            state.state,
            f"HEAD in {repo} does not point at a branch: "
            "check out a branch before syncing",
        )
    if state.state == STATE_NO_REMOTE:
        raise state_error(
            state.state,
            f"branch {state.branch or 'HEAD'} in {repo} has no upstream branch: "
            "add a remote and push once with `git push -u`",
        )
    return state


def head(repo: Path) -> str:
    """Return the current commit hash."""
    return git_text(repo, "rev-parse", "HEAD").strip()


def commits_between(repo: Path, old: str, new: str) -> list[dict]:
    """Return the commits reachable from `new` but not `old`, oldest first."""
    if old == new:
        return []
    output = git_text(
        repo, "log", "--reverse", "--format=%h\x1f%s", f"{old}..{new}"
    ).strip()
    commits: list[dict] = []
    for line in output.splitlines():
        short, _, subject = line.partition("\x1f")
        commits.append({"hash": short, "subject": subject})
    return commits


def areas_between(repo: Path, old: str, new: str) -> list[str]:
    """Return the top-level areas (machine folders, shared, root files) touched."""
    if old == new:
        return []
    output = git_text(repo, "diff", "--name-only", f"{old}..{new}").strip()
    areas = {area_of(path) for path in output.splitlines() if path}
    return sorted(areas)


def area_of(path: str) -> str:
    """Map a repository path onto the area it belongs to."""
    parts = path.split("/")
    if parts[0] == "machines" and len(parts) > 1:
        return "/".join(parts[:2])
    return parts[0]
