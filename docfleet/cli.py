"""Command line interface.

Exit codes:
    0  success
    1  operation-level failure (a link item failed, restore skipped items)
    2  environment or configuration error (nothing was modified)

`--json` turns every command into a machine-readable document on stdout. The
documented keys are stable: `command`, plus `mode`/`created` for init;
`action`, `repo`, `machine`, `manifest`, `items`, `status`, `error` for link;
`state`, `commits`, `areas` for start; `state`, `staged`, `committed`,
`violations`, `unpushed` for close; `violations` (each `{check, path,
message}`) and `fixed` for doctor; `path` and `status` for index.
Errors print `{"error": <message>, "exit_code": <code>}`, plus `state` when a
git state caused them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .doctor import run_doctor
from .errors import DocfleetError
from .indexer import run_index
from .layout import find_repo, init_join, init_new, machine_names, read_fleet
from .links import run_link
from .restore import run_restore
from .sync import run_close, run_start


def _add_repo(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--repo", help="fleet repository (default: search upwards)")
    return parser


def _add_location(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    _add_repo(parser)
    parser.add_argument("--machine", help="machine to act on (default: the only one)")
    return parser


def _add_init(subparsers: argparse._SubParsersAction) -> None:
    init = subparsers.add_parser("init", help="create or join a fleet repository")
    where = init.add_mutually_exclusive_group(required=True)
    where.add_argument("--new", metavar="REPO", help="create a layout in REPO")
    where.add_argument("--join", metavar="REPO", help="join the fleet in REPO")
    init.add_argument("--machine", required=True, help="name of this machine")


def _add_link(subparsers: argparse._SubParsersAction) -> None:
    link = _add_location(
        subparsers.add_parser("link", help="install, adopt or restore links")
    )
    link.add_argument(
        "--adopt",
        action="store_true",
        help="move existing target directories into the repository as sources",
    )
    link.add_argument(
        "--restore", action="store_true", help="reverse a previous link run"
    )
    link.add_argument("--at", metavar="TS", help="restore the run with timestamp TS")


def _add_session(subparsers: argparse._SubParsersAction) -> None:
    _add_location(
        subparsers.add_parser(
            "start", help="fetch and rebase, then report what other machines changed"
        )
    )
    close = _add_location(
        subparsers.add_parser(
            "close", help="commit this machine's areas, rebase and push"
        )
    )
    close.add_argument("-m", "--message", help="commit message")
    doctor = _add_location(
        subparsers.add_parser(
            "doctor", help="check the fleet layout and links for problems"
        )
    )
    doctor.add_argument(
        "--fix",
        action="store_true",
        help="reinstall missing links and rewrite INDEX.md (nothing else)",
    )
    _add_repo(subparsers.add_parser("index", help="rebuild INDEX.md from the layout"))


def build_parser() -> argparse.ArgumentParser:
    """Build the docfleet argument parser."""
    parser = argparse.ArgumentParser(
        prog="docfleet",
        description="Keep agent docs and memory in sync across machines.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--json", action="store_true", help="print machine-readable JSON output"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_init(subparsers)
    _add_link(subparsers)
    _add_session(subparsers)
    return parser


def _resolve_repo(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().absolute()
    return find_repo(Path.cwd())


def _resolve_machine(repo: Path, raw: str | None) -> str:
    if raw:
        return raw
    names = machine_names(read_fleet(repo))
    if len(names) == 1:
        return names[0]
    raise DocfleetError(
        f"{len(names)} machines are registered in {repo}: "
        "pass --machine to say which one to act on"
    )


def cmd_init(args: argparse.Namespace) -> dict:
    """Run `docfleet init`."""
    if args.new:
        return init_new(Path(args.new).expanduser().absolute(), args.machine)
    return init_join(Path(args.join).expanduser().absolute(), args.machine)


def cmd_link(args: argparse.Namespace) -> dict:
    """Run `docfleet link`."""
    repo = _resolve_repo(args.repo)
    machine = _resolve_machine(repo, args.machine)
    if args.restore:
        return run_restore(repo, machine, args.at)
    if args.at:
        raise DocfleetError("--at is only meaningful together with --restore")
    return run_link(repo, machine, adopt=args.adopt)


def cmd_start(args: argparse.Namespace) -> dict:
    """Run `docfleet start`."""
    repo = _resolve_repo(args.repo)
    return run_start(repo, _resolve_machine(repo, args.machine))


def cmd_close(args: argparse.Namespace) -> dict:
    """Run `docfleet close`."""
    repo = _resolve_repo(args.repo)
    return run_close(repo, _resolve_machine(repo, args.machine), args.message)


def cmd_doctor(args: argparse.Namespace) -> dict:
    """Run `docfleet doctor`."""
    repo = _resolve_repo(args.repo)
    return run_doctor(repo, _resolve_machine(repo, args.machine), fix=args.fix)


def cmd_index(args: argparse.Namespace) -> dict:
    """Run `docfleet index`."""
    return run_index(_resolve_repo(args.repo))


def _print_init(result: dict) -> None:
    verb = "created" if result["mode"] == "new" else "joined"
    print(f"{verb} fleet at {result['repo']} for machine {result['machine']}")
    for path in result["created"]:
        print(f"  + {path}")


def _print_link(result: dict) -> None:
    if not result["items"]:
        print(f"no links declared for machine {result['machine']}")
    for item in result["items"]:
        line = f"  {item['state']:<9} {item['source']} -> {item['target']}"
        if item["mode"] != "none":
            line += f"  [{item['mode']}]"
        if item.get("backup_path"):
            line += f"\n            backup: {item['backup_path']}"
        print(line)
    if result["manifest"]:
        print(f"manifest: {result['manifest']}")
    if result["error"]:
        print(f"error: {result['error']}", file=sys.stderr)


def _print_incoming(result: dict) -> None:
    if not result["commits"]:
        print("no changes from other machines")
        return
    print(f"{len(result['commits'])} commit(s) from other machines:")
    for commit in result["commits"]:
        print(f"  {commit['hash']}  {commit['subject']}")
    print(f"areas touched: {', '.join(result['areas'])}")


def _print_start(result: dict) -> None:
    print(f"machine {result['machine']} ({result['state']})")
    _print_incoming(result)
    if result["unpushed"]:
        print(f"{result['unpushed']} local commit(s) not pushed yet")


def _print_close(result: dict) -> None:
    if result["violations"]:
        print("close stopped: these paths are outside the areas you own")
        for path in result["violations"]:
            print(f"  ! {path}")
        sys.stdout.flush()
        print(f"error: {result['error']}", file=sys.stderr)
        return
    if result["committed"]:
        print(f"committed {result['committed']} ({len(result['staged'])} path(s))")
    else:
        print("nothing to commit")
    _print_incoming(result)
    print(f"pushed; {result['unpushed']} local commit(s) not pushed yet")


def _print_doctor(result: dict) -> None:
    for item in result["fixed"]:
        print(f"  fixed [{item['check']}] {item['path']} ({item['action']})")
    for item in result["violations"]:
        print(f"  [{item['check']}] {item['path']}\n      {item['message']}")
    if not result["violations"]:
        print(f"no violations ({len(result['checks'])} checks)")


def _print_index(result: dict) -> None:
    print(f"{result['status']}: {result['path']}")


PRINTERS = {
    "init": _print_init,
    "link": _print_link,
    "start": _print_start,
    "close": _print_close,
    "doctor": _print_doctor,
    "index": _print_index,
}

HANDLERS = {
    "init": cmd_init,
    "link": cmd_link,
    "start": cmd_start,
    "close": cmd_close,
    "doctor": cmd_doctor,
    "index": cmd_index,
}


def _emit(result: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        PRINTERS[result["command"]](result)
    return int(result.get("exit_code", 0))


def _fail(exc: DocfleetError, as_json: bool) -> int:
    message = str(exc)
    if as_json:
        payload = {"error": message, "exit_code": exc.exit_code, **exc.details}
        print(json.dumps(payload, indent=2))
    else:
        print(f"docfleet: {message}", file=sys.stderr)
    return exc.exit_code


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        result = HANDLERS[args.command](args)
    except DocfleetError as exc:
        return _fail(exc, args.json)
    return _emit(result, args.json)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
