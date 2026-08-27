# ADR 0003 — Linked directories, not copied files

**Status:** accepted · **Date:** 2026-08-27

## Context

The agent reads and writes a fixed path, say `~/.myagent/memory`. The repository holds `machines/laptop/memory/`. Something has to connect the two.

The straightforward implementation is a copy step: copy the agent path into the repository before committing, copy it back out after pulling. It needs no filesystem tricks and works identically everywhere.

It also has to answer a question that has no good answer: what happens to a file that exists on one side and not the other? A copy-in cannot distinguish "the agent deleted this" from "the agent has not created it yet", so it either resurrects deleted files forever or deletes files it should not. And it only runs when you remember to run it, which means the repository is stale exactly when you are moving between machines in a hurry.

## Decision

Make the agent path *be* the repository folder, through a directory link — a symlink on macOS and Linux, a directory junction on Windows. `docfleet link` reads the declarations in `machine.json` and installs them.

**Directories only.** A declaration whose target exists and is not a directory is rejected with exit `2`; individual files are never linked.

## Consequences

**Good.** There is no sync step, so there is nothing to forget and no stale window: the agent writes, and the bytes are already in the git work tree. Deletes, renames and new files need no reconciliation logic because there is only ever one copy of the data. `git status` tells the literal truth about the agent's memory at any moment.

**Costs.** A link is a real filesystem object with real failure modes — it can be removed, replaced, or left pointing at a stale location by an unrelated tool. `docfleet doctor` exists largely because of this, and reports each case under `link-broken`; `doctor --fix` reinstalls links through the normal `link` path. Tools that resolve symlinks before writing (some editors' atomic-save implementations) can replace a link with a regular directory; doctor catches that too. And installing a link over an existing directory means moving real data, which is why the whole no-data-loss contract — backups, manifests, `--restore` — exists at all.

**Why directories only.** A file link breaks the moment the file is replaced rather than modified, which is what atomic saves and most agent write paths actually do: write `notes.md.tmp`, rename over `notes.md`, and the link is gone, replaced by a plain file. A directory link is stable under exactly that operation, because the rename happens *inside* the linked directory. Linking directories also means one link covers a folder whose contents change constantly, so the link declaration does not need updating when the agent adds a file.

**The Windows story.** On Windows, `os.symlink` for a directory requires either administrator rights or Developer Mode — an install-time obstacle that would make docfleet fail for a normal user on their own machine. Directory *junctions* have no such requirement: any user can create one in a directory they own. So `create_dir_link` calls `_winapi.CreateJunction` first on Windows and falls back to `os.symlink` only if that fails. Junctions apply to directories and nothing else, which is the deeper reason the directories-only rule is not merely a preference: it is what makes one code path work unprivileged on all three platforms. The cost is that a junction is not a symlink — `Path.is_symlink()` returns `False` for one — so docfleet detects links through a helper that also consults `os.path.isjunction`, and removes them through a helper that falls back from `unlink` to `rmdir`.
