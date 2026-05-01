# Gifts Sales Work Context

Last updated: 2026-04-30

This file captures the current project state, decisions, shipped work, open gaps, and next direction so future sessions can resume quickly.

## Product Direction

The project is a Telegram gifts automation and research tool.

Current core idea:

1. Scan gifts from a Telegram account/profile into a local SQLite inventory.
2. Analyze gifts locally.
3. Compare each gift/model against marketplace data, starting with Portals floors.
4. Generate proposed actions.
5. Route risky/write actions through approvals.
6. Execute approved actions through single-writer queues.

Target near-term workflow:

```bash
gifts-sales gifts scan
gifts-sales gifts export --output data/gifts.csv
gifts-sales markets portals floors --from-local
gifts-sales gifts plan-portals --policy-file rules/portals_policy.yaml --create-approvals
gifts-sales approvals list --status pending
gifts-sales approvals approve --id 1
gifts-sales approvals run-approved
```

User's preferred Portals vision:

- Scan gifts in the user's Telegram profile.
- For each owned gift, scan Portals floor prices by concrete collection/model/attributes.
- Use that data to propose or automatically create sale/listing actions.
- Use a bot/approval layer for confirmation before write actions.

## Important Distinction

There are three different execution domains:

1. Telegram/off-chain MTProto:
   - scan saved/profile gifts;
   - transfer gifts;
   - Telegram internal marketplace listing/delisting.

2. Portals/off-chain Telegram Mini App/private API:
   - floors;
   - market activity;
   - Portals owned gifts;
   - Portals sale/buy/offers.

3. GetGems/on-chain TON:
   - wallet NFTs;
   - sale contracts;
   - wallet signing;
   - future agentic wallet flow.

Do not mix their executors. Keep approvals shared, but execution separate.

## Implemented So Far

### Inventory

Commands:

```bash
gifts-sales gifts scan
gifts-sales gifts scan --peer @some_profile
gifts-sales gifts list-local
gifts-sales gifts list-local --owner-peer @some_profile
gifts-sales gifts export --output data/gifts.csv --format csv
gifts-sales gifts export --output data/gifts.json --format json
```

Notes:

- `owner_peer=self` means gifts scanned from the current account.
- `owner_peer=@username` means visible gifts scanned from another profile via `--peer`.
- Gifts scanned through `--peer` are analysis/export only; listing/transfer is blocked for non-`self` gifts.
- Transferred gifts are hidden from list/export by default unless `--include-transferred` is passed.

### Telegram Listing/Delisting

Commands:

```bash
gifts-sales gifts list --gift-id 3 --price-ton 10.0 --dry-run
gifts-sales gifts list --gift-id 3 --price-ton 10.0
gifts-sales gifts delist --gift-id 3 --dry-run
gifts-sales gifts delist --gift-id 3
```

Safety:

- Real listing/delisting goes through `JobQueueService`.
- `dry-run` does not call Telegram and does not mutate sale state.
- `TON_TO_STARS_RATE` is required for real listing when `REQUIRE_TON_RATE_FOR_SALES=true`.
- Optional caps:
  - `MAX_PRICE_TON`
  - `MAX_BULK_JOBS`

### Transfer / Portals Recipient

Commands:

```bash
gifts-sales gifts transfer --gift-id 3 --to @recipient --dry-run
gifts-sales gifts transfer --gift-id 3 --to @recipient
gifts-sales gifts send-to-portals --gift-id 3 --dry-run
gifts-sales gifts send-to-portals --gift-id 3
```

Notes:

- `send-to-portals` uses `PORTALS_RECIPIENT` unless `--to` is provided.
- Transfer uses Telegram `payments.transferStarGift`.
- Telegram only allows direct transfer when it is free; if a paid transfer flow is required, Telegram may return `PAYMENT_REQUIRED`.
- Paid transfer checkout is not automated yet.

### Job Queue

Commands:

```bash
gifts-sales jobs list
gifts-sales jobs list --status pending
gifts-sales jobs retry --job-id 7
gifts-sales jobs retry-failed
gifts-sales jobs run
```

Notes:

- Single-writer queue handles real Telegram write operations.
- It creates fresh DB session-bound services per job.
- It handles retries and `FLOOD_WAIT` scheduling.

### Approval Pipeline

Commands:

```bash
gifts-sales gifts plan-portals --policy-file rules/portals_policy.yaml --to @portals
gifts-sales gifts plan-portals --policy-file rules/portals_policy.yaml --to @portals --create-approvals
gifts-sales approvals list
gifts-sales approvals list --status pending
gifts-sales approvals approve --id 1
gifts-sales approvals reject --id 2
gifts-sales approvals run-approved
```

Current behavior:

- `plan-portals` selects local gifts using `rules/portals_policy.yaml`.
- It creates approval requests for candidate Portals transfers.
- Auto-approval is supported by policy, but default policy is conservative.
- `approvals run-approved` creates transfer jobs and processes them through the queue.

Optional notification:

