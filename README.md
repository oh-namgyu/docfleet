# docfleet - work in progress

docfleet is a git-native layout convention plus a zero-dependency Python CLI for
keeping AI-agent documents and memory in sync across several machines. One git
repository holds `machines/<name>/` for per-machine content, `shared/` for what
every machine uses, and a `fleet.json` registry at the root; each machine then
links its agent tool paths at the folders it owns inside the repository, so a
`git pull` is all it takes to move context between a laptop, a desktop and an
office workstation. Stages 1-2 (`init` and `link` with `--adopt` / `--restore`)
are implemented; `start`, `close`, `doctor` and `index` are still stubs. Full
documentation follows.

## License

MIT - see [LICENSE](LICENSE).
