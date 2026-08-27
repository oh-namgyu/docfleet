# Quickstart: two machines

A complete walkthrough. Machine **laptop** creates the fleet and adopts an agent memory directory it already has; machine **desktop** clones the repository, joins the fleet, links its own memory, and picks up what the laptop published.

Every command below is real, and the output shown is real output with the paths shortened. The example agent keeps its memory in `~/.myagent/memory` — substitute whatever path your own agent uses.

**Before you start**, on both machines:

```bash
pip install git+https://github.com/oh-namgyu/docfleet
docfleet --version
```

You also need an empty git remote the two machines can both reach. Anything git speaks to works — a private repository on a git host, or a bare repository on a NAS. The walkthrough calls it `git@github.com:you/fleet.git`.

---

## Part 1 — laptop creates the fleet

### 1.1 Make the repository

docfleet never runs `git init` for you, so the repository comes first:

```bash
mkdir ~/fleet && cd ~/fleet
git init -b main
git remote add origin git@github.com:you/fleet.git
```

### 1.2 Create the layout

```bash
docfleet init --new . --machine laptop
```

```
created fleet at /home/you/fleet for machine laptop
  + shared/commands
  + shared/standards
  + machines/laptop/docs
  + machines/laptop/memory
  + machines/laptop/machine.json
  + fleet.json
  + README.md
```

### 1.3 Declare the link

Edit `machines/laptop/machine.json` so it reads:

```json
{
  "machine": "laptop",
  "links": [
    { "source": "memory", "target": "~/.myagent/memory" }
  ]
}
```

`source` is a directory inside `machines/laptop/`; `target` is where the agent looks on this machine.

### 1.4 Adopt the memory you already have

`~/.myagent/memory` already exists and holds real notes. `--adopt` moves that directory into the repository and puts the link in its place, so nothing is copied and nothing is lost:

```bash
docfleet link --adopt
```

```
  linked    memory -> /home/you/.myagent/memory  [adopt]
manifest: /home/you/.docfleet/backup/249fa33eea02/20260227-160032/manifest.json
```

Check what happened:

```bash
ls -l ~/.myagent/
# memory -> /home/you/fleet/machines/laptop/memory

ls ~/fleet/machines/laptop/memory/
# notes.md          ← your real notes, now inside the repository
```

The agent still reads and writes `~/.myagent/memory`. Those bytes are now in a git work tree.

> Without `--adopt`, an existing directory at the target would have been moved into the manifest's backup slot instead — never deleted — and `machines/laptop/memory/` would have stayed as it was. Either way, `docfleet link --restore` reverses the run.

### 1.5 Publish

The first publish is plain git, because `docfleet close` needs an upstream branch to rebase onto and push to:

```bash
docfleet index
git add -A && git commit -m "create fleet"
git push -u origin main
```

```
written: /home/you/fleet/INDEX.md
```

### 1.6 Confirm

```bash
docfleet doctor
```

```
no violations (7 checks)
```

Exit code `0`. From here on, `docfleet close` handles commit, rebase and push.

---

## Part 2 — desktop joins

Now move to the second machine. It has its own `~/.myagent/memory` with its own local scratch notes in it.

### 2.1 Clone

```bash
git clone git@github.com:you/fleet.git ~/fleet && cd ~/fleet
```

The clone already has `origin` and an upstream branch, so no manual push is needed on this machine.

### 2.2 Join the fleet

```bash
docfleet init --join . --machine desktop
```

```
joined fleet at /home/you/fleet for machine desktop
  + machines/desktop/docs
  + machines/desktop/memory
  + machines/desktop/machine.json
```

`--join` adds `desktop` to `fleet.json` and creates only this machine's folders; the shared skeleton is already there.

### 2.3 Declare and adopt

Edit `machines/desktop/machine.json` the same way — note that the `target` is this machine's path and has nothing to do with the laptop's:

```json
{
  "machine": "desktop",
  "links": [
    { "source": "memory", "target": "~/.myagent/memory" }
  ]
}
```

```bash
docfleet link --adopt --machine desktop
```

