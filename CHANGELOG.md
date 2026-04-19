# Changelog

All notable changes to the `elixa` CLI are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.3] — 2026-04-19

### Fixed
- The `E` in the `ELIXA` wordmark now has a middle bar and reads as an
  E instead of a C. Redrew all five glyphs against a true 5-pixel-tall
  grid rendered across 3 terminal rows (was 2), so every letter has
  the right crossbars.

## [0.2.2] — 2026-04-19

### Changed
- Fully custom `elixa` / `elixa --help` screen, rendered outside Typer.
  Hero wordmark in a blue→violet gradient, tagline, usage line,
  section markers (`▸ public`, `▸ authentication`, `▸ merchant`),
  conversational command descriptions, and a "new? try…" footer.
- Per-subcommand help still uses Typer + Rich, now with bolder
  (`#3B82F6`) panel borders that match the main screen.

### Added
- `elixa.cli:main_entrypoint` — thin wrapper that intercepts bare
  `elixa`, `elixa help`, `elixa -h`, and `elixa --help` to route them
  to the branded renderer. All other invocations fall through to Typer
  unchanged.

## [0.2.1] — 2026-04-19

### Changed
- `elixa --help` now uses the branded palette (blue primary, cyan options,
  violet metavars, amber env vars) instead of Typer's defaults.
- Top-level commands are grouped into three panels — **Public**,
  **Authentication**, **Merchant** — so the front door reads like a
  deliberate product surface.

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
