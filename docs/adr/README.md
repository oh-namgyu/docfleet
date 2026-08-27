# Architecture decision records

Why docfleet is built the way it is. Each record states the context that forced a choice, the choice, and what it costs.

| ADR | Decision |
| --- | --- |
| [0001](0001-git-repo-not-sync-server.md) | A git repository, not a sync server |
| [0002](0002-read-only-peer-folders.md) | Peer machine folders are read-only, enforced in `close` |
| [0003](0003-directory-links.md) | Linked directories, not copied files |
| [0004](0004-stdlib-only.md) | Standard library only, zero runtime dependencies |
