# Contributing to docfleet

Thanks for your interest! Bug reports and pull requests are welcome. docfleet
moves real directories, so changes are held to its safety model.

## Development setup

```sh
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"     # pytest is the only dev dependency
python -m pytest -q
docfleet --help
```

The tests create real git repositories and commits in temporary directories,
so git needs a committer identity (`user.name` / `user.email`). CI runs the
suite on Python 3.10 and 3.12 on Linux, and on 3.12 on macOS and Windows,
plus a smoke job that installs the package and runs the documented
quickstart.

## Guidelines

- **Standard library only.** No runtime dependencies, ever; see
  [ADR 0004](docs/adr/0004-stdlib-only.md).
- **Keep the no-data-loss contract.** Validate the whole configuration before
  touching the filesystem, move displaced data instead of deleting it, record
  every move in the manifest before linking, and keep every run reversible
  with `--restore`. See the Safety model in the [README](README.md).
- **Conservative git.** Never `push --force` or `reset --hard`; abort a
  conflicting rebase and explain the manual steps instead.
- **Keep the ownership rule.** `close` stages only the areas the current
  machine owns, with no override flag.
- **Document output changes.** A change to `--json` output or exit codes
  updates [docs/schema.md](docs/schema.md); a change to the layout updates
  [docs/structure.md](docs/structure.md).
- **Cross-platform.** Windows uses directory junctions; keep path handling
  working on all three CI platforms.
- Add a regression test for any bug fix, and a CHANGELOG entry for anything a
  user would notice.

## Pull requests

Keep PRs focused on one change, describe what changed and how you verified
it, and make sure `python -m pytest -q` is green before opening one.
