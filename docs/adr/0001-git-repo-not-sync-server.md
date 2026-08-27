# ADR 0001 — A git repository, not a sync server

**Status:** accepted · **Date:** 2026-08-27

## Context

The problem is moving agent documents and memory between a handful of machines owned by one person. The obvious shapes for that are:

1. **A sync service** — a small server the machines talk to, holding the canonical copy.
2. **A file-sync product** — a folder replicated by an existing consumer tool.
3. **A git repository** — machines push and pull an ordinary repository.

The content is almost entirely text that a person reads and edits: notes, standards, memory files. It changes a few times a day, not a few times a second. Two machines edit the same file at the same moment rarely, but *do* both edit the same file across a week. When something goes wrong, the question is nearly always "what did the other machine change, and when?"

Options 1 and 2 both solve real-time replication, which is not the problem here, and both introduce something that has to be running and reachable for work to happen.

## Decision

Use a plain git repository as the only transport. docfleet ships no server, no daemon, no background process and no account. `start` is fetch-then-rebase; `close` is stage-commit-rebase-push. The remote is whatever git can reach.

docfleet does not even create the repository: `init` requires an existing git work tree and says so if there is not one. The repository is the user's, and git remains the tool that owns it.

## Consequences

**Good.** History, diffs, blame and revert come free, and they are exactly the tools for "what did the other machine change?". Any git host works, including a private repository or a bare repo on a NAS. Nothing runs when you are not using it, so there is nothing to keep alive, and no availability of ours to depend on. A fleet repository remains fully usable with plain git if docfleet disappears — the convention outlives the tool.

**Costs.** Sync is explicit: you run `start` and `close`, and a machine you forget to close simply has not published. There is no locking, so two machines can produce a conflict in `shared/`; git surfaces it, and docfleet aborts the rebase and hands it back rather than guessing. Binary or very large memory files are a poor fit for git and stay a poor fit here. The first publish needs one manual `git push -u` to establish an upstream, because `close` needs an upstream branch to rebase onto.

**Rejected alternative worth naming.** A file-sync product would have made the daily loop invisible, and it is genuinely tempting. It was rejected because it replicates a *conflicted* state instead of refusing it: two machines editing one memory file silently produce a duplicate file, and no history explains which side is which. The ownership rule in [ADR 0002](0002-read-only-peer-folders.md) is only enforceable because a commit is an explicit, inspectable event.
