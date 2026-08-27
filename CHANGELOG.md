# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-08-27

First release. Everything below is new.

### The layout convention

- A fleet repository: `fleet.json` registry at the root, one `machines/<name>/`
  folder per machine, one `shared/` folder for content every machine uses.
- The ownership rule: a machine may write its own machine folder, `shared/`,
  and the root metadata files. Every other machine folder is read-only to it.
- Documented as a standalone specification in [docs/structure.md](docs/structure.md),
  with the reasoning in [docs/adr/](docs/adr/).

### Commands

- `docfleet init --new` / `--join` — create the layout in an existing git
  repository, or register an additional machine in a cloned fleet.
- `docfleet link` — install the directory links declared in `machine.json`;
  `--adopt` moves an existing target directory into the repository to become
  the link source, `--restore` (with optional `--at TS`) reverses a run.
- `docfleet start` — fetch, rebase when the upstream moved ahead, and report
  the commits and areas that arrived from other machines.
- `docfleet close` — stage only the areas this machine owns, commit, rebase
  and push; a change outside those areas stops the run before anything is
  staged, with no override flag.
- `docfleet doctor` — seven structure checks (`layout`, `machine-name`,
  `registry`, `mapping`, `link-broken`, `cross-machine`, `index-stale`);
  `--fix` reinstalls links and rewrites `INDEX.md` and nothing else.
- `docfleet index` — rebuild `INDEX.md` deterministically from the layout.
- Global `--json` on every command, with a documented field-by-field schema in
  [docs/schema.md](docs/schema.md), and the exit-code contract `0` / `1` / `2`.

### Behaviour worth calling out

- No-data-loss contract: the whole configuration is validated before any
  filesystem change; displaced directories are moved, never deleted; every
  move is recorded in a manifest before the link is created; `--restore` walks
  a run back and skips — rather than overwrites — any target that something
  new has taken over.
- No git operation uses `--force` or `reset --hard`. A conflicting rebase is
  aborted and explained; a rejected push is retried once after a fresh fetch
  and rebase.
- Windows uses directory junctions, so linking needs no elevated privileges.

### Project

- Zero runtime dependencies; Python 3.10+; MIT licensed.
- 80 tests, run on Linux, macOS and Windows in CI, plus a smoke job that
  installs the package and runs the documented quickstart end to end.

[0.1.0]: https://github.com/oh-namgyu/docfleet/releases/tag/v0.1.0