- If `BOT_TOKEN` and `APPROVAL_CHAT_ID` are set, pending approval requests are sent to Telegram as text notifications.
- Inline approve/reject buttons are not implemented yet.

### Portals Market Research

Commands:

```bash
gifts-sales markets portals auth --write-env
gifts-sales markets portals search --gift-name "Toy Bear"
gifts-sales markets portals search --gift-name "Toy Bear" --save
gifts-sales markets portals floors --save
gifts-sales markets portals filter-floors --gift-name "Toy Bear" --save
gifts-sales markets portals sync-floors --from-local
```

Notes:

- This connector is read-only.
- It uses `PORTALS_AUTH_DATA`, the full Telegram Mini App auth header value including `tma `.
- It stores snapshots in `market_floors` and `market_listings`.
- It is based on observed Portals private API behavior from the community wrapper `bleach-hub/portalsmp`.
- Write actions are intentionally not implemented yet.

### Policy File

Current example:

[rules/portals_policy.yaml](/Users/sega/gifts%20sales/rules/portals_policy.yaml)

It controls:

- recipient;
- auto approval;
- max requests per plan;
- match criteria;
- manual approval triggers.

### Market Research Notes

Research file:

[docs/markets-research.md](/Users/sega/gifts%20sales/docs/markets-research.md)

Current findings:

#### Portals

- No official public developer API docs found.
- Community wrapper exists: `bleach-hub/portalsmp`.
- It supports search, floors, owned Portals gifts, sale, bulk list, buy, offers, withdraw.
- It uses Telegram Mini App auth data (`Authorization: tma ...`).
- Treat as private/unstable API.
- Recommended next step: read-only Portals connector first.

#### GetGems

- On-chain TON marketplace.
- No official REST API for listing found.
- Selling requires wallet-signed blockchain transaction.
- GetGems smart contracts are public in `getgems-io/nft-contracts`.
- Known marketplace fee is 5%.
- Recommended next step: read-only on-chain connector and transaction planner; manual TonConnect signing first.

## Key Files

CLI:

- [app/cli/gifts.py](/Users/sega/gifts%20sales/app/cli/gifts.py)
- [app/cli/jobs.py](/Users/sega/gifts%20sales/app/cli/jobs.py)
- [app/cli/approvals.py](/Users/sega/gifts%20sales/app/cli/approvals.py)
- [app/cli/markets.py](/Users/sega/gifts%20sales/app/cli/markets.py)

Services:

- [app/services/inventory.py](/Users/sega/gifts%20sales/app/services/inventory.py)
- [app/services/listing.py](/Users/sega/gifts%20sales/app/services/listing.py)
- [app/services/transfer.py](/Users/sega/gifts%20sales/app/services/transfer.py)
- [app/services/job_queue.py](/Users/sega/gifts%20sales/app/services/job_queue.py)
- [app/services/approval_notifier.py](/Users/sega/gifts%20sales/app/services/approval_notifier.py)
- [app/markets/portals.py](/Users/sega/gifts%20sales/app/markets/portals.py)

Rules/policy:

- [app/rules/loader.py](/Users/sega/gifts%20sales/app/rules/loader.py)
- [app/rules/policy.py](/Users/sega/gifts%20sales/app/rules/policy.py)
- [rules/example_rules.yaml](/Users/sega/gifts%20sales/rules/example_rules.yaml)
- [rules/portals_policy.yaml](/Users/sega/gifts%20sales/rules/portals_policy.yaml)

Models/storage:

- [app/models/gift.py](/Users/sega/gifts%20sales/app/models/gift.py)
- [app/models/job.py](/Users/sega/gifts%20sales/app/models/job.py)
- [app/models/approval.py](/Users/sega/gifts%20sales/app/models/approval.py)
- [app/models/market.py](/Users/sega/gifts%20sales/app/models/market.py)
- [app/storage/gift_repo.py](/Users/sega/gifts%20sales/app/storage/gift_repo.py)
- [app/storage/job_repo.py](/Users/sega/gifts%20sales/app/storage/job_repo.py)
- [app/storage/approval_repo.py](/Users/sega/gifts%20sales/app/storage/approval_repo.py)
- [app/storage/market_repo.py](/Users/sega/gifts%20sales/app/storage/market_repo.py)

Docs:

- [README.md](/Users/sega/gifts%20sales/README.md)
- [docs/markets-research.md](/Users/sega/gifts%20sales/docs/markets-research.md)

## Environment

Important `.env` keys:

```dotenv
API_ID=
API_HASH=
PHONE=
SESSION_NAME=data/session
DB_URL=sqlite+aiosqlite:///data/gifts.db

PORTALS_RECIPIENT=@portals
PORTALS_AUTH_DATA=tma ...
PORTALS_API_BASE=https://portal-market.com/api
TON_TO_STARS_RATE=100.0
REQUIRE_TON_RATE_FOR_SALES=true
MAX_BULK_JOBS=50
# MAX_PRICE_TON=100.0

# Optional approval notifications
BOT_TOKEN=
APPROVAL_CHAT_ID=
```

