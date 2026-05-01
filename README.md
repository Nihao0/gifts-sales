# gifts-sales

Production-minded MVP Telegram userbot for listing collectible gifts on Telegram's internal gift marketplace for TON.

## Features

- **MTProto user session** via Telethon (not Bot API)
- **Scan** all owned collectible gifts and persist locally (SQLite)
- **List** a gift for sale at a given TON price
- **Delist** a gift from sale
- **Bulk listing** via YAML rule files
- **Dry-run mode** for all write operations
- **Single-writer job queue** — no concurrent MTProto writes
- **Local collection database** for analysis, filtering, export, and sale planning
- **Transfer gifts to another Telegram peer** (including a configured Portals recipient)
- **FLOOD_WAIT handling** — schedules retry instead of blocking
- **Idempotency** — no duplicate jobs, no redundant API calls
- **Structured logging** (JSON or console)
- **CLI** powered by Typer

## Current checkpoint

Start future sessions with [`docs/project-checkpoint.md`](docs/project-checkpoint.md).
It summarizes the live `@segamegahigh` scan, Portals floor research, current
limits, and the next implementation plan.

## Requirements

- Python 3.12+
- A Telegram account with collectible gifts
- Telegram API credentials from [my.telegram.org/apps](https://my.telegram.org/apps)

## Setup

```bash
# Clone / enter the project directory
cd "gifts sales"

# Create and activate a virtualenv
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Copy and fill in the config
cp .env.example .env
$EDITOR .env
```

### `.env` essentials

```dotenv
API_ID=12345678
API_HASH=your_api_hash_here
PHONE=+79001234567
LOG_FORMAT=console      # "console" for human-readable output
```

## Authentication

```bash
# First-time login — saves a Telethon session file in data/
gifts-sales auth login

# Check who is logged in
gifts-sales auth whoami
```

## Usage

### Scan gifts from Telegram

```bash
gifts-sales gifts scan

# Scan visible gifts from another profile using the currently logged-in session
gifts-sales gifts scan --peer @some_profile
```

### List all locally stored gifts

```bash
gifts-sales gifts list-local

# Study a subset
gifts-sales gifts list-local --not-for-sale
gifts-sales gifts list-local --title-contains Rocket
gifts-sales gifts list-local --collectible-id 7261748364
gifts-sales gifts list-local --owner-peer @some_profile
```

### Export gifts for analysis

```bash
gifts-sales gifts export --output data/gifts.csv --format csv
gifts-sales gifts export --output data/gifts.json --format json
gifts-sales gifts export --owner-peer @some_profile --output data/profile_gifts.csv
```

By default, transferred-out gifts are hidden from `list-local` and `export`.
Pass `--include-transferred` to include them.

Gifts scanned with `--peer` are for analysis/export only. Telegram will not let
the current account sell or transfer gifts owned by a different account.

### Research Portals floors

```bash
# Fetch collection-level Portals floors
gifts-sales markets portals floors --save

# Fetch model/backdrop/symbol floors for one collection
gifts-sales markets portals filter-floors --gift-name "Toy Bear" --save

# Sync attribute floors for local gifts from a scanned profile
gifts-sales markets portals sync-floors --from-local --owner-peer @some_profile --limit 1000

# Rank local gifts by saved Portals attribute-floor signals
gifts-sales markets portals portfolio-report --owner-peer @some_profile --limit 25

# Export every local gift, including gifts without saved Portals market data
gifts-sales markets portals portfolio-report \
  --owner-peer @some_profile \
  --include-unmatched \
  --output data/profile_portals_report.csv \
  --format csv
```

Portals floor signals are research data, not automatic listing prices. The
attribute report shows collection/model/symbol/backdrop floors separately,
marks the strongest signal, and gives a conservative next action. Telegram
internal market prices still need to be checked before final sale decisions.

### Show details for a specific gift

```bash
gifts-sales gifts show --gift-id 3
```

### List a gift for sale

```bash
# Dry-run first
gifts-sales gifts list --gift-id 3 --price-ton 10.0 --dry-run

# Actual listing
gifts-sales gifts list --gift-id 3 --price-ton 10.0
```

### Delist a gift

```bash
gifts-sales gifts delist --gift-id 3 --dry-run
gifts-sales gifts delist --gift-id 3
```

### Transfer a gift to Portals

```bash
# Preview first
gifts-sales gifts send-to-portals --gift-id 3 --dry-run

# Actual transfer, using PORTALS_RECIPIENT from .env
gifts-sales gifts send-to-portals --gift-id 3

# Or transfer to an explicit recipient
gifts-sales gifts transfer --gift-id 3 --to @some_recipient --dry-run
gifts-sales gifts transfer --gift-id 3 --to @some_recipient
```

Telegram only allows direct `payments.transferStarGift` when the transfer is
free. If Telegram requires a paid transfer flow, the job will fail with
`PAYMENT_REQUIRED`; paid transfer checkout is intentionally not automated yet.

### Approval-based Portals automation

```bash
# Preview candidates using a conservative policy
gifts-sales gifts plan-portals --policy-file rules/portals_policy.yaml

# Persist approval requests
gifts-sales gifts plan-portals --policy-file rules/portals_policy.yaml --create-approvals

# Review and approve
gifts-sales approvals list --status pending
gifts-sales approvals approve --id 1
gifts-sales approvals reject --id 2

# Execute approved requests through the single-writer queue
gifts-sales approvals run-approved
```

If `BOT_TOKEN` and `APPROVAL_CHAT_ID` are set, newly-created pending approval
requests are also sent to Telegram as notification messages. Approval still
happens through the CLI in this MVP; inline bot buttons can be added next.

### Portals market research

Portals market commands are read-only and use Telegram Mini App auth data.
Set `PORTALS_AUTH_DATA` first.

```bash
# Fetch Portals auth data from the logged-in Telegram user session
gifts-sales markets portals auth --write-env

# Search current listings
gifts-sales markets portals search --gift-name "Toy Bear"

# Fetch collection floors
gifts-sales markets portals floors --save

# Fetch model/backdrop/symbol floors for one collection
gifts-sales markets portals filter-floors --gift-name "Toy Bear" --save

# Fetch attribute floors for unique local gift titles
gifts-sales markets portals sync-floors --from-local
```

This is intentionally read-only. Portals write actions such as list/buy/change
price should be added later as a separate executor behind approvals.

### Bulk listing via YAML rules

```bash
# Preview what would happen
gifts-sales gifts bulk-list --rule-file rules/example_rules.yaml --dry-run

# Execute
gifts-sales gifts bulk-list --rule-file rules/example_rules.yaml
```

`bulk-list --dry-run` reads local gifts and rules only: it does not create jobs,
does not update the local DB, and does not call Telegram.

### Job management

```bash
# List all jobs
gifts-sales jobs list

# Filter by status
gifts-sales jobs list --status failed

# Retry a specific job
gifts-sales jobs retry --job-id 7

# Reset all failed jobs
gifts-sales jobs retry-failed

# Run pending jobs that are due now
gifts-sales jobs run
```

## YAML Rule Format

```yaml
rules:
  - name: rare_gifts
    match:
      max_availability_total: 1000   # optional
      is_for_sale: false             # optional
      title_contains: "Rocket"       # optional, case-insensitive
      collectible_id: 123456         # optional, exact match
      min_availability_issued: 10    # optional
      max_availability_issued: 500   # optional
      min_availability_total: 100    # optional
    action: list    # "list" | "delist"
    price_ton: 25.0 # required when action=list
    dry_run: false
    max_attempts: 5
```

All match criteria are AND-combined. The first matching rule per gift wins.

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `API_ID` | — | Telegram API ID |
| `API_HASH` | — | Telegram API hash |
| `PHONE` | — | Phone number with country code |
| `SESSION_NAME` | `data/session` | Telethon session file path |
| `SESSION_PASSWORD` | — | 2FA password (if set) |
| `DB_URL` | `sqlite+aiosqlite:///data/gifts.db` | SQLAlchemy database URL |
| `DRY_RUN` | `false` | Global dry-run toggle |
| `FLOOD_SLEEP_THRESHOLD` | `60` | Max seconds to auto-sleep on FLOOD_WAIT |
| `MAX_JOB_ATTEMPTS` | `5` | Max retry attempts per job |
| `MAX_BULK_JOBS` | `50` | Safety limit for one bulk execution |
| `MAX_PRICE_TON` | — | Optional hard cap for listing prices |
| `PORTALS_RECIPIENT` | — | Default recipient for `gifts send-to-portals` |
| `PORTALS_AUTH_DATA` | — | Telegram Mini App auth header value for Portals read-only API |
| `PORTALS_API_BASE` | `https://portal-market.com/api` | Portals private API base URL |
| `BOT_TOKEN` | — | Optional Telegram Bot API token for approval notifications |
| `APPROVAL_CHAT_ID` | — | Optional chat ID for approval notifications |
| `TON_TO_STARS_RATE` | — | Explicit TON→Stars rate for real listing |
| `REQUIRE_TON_RATE_FOR_SALES` | `true` | Require explicit `TON_TO_STARS_RATE` before real listing |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `json` | `json` or `console` |

## Architecture

```
app/
  cli/          Typer commands (auth, gifts, jobs)
  config/       Pydantic Settings
  client/       Telethon wrapper + hand-written MTProto TLRequests
  models/       SQLAlchemy ORM (Gift, Job)
  schemas/      Pydantic I/O schemas
  services/     Business logic (inventory, listing, transfer, pricing, job queue)
  storage/      Repositories (gifts, jobs, approvals)
  rules/        YAML rule loader and matcher
  storage/      Repository pattern (GiftRepository, JobRepository)
  utils/        Logging, retry scheduling
tests/
  unit/         Pure unit tests (pricing math, rule matching, retry logic, idempotency)
  integration/  DB-backed tests (inventory scan)
```

### Job Queue

All real write operations (list/delist/transfer) go through a single-writer `asyncio.Queue`. This prevents concurrent MTProto calls on the same account.

FLOOD_WAIT above `FLOOD_SLEEP_THRESHOLD` is not slept — instead, `jobs.retry_after` is set in the DB and the job is re-enqueued on next startup or `jobs retry-failed`.

Dry-runs are previews: they do not call Telegram and do not mutate local gift sale state.

## Running Tests

```bash
pytest tests/ -v
```

## Extending

### Future GetGems integration

`PricingService` accepts an optional `market_provider` implementing:

```python
class MarketProvider(Protocol):
    async def get_stars_per_ton(self) -> float: ...
```

Inject a `GetGemsProvider` to override live rate fetching.

## License

MIT
