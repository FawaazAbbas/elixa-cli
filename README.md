# Elixa CLI

> Structured product search for AI agents — from the terminal.

`elixa` is the official CLI for [Elixa](https://search.elixa.app), the product
search engine built for machines. Every product is normalised into a strict
56-field schema and ranked by relevancy + completeness. The CLI gives you
search, catalog submission, feed management, analytics, and API key
administration — all scriptable, all JSON-friendly.

```bash
pip install elixa
```

---

## Quick start

```bash
# Search anonymously — no auth required.
elixa search "merino jumper" --max-price 150 --availability in_stock

# See the full 56-field product detail.
elixa product 3f5c2e7a-...

# Sign in to push a feed or view analytics.
elixa login
elixa submit products.json
elixa analytics summary --days 7
```

---

## Output modes

`elixa` picks the right format automatically:

| Scenario                         | Default    |
|----------------------------------|------------|
| Running in a terminal (TTY)      | **Table**  |
| Piped to another command / file  | **JSON**   |

Force either mode with `--format`:

```bash
elixa search "wireless headphones" --format json | jq '.results[0]'
elixa schema --format table
```

This mirrors how `gh` and `stripe` behave — readable for humans, parseable
for agents, no surprises either way.

---

## Authentication

Three ways to authenticate, in priority order:

1. **`ELIXA_API_KEY` env var** — best for CI and scripts.
   ```bash
   export ELIXA_API_KEY=sk_live_...
   ```
2. **`elixa login`** — interactive; saves a session token to
   `~/.config/elixa/credentials.json` (chmod 600).
   ```bash
   elixa login
   # email: me@mystore.com
   # password: ········
   ```
3. **No auth** — public commands work out of the box (search, product,
   merchants, schema, health).

Sign out with `elixa logout`. Verify who you are with `elixa whoami`.

---

## Configuration

| Variable            | Default                     | Purpose                                      |
|---------------------|-----------------------------|----------------------------------------------|
| `ELIXA_API_URL`     | `https://api.elixa.app`     | Override the API base URL (local dev / proxies). |
| `ELIXA_API_KEY`     | —                           | Bearer token (takes precedence over session). |
| `XDG_CONFIG_HOME`   | `~/.config`                 | Where credentials are stored.                |

Override `--api-url` on any command to target a different instance:

```bash
elixa --api-url http://localhost:8000 health
```

---

## Commands

### Public

| Command          | Description                                                |
|------------------|------------------------------------------------------------|
| `elixa search`   | Search products with structured filters.                   |
| `elixa product`  | Full 56-field detail for one product.                      |
| `elixa merchants`| List merchants with product counts and avg scores.         |
| `elixa schema`   | Show the schema + scoring tiers.                           |
| `elixa health`   | Ping the API.                                              |
| `elixa docs`     | Open the docs in your browser.                             |
| `elixa version`  | Print CLI version.                                         |

### Auth

| Command          | Description                                                |
|------------------|------------------------------------------------------------|
| `elixa login`    | Sign in with email + password.                             |
| `elixa signup`   | Create a merchant account.                                 |
| `elixa logout`   | Clear saved credentials.                                   |
| `elixa whoami`   | Show the signed-in merchant.                               |

### Merchant-scoped

| Command                     | Description                                        |
|-----------------------------|----------------------------------------------------|
| `elixa submit <file>`       | Push a JSON or CSV feed directly.                  |
| `elixa products list`       | List products in your catalog.                     |
| `elixa feeds list`          | List registered feed URLs.                         |
| `elixa feeds add <url>`     | Register a feed for periodic fetching.             |
| `elixa feeds show <id>`     | Show details for one feed source.                  |
| `elixa feeds fetch <id>`    | Trigger an immediate fetch.                        |
| `elixa feeds pause <id>`    | Pause auto-fetching.                               |
| `elixa feeds resume <id>`   | Resume a paused feed.                              |
| `elixa feeds remove <id>`   | Remove a feed source.                              |
| `elixa keys list`           | List active + revoked API keys.                    |
| `elixa keys create <name>`  | Create a new API key (plaintext shown once).       |
| `elixa keys revoke <id>`    | Revoke a key.                                      |
| `elixa domain show`         | Show the TXT record to add at your DNS host.       |
| `elixa domain verify`       | Re-check your DNS record.                          |
| `elixa analytics summary`   | Impressions, clicks, CTR, searches.                |
| `elixa analytics queries`   | Top queries that surfaced your products.           |
| `elixa analytics products`  | Your most-viewed products.                         |
| `elixa analytics events`    | Raw event stream.                                  |

Run any command with `-h`/`--help` for the full flag list.

---

## Feed submission

JSON (either an array or `{"products": [...]}`):

```bash
elixa submit products.json
```

CSV (UTF-8, header row matches field names from `elixa schema`):

```bash
elixa submit products.csv
```

The response includes a completeness breakdown: per-bucket distribution
(`0-29`, `30-49`, …, `90-100`) and the fields most commonly missing
across your catalog.

---

## Errors

Every non-2xx response comes back as a structured envelope:

```json
{
  "code": "product_not_found",
  "detail": "No product with that elixa_id.",
  "hint": "Check the ID or run `elixa search` to find live products.",
  "request_id": "req_01H8X..."
}
```

`elixa` renders it as:

```
✗ No product with that elixa_id.
  HTTP 404  •  product_not_found  •  req_01H8X...
  Check the ID or run `elixa search` to find live products.
```

Scripts can parse the JSON mode (`--format json`) and branch on the stable
`code` field — never regex English detail strings.

---

## Examples

```bash
# Find sub-£100 jumpers from a specific merchant, sorted by completeness.
elixa search "wool jumper" \
  --max-price 100 --currency GBP \
  --merchant mystore.com --sort completeness

# Pipe search results into a downstream agent.
elixa search "4k monitor" --format json \
  | jq '.results[] | {id: .elixa_id, price, merchant: .merchant_domain}'

# Register a feed that refreshes every 24 hours.
elixa feeds add https://mystore.com/products.xml --schedule-hours 24

# Top 20 queries over the last 7 days.
elixa analytics queries --days 7 --limit 20

# Grant a CI job read-only search access.
elixa keys create "ci-search" --scope search:read
```

---

## License

MIT © 2026 Fawaaz Abbas. See [LICENSE](./LICENSE).
