"""Command line interface.

Exit codes:
    0  success
    1  operation-level failure (a link item failed, restore skipped items)
    2  environment or configuration error (nothing was modified)

`--json` turns every command into a machine-readable document on stdout. The
documented keys are stable: `command`, plus `mode`/`created` for init and
`action`, `repo`, `machine`, `manifest`, `items`, `status`, `error` for link.
Errors print `{"error": <message>, "exit_code": <code>}`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .errors import DocfleetError
from .layout import find_repo, init_join, init_new, machine_names, read_fleet
from .links import run_link
from .restore import run_restore

STUB_COMMANDS = {
    "start": "load the machine context at the start of a session",
    "close": "sync and hand off at the end of a session",
    "doctor": "check the fleet layout and links for problems",
    "index": "rebuild the document index",
}


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

    init = subparsers.add_parser("init", help="create or join a fleet repository")
    where = init.add_mutually_exclusive_group(required=True)
    where.add_argument("--new", metavar="REPO", help="create a layout in REPO")
    where.add_argument("--join", metavar="REPO", help="join the fleet in REPO")
    init.add_argument("--machine", required=True, help="name of this machine")

    link = subparsers.add_parser("link", help="install, adopt or restore links")
    link.add_argument("--repo", help="fleet repository (default: search upwards)")
    link.add_argument("--machine", help="machine to act on (default: the only one)")
    link.add_argument(
        "--adopt",
        action="store_true",
        help="move existing target directories into the repository as sources",
    )
    link.add_argument(
        "--restore", action="store_true", help="reverse a previous link run"
    )
    link.add_argument("--at", metavar="TS", help="restore the run with timestamp TS")

    for name, help_text in STUB_COMMANDS.items():
        subparsers.add_parser(name, help=f"{help_text} (not implemented yet)")
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


def _emit(result: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, indent=2))
    elif result["command"] == "init":
        _print_init(result)
    else:
        _print_link(result)
    return int(result.get("exit_code", 0))


def _fail(message: str, code: int, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"error": message, "exit_code": code}, indent=2))
    else:
        print(f"docfleet: {message}", file=sys.stderr)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    if args.command in STUB_COMMANDS:
        print(f"docfleet {args.command}: not implemented yet", file=sys.stderr)
        raise SystemExit(2)
    handlers = {"init": cmd_init, "link": cmd_link}
    try:
        result = handlers[args.command](args)
    except DocfleetError as exc:
        return _fail(str(exc), exc.exit_code, args.json)
    return _emit(result, args.json)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
