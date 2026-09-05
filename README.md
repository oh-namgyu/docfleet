# docfleet

[![CI](https://github.com/oh-namgyu/docfleet/actions/workflows/ci.yml/badge.svg)](https://github.com/oh-namgyu/docfleet/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

> **한글 요약** — docfleet은 여러 대의 컴퓨터에서 쓰는 AI 에이전트의 문서와 메모리를 하나의 git 저장소로 모으는 폴더 규약이자, 그 규약을 지켜 주는 의존성 없는 파이썬 CLI입니다. 저장소는 컴퓨터마다 하나씩 갖는 `machines/<이름>/` 과 모두가 함께 쓰는 `shared/`, 그리고 등록부인 `fleet.json` 으로 이루어집니다. 각 컴퓨터는 에이전트가 실제로 읽는 경로(예: `~/.myagent/memory`)를 자기 폴더로 **디렉터리 심링크(윈도우에서는 정션)** 로 연결하므로, 파일을 복사하지 않고 `git pull` 한 번이면 맥락이 옮겨 갑니다. 규칙은 단순합니다 — 자기 폴더는 읽기·쓰기, 남의 폴더는 읽기 전용, `shared/` 는 모두 쓰기 가능이며 `docfleet close` 가 커밋 직전에 이를 강제합니다. 서버도, 데몬도, 런타임 의존성도 없습니다.

**A git-native layout convention — plus a zero-dependency CLI — for keeping AI-agent docs and memory in sync across your machines.**

---

## Why

You run the same AI coding agent on a laptop, a desktop, and an office machine. Each one slowly accumulates its own context: notes the agent wrote, project documents, memory files, shared instructions. None of it moves between machines on its own.

So you improvise. You copy a folder over. You paste yesterday's notes into today's session. You end up with three divergent copies of the same memory directory and no idea which one is current — and when you finally try to merge them, you find out that the machine-specific parts (paths, ports, local quirks) were never supposed to merge in the first place.

docfleet takes the position that this is a **layout problem, not a tooling problem**. Two kinds of content are mixed together and need to be separated:

| Content | Lives in | Who writes it |
| --- | --- | --- |
| "What *this* machine knows" — local memory, machine-specific docs | `machines/<name>/` | that machine only |
| "What *every* machine uses" — commands, standards, conventions | `shared/` | any machine |

Once they are separated, a plain git repository is enough to carry both. That is the whole idea. The CLI exists to make the convention cheap to follow and hard to violate by accident.

## The layout

A fleet repository is an ordinary git repository shaped like this:

```
fleet-repo/
├── fleet.json                   # the machine registry — who is in the fleet
├── INDEX.md                     # generated table of contents (docfleet index)
├── README.md                    # created on init when missing
│
├── machines/                    # one folder per machine
│   ├── laptop/
│   │   ├── machine.json         # this machine's link declarations
│   │   ├── docs/                # laptop's documents      ← listed in INDEX.md
│   │   └── memory/              # laptop's agent memory   ← usually the link source
│   ├── desktop/
│   │   ├── machine.json
│   │   ├── docs/
│   │   └── memory/
│   └── office/
│       └── ...
│
└── shared/                      # every machine reads and writes this
    ├── commands/
    └── standards/
```

`machines/laptop/` is read-write **on the laptop** and read-only everywhere else. The same folder is therefore a reliable answer to "what does the desktop currently think?" — you can read it from any machine, and you never have to wonder whether your local edit is about to clobber it.

Empty directories are kept in git with a `.gitkeep` file, which `docfleet` writes on `init` and ignores everywhere else.

The full specification — every path, every schema field, naming rules, and a suggested document-tier convention — is in **[docs/structure.md](docs/structure.md)**.

## How it works

Two mechanisms, no server:

**1. Directory links, not copies.** Your agent reads `~/.myagent/memory`. docfleet makes that path a *directory link* — a symlink on macOS and Linux, a directory junction on Windows — pointing into `machines/<name>/memory/` inside the repository. The agent keeps writing to the path it always used; the bytes land inside a git work tree. There is no sync loop, no file watcher, no copy step to forget. Only directories are linked, never individual files: a directory link stays correct while files inside it are created, renamed and deleted.

**2. Git is the only transport.** `docfleet start` is fetch-then-rebase plus a report of what other machines changed. `docfleet close` is stage-your-own-areas, commit, rebase, push. There is no docfleet server, no daemon, no account, and no background process — if git can reach the remote, docfleet works, and if it cannot, nothing happens at all. The remote can be anything git speaks to, including a private repository or a folder on a NAS.

Everything is written against the Python standard library. No runtime dependencies, ever — see [ADR 0004](docs/adr/0004-stdlib-only.md).

## Quickstart

```bash
pip install git+https://github.com/oh-namgyu/docfleet
```

**Create the fleet on the first machine.** docfleet never runs `git init` for you, so make the repository first:

```bash
mkdir ~/fleet && cd ~/fleet
git init -b main
git remote add origin git@github.com:you/fleet.git

docfleet init --new . --machine laptop
```

That writes `fleet.json`, `machines/laptop/{docs,memory}/`, `machines/laptop/machine.json`, `shared/{commands,standards}/`, and a placeholder `README.md`.

**Declare what to link.** Edit `machines/laptop/machine.json`:

```json
{
  "machine": "laptop",
  "links": [
    { "source": "memory", "target": "~/.myagent/memory" }
  ]
}
```

`source` is a directory inside the machine folder; `target` is an absolute path on this machine (`~` is expanded).

**Adopt the data you already have.** Your agent's memory directory already exists and has content in it. `--adopt` *moves* that directory into the repository and puts the link in its place:

```bash
docfleet link --adopt
```

Without `--adopt`, an existing directory at the target is moved to a timestamped backup instead — never deleted. Either way the move is recorded in a manifest before the link is created, and `docfleet link --restore` walks it back.

**Publish it.** The very first publish is plain git, because `close` needs an upstream branch to rebase onto and push to:

```bash
docfleet index                      # regenerate INDEX.md
git add -A && git commit -m "create fleet"
git push -u origin main             # sets the upstream, once
```

From here on, `docfleet close` does the commit-rebase-push for you.

**Join from the second machine:**

```bash
git clone git@github.com:you/fleet.git ~/fleet && cd ~/fleet

docfleet init --join . --machine desktop
# edit machines/desktop/machine.json, then:
docfleet link --adopt
docfleet close
```

**The daily loop**, on whichever machine you sit down at:

```bash
docfleet start          # pull in what the other machines did, and say what changed
# ... work; your agent reads and writes through the link as usual ...
docfleet close -m "notes from the API refactor"
```

A full copy-pasteable two-machine walkthrough is in **[docs/quickstart-two-machines.md](docs/quickstart-two-machines.md)**.

## Commands

| Command | Flags | What it does |
| --- | --- | --- |
| `docfleet init --new REPO --machine NAME` | — | create the layout in an existing git repository and register the first machine |
| `docfleet init --join REPO --machine NAME` | — | register an additional machine in a cloned fleet |
| `docfleet link` | `--adopt`, `--restore`, `--at TS`, `--repo`, `--machine` | install the links declared in `machine.json` |
| `docfleet start` | `--repo`, `--machine` | fetch, rebase when the upstream moved ahead, report incoming commits and areas |
| `docfleet close` | `-m/--message`, `--repo`, `--machine` | stage the owned areas, commit, rebase, push |
| `docfleet doctor` | `--fix`, `--repo`, `--machine` | run seven structure checks over the repository |
| `docfleet index` | `--repo` | rebuild `INDEX.md` from the layout |

Global flags: `--json` (machine-readable output on stdout, documented field by field in [docs/schema.md](docs/schema.md)) and `--version`.

`--repo` defaults to the nearest fleet repository at or above the working directory. `--machine` defaults to the only registered machine, and is required once there are two or more.

**Exit codes:**

| Code | Meaning |
| --- | --- |
| `0` | success |
| `1` | the operation ran but could not finish it all — a blocked `close`, a rebase conflict, doctor violations, a failed link item, skipped restore items |
| `2` | environment or configuration error — **nothing was modified** |

`docfleet link` validates the *entire* configuration before touching the filesystem, so a malformed `machine.json` is always a clean exit `2`.

## The rules

One rule, stated three ways:

- **Your machine folder** — `machines/<your name>/` — is yours to read and write.
- **Every other machine folder** is read-only to you. Read it freely; never commit into it.
- **`shared/`** and the root metadata files (`fleet.json`, `README.md`, `INDEX.md`) are writable by everyone.

`docfleet close` enforces this at the write path rather than trusting you to remember it. It reads `git status`, and if any changed path falls outside the areas this machine owns, it stops **before staging anything**:

```
close stopped: these paths are outside the areas you own
  ! machines/desktop/memory/notes.md
```

Nothing is committed, exit code `1`, and there is no flag to override it — the fix is to move your edit into your own folder or into `shared/`. Because `close` stages an explicit path list rather than running `git add -A`, a stray file in someone else's folder cannot ride along unnoticed either.

`docfleet doctor` reports the same situation ahead of time under the check id `cross-machine`, and deliberately refuses to "fix" it: uncommitted work in another machine's folder is somebody's unsaved work, not a defect. See [ADR 0002](docs/adr/0002-read-only-peer-folders.md) for why the enforcement lives in `close` instead of a git hook.

## Safety model

docfleet moves real directories around, so it owes you a hard contract. The contract is: **no operation deletes data you did not put there.**

1. **Validate first, then act.** `docfleet link` plans and validates every declared item — sources exist, targets are absolute, no duplicates, nothing points inside the repository — before a single filesystem call. Any problem aborts with exit `2` and an untouched disk.

2. **Displaced data is moved, never removed.** When a target path already holds a real directory, that directory is *moved*: into a timestamped backup under `~/.docfleet/backup/<repo-id>/<ts>/`, or — with `--adopt` — into the machine folder to become the link source. `--adopt` additionally refuses to run if the source inside the repository already holds content, so an adopt can never overwrite what is already tracked.

3. **Every move is recorded before the link is made.** The manifest at `~/.docfleet/backup/<repo-id>/<ts>/manifest.json` records each item's source, target, mode (`none` / `backup` / `adopt`), state (`pending` → `linked` / `failed`) and backup location. It is flushed to disk after every step, so even a crash mid-run leaves a readable record.

4. **Everything is reversible.** `docfleet link --restore` replays the newest run backwards — removing links and moving the displaced directories home. `--at TS` selects an older run by its timestamp. If something new has appeared at a target in the meantime, that item is reported as `skipped` and left completely alone; a later restore retries it. Backups are never deleted automatically.

5. **Git operations stay conservative.** No command in docfleet ever runs `git push --force` or `git reset --hard`. A rebase that hits a conflict is aborted immediately — leaving your branch exactly as it was — and the manual resolution steps are printed. A rejected push is retried exactly once after a fresh fetch and rebase; if it is rejected again, your commits simply stay in the local branch and docfleet tells you so.

## Docs

| Document | What's in it |
| --- | --- |
| [docs/structure.md](docs/structure.md) | the layout convention as a standalone spec: paths, ownership, `fleet.json` / `machine.json` schemas, naming rules, document tiers |
| [docs/schema.md](docs/schema.md) | `--json` output field by field, per command, plus exit codes and git state names |
| [docs/quickstart-two-machines.md](docs/quickstart-two-machines.md) | copy-pasteable walkthrough: laptop creates the fleet, desktop joins it |
| [docs/adr/](docs/adr/) | why it is built this way — four architecture decision records |
| [README_KOR.md](README_KOR.md) | 한국어 전문 |
| [CHANGELOG.md](CHANGELOG.md) | release notes |

## License

MIT — see [LICENSE](LICENSE). Security policy: [SECURITY.md](SECURITY.md).
