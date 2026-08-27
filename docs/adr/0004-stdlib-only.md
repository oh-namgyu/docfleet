# ADR 0004 — Standard library only, zero runtime dependencies

**Status:** accepted · **Date:** 2026-08-27

## Context

docfleet is a small CLI that parses arguments, reads and writes JSON, manipulates paths, creates links and shells out to `git`. Every one of those has a well-liked third-party answer: `click` or `typer` for the CLI, `pydantic` for the config schemas, `GitPython` for the git work, `rich` for the output.

The deployment situation argues the other way. This tool gets installed on every machine in a fleet, including machines set up in a hurry, machines behind a restrictive network, and machines whose Python is whatever the operating system shipped. It is also the tool you reach for when something is already wrong — a link is missing, a folder did not sync — which is the worst possible moment to discover that an install is broken.

## Decision

Use the Python standard library only. `dependencies = []` in `pyproject.toml`, permanently, and `requires-python = ">=3.10"`.

Concretely: `argparse` for the CLI, `json` for configuration, `pathlib` and `os` for paths and links, `subprocess` invoking the `git` executable directly, `dataclasses` for the few structured values, and plain `print` for output. `pytest` is a development dependency and is not needed to run the tool.

## Consequences

**Good.** `pip install` cannot fail on a resolution conflict, because there is nothing to resolve. The tool cannot be broken by someone else's release, and it has no upgrade treadmill: a fleet repository set up today keeps working. Installation into a system Python is harmless to that Python. The entire runtime is auditable by reading one package of about a thousand lines.

**Costs.** Some things are hand-written that a library would have supplied: the git state classification in `gitops.py`, the JSON schema validation in `layout.py` and `links.py`, and the plain-text printers in `cli.py`. Output is unstyled — no colour, no progress bars — which is a real ergonomic loss, partly offset by `--json` for anything programmatic. Error messages from `argparse` are less polished than a modern CLI framework's. Python 3.10 as the floor rules out newer syntax; `from __future__ import annotations` covers the annotation gap, and `os.path.isjunction` (3.12) is accessed through `getattr` so that older versions degrade instead of crashing.

**Not a decision about testing.** `pytest` remains a dev dependency, and the CI matrix installs it. The rule is about what a *user* must install to run `docfleet`, which is: Python, and git.
