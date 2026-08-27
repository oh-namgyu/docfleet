# `--json` output schema

Every command accepts the global `--json` flag, which replaces the human-readable printer with one JSON document on stdout, indented by two spaces. Nothing else is written to stdout, so the output can be piped straight into a parser.

```bash
docfleet --json doctor --repo ~/fleet --machine laptop
```

`--json` is a **global** flag and goes before the subcommand.

Every successful document carries `command`, naming the subcommand that produced it. Most also carry `repo` (absolute path), `machine`, `status`, `error` and `exit_code`. The exceptions are noted per command below.

---

## Common values

### Exit codes

| Code | Meaning | Filesystem |
| --- | --- | --- |
| `0` | success | as requested |
| `1` | the operation ran but could not complete every part of it | partially changed, and recorded |
| `2` | environment or configuration error | **unchanged** |

Exit code `1` covers: a blocked `close`, a link item that failed mid-run, restore items that had to be skipped, and any `doctor` run that found violations. Exit code `2` covers: a missing or malformed `fleet.json` / `machine.json`, an unusable git state, an ambiguous `--machine`, an invalid link declaration, and a missing manifest.

The `exit_code` field in the document always equals the process exit code.

### Git state names

`start` and `close` report the working tree state they ended in, under `state`:

| State | Meaning |
| --- | --- |
| `clean` | in sync with the upstream, nothing to commit |
| `dirty` | in sync with the upstream, but the work tree has changes |
| `ahead` | this branch holds commits the upstream lacks |
| `behind` | the upstream holds commits this branch lacks |
| `diverged` | both sides hold commits the other lacks |
| `rebase-conflict` | a rebase is in progress, waiting for a resolution |
| `detached` | `HEAD` does not point at a branch |
| `no-remote` | no upstream branch, or the remote cannot be reached |
| `not-a-repo` | the directory is not inside a git working tree |

The last three are environment errors: they abort with exit code `2` and appear in the error document's `state` field rather than in a success document.

### Error documents

Any command that raises instead of completing prints this shape:

