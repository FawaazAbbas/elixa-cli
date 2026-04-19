"""
Terminal output.

Palette mirrors the web tokens (blue primary, violet accent, green/amber/
red for status). Rich renders hex colours natively on truecolor TTYs, so
output looks the same as the console UI pixel-for-pixel on colour.

Two output modes:
  • json   — machine-readable; printed with indentation for greppability
  • table  — human-friendly; lots of whitespace, rounded boxes, aligned
             numbers. Auto-selected when stdout is a TTY (see
             `config.resolve_output_mode`).

Every formatter takes a plain dict (what the backend returned) and prints
via `console`. Nothing mutates the input.
"""

from __future__ import annotations

import json
from typing import Any

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Two consoles — stdout for data, stderr for decorations/errors — so
# users can still pipe `elixa search ... | jq` and keep their prompts
# clean of framing noise.
console     = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)

# ── Palette (synced with web/src/styles/tokens.css) ────────────────

PRIMARY    = "#3B82F6"   # blue 500
PRIMARY_DIM = "#93C5FD"  # blue 300 — quieter borders
SECONDARY  = "#8B5CF6"   # violet 500
SUCCESS    = "#16A34A"   # green
WARN       = "#D97706"   # amber
DANGER     = "#DC2626"   # red
MUTED      = "grey58"
ACCENT     = "#06B6D4"   # cyan — IDs, prefixes

# ── Glyphs ──────────────────────────────────────────────────────────
# Single-codepoint symbols that fall back cleanly on limited TTYs. Kept
# minimal so we don't look like a Christmas tree.
GLYPH_OK    = "✓"
GLYPH_ERR   = "✗"
GLYPH_WARN  = "!"
GLYPH_DOT   = "•"
GLYPH_ON    = "●"
GLYPH_OFF   = "○"
GLYPH_HALF  = "◐"
GLYPH_ARROW = "→"


# ── Generic helpers ────────────────────────────────────────────────

