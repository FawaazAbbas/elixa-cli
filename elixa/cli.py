"""
Elixa CLI — structured product search for AI agents, from the terminal.

Design goals (same as the web console):
  • JSON by default when piped, tables when a human is watching.
  • Every command prints the same structured error envelope on failure
    (code, detail, hint, request_id) so agents can branch on it.
  • Auth is optional. Public commands (search, product, merchants, schema,
    health) work with zero setup. Merchant-scoped commands require a login
    or an ELIXA_API_KEY.

Commands:
  Public:
    elixa search          Search products with filters
    elixa product         Full 56-field product detail
    elixa merchants       List merchants
    elixa schema          Show the field schema + scoring rules
    elixa health          Ping the API
    elixa docs            Open the docs in a browser
    elixa version         Show CLI version

  Auth:
    elixa login           Sign in with email + password
    elixa signup          Create a merchant account
    elixa logout          Clear saved credentials
    elixa whoami          Who am I signed in as?

  Merchant (authed):
    elixa submit          Submit a feed (JSON/CSV)
    elixa products list   List your own products
    elixa feeds ...       Register/list/fetch/remove feeds
    elixa keys ...        Manage API keys
    elixa domain ...      Domain verification
    elixa analytics ...   Impressions, clicks, top queries, events
"""

from __future__ import annotations

import json as json_lib
import sys
import time
import webbrowser
from enum import Enum
from pathlib import Path
from typing import Any

import typer

from elixa import __version__
from elixa.client import ElixaAPIError, ElixaClient
from elixa.config import (
    Credentials,
    clear_credentials,
    credentials_path,
    load_credentials,
    resolve_api_url,
    resolve_output_mode,
    save_credentials,
)
from elixa.formatters import (
    ACCENT,
    DANGER,
    GLYPH_OK,
    MUTED,
    PRIMARY,
    SUCCESS,
    WARN,
    console,
    err_console,
    print_analytics_summary,
    print_api_keys,
    print_domain_instructions,
    print_error,
    print_events,
    print_feed_fetch_result,
    print_feed_source_detail,
    print_feed_sources,
    print_feed_submit_result,
    print_health,
    print_json,
    print_me,
    print_merchants,
    print_new_api_key,
    print_product,
    print_schema,
    print_search_results,
    print_top_products,
    print_top_queries,
    print_verify_result,
)
from rich.text import Text


# ══════════════════════════════════════════════════════════════════
# Typed enums for choices
# ══════════════════════════════════════════════════════════════════

class OutputFormat(str, Enum):
    auto  = "auto"
    json  = "json"
    table = "table"


class Gender(str, Enum):
    male = "male"
    female = "female"
    unisex = "unisex"


class AgeGroup(str, Enum):
    newborn = "newborn"
    infant = "infant"
    toddler = "toddler"
    kids = "kids"
    adult = "adult"


class Condition(str, Enum):
    new = "new"
    used = "used"
    refurbished = "refurbished"


class Availability(str, Enum):
    in_stock = "in_stock"
    out_of_stock = "out_of_stock"
    preorder = "preorder"
    backorder = "backorder"


class Sort(str, Enum):
    relevancy = "relevancy"
    price_asc = "price_asc"
    price_desc = "price_desc"
    completeness = "completeness"
    rating = "rating"
    newest = "newest"


class FeedFormat(str, Enum):
    xml = "xml"
    csv = "csv"
    tsv = "tsv"
    json = "json"
    sheets = "sheets"


class EventType(str, Enum):
    impression = "impression"
    click = "click"
    search = "search"
    feed_fetch = "feed_fetch"


# ══════════════════════════════════════════════════════════════════
# Typer apps
# ══════════════════════════════════════════════════════════════════

_TAGLINE = (
    "[bold]Elixa[/bold] — structured product search for AI agents. "
    "[dim]One API, every merchant, 56 fields, free forever.[/dim]"
)

app = typer.Typer(
    name="elixa",
    help=_TAGLINE,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)

