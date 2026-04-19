"""
CLI configuration: resolve the API base URL, load/save credentials, and
decide whether stdout looks like a TTY (so we can swap to human-friendly
table output automatically, the same way `gh` does it).

Credentials live at `~/.config/elixa/credentials.json` (or
`$XDG_CONFIG_HOME/elixa/credentials.json` if set). The file is chmod 600
on POSIX so it doesn't end up world-readable by accident.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

DEFAULT_API_URL = "https://api.elixa.app"
LOCAL_API_URL   = "http://localhost:8000"


def config_dir() -> Path:
    """Resolve ~/.config/elixa (honouring XDG_CONFIG_HOME)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "elixa"


def credentials_path() -> Path:
    return config_dir() / "credentials.json"


# ── Credentials ─────────────────────────────────────────────────────

@dataclass
class Credentials:
    """Whatever we need to authenticate merchant-scoped calls.

    We persist a session token (from `elixa login`) OR an API key (from
    the console). Exactly one is used at a time; the session token takes
    priority if both exist.
    """
    api_url: str
    session_token: str | None = None
    api_key: str | None = None
    merchant_id: str | None = None
    merchant_name: str | None = None
    merchant_domain: str | None = None
    email: str | None = None
    expires_at: int | None = None  # epoch seconds

    def is_authenticated(self) -> bool:
        return bool(self.session_token or self.api_key)

    def auth_header(self) -> dict[str, str]:
        """Return a dict with the Authorization header if we have one."""
        if self.session_token:
            return {"Authorization": f"Bearer {self.session_token}"}
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}


def load_credentials() -> Credentials | None:
    """Return stored credentials, or None if nothing saved."""
    path = credentials_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return Credentials(**{
        k: v for k, v in data.items() if k in Credentials.__dataclass_fields__
    })


def save_credentials(creds: Credentials) -> Path:
    """Persist credentials, chmod 600."""
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(creds), indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows etc.
    return path


def clear_credentials() -> bool:
    """Delete the credentials file. Returns True if something was removed."""
    path = credentials_path()
    if path.exists():
        path.unlink()
        return True
    return False


# ── API URL resolution ──────────────────────────────────────────────

def resolve_api_url(override: str | None = None) -> str:
    """Pick the API base URL. Priority: explicit flag → env → saved creds → default."""
    if override:
        return override.rstrip("/")
    env = os.environ.get("ELIXA_API_URL")
    if env:
        return env.rstrip("/")
    creds = load_credentials()
    if creds and creds.api_url:
        return creds.api_url.rstrip("/")
    return DEFAULT_API_URL


# ── Output mode ─────────────────────────────────────────────────────

OutputMode = Literal["auto", "table", "json"]


def resolve_output_mode(requested: OutputMode) -> Literal["table", "json"]:
    """
    Pick JSON when piped, table when the human is watching — unless they
    explicitly asked for one. Machine-readability for agents, readability
    for humans, no surprises either way.
    """
    if requested in ("table", "json"):
        return requested
    return "table" if sys.stdout.isatty() else "json"


def resolve_api_key_env() -> str | None:
    """ELIXA_API_KEY overrides saved credentials — useful for CI."""
    return os.environ.get("ELIXA_API_KEY")