def print_json(data: Any) -> None:
    """Print indented JSON to stdout, exactly — no colour codes injected."""
    print(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def _panel_title(title: str, subtitle: str | None = None) -> Text:
    t = Text()
    t.append("◆ ", style=f"bold {PRIMARY}")
    t.append(title, style="bold")
    if subtitle:
        t.append("  ")
        t.append(subtitle, style=MUTED)
    return t


def banner(title: str, subtitle: str | None = None) -> None:
    console.print()
    console.print(_panel_title(title, subtitle))
    console.print(Text("─" * 60, style=PRIMARY_DIM))


def section(label: str) -> None:
    console.print()
    console.print(Text(label, style=f"bold {PRIMARY}"))


def kv_table() -> Table:
    """Two-column key/value grid — meta cards use this a lot."""
    t = Table(show_header=False, box=None, padding=(0, 2), pad_edge=False)
    t.add_column(style=MUTED, no_wrap=True, min_width=16)
    t.add_column(overflow="fold")
    return t


def data_table(**overrides: Any) -> Table:
    defaults: dict[str, Any] = dict(
        show_header=True,
        header_style=f"bold {PRIMARY}",
        box=ROUNDED,
        border_style=PRIMARY_DIM,
        pad_edge=False,
        padding=(0, 1),
        expand=True,
    )
    defaults.update(overrides)
    return Table(**defaults)


def truncate(text: Any, n: int = 40) -> str:
    if text is None:
        return "—"
    s = str(text)
    return s if len(s) <= n else s[: n - 1] + "…"


def fmt_money(amount: Any, currency: Any = None) -> str:
    if amount is None:
        return "—"
    try:
        f = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    c = (currency or "").upper() if currency else ""
    if f == int(f):
        body = f"{int(f):,}"
    else:
        body = f"{f:,.2f}"
    return f"{c} {body}".strip()


def fmt_availability(a: str | None) -> Text:
    if not a:
        return Text("—", style=MUTED)
    table = {
        "in_stock":     (f"{GLYPH_ON} in stock",      SUCCESS),
        "out_of_stock": (f"{GLYPH_OFF} out of stock", DANGER),
        "preorder":     (f"{GLYPH_HALF} preorder",    WARN),
        "backorder":    (f"{GLYPH_HALF} backorder",   WARN),
    }
    text, style = table.get(a, (a, "white"))
    return Text(text, style=style)


def fmt_score(score: Any) -> Text:
    if score is None:
        return Text("—", style=MUTED)
    try:
        n = int(float(score))
    except (TypeError, ValueError):
        return Text(str(score))
    if n >= 90:  style = f"bold {SUCCESS}"
    elif n >= 70: style = SUCCESS
    elif n >= 50: style = WARN
    else:         style = DANGER
    return Text(f"{n}", style=style)


def fmt_status(status: str | None) -> Text:
    if not status:
        return Text("—", style=MUTED)
    palette = {
        "success":  SUCCESS,
        "ok":       SUCCESS,
        "healthy":  SUCCESS,
        "running":  WARN,
        "pending":  MUTED,
        "failed":   DANGER,
        "error":    DANGER,
    }
    return Text(status, style=palette.get(status, "white"))


# ══════════════════════════════════════════════════════════════════
# Errors
# ══════════════════════════════════════════════════════════════════

def print_error(err: "ElixaAPIErrorLike") -> None:  # type: ignore[name-defined]
    """Pretty-print the backend's error envelope."""
    err_console.print()
    header = Text()
    header.append(f"{GLYPH_ERR} ", style=f"bold {DANGER}")
    header.append(err.message, style="bold")
    err_console.print(header)
    meta = Text()
    if err.status_code:
        meta.append(f"  HTTP {err.status_code}", style=MUTED)
    if err.code:
        meta.append(f"  {GLYPH_DOT} {err.code}", style=MUTED)
    if err.request_id:
        meta.append(f"  {GLYPH_DOT} ", style=MUTED)
        meta.append(err.request_id, style=ACCENT)
    if meta.plain:
        err_console.print(meta)
    if err.hint:
        err_console.print(Text(f"  {err.hint}", style=WARN))
    err_console.print()


# ══════════════════════════════════════════════════════════════════
# Search results
# ══════════════════════════════════════════════════════════════════

def print_search_results(data: dict) -> None:
    results = data.get("results") or []
    total   = data.get("total_results", 0)
    query   = data.get("query", "")

    banner("Search", f'"{query}"  {GLYPH_DOT}  {total:,} result{"s" if total != 1 else ""}')

    if not results:
        console.print()
        console.print(Text("  no products matched your query.", style=MUTED))
        return

    t = data_table()
    t.add_column("Title", max_width=48, overflow="ellipsis")
    t.add_column("Brand", max_width=18, overflow="ellipsis")
    t.add_column("Price", justify="right")
    t.add_column("Stock")
    t.add_column("Score", justify="right")
    t.add_column("Merchant", max_width=18, overflow="ellipsis")

    for r in results:
        t.add_row(
            truncate(r.get("title"), 48),
            truncate(r.get("brand") or "—", 18),
            fmt_money(r.get("price"), r.get("currency")),
            fmt_availability(r.get("availability")),
            fmt_score(r.get("elixa_completeness_score")),
            truncate(r.get("merchant_name") or "—", 18),
        )
    console.print(t)

    limit  = data.get("limit", 20)
    offset = data.get("offset", 0)
    if total > limit:
        lo = offset + 1
        hi = min(offset + len(results), total)
        console.print()
        console.print(Text(
            f"  showing {lo}–{hi} of {total:,}.  next page: --offset {offset + limit}",
            style=MUTED,
        ))


# ══════════════════════════════════════════════════════════════════
# Product detail
# ══════════════════════════════════════════════════════════════════

def print_product(p: dict) -> None:
    title = p.get("title") or "Untitled"
    brand = p.get("brand") or ""
    header = Text()
    header.append(title, style="bold")
    if brand:
        header.append("   ")
        header.append(brand, style=MUTED)

    console.print()
    console.print(Panel.fit(header, border_style=PRIMARY, padding=(0, 2)))

    # Price row
    price_row = Text()
    price_row.append(fmt_money(p.get("price"), p.get("currency")), style=f"bold {SUCCESS}")
    if p.get("sale_price") and p["sale_price"] != p.get("price"):
        price_row.append("   was ", style=MUTED)
        price_row.append(fmt_money(p["sale_price"], p.get("currency")), style=MUTED)
    console.print(price_row)

    meta = kv_table()
    meta.add_row("Availability", fmt_availability(p.get("availability")))
    meta.add_row("Condition",    p.get("condition") or "—")

    colour = p.get("colour")
    if colour:
        if isinstance(colour, dict):
            cell = f"{colour.get('name', '')} {colour.get('hex', '')}".strip()
            meta.add_row("Colour", cell or "—")
        else:
            meta.add_row("Colour", str(colour))

    if p.get("size"):
        sys_ = p.get("size_system")
        meta.add_row("Size", f"{p['size']} ({sys_})" if sys_ else p["size"])

    for key, label in [
        ("material",  "Material"),
        ("gender",    "Gender"),
        ("age_group", "Age group"),
    ]:
        if p.get(key):
            meta.add_row(label, p[key])

    if p.get("rating") is not None:
        reviews = p.get("review_count") or 0
        meta.add_row("Rating", f"★ {p['rating']:.1f}  ({reviews:,} reviews)")

    if p.get("delivery_estimate_days"):
        meta.add_row("Delivery", f"{p['delivery_estimate_days']} days")

    if isinstance(p.get("shipping_cost"), dict):
        sc = p["shipping_cost"]
        meta.add_row("Shipping", fmt_money(sc.get("amount"), sc.get("currency")))

    if p.get("merchant_name"):
        meta.add_row("Merchant", p["merchant_name"])
    if p.get("merchant_domain"):
        meta.add_row("Domain", p["merchant_domain"])
    if p.get("source_url"):
        meta.add_row("Source", p["source_url"])

    meta.add_row("Completeness", fmt_score(p.get("elixa_completeness_score")))
    meta.add_row("Elixa ID", Text(p.get("elixa_id", "—"), style=ACCENT))

    console.print()
    console.print(meta)

    desc = p.get("description")
    if desc:
        section("Description")
        console.print(Text(desc))

    for key, title_ in [("product_highlights", "Highlights"), ("product_details", "Details")]:
        items = p.get(key)
        if not items:
            continue
        section(title_)
        for item in items:
            if isinstance(item, dict) and "name" in item:
                row = Text()
                row.append(f"  {item['name']}: ", style=MUTED)
                row.append(str(item.get("value", "")))
                console.print(row)
            else:
                console.print(Text(f"  {GLYPH_DOT} {item}"))


# ══════════════════════════════════════════════════════════════════
# Merchants
# ══════════════════════════════════════════════════════════════════

def print_merchants(data: dict) -> None:
    rows = data.get("merchants") or []
    total = data.get("total_merchants", 0)
    banner("Merchants", f"{total:,} indexed")
    if not rows:
        console.print()
        console.print(Text("  no merchants match.", style=MUTED))
        return

    t = data_table()
    t.add_column("Name", max_width=30, overflow="ellipsis")
    t.add_column("Domain", max_width=32, overflow="ellipsis")
    t.add_column("Products", justify="right")
    t.add_column("Avg score", justify="right")
    t.add_column("Trust", justify="right")

    for m in rows:
        trust = m.get("merchant_trust_score")
        t.add_row(
            truncate(m.get("merchant_name") or "—", 30),
            truncate(m.get("merchant_domain") or "—", 32),
            f"{m.get('product_count', 0):,}",
            fmt_score(m.get("avg_completeness_score")),
            f"{trust:.0f}" if trust is not None else "—",
        )
    console.print(t)


# ══════════════════════════════════════════════════════════════════
# Schema
# ══════════════════════════════════════════════════════════════════

def print_schema(schema: dict) -> None:
    banner(
        f"Elixa Schema v{schema.get('version', '1.0')}",
        f"{schema.get('total_fields', 56)} fields",
    )

    tiers = (schema.get("scoring") or {}).get("tiers") or {}
    if tiers:
        section("Scoring tiers")
        t = data_table()
        t.add_column("Tier")
        t.add_column("Count", justify="right")
        t.add_column("Pts each", justify="right")
        t.add_column("Max", justify="right")
        for name, info in tiers.items():
            t.add_row(
                name.replace("_", " ").title(),
                str(info.get("count", 0)),
                str(info.get("points_each", 0)),
                str(info.get("max", 0)),
            )
        console.print(t)

    groups = schema.get("field_groups") or {}
    if groups:
        section("Field groups")
        for name, fields in groups.items():
            row = Text()
            row.append(f"  {name.replace('_', ' ').title()}  ")
            row.append(f"({len(fields) if isinstance(fields, dict) else 0} fields)", style=MUTED)
            console.print(row)

    enums = schema.get("accepted_values") or {}
    if enums:
        section("Enumerated values")
        for field, values in enums.items():
            row = Text()
            row.append(f"  {field}: ", style=MUTED)
            row.append(", ".join(values) if isinstance(values, list) else str(values))
            console.print(row)


# ══════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════

def print_health(data: dict) -> None:
    status = data.get("status") or "unknown"
    healthy = status in {"healthy", "ok"}
    glyph = GLYPH_ON if healthy else GLYPH_HALF
    style = SUCCESS if healthy else WARN
    row = Text()
    row.append(f"{glyph} {status}", style=f"bold {style}")
    if data.get("database"):
        row.append(f"   db: {data['database']}", style=MUTED)
    if data.get("version"):
        row.append(f"   v{data['version']}", style=MUTED)
    err_console.print(row)


# ══════════════════════════════════════════════════════════════════
# Feed submission
# ══════════════════════════════════════════════════════════════════

def print_feed_submit_result(r: dict) -> None:
    accepted = r.get("accepted", 0)
    rejected = r.get("rejected", 0)
    banner("Feed submitted", f"{accepted:,} accepted  {GLYPH_DOT}  {rejected:,} rejected")

    m = kv_table()
    m.add_row("Accepted", Text(f"{accepted:,}", style=f"bold {SUCCESS}"))
    m.add_row("Rejected", Text(f"{rejected:,}", style=DANGER if rejected else MUTED))
    m.add_row("Avg score", fmt_score(r.get("avg_completeness_score")))
    console.print()
    console.print(m)

    errors = r.get("errors") or []
    if errors:
        section(f"Errors  ({len(errors)} total, showing 20)")
        t = data_table(header_style=f"bold {DANGER}", border_style=DANGER)
        t.add_column("Row", justify="right")
        t.add_column("Field")
        t.add_column("Error")
        for e in errors[:20]:
            t.add_row(
                str(e.get("index", "")),
                e.get("field") or "—",
                truncate(e.get("error"), 80),
            )
        console.print(t)

    report = r.get("completeness_report") or {}
    dist   = report.get("score_distribution") or {}
    if dist:
        section("Score distribution")
        bucket_tone = {
            "90-100": SUCCESS, "70-89": SUCCESS,
            "50-69":  WARN,    "30-49": WARN,
            "0-29":   DANGER,
        }
        max_count = max(dist.values()) or 1
        for bucket in ("90-100", "70-89", "50-69", "30-49", "0-29"):
            count = dist.get(bucket, 0)
            bar_width = int((count / max_count) * 40)
            line = Text()
            line.append(f"  {bucket:>7}  ", style=MUTED)
            line.append("█" * bar_width, style=bucket_tone.get(bucket, "white"))
            line.append(f"  {count:,}")
            console.print(line)

    missing = report.get("most_missing_fields") or []
    if missing:
        section("Most commonly missing")
        console.print(Text(f"  {', '.join(missing[:10])}", style=WARN))


# ══════════════════════════════════════════════════════════════════
# Feed sources
# ══════════════════════════════════════════════════════════════════

def print_feed_sources(data: dict) -> None:
    sources = data.get("sources") or []
    total = data.get("total", 0)
    banner("Feed sources", f"{total:,} registered")
    if not sources:
        console.print()
        console.print(Text(
            f"  no feeds registered. register one with: elixa feeds add <url>",
            style=MUTED,
        ))
        return

    t = data_table()
    t.add_column("Merchant", max_width=20, overflow="ellipsis")
    t.add_column("URL", max_width=40, overflow="ellipsis")
    t.add_column("Fmt")
    t.add_column("Every", justify="right")
    t.add_column("Status")
    t.add_column("Products", justify="right")
    t.add_column("ID", max_width=8, overflow="ellipsis")

    for s in sources:
        hours = s.get("schedule_hours", 168)
        every = f"{hours}h" if hours < 168 else f"{hours // 168}w"
        label = s.get("merchant_name") or "—"
        if not s.get("is_active", True):
            label += " (paused)"
        t.add_row(
            truncate(label, 20),
            truncate(s.get("feed_url") or "—", 40),
            s.get("format") or "?",
            every,
            fmt_status(s.get("last_status") or "pending"),
            f"{s.get('last_products_accepted', 0):,}",
            truncate(s.get("id") or "—", 8),
        )
    console.print(t)


def print_feed_source_detail(s: dict) -> None:
    banner(s.get("merchant_name") or "Feed source")
    m = kv_table()
    m.add_row("ID", Text(s.get("id") or "—", style=ACCENT))
    m.add_row("Merchant", s.get("merchant_name") or "—")
    m.add_row("Domain", s.get("merchant_domain") or "—")
    m.add_row("Feed URL", s.get("feed_url") or "—")
    m.add_row("Format", s.get("format") or "—")
    m.add_row("Schedule", f"every {s.get('schedule_hours', 0)}h")
    m.add_row(
        "Active",
        Text("yes", style=SUCCESS) if s.get("is_active") else Text("no", style=MUTED),
    )
    m.add_row("Last fetched", s.get("last_fetched_at") or "never")
    m.add_row("Last status", fmt_status(s.get("last_status")))
    m.add_row("Products fetched", f"{s.get('last_products_fetched', 0):,}")
    m.add_row("Last accepted", Text(f"{s.get('last_products_accepted', 0):,}", style=SUCCESS))
    m.add_row("Last rejected", f"{s.get('last_products_rejected', 0):,}")
    m.add_row("Avg completeness", fmt_score(s.get("last_avg_completeness")))
    if s.get("last_error"):
        m.add_row("Last error", Text(s["last_error"], style=DANGER))
    console.print()
    console.print(m)


def print_feed_fetch_result(r: dict) -> None:
    status = r.get("status") or "unknown"
    banner("Feed fetch", status)

    if r.get("error"):
        console.print()
        console.print(Text(f"  {r['error']}", style=DANGER))
        return

    m = kv_table()
    m.add_row("Status", fmt_status(status))
    m.add_row("Products fetched", f"{r.get('products_fetched', 0):,}")
    m.add_row("Accepted", Text(f"{r.get('products_accepted', 0):,}", style=f"bold {SUCCESS}"))
    m.add_row("Rejected", f"{r.get('products_rejected', 0):,}")
    m.add_row("Avg completeness", fmt_score(r.get("avg_completeness_score")))
    m.add_row("Duration", f"{r.get('duration_seconds', 0):.1f}s")

    stale_oos = r.get("stale_marked_out_of_stock") or 0
    stale_del = r.get("stale_deleted") or 0
    if stale_oos or stale_del:
        m.add_row("Stale → OOS", f"{stale_oos:,}")
        m.add_row("Stale → deleted", f"{stale_del:,}")

    console.print()
    console.print(m)

    errors = r.get("errors") or []
    if errors:
        section(f"Validation errors  ({len(errors)} total, showing 10)")
        for e in errors[:10]:
            line = Text()
            line.append(f"  [{e.get('index', '?')}] ", style=MUTED)
            line.append(f"{e.get('field') or '—'}: ", style=WARN)
            line.append(str(e.get("error") or ""))
            console.print(line)


# ══════════════════════════════════════════════════════════════════
# Merchant-scoped
# ══════════════════════════════════════════════════════════════════

def print_me(me: dict) -> None:
    banner("Merchant", me.get("merchant_name") or "—")
    m = kv_table()
    m.add_row("ID", Text(me.get("merchant_id") or "—", style=ACCENT))
    m.add_row("Name", me.get("merchant_name") or "—")
    m.add_row("Domain", me.get("merchant_domain") or "—")
    m.add_row("Email", me.get("email") or "—")
    m.add_row(
        "Domain verified",
        Text("yes", style=SUCCESS) if me.get("domain_verified") else Text("no", style=WARN),
    )
    m.add_row("Products", f"{me.get('product_count', 0):,}")
    m.add_row("Avg score", fmt_score(me.get("avg_completeness_score")))
    console.print()
    console.print(m)


def print_analytics_summary(s: dict) -> None:
    banner(
        "Analytics",
        f"{s.get('window_days', 30)}-day window",
    )
    m = kv_table()
    m.add_row("Impressions", Text(f"{s.get('impressions', 0):,}", style=f"bold {PRIMARY}"))
    m.add_row("Clicks",      Text(f"{s.get('clicks', 0):,}",      style=f"bold {SUCCESS}"))
    ctr = s.get("click_through_rate", 0) or 0
    m.add_row("CTR", f"{ctr * 100:.2f}%")
    m.add_row("Searches",    f"{s.get('searches', 0):,}")
    m.add_row("Feed fetches", f"{s.get('feed_fetches', 0):,}")
    console.print()
    console.print(m)


def print_top_queries(rows: list[dict]) -> None:
    banner("Top queries", f"{len(rows)} shown")
    if not rows:
        console.print()
        console.print(Text("  no queries in this window yet.", style=MUTED))
        return

    max_count = max((r.get("count", 0) for r in rows), default=0) or 1
    for i, r in enumerate(rows, 1):
        count = r.get("count", 0)
        bar = int((count / max_count) * 32)
        line = Text()
        line.append(f"  {i:>2}. ", style=MUTED)
        line.append(f"{truncate(r.get('query', ''), 40):<42}")
        line.append("█" * bar, style=PRIMARY)
        line.append(f"  {count:,}", style=MUTED)
        console.print(line)


def print_top_products(rows: list[dict]) -> None:
    banner("Top products", f"{len(rows)} shown")
    if not rows:
        console.print()
        console.print(Text("  no product events yet.", style=MUTED))
        return
    t = data_table()
    t.add_column("#", justify="right")
    t.add_column("Title", max_width=50, overflow="ellipsis")
    t.add_column("Impr.", justify="right")
    t.add_column("Clicks", justify="right")
    t.add_column("CTR", justify="right")
    for i, r in enumerate(rows, 1):
        ctr = r.get("click_through_rate", 0) or 0
        t.add_row(
            str(i),
            truncate(r.get("title") or "(untitled)", 50),
            f"{r.get('impressions', 0):,}",
            f"{r.get('clicks', 0):,}",
            f"{ctr * 100:.1f}%",
        )
    console.print(t)


def print_events(data: dict) -> None:
    events = data.get("events") or []
    total  = data.get("total", 0)
    banner("Events", f"{total:,} total, showing {len(events)}")
    if not events:
        console.print()
        console.print(Text("  no events match.", style=MUTED))
        return
    t = data_table()
    t.add_column("Type", max_width=12)
    t.add_column("When", max_width=24, overflow="ellipsis")
    t.add_column("Query / product", overflow="ellipsis")
    for e in events:
        kind_tone = {
            "click":       SUCCESS,
            "impression":  PRIMARY,
            "search":      MUTED,
            "feed_fetch":  WARN,
        }.get(e.get("event_type"), "white")
        subject = e.get("query") or e.get("elixa_id") or "—"
        t.add_row(
            Text(e.get("event_type") or "—", style=kind_tone),
            e.get("created_at") or "—",
            truncate(subject, 60),
        )
    console.print(t)


# ══════════════════════════════════════════════════════════════════
# API keys
# ══════════════════════════════════════════════════════════════════

def print_api_keys(data: dict) -> None:
    keys = data.get("keys") or []
    active = [k for k in keys if not k.get("revoked_at")]
    revoked = [k for k in keys if k.get("revoked_at")]
    banner("API keys", f"{len(active)} active, {len(revoked)} revoked")
    if not keys:
        console.print()
        console.print(Text(
            "  no keys yet. create one with: elixa keys create <name>",
            style=MUTED,
        ))
        return

    def _print(rows: list[dict], title: str, border: str) -> None:
        if not rows:
            return
        section(title)
        t = data_table(border_style=border)
        t.add_column("Name", max_width=24, overflow="ellipsis")
        t.add_column("Prefix", max_width=14)
        t.add_column("Scopes", overflow="fold")
        t.add_column("Created")
        t.add_column("Last used")
        for k in rows:
            t.add_row(
                k.get("name") or "—",
                Text(f"{k.get('key_prefix', '?')}…", style=ACCENT),
                ", ".join(k.get("scopes") or []) or "—",
                truncate(k.get("created_at"), 24),
                truncate(k.get("last_used_at"), 24) if k.get("last_used_at") else "—",
            )
        console.print(t)

    _print(active, "Active", PRIMARY_DIM)
    _print(revoked, "Revoked", MUTED)


def print_new_api_key(k: dict) -> None:
    """Big copy-this-once banner — plaintext token appears exactly once."""
    console.print()
    console.print(Panel(
        Text.from_markup(
            f"[bold {SUCCESS}]{GLYPH_OK} Key created[/]\n\n"
            f"[{MUTED}]This token won't be shown again. Store it in your secret manager.[/]\n\n"
            f"[bold]{k.get('key')}[/]"
        ),
        border_style=SUCCESS,
        padding=(1, 2),
    ))
    m = kv_table()
    m.add_row("Name", k.get("name") or "—")
    m.add_row("ID",   Text(k.get("id") or "—", style=ACCENT))
    m.add_row("Scopes", ", ".join(k.get("scopes") or []) or "—")
    console.print(m)


# ══════════════════════════════════════════════════════════════════
# Domain
# ══════════════════════════════════════════════════════════════════

def print_domain_instructions(inst: dict) -> None:
    verified = inst.get("verified", False)
    banner(
        "Domain verification",
        "verified" if verified else "unverified",
    )
    if verified:
        console.print()
        console.print(Text(
            f"  {GLYPH_OK} {inst.get('domain')} is verified.",
            style=SUCCESS,
        ))
        return

    section("Add this TXT record at your DNS host")
    t = data_table()
    t.add_column("Host")
    t.add_column("Type")
    t.add_column("Value", overflow="fold")
    t.add_row(
        Text(inst.get("record_host") or "—", style=ACCENT),
        inst.get("record_type") or "TXT",
        Text(inst.get("expected_value") or "—", style=ACCENT),
    )
    console.print(t)
    console.print()
    console.print(Text(
        "  once the record is live, re-check with: elixa domain verify",
        style=MUTED,
    ))


def print_verify_result(r: dict) -> None:
    verified = r.get("verified")
    style = SUCCESS if verified else WARN
    glyph = GLYPH_OK if verified else GLYPH_WARN
    console.print()
    console.print(Text(f"{glyph} {r.get('message', 'unknown')}", style=f"bold {style}"))
    if verified:
        console.print(Text(f"  {r.get('domain')} is verified.", style=MUTED))