feeds_app = typer.Typer(
    help="Register, list, fetch, and manage feed sources.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(feeds_app, name="feeds")

keys_app = typer.Typer(
    help="Create, list, and revoke API keys.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(keys_app, name="keys")

domain_app = typer.Typer(
    help="Verify ownership of your merchant domain.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(domain_app, name="domain")

analytics_app = typer.Typer(
    help="Impressions, clicks, top queries, events stream.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(analytics_app, name="analytics")

products_app = typer.Typer(
    help="Your own products (authed).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(products_app, name="products")


# ══════════════════════════════════════════════════════════════════
# Shared state + helpers
# ══════════════════════════════════════════════════════════════════

class CLIState:
    api_url: str | None = None


_state = CLIState()


def _client() -> ElixaClient:
    """Spin up a client with the resolved URL and saved credentials."""
    return ElixaClient(base_url=_state.api_url)


def _handle_error(e: ElixaAPIError) -> None:
    """Pretty-print and exit with a non-zero code."""
    print_error(e)
    raise typer.Exit(code=1)


def _emit(data: Any, *, fmt: OutputFormat, table_printer) -> None:
    """Route to JSON or table output based on --format + TTY detection."""
    mode = resolve_output_mode(fmt.value)  # type: ignore[arg-type]
    if mode == "json":
        print_json(data)
    else:
        table_printer(data)


def _require_auth() -> Credentials:
    """Guard for authed commands — print a helpful error if not signed in."""
    creds = load_credentials()
    if (creds and creds.is_authenticated()) or _has_env_key():
        return creds or Credentials(api_url=resolve_api_url(_state.api_url))
    err_console.print()
    err_console.print(Text.from_markup(
        f"[bold {DANGER}]✗[/] You're not signed in.\n"
        f"[{MUTED}]  Run [bold]elixa login[/] or set [bold]ELIXA_API_KEY[/] to continue.[/]"
    ))
    err_console.print()
    raise typer.Exit(code=1)


def _has_env_key() -> bool:
    import os
    return bool(os.environ.get("ELIXA_API_KEY"))


# ══════════════════════════════════════════════════════════════════
# Global callback
# ══════════════════════════════════════════════════════════════════

def _version_callback(value: bool):
    if value:
        typer.echo(f"elixa {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    api_url: str = typer.Option(
        None, "--api-url",
        envvar="ELIXA_API_URL",
        help="Override the API base URL. Default: https://api.elixa.dev",
    ),
    version: bool = typer.Option(
        None, "--version", "-V",
        callback=_version_callback, is_eager=True,
        help="Show CLI version and exit.",
    ),
):
    """Root callback — captures --api-url for every command."""
    _state.api_url = api_url


# ══════════════════════════════════════════════════════════════════
# Public: version, docs, health
# ══════════════════════════════════════════════════════════════════

@app.command()
def version():
    """Show the CLI version."""
    typer.echo(f"elixa {__version__}")


@app.command()
def docs():
    """Open the Elixa docs in your browser."""
    url = "https://elixa.dev/docs"
    err_console.print(f"[{PRIMARY}]→[/] opening [bold]{url}[/]")
    webbrowser.open(url)


@app.command()
def health(
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Ping the API and report database + version."""
    try:
        with _client() as client:
            data = client.health()
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_health)


# ══════════════════════════════════════════════════════════════════
# Public: search, product, merchants, schema
# ══════════════════════════════════════════════════════════════════

@app.command()
def search(
    query: str = typer.Argument(..., help="Natural-language query."),
    category: str = typer.Option(None, "--category", "-c"),
    brand: str = typer.Option(None, "--brand", "-b"),
    colour: str = typer.Option(None, "--colour", help="Controlled colour name."),
    material: str = typer.Option(None, "--material"),
    size: str = typer.Option(None, "--size"),
    gender: Gender = typer.Option(None, "--gender"),
    age_group: AgeGroup = typer.Option(None, "--age-group"),
    condition: Condition = typer.Option(None, "--condition"),
    availability: Availability = typer.Option(None, "--availability"),
    merchant: str = typer.Option(None, "--merchant", help="Merchant name or domain."),
    min_price: float = typer.Option(None, "--min-price"),
    max_price: float = typer.Option(None, "--max-price"),
    currency: str = typer.Option(None, "--currency", help="3-letter ISO code."),
    min_rating: float = typer.Option(None, "--min-rating", min=0, max=5),
    min_completeness: int = typer.Option(None, "--min-completeness", min=0, max=100),
    sort: Sort = typer.Option(Sort.relevancy, "--sort"),
    limit: int = typer.Option(40, "--limit", "-n", min=1, max=100),
    offset: int = typer.Option(0, "--offset", min=0),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Search the Elixa product index."""
    try:
        with _client() as client:
            data = client.search(
                query,
                category=category, brand=brand, colour=colour,
                material=material, size=size,
                gender=gender.value if gender else None,
                age_group=age_group.value if age_group else None,
                condition=condition.value if condition else None,
                availability=availability.value if availability else None,
                merchant=merchant,
                min_price=min_price, max_price=max_price,
                currency=currency.upper() if currency else None,
                min_rating=min_rating, min_completeness=min_completeness,
                sort=sort.value, limit=limit, offset=offset,
            )
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_search_results)


@app.command()
def product(
    elixa_id: str = typer.Argument(..., help="Elixa product ID (UUID)."),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Fetch a single product (all 56 fields)."""
    try:
        with _client() as client:
            data = client.get_product(elixa_id)
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_product)


@app.command()
def merchants(
    q: str = typer.Option(None, "--search", "-q", help="Substring match on name."),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100),
    offset: int = typer.Option(0, "--offset", min=0),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """List indexed merchants."""
    try:
        with _client() as client:
            data = client.list_merchants(q=q, limit=limit, offset=offset)
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_merchants)


@app.command()
def schema(
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Show the full 56-field schema and scoring rules."""
    try:
        with _client() as client:
            data = client.get_schema()
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_schema)


# ══════════════════════════════════════════════════════════════════
# Auth: login, signup, logout, whoami
# ══════════════════════════════════════════════════════════════════

@app.command()
def login(
    email: str = typer.Option(None, "--email", "-e", help="Merchant email."),
    password: str = typer.Option(None, "--password", "-p", hide_input=True),
):
    """Sign in and save a session token at ~/.config/elixa/credentials.json."""
    if not email:
        email = typer.prompt("Email")
    if not password:
        password = typer.prompt("Password", hide_input=True)

    try:
        with _client() as client:
            resp = client.login(email, password)
    except ElixaAPIError as e:
        _handle_error(e)

    token = resp.get("access_token") or resp.get("token")
    if not token:
        err_console.print(f"[{DANGER}]✗[/] Login succeeded but no token returned.")
        raise typer.Exit(code=1)

    expires_in = resp.get("expires_in") or 0
    merchant   = resp.get("merchant") or {}

    creds = Credentials(
        api_url         = resolve_api_url(_state.api_url),
        session_token   = token,
        merchant_id     = merchant.get("id") or resp.get("merchant_id"),
        merchant_name   = merchant.get("name") or resp.get("merchant_name"),
        merchant_domain = merchant.get("domain") or resp.get("merchant_domain"),
        email           = merchant.get("email") or email,
        expires_at      = int(time.time()) + int(expires_in) if expires_in else None,
    )
    path = save_credentials(creds)
    err_console.print(
        f"[bold {SUCCESS}]{GLYPH_OK} Signed in[/] as [bold]{creds.email}[/] "
        f"[{MUTED}]({creds.merchant_name or '—'})[/]"
    )
    err_console.print(f"[{MUTED}]  credentials saved to {path}[/]")


@app.command()
def signup(
    email: str = typer.Option(None, "--email", "-e"),
    password: str = typer.Option(None, "--password", "-p", hide_input=True),
    merchant_name: str = typer.Option(None, "--merchant", "-m"),
    merchant_domain: str = typer.Option(None, "--domain", "-d"),
):
    """Create a new merchant account and sign in."""
    if not email:           email           = typer.prompt("Email")
    if not password:        password        = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    if not merchant_name:   merchant_name   = typer.prompt("Merchant name")
    if not merchant_domain: merchant_domain = typer.prompt("Merchant domain (e.g. mystore.com)")

    try:
        with _client() as client:
            resp = client.signup(
                email=email, password=password,
                merchant_name=merchant_name, merchant_domain=merchant_domain,
            )
    except ElixaAPIError as e:
        _handle_error(e)

    token = resp.get("access_token") or resp.get("token")
    merchant = resp.get("merchant") or {}
    creds = Credentials(
        api_url         = resolve_api_url(_state.api_url),
        session_token   = token,
        merchant_id     = merchant.get("id") or resp.get("merchant_id"),
        merchant_name   = merchant.get("name") or merchant_name,
        merchant_domain = merchant.get("domain") or merchant_domain,
        email           = email,
    )
    if token:
        save_credentials(creds)
    err_console.print(
        f"[bold {SUCCESS}]{GLYPH_OK} Merchant created[/] — "
        f"[bold]{merchant_name}[/] [{MUTED}]({merchant_domain})[/]"
    )
    err_console.print(
        f"[{MUTED}]  next: verify your domain with[/] [bold]elixa domain show[/]"
    )


@app.command()
def logout():
    """Forget saved credentials."""
    removed = clear_credentials()
    if removed:
        err_console.print(f"[{SUCCESS}]{GLYPH_OK}[/] Signed out.")
    else:
        err_console.print(f"[{MUTED}]  no saved credentials.[/]")


@app.command()
def whoami(
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Show the currently signed-in merchant."""
    _require_auth()
    try:
        with _client() as client:
            data = client.me()
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_me)


# ══════════════════════════════════════════════════════════════════
# Merchant: submit
# ══════════════════════════════════════════════════════════════════

@app.command()
def submit(
    file_path: Path = typer.Argument(..., exists=True, readable=True, help="Feed file (.json or .csv)."),
    merchant_name: str = typer.Option(None, "--merchant", "-m", help="Merchant name (defaults to your account)."),
    merchant_domain: str = typer.Option(None, "--domain", "-d", help="Merchant domain (defaults to your account)."),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Submit a product feed directly (bypasses the scheduler)."""
    creds = _require_auth()
    merchant_name   = merchant_name   or creds.merchant_name
    merchant_domain = merchant_domain or creds.merchant_domain
    if not merchant_name or not merchant_domain:
        err_console.print(
            f"[{DANGER}]✗[/] --merchant and --domain are required "
            f"(your saved session didn't include them)."
        )
        raise typer.Exit(code=1)

    ext = file_path.suffix.lower()
    try:
        with _client() as client:
            if ext == ".json":
                with open(file_path) as f:
                    data = json_lib.load(f)
                if isinstance(data, list):
                    products = data
                elif isinstance(data, dict) and "products" in data:
                    products = data["products"]
                else:
                    err_console.print(
                        f"[{DANGER}]✗[/] JSON feed must be an array or have a 'products' key."
                    )
                    raise typer.Exit(code=1)
                result = client.submit_feed_json(
                    merchant_name=merchant_name,
                    merchant_domain=merchant_domain,
                    products=products,
                )
            elif ext == ".csv":
                result = client.submit_feed_csv(
                    file_path,
                    merchant_name=merchant_name,
                    merchant_domain=merchant_domain,
                )
            else:
                err_console.print(
                    f"[{DANGER}]✗[/] Unsupported feed file: {ext}. Use .json or .csv."
                )
                raise typer.Exit(code=1)
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(result, fmt=format, table_printer=print_feed_submit_result)


# ══════════════════════════════════════════════════════════════════
# Merchant: products list
# ══════════════════════════════════════════════════════════════════

@products_app.command("list")
def products_list(
    q: str = typer.Option(None, "--search", "-q"),
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=200),
    offset: int = typer.Option(0, "--offset", min=0),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """List products in your catalog."""
    _require_auth()
    try:
        with _client() as client:
            data = client.list_my_products(q=q, limit=limit, offset=offset)
    except ElixaAPIError as e:
        _handle_error(e)
    # /merchant/products returns the same shape as /search, so reuse that printer.
    _emit(data, fmt=format, table_printer=print_search_results)


# ══════════════════════════════════════════════════════════════════
# Merchant: feeds (subcommand group)
# ══════════════════════════════════════════════════════════════════

@feeds_app.command("list")
def feeds_list(
    active_only: bool = typer.Option(False, "--active-only"),
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=200),
    offset: int = typer.Option(0, "--offset", min=0),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """List your registered feed sources."""
    _require_auth()
    try:
        with _client() as client:
            data = client.list_feed_sources(active_only=active_only, limit=limit, offset=offset)
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_feed_sources)


@feeds_app.command("add")
def feeds_add(
    feed_url: str = typer.Argument(..., help="Public feed URL."),
    merchant_name: str = typer.Option(None, "--merchant", "-m"),
    merchant_domain: str = typer.Option(None, "--domain", "-d"),
    feed_format: FeedFormat = typer.Option(None, "--format-hint"),
    schedule_hours: int = typer.Option(168, "--schedule-hours", min=1, max=720),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Register a feed URL for periodic fetching."""
    creds = _require_auth()
    merchant_name   = merchant_name   or creds.merchant_name
    merchant_domain = merchant_domain or creds.merchant_domain
    if not merchant_name or not merchant_domain:
        err_console.print(
            f"[{DANGER}]✗[/] --merchant and --domain are required."
        )
        raise typer.Exit(code=1)

    try:
        with _client() as client:
            data = client.register_feed_source(
                merchant_name=merchant_name,
                merchant_domain=merchant_domain,
                feed_url=feed_url,
                format=feed_format.value if feed_format else None,
                schedule_hours=schedule_hours,
            )
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_feed_source_detail)


@feeds_app.command("show")
def feeds_show(
    source_id: str = typer.Argument(..., help="Feed source UUID."),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Show details for a single feed source."""
    _require_auth()
    try:
        with _client() as client:
            data = client.get_feed_source(source_id)
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_feed_source_detail)


@feeds_app.command("fetch")
def feeds_fetch(
    source_id: str = typer.Argument(..., help="Feed source UUID."),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Trigger an immediate fetch (bypasses the schedule)."""
    _require_auth()
    try:
        with _client() as client:
            data = client.trigger_feed_fetch(source_id)
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_feed_fetch_result)


@feeds_app.command("remove")
def feeds_remove(
    source_id: str = typer.Argument(..., help="Feed source UUID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
):
    """Remove a feed source (already-indexed products are kept)."""
    _require_auth()
    if not yes and not typer.confirm(f"Remove feed source {source_id}?"):
        raise typer.Abort()
    try:
        with _client() as client:
            client.delete_feed_source(source_id)
    except ElixaAPIError as e:
        _handle_error(e)
    err_console.print(f"[{SUCCESS}]{GLYPH_OK}[/] removed [bold]{source_id}[/]")


@feeds_app.command("pause")
def feeds_pause(source_id: str = typer.Argument(..., help="Feed source UUID.")):
    """Stop auto-fetching without losing the registration."""
    _require_auth()
    try:
        with _client() as client:
            client.update_feed_source(source_id, is_active=False)
    except ElixaAPIError as e:
        _handle_error(e)
    err_console.print(f"[{WARN}]◐[/] paused [bold]{source_id}[/]")


@feeds_app.command("resume")
def feeds_resume(source_id: str = typer.Argument(..., help="Feed source UUID.")):
    """Resume a paused feed source."""
    _require_auth()
    try:
        with _client() as client:
            client.update_feed_source(source_id, is_active=True)
    except ElixaAPIError as e:
        _handle_error(e)
    err_console.print(f"[{SUCCESS}]{GLYPH_OK}[/] resumed [bold]{source_id}[/]")


# ══════════════════════════════════════════════════════════════════
# Merchant: API keys
# ══════════════════════════════════════════════════════════════════

@keys_app.command("list")
def keys_list(
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """List active and revoked API keys."""
    _require_auth()
    try:
        with _client() as client:
            data = client.list_api_keys()
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_api_keys)


@keys_app.command("create")
def keys_create(
    name: str = typer.Argument(..., help="Human-readable label for the key."),
    scopes: list[str] = typer.Option(
        ["search:read"],
        "--scope", "-s",
        help="Scope to grant. Repeat for multiple. Default: search:read.",
    ),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Create a new API key. The plaintext token is shown exactly once."""
    _require_auth()
    try:
        with _client() as client:
            data = client.create_api_key(name=name, scopes=scopes)
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_new_api_key)


@keys_app.command("revoke")
def keys_revoke(
    key_id: str = typer.Argument(..., help="ID of the key to revoke."),
    yes: bool = typer.Option(False, "--yes", "-y"),
):
    """Revoke an API key. Cannot be undone."""
    _require_auth()
    if not yes and not typer.confirm(f"Revoke key {key_id}? This cannot be undone."):
        raise typer.Abort()
    try:
        with _client() as client:
            client.revoke_api_key(key_id)
    except ElixaAPIError as e:
        _handle_error(e)
    err_console.print(f"[{SUCCESS}]{GLYPH_OK}[/] revoked [bold]{key_id}[/]")


# ══════════════════════════════════════════════════════════════════
# Merchant: domain
# ══════════════════════════════════════════════════════════════════

@domain_app.command("show")
def domain_show(
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Show the TXT record you need to add at your DNS host."""
    _require_auth()
    try:
        with _client() as client:
            data = client.get_domain_instructions()
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_domain_instructions)


@domain_app.command("verify")
def domain_verify(
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Re-check your DNS record and verify ownership."""
    _require_auth()
    try:
        with _client() as client:
            data = client.verify_domain()
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_verify_result)


# ══════════════════════════════════════════════════════════════════
# Merchant: analytics
# ══════════════════════════════════════════════════════════════════

@analytics_app.command("summary")
def analytics_summary(
    days: int = typer.Option(30, "--days", "-d", min=1, max=365),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Impressions, clicks, CTR, searches, feed fetches for the window."""
    _require_auth()
    try:
        with _client() as client:
            data = client.analytics_summary(days=days)
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_analytics_summary)


@analytics_app.command("queries")
def analytics_queries(
    days: int = typer.Option(30, "--days", "-d", min=1, max=365),
    limit: int = typer.Option(10, "--limit", "-n", min=1, max=100),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Top queries that surfaced your products."""
    _require_auth()
    try:
        with _client() as client:
            data = client.top_queries(days=days, limit=limit)
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_top_queries)


@analytics_app.command("products")
def analytics_products(
    days: int = typer.Option(30, "--days", "-d", min=1, max=365),
    limit: int = typer.Option(10, "--limit", "-n", min=1, max=100),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Your most-viewed products in the window."""
    _require_auth()
    try:
        with _client() as client:
            data = client.top_products(days=days, limit=limit)
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_top_products)


@analytics_app.command("events")
def analytics_events(
    event_type: EventType = typer.Option(None, "--type", "-t", help="Filter by event type."),
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=200),
    offset: int = typer.Option(0, "--offset", min=0),
    format: OutputFormat = typer.Option(OutputFormat.auto, "--format", "-f"),
):
    """Raw event stream (impressions, clicks, searches, feed fetches)."""
    _require_auth()
    try:
        with _client() as client:
            data = client.events(
                event_type=event_type.value if event_type else None,
                limit=limit, offset=offset,
            )
    except ElixaAPIError as e:
        _handle_error(e)
    _emit(data, fmt=format, table_printer=print_events)


# ══════════════════════════════════════════════════════════════════
# Entrypoint
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app()
