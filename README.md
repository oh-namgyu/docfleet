# docfleet - work in progress

docfleet is a git-native layout convention plus a zero-dependency Python CLI for
keeping AI-agent documents and memory in sync across several machines. One git
repository holds `machines/<name>/` for per-machine content, `shared/` for what
every machine uses, and a `fleet.json` registry at the root; each machine then
links its agent tool paths at the folders it owns inside the repository, so a
`git pull` is all it takes to move context between a laptop, a desktop and an
office workstation.

## The ownership rule

A machine may write its own `machines/<name>/` folder, `shared/`, and the root
metadata files (`fleet.json`, `README.md`, `INDEX.md`). Every other machine's
folder is read-only. `docfleet close` enforces this at the write path: it stages
only the owned areas, and a change anywhere else stops the run before anything
is committed. There is no override flag.

## Commands

| Command | What it does |
| --- | --- |
| `docfleet init --new REPO --machine NAME` | create the layout in an existing git repository |
| `docfleet init --join REPO --machine NAME` | register another machine in a cloned fleet |
| `docfleet link` | install the links declared in `machine.json` (`--adopt`, `--restore`) |
| `docfleet start` | fetch, rebase when the upstream moved, report what other machines changed |
| `docfleet close` | commit the owned areas, rebase, push (retries a rejected push once) |
| `docfleet doctor` | lint the layout, the registry, the links and the index (`--fix`) |
| `docfleet index` | rebuild `INDEX.md` from the layout |

`--json` turns any command into a machine-readable document on stdout.

Exit codes: `0` success, `1` the operation ran but could not finish (a blocked
`close`, a rebase conflict, doctor violations), `2` an environment or
configuration error with nothing modified.

Nothing in docfleet uses `git push --force` or `git reset --hard`. A rebase that
hits a conflict is aborted, which leaves the branch exactly as it was, and the
resolution steps are printed.

## License

MIT - see [LICENSE](LICENSE).
