# Market Operations Guide

Last updated: 2026-05-01

This guide is for a future agent or developer who needs to continue work without
reading the entire chat history. It explains how this project currently works
with Telegram gifts, Telegram internal market, and Portals.

## Core Rule

Separate research from execution.

Research commands can scan profiles and market data. Execution commands transfer
or list gifts and must stay behind dry-run, approvals, and the single-writer job
queue.

## Local Data And Ownership

Local DB:

- `data/gifts.db`

Main tables:

- `gifts` — local inventory and visible-profile scan results.
- `market_floors` — Portals collection/filter hint snapshots.
- `market_listings` — saved market listing snapshots.
- `jobs` — queued write operations.
- `approval_requests` — manual approval layer.

Ownership matters:

- `owner_peer='self'` means the logged-in Telegram account owns the gift.
- `owner_peer='@segamegahigh'` or another username means the gift was scanned
  from a visible profile and is for analysis only.
- Telegram listing/transfer services intentionally refuse non-`self` gifts.
- If a gift was scanned from a different visible profile, this app cannot sell
  or transfer it from the logged-in account unless the gift is actually moved to
  that account.

## Telegram Session And Auth

Check login:

```bash
.venv/bin/gifts-sales auth whoami
```

Login:

```bash
.venv/bin/gifts-sales auth login
```

Important files:

- `.env` contains secrets and is git-ignored.
- `data/session` is the Telethon session and must not be committed.
- `API_ID`, `API_HASH`, `PHONE`, `SESSION_NAME` are needed for Telegram.

## Scan Gifts

Scan current logged-in account:

```bash
.venv/bin/gifts-sales gifts scan
```

Scan visible gifts from another profile:

```bash
.venv/bin/gifts-sales gifts scan --peer @segamegahigh
```

List local gifts:

```bash
.venv/bin/gifts-sales gifts list-local --owner-peer @segamegahigh
.venv/bin/gifts-sales gifts list-local --owner-peer self
```

Export local gifts:

```bash
.venv/bin/gifts-sales gifts export \
  --owner-peer @segamegahigh \
  --output data/segamegahigh_gifts.csv \
  --format csv
```

## Telegram Internal Market

### What Works

Dry-run listing:

```bash
.venv/bin/gifts-sales gifts list \
  --gift-id 123 \
  --price-ton 10 \
  --dry-run
```

Real listing:

```bash
.venv/bin/gifts-sales gifts list \
  --gift-id 123 \
  --price-ton 10
```

Dry-run delist:

```bash
.venv/bin/gifts-sales gifts delist --gift-id 123 --dry-run
```

Real delist:

```bash
.venv/bin/gifts-sales gifts delist --gift-id 123
```

Bulk listing by rule file:

```bash
.venv/bin/gifts-sales gifts bulk-list \
  --rule-file rules/example_rules.yaml \
  --dry-run
```

Real bulk listing:

```bash
.venv/bin/gifts-sales gifts bulk-list \
  --rule-file rules/example_rules.yaml
```

### How It Works

Telegram market listing uses:

- `app/services/listing.py`
- `UpdateStarGiftPriceRequest`
- `InputSavedStarGiftUser(msg_id=gift.msg_id)`
- `StarsAmount`

Price conversion:

- CLI price is in TON.
- Telegram listing request needs Stars.
- `PricingService` converts TON to Stars.
- Be careful with `TON_TO_STARS_RATE` and `REQUIRE_TON_RATE_FOR_SALES`.

Safety:

- Listing refuses gifts where `owner_peer != "self"`.
- Listing needs `gift.msg_id`.
- Run `gifts scan` on the logged-in account before listing.
- Real operations go through the job queue.

Current limitation:

- Telegram internal market price research is not fully implemented.
- `GetStarGiftResaleOptionsRequest` has returned `INPUT_METHOD_INVALID...` in
  some contexts.
- Do not assume Telegram market price data is reliable until this is fixed.

## Portals Auth

Fetch Portals Mini App auth:

```bash
.venv/bin/gifts-sales markets portals auth --write-env
```

Config:

- `PORTALS_API_BASE=https://portal-market.com/api`
- `PORTALS_AUTH_DATA=tma ...`
- `PORTALS_RECIPIENT=...` for transfers.

Do not print or commit `PORTALS_AUTH_DATA`.

## Portals Research

### Collection Floors

Fetch collection floors:

```bash
.venv/bin/gifts-sales markets portals floors --save
```

### Attribute Filter Hints

Fetch model/backdrop/symbol filter hints for one collection:

```bash
.venv/bin/gifts-sales markets portals filter-floors \
  --gift-name "Toy Bear" \
  --save
```

Sync filter hints for all local profile collections:

```bash
.venv/bin/gifts-sales markets portals sync-floors \
  --from-local \
  --owner-peer @segamegahigh \
  --limit 1000 \
  --no-render
```