```
  linked    memory -> /home/you/.myagent/memory  [adopt]
manifest: /home/you/.docfleet/backup/6cf3af6f5df1/20260227-160047/manifest.json
```

`--machine` is required from now on: there are two registered machines, so docfleet will not guess which one you mean. (`docfleet` still finds the repository by itself from anywhere inside it.)

### 2.4 Publish with `close`

```bash
docfleet index
docfleet close --machine desktop -m "join the fleet from desktop"
```

```
committed 485823b (5 path(s))
no changes from other machines
pushed; 0 local commit(s) not pushed yet
```

Five paths: `fleet.json`, `INDEX.md`, and the three files under `machines/desktop/`.

### 2.5 Read what the laptop knows

```bash
cat machines/laptop/memory/notes.md
```

```
session notes from the laptop
```

That is the payoff: the laptop's memory is readable here, in full, without copying anything or logging into anything.

### 2.6 What happens if you edit it

Suppose an agent running on the desktop decides to tidy up the laptop's notes:

```bash
echo "meddling" >> machines/laptop/memory/notes.md
docfleet close --machine desktop
```

```
close stopped: these paths are outside the areas you own
  ! machines/laptop/memory/notes.md
error: 1 change(s) outside the areas machine 'desktop' owns (machines/desktop/, shared/ and the root metadata files); nothing was committed
```

Exit code `1`, nothing staged, nothing committed. Put the edit back:

```bash
git checkout -- machines/laptop/memory/notes.md
```

Peer folders are readable and not writable — that is the whole ownership rule, enforced at the moment you try to publish.

---

## Part 3 — the daily loop, back on the laptop

### 3.1 Start the session

```bash
cd ~/fleet
docfleet start --machine laptop
```

```
machine laptop (clean)
1 commit(s) from other machines:
  485823b  join the fleet from desktop
areas touched: INDEX.md, fleet.json, machines/desktop
```

`start` fetched, rebased because the upstream had moved ahead, and reported exactly what arrived and which areas it touched. The desktop's memory is now readable here too:

```bash
ls machines/desktop/memory/
# todo.md
```

### 3.2 Work

Nothing special: your agent reads and writes `~/.myagent/memory` as it always has.

```bash
echo "today: fixed the parser" >> ~/.myagent/memory/notes.md
```

### 3.3 Close the session

```bash
docfleet close --machine laptop -m "notes from the parser fix"
```

```
committed 9b754ff (1 path(s))
no changes from other machines
pushed; 0 local commit(s) not pushed yet
```

That is the loop, forever: `start` when you sit down, `close` when you get up. Whichever machine you open next has it.

---

## Troubleshooting

| What you see | What it means | What to do |
| --- | --- | --- |
| `2 machines are registered … pass --machine` (exit 2) | more than one machine in the fleet and no `--machine` | add `--machine <name>` |
| `no fleet repository found at or above …` (exit 2) | you are not inside a fleet repository | `cd` into it, or pass `--repo` |
| `branch main … has no upstream branch` (exit 2) | `close` or `start` has nothing to push to or fetch from | `git push -u origin main` once |
| `close stopped: these paths are outside the areas you own` (exit 1) | an edit landed in a peer machine's folder | move it to your own folder or to `shared/`, or revert it |
| `rebase … hit a conflict` (exit 1) | both machines changed the same lines, usually in `shared/` | the rebase was already aborted, so your branch is untouched; follow the printed steps and run `close` again |
| `[link-broken] … is missing` from `doctor` (exit 1) | something removed or replaced a link | `docfleet doctor --fix --machine <name>` |
| `[index-stale] INDEX.md no longer matches the layout` | documents were added or removed since the last index | `docfleet index` |

Undoing a link run entirely:

```bash
docfleet link --restore --machine laptop        # reverse the newest run
docfleet link --restore --machine laptop --at 20260227-160032   # or an older one
```

Restore removes the links and moves the displaced directories back where they were. If something new has taken over a target position in the meantime, that item is reported as `skipped` and left completely alone.

## Next

- [structure.md](structure.md) — the layout convention as a specification, including how to organise documents once there are more than a handful
- [schema.md](schema.md) — `--json` output, field by field, for scripting
- [adr/](adr/) — why it is built this way
