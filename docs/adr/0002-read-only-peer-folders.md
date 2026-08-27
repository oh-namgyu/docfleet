# ADR 0002 — Peer machine folders are read-only, enforced in `close`

**Status:** accepted · **Date:** 2026-08-27

## Context

Every machine's content lands in one shared repository, so every machine can *see* every other machine's folder. That is a feature: reading what the desktop knows from the laptop is the whole point of pooling them.

Writing is a different matter. A machine's folder describes that machine — its paths, its local state, its agent's memory of work done there. Nobody else is in a position to update it correctly, and an agent running on the laptop editing `machines/desktop/memory/` produces a change that the desktop's own agent will overwrite or, worse, believe.

Left unstated, this rule gets broken constantly. `git add -A` is muscle memory, and an agent asked to "update the notes" has no idea which folder it is standing in.

## Decision

Each machine folder is read-write to its owner and read-only to every other machine. `shared/` and the root metadata files (`fleet.json`, `README.md`, `INDEX.md`) are writable by all.

Enforcement lives in `docfleet close`, not in a git hook. `close` reads `git status`, and if any changed path falls outside the owned areas it stops before staging anything, prints the offending paths and exits `1`. There is no override flag. `close` also stages an explicit path list rather than `git add -A`, so an unrelated file in a peer folder cannot ride along on a legitimate commit.

`docfleet doctor` reports the same condition as `cross-machine`, and `doctor --fix` deliberately does not repair it.

## Consequences

**Good.** The rule is enforced where it is broken — at the moment of writing — and it fails loud and early, before a commit exists to unpick. Because it is a check on paths and not on file contents, it costs nothing and never has a false positive. Reading peer folders stays completely unrestricted, so the pooling benefit is intact.

**Costs.** Enforcement only covers commits made through `docfleet close`. Plain `git commit -am` bypasses it entirely — this is a convention with a helpful implementation, not a permission model, and the README says so. Legitimate cross-machine edits (fixing a typo in the desktop's notes from the laptop) have no shortcut: you make the edit on the machine that owns it, or you move the content to `shared/`.

**Why not a git hook.** A pre-commit hook was the first design and was dropped for three reasons. Hooks are not cloned, so every new machine would need a separate install step, and a machine that skipped it would be silently unprotected — the exact failure the rule exists to prevent. Hooks apply to *all* commits in the repository, including ones a person deliberately makes with plain git, which turns a convention into an obstruction. And a hook can only reject; it cannot explain which areas you own and what to do instead. Putting the check inside `close` means the guarantee travels with the tool, not with a machine's local git configuration, and the failure message can name the areas and the fix.