Important:

- `collections/filters` values are filter hints, not guaranteed listing floors.
- Do not use filter hints as final sale prices.
- Example bug found: `Durov’s Cap / Black` filter hint showed `19.99`, while
  exact listing search showed `60000 TON`.

### Portfolio Report

Show top rows:

```bash
.venv/bin/gifts-sales markets portals portfolio-report \
  --owner-peer @segamegahigh \
  --limit 25
```

Export full profile report:

```bash
.venv/bin/gifts-sales markets portals portfolio-report \
  --owner-peer @segamegahigh \
  --include-unmatched \
  --output data/segamegahigh_portals_report.csv \
  --format csv
```

Meaning:

- `Filter Hints TON C / M / S / B` means collection/model/symbol/backdrop hints.
- `Best Hint` is only a research signal.
- `Next = verify exact listing` means do not sell until exact listing search is
  done.

## Portals Exact Listing Search

Use exact listing search for sale decisions.

Example:

```bash
.venv/bin/gifts-sales markets portals search \
  --gift-name "Durov’s Cap" \
  --backdrop Black \
  --sort price_asc \
  --limit 5
```

Known result from live test:

- `Durov’s Cap + Black` returned one listing at `60000 TON`.

Implementation detail:

- `nfts/search` must use `collection_ids`, not `filter_by_collections`.
- `PortalsClient.search()` now resolves collection ids through `/collections`.
- If this regresses, exact search may return unrelated gifts.

Next needed command:

```bash
.venv/bin/gifts-sales research verify-portals-listings \
  --owner-peer @segamegahigh
```

This command does not exist yet. It should:

- iterate through sale candidates or all local collections;
- run exact Portals search using collection id + available attributes;
- store exact listing snapshots separately from filter hints;
- mark match strength:
  - collection only;
  - model only;
  - symbol only;
  - backdrop only;
  - model + symbol + backdrop.

## Portals Transfer

### What Works

Dry-run transfer to explicit peer:

```bash
.venv/bin/gifts-sales gifts transfer \
  --gift-id 123 \
  --to @some_recipient \
  --dry-run
```

Real transfer:

```bash
.venv/bin/gifts-sales gifts transfer \
  --gift-id 123 \
  --to @some_recipient
```

Dry-run send to configured Portals recipient:

```bash
.venv/bin/gifts-sales gifts send-to-portals \
  --gift-id 123 \
  --dry-run
```

Real send to configured Portals recipient:

```bash
.venv/bin/gifts-sales gifts send-to-portals \
  --gift-id 123
```

### How It Works

Portals transfer currently uses Telegram gift transfer:

- `app/services/transfer.py`
- `TransferStarGiftRequest`
- `InputSavedStarGiftUser(msg_id=gift.msg_id)`
- destination peer from CLI or `PORTALS_RECIPIENT`.

Safety:

- Transfer refuses gifts where `owner_peer != "self"`.
- Transfer needs `gift.msg_id`.
- Dry-run first.
- Real operation goes through job queue.
- Local gift is marked transferred only after Telegram request succeeds.

### What Is Not Proven Yet

Full flow not yet proven:

1. Transfer gift to Portals recipient.
2. Confirm it appears in Portals UI/account.
3. List it on Portals.
4. Confirm listing status and price.

Portals listing executor is not implemented yet.

## Approval Workflow

Portals transfer planning:

```bash
.venv/bin/gifts-sales gifts plan-portals \
  --policy-file rules/portals_policy.yaml
```

Create approvals:

```bash
.venv/bin/gifts-sales gifts plan-portals \
  --policy-file rules/portals_policy.yaml \
  --create-approvals
```

Review:

```bash
.venv/bin/gifts-sales approvals list --status pending
.venv/bin/gifts-sales approvals approve --id 1
.venv/bin/gifts-sales approvals reject --id 2
```

Run approved:

```bash
.venv/bin/gifts-sales approvals run-approved
```

Use approvals for any bulk transfer/listing workflow.

## Recommended Next Work

Priority 1: exact Portals listing verification.

- Add a command that verifies exact listings for all candidate gifts.
- Store exact listing prices separately from filter hints.
- Update reports to show exact listing floor next to filter hints.

Priority 2: bulk execution from sale candidates.

- Generate candidate file.
- Create Telegram listing approvals for `self` gifts.
- Create Portals transfer approvals for gifts that should go to Portals.
- Execute through job queue.

Priority 3: Portals arrival/listing workflow.

- After transfer, detect gift in Portals.
- Then create Portals listing plan.
- Keep Portals write actions behind approvals.

## Do Not Do Yet

- Do not treat filter hints as final prices.
- Do not automate buys.
- Do not automate paid transfer checkout.
- Do not transfer/list gifts from visible profiles unless they are owned by
  `self`.
- Do not commit `.env`, sessions, auth data, or generated `data/*.csv` files.
