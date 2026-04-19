# Changelog

All notable changes to the `elixa` CLI are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-04-19

First public release.

### Added
- Full merchant surface: `login`, `signup`, `logout`, `whoami`.
- Subcommand groups: `feeds`, `keys`, `domain`, `analytics`, `products`.
- Smart output mode — tables when piped to a TTY, JSON when piped to
  another command. Force either with `--format`.
- Structured error envelope printer (`code`, `detail`, `hint`,
  `request_id`) so agents can branch on a stable machine-readable token.
- Credential store at `~/.config/elixa/credentials.json` (chmod 600),
  XDG-aware. `ELIXA_API_KEY` env var takes precedence.
- `docs` command opens `https://elixa.dev/docs` in the browser.
- Completeness bar chart in `submit` output.
- Inline usage bar chart in `analytics queries`.

### Changed
- New blue/violet palette synced with the web console tokens.
- Default API URL is now `https://api.elixa.dev` (was `http://localhost:8000`).

## [0.1.0]

Initial internal prototype. Not published.