Note:

- API credentials are now optional for local planning commands.
- Telegram operations still require `API_ID` and `API_HASH`.

## Current Verification State

Last green checks:

```bash
.venv/bin/python -m ruff check app tests
.venv/bin/python -m pytest tests/ -q
```

Result:

- Ruff: passed.
- Pytest: 61 passed.

CLI smoke that worked:

```bash
gifts-sales gifts plan-portals --policy-file rules/portals_policy.yaml --to @portals
gifts-sales approvals list
```

Because local `data/` is empty and `.env` is absent, plan output currently matches zero gifts.

## What Is Not Done Yet

High priority:

1. Real login and account scan:
   - create `.env`;
   - `gifts-sales auth login`;
   - `gifts-sales gifts scan`;
   - export local inventory.

2. Improve read-only Portals connector:
   - obtain/store real `PORTALS_AUTH_DATA`;
   - validate response shapes against live API;
   - enrich local gifts with Portals model/backdrop/symbol matching;
   - build suggested listing prices from stored floors.

3. Match local gifts to Portals floor data:
   - enrich local gift model with attributes if available in raw JSON;
   - map Telegram gift names/models to Portals query fields;
   - compute suggested listing price.

4. Approval bot with inline buttons:
   - Bot API webhook/polling command handler;
   - `Approve` / `Reject` buttons;
   - update `approval_requests` status.

Medium priority:

5. Portals write executor:
   - list;
   - change price;
   - cancel listing;
   - buy.
   All behind approvals.

6. Market research service:
   - normalized market snapshots;
   - floors;
   - spreads;
   - history;
   - suggested actions.

7. GetGems read-only connector:
   - wallet NFTs;
   - TON indexer;
   - GetGems/on-chain sale detection.

Later:

8. GetGems transaction planner:
   - fixed-price sale contract plan;
   - fee/gas estimate;
   - TonConnect manual signing.

9. Agentic wallet:
   - separate low-balance wallet;
   - policy-limited operations;
   - no autonomous spending until approvals are proven.

## Suggested Next Implementation Plan

Next session should probably start with Portals read-only connector.

Proposed steps:

1. Add config:
   - `PORTALS_AUTH_DATA`
   - `PORTALS_API_BASE`
   - `PORTALS_READ_ONLY=true`

2. Add `app/markets/portals.py`:
   - `search(...)`
   - `gifts_floors()`
   - `filter_floors(gift_name)`
   - `market_activity(...)`

3. Add `app/models/market.py`:
   - `MarketObservation`
   - `MarketFloor`

4. Add CLI:

```bash
gifts-sales markets portals search --gift-name "Toy Bear"
gifts-sales markets portals floors --gift-name "Toy Bear"
gifts-sales markets portals sync-floors --from-local
```

5. Add matching:

```bash
gifts-sales gifts enrich-portals-floors
gifts-sales gifts plan-portals-listing --policy-file rules/portals_listing_policy.yaml
```

6. Keep all Portals write actions disabled until read-only behavior is stable.

## Cautions

- Portals API is not official. Treat it as private, unstable, and account-risky.
- Any buy/list/change-price action must go through approval requests.
- GetGems is on-chain; never put private keys into this app until a separate wallet/agentic-wallet design is approved.
- Do not automate paid transfer flows without explicit confirmation.

## 2026-05-01 Live Portals/Profile Test

Current Telegram session:
- Logged in with the local Telethon session.
- Used `@segamegahigh` as the visible profile to scan.

What worked:
- `gifts-sales gifts scan --peer @segamegahigh` fetched 2686 visible gifts.
- The first scan exposed a bug: visible profile gifts can arrive without `saved_id`/`msg_id`, so all rows collapsed into `@segamegahigh:0`.
- Fixed the local identity fallback to use `visible:{index}:{gift_id}:{date}` when Telegram does not provide a saved/message id.
- Re-scanned and cleaned the stale `@segamegahigh:0` artifact. Local DB now has 2686 distinct rows for `@segamegahigh`.
- 2027 of those rows have collection titles and can be mapped to Portals-style collection names.
- Portals live `collections/filters?short_names=...` currently returns `collections -> <short_name> -> models/backdrops/symbols`; parser now supports that shape.
- `markets portals filter-floors --gift-name "Toy Bear"` returned 394 attribute floor rows.
- `markets portals sync-floors --from-local --owner-peer @segamegahigh --limit 5` saved 1799 floor rows for 5 local collections.
- Added `markets portals portfolio-report --owner-peer @segamegahigh --limit 15`; first run found 208 local gifts with saved Portals attribute-floor matches.

Important interpretation:
- `portfolio-report` is a research ranking, not a final pricing engine.
- It ranks by the highest matching attribute floor among model/backdrop/symbol. A high symbol floor can be a useful signal, but it does not guarantee the exact combined gift will sell at that price.
- Next pricing step should combine exact listing search where possible, collection floor, model floor, symbol floor, backdrop floor, rarity/supply, and manual approval thresholds.