```json
{
  "error": "branch main in /home/u/fleet has no upstream branch: add a remote and push once with `git push -u` (state: no-remote)",
  "exit_code": 2,
  "state": "no-remote"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `error` | string | the full message, identical to what the plain printer sends to stderr |
| `exit_code` | integer | `1` or `2` |
| `state` | string | present only when a git state caused the error |

An error document has no `command` field. Without `--json`, the same message goes to **stderr** prefixed with `docfleet: `, and stdout stays empty.

---

## `init`

```json
{
  "command": "init",
  "mode": "new",
  "repo": "/home/u/fleet",
  "machine": "laptop",
  "created": [
    "shared/commands",
    "shared/standards",
    "machines/laptop/docs",
    "machines/laptop/memory",
    "machines/laptop/machine.json",
    "fleet.json",
    "README.md"
  ]
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `command` | string | `"init"` |
| `mode` | string | `"new"` for `--new`, `"join"` for `--join` |
| `repo` | string | absolute path of the fleet repository |
| `machine` | string | the machine that was registered |
| `created` | array of strings | repository-relative paths created, in creation order |

`init` has no `exit_code` field; it either succeeds with process exit `0` or raises an error document. `--join` reports only the machine's own paths in `created`, since the shared skeleton already exists.

---

## `link`, `link --adopt`, `link --restore`

All three produce the same shape; `action` distinguishes them.

```json
{
  "command": "link",
  "action": "link",
  "repo": "/home/u/fleet",
  "machine": "laptop",
  "manifest": "/home/u/.docfleet/backup/3f2a91c04b7e/20260227-101500/manifest.json",
  "items": [
    {
      "source": "memory",
      "target": "/home/u/.myagent/memory",
      "mode": "adopt",
      "state": "linked",
      "backup_path": null
    }
  ],
  "status": "ok",
  "error": null,
  "exit_code": 0,
  "adopt": true
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `command` | string | `"link"` for all three |
| `action` | string | `"link"` for an install or adopt run, `"restore"` for `--restore` |
| `repo` | string | absolute path of the fleet repository |
| `machine` | string | the machine whose declarations were processed |
| `manifest` | string or null | absolute path of the run's manifest; `null` when the run changed nothing and therefore created none |
| `items` | array | one entry per processed declaration, in declaration order for a link run and in **reverse** order for a restore |
| `status` | string | `"ok"`, or `"partial"` when `error` is set |
| `error` | string or null | what went wrong: the failing item for a link run, the count of skipped items for a restore |
| `exit_code` | integer | `0`, or `1` when `error` is set |
| `adopt` | boolean | present on `action: "link"` only; absent on a restore |

### `items[]`

| Field | Type | Meaning |
| --- | --- | --- |
| `source` | string | the declaration's `source`, relative to the machine folder |
| `target` | string | the resolved absolute target path, with `~` already expanded |
| `mode` | string | what had to happen to the target — see below |
| `state` | string | how the item ended — see below |
| `backup_path` | string or null | absolute path the displaced directory was moved to; `null` unless `mode` is `"backup"` |

**`mode`** — what occupied the target and what was done about it:

| Value | Meaning |
| --- | --- |
| `none` | the target did not exist, or already held the correct link; nothing was moved |
| `backup` | the target held a directory or a stale link; it was moved into the manifest's backup slot |
| `adopt` | `--adopt` was given and the target's directory was moved into the machine folder to become the link source |

**`state`** — the outcome:

| Value | Appears in | Meaning |
| --- | --- | --- |
| `current` | link run | the correct link was already in place; nothing was done and no manifest entry was written |
| `linked` | link run | the link now exists; any displaced data is recorded in the manifest |
| `failed` | link run | the item could not be completed; the run stopped here and later items were not attempted |
| `restored` | restore | the link was removed and the displaced data moved back |
| `skipped` | restore | something new occupies the target, so the item was left untouched for a later restore |

A link run stops at the first failure, so `items` may be shorter than the declaration list. Items reported as `current` never reach the manifest — restoring a run therefore never removes a link some earlier run installed.

---

## `start`

```json
{
  "command": "start",
  "repo": "/home/u/fleet",
  "machine": "desktop",
  "state": "clean",
  "commits": [
    { "hash": "a1b2c3d", "subject": "docfleet close: laptop 2026-02-27" }
  ],
  "areas": ["machines/laptop", "shared"],
  "unpushed": 0,
  "status": "ok",
  "error": null,
  "exit_code": 0
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `command` | string | `"start"` |
| `state` | string | the git state after fetching and rebasing — see the table above |
| `commits` | array | commits the upstream held and this branch lacked, **oldest first**; empty when nothing arrived |
| `commits[].hash` | string | abbreviated commit hash |
| `commits[].subject` | string | the commit's subject line |
| `areas` | array of strings | top-level areas the incoming commits touched: `machines/<name>`, `shared`, or a root file name |
| `unpushed` | integer | local commits not yet on the upstream |
| `status` | string | always `"ok"` — any problem raises an error document instead |
| `error` | null | always null on success |
| `exit_code` | integer | always `0` |

`start` never commits. If the upstream moved ahead while the work tree is dirty, it refuses with exit `1` rather than rebasing over your changes.

---

## `close`

On success:

```json
{
  "command": "close",
  "repo": "/home/u/fleet",
  "machine": "laptop",
  "state": "clean",
  "violations": [],
  "staged": ["machines/laptop/memory/notes.md", "shared/standards/style.md"],
  "committed": "9f81c02",
  "commits": [],
  "areas": [],
  "unpushed": 0,
  "status": "ok",
  "error": null,
  "exit_code": 0
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `command` | string | `"close"` |
| `state` | string | the git state after committing, rebasing and pushing |
| `violations` | array of strings | repository-relative paths outside the machine's owned areas; empty on success |
| `staged` | array of strings | paths that ended up in the commit, sorted |
| `committed` | string or null | abbreviated hash of the new commit; `null` when there was nothing to commit |
| `commits` | array | commits that arrived from other machines during the rebase, same shape as `start` |
| `areas` | array of strings | areas those incoming commits touched |
| `unpushed` | integer | local commits still not on the upstream after the push |
| `status` | string | `"ok"` or `"blocked"` |
| `error` | string or null | set when `status` is `"blocked"` |
| `exit_code` | integer | `0`, or `1` when blocked |

When a change is found outside the owned areas, `close` stops **before staging anything**:

```json
{
  "command": "close",
  "repo": "/home/u/fleet",
  "machine": "laptop",
  "state": "dirty",
  "violations": ["machines/desktop/memory/notes.md"],
  "staged": [],
  "committed": null,
  "commits": [],
  "areas": [],
  "unpushed": 0,
  "status": "blocked",
  "error": "1 change(s) outside the areas machine 'laptop' owns (machines/laptop/, shared/ and the root metadata files); nothing was committed",
  "exit_code": 1
}
```

A blocked `close` is the only way to get `status: "blocked"`. Rebase conflicts and twice-rejected pushes raise error documents instead, with `state` set to `rebase-conflict` or to whatever the tree ended in.

---

## `doctor`

```json
{
  "command": "doctor",
  "repo": "/home/u/fleet",
  "machine": "laptop",
  "checks": ["layout", "machine-name", "registry", "mapping", "link-broken", "cross-machine", "index-stale"],
  "violations": [
    {
      "check": "link-broken",
      "path": "/home/u/.myagent/memory",
      "message": "link for 'memory' is missing"
    }
  ],
  "fixed": [],
  "status": "violations",
  "error": "1 violation(s) found",
  "exit_code": 1
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `command` | string | `"doctor"` |
| `checks` | array of strings | every check id that was run, always all seven, in check order |
| `violations` | array | findings, in check order; empty when the repository is conformant |
| `violations[].check` | string | the check id that fired |
| `violations[].path` | string | absolute path the finding is about |
| `violations[].message` | string | what is wrong, in one sentence |
| `fixed` | array | repairs made by `--fix`; empty without it |
| `fixed[].check` | string | the check id the repair addressed: `link-broken` or `index-stale` |
| `fixed[].path` | string | the path that was repaired |
| `fixed[].action` | string | for `link-broken`, the resulting item state (`linked`, `current`, `failed`); for `index-stale`, `"written"` |
| `status` | string | `"ok"` or `"violations"` |
| `error` | string or null | `"<n> violation(s) found"`, or null |
| `exit_code` | integer | `0` when there are no violations, `1` otherwise |

With `--fix`, `violations` is re-collected **after** the repairs, so it reports what remains. A run that repaired everything therefore returns `exit_code: 0` with a non-empty `fixed`.

The check ids and what each one means are listed in [structure.md §11](structure.md#11-conformance).

---

## `index`

```json
{
  "command": "index",
  "repo": "/home/u/fleet",
  "path": "/home/u/fleet/INDEX.md",
  "status": "written",
  "exit_code": 0
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `command` | string | `"index"` |
| `path` | string | absolute path of the index file |
| `status` | string | `"written"` when the file changed, `"unchanged"` when it was already correct |
| `exit_code` | integer | always `0` |

`index` takes `--repo` but no `--machine`: the index covers the whole fleet. It has no `machine`, `error` or `status: "ok"` field.

---

## Manifest

Not a command output, but the same stability applies: `~/.docfleet/backup/<repo-id>/<ts>/manifest.json` is the durable record of one `link` run.

```json
{
  "version": 1,
  "repo": "/home/u/fleet",
  "machine": "laptop",
  "ts": "20260227-101500",
  "items": [
    {
      "source": "memory",
      "target": "/home/u/.myagent/memory",
      "mode": "backup",
      "state": "linked",
      "backup_path": "/home/u/.docfleet/backup/3f2a91c04b7e/20260227-101500/0/memory",
      "source_existed": true
    }
  ]
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | integer | manifest schema version; currently `1` |
| `repo` | string | absolute path of the repository the run acted on |
| `machine` | string | the machine whose declarations were applied |
| `ts` | string | the run directory's name: `YYYYMMDD-HHMMSS`, plus `-1`, `-2` … if two runs share a second |
| `items` | array | the items this run actually changed, in execution order |
| `items[].source_existed` | boolean | whether the link source already existed before the run; used by `--restore` to decide whether to recreate an empty source folder |

The other item fields match the `--json` item fields above. The manifest is flushed after every step, so its `state` values are the live progress of a run:

```
pending ──► linked ──► restored
   │           │
   │           └─────► skipped ──► restored   (a later restore retries)
   └─────► failed ───► restored
```

`pending` is what an item looks like while it is being applied — finding one in a manifest means the process died mid-item, and `--restore` will walk it back. `restored` is terminal: restore never touches such an item again, so re-running a restore is a no-op.

Backups are never deleted automatically. Removing an old run directory by hand is safe once you no longer need to restore it.
