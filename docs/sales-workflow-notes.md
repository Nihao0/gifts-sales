# Sales Workflow Notes

Last updated: 2026-05-01

This note captures the current thinking about selling and transferring gifts.
The direction is to prioritize reliable execution workflows over endless price
parsing.

## Current State

### Telegram Internal Market

Already implemented:

- `gifts-sales gifts list --gift-id <id> --price-ton <price> --dry-run`
- `gifts-sales gifts list --gift-id <id> --price-ton <price>`
- `gifts-sales gifts delist --gift-id <id> --dry-run`
- `gifts-sales gifts delist --gift-id <id>`
- `gifts-sales gifts bulk-list --rule-file ... --dry-run`
- `gifts-sales gifts bulk-list --rule-file ...`
- Single-writer job queue for real write operations.
- Local sale status update after successful listing/delisting.

Current limitations:

- Listing only works for gifts owned by the logged-in account:
  `owner_peer == "self"`.
- Gifts scanned from `@segamegahigh` are visible-profile analysis rows. They
  cannot be listed by the logged-in account unless those gifts are actually on
  that account.
- Real listing depends on `msg_id`, so a normal self scan must be current before
  listing.
- TON to Stars conversion still needs careful verification before large real
  sales.
- Bulk listing exists, but it is rule-file based, not yet a polished sale
  candidate workflow with exact market checks and approvals.

### Portals Transfer

Already implemented:

- `gifts-sales gifts transfer --gift-id <id> --to <peer> --dry-run`
- `gifts-sales gifts transfer --gift-id <id> --to <peer>`
- `gifts-sales gifts send-to-portals --gift-id <id> --dry-run`
- `gifts-sales gifts send-to-portals --gift-id <id>`
- `PORTALS_RECIPIENT` config support.
- `gifts-sales gifts plan-portals --policy-file ...`
- Optional approval request creation for planned Portals transfers.

Current limitations:

- This transfers one gift at a time unless routed through approvals/jobs.
- The exact Portals recipient/account must be confirmed before real transfers.
- We have not yet completed a full live flow:
  transfer gift -> gift appears in Portals -> create/list sale in Portals.
- Paid Telegram transfer checkout is intentionally not automated.
- Portals listing/change-price/buy executor is not implemented yet.

## Decision

Focus next on transfer/listing workflows, not broad market scraping.

Price research is still useful, but it should feed execution:

1. Scan profile/account gifts.
2. Build sale candidates.
3. Verify exact listings where needed.
4. Ask for approval.
5. Execute Telegram listing or Portals transfer.
6. Confirm resulting state.

Do not spend the next block building a full Telegram market scraper for every
collection/backdrop/model/symbol if reliable execution is the bottleneck.

## Telegram Market Pricing

Possible but lower priority right now:

- Parse Telegram internal market/resale options for the gifts we actually own.
- Compare Telegram internal price signals against Portals exact listings.
- Use ready-made price services if they are reliable enough.

Reason to postpone:

- We already have enough Portals signal to identify candidates.
- The bigger missing piece is safely moving/listing gifts.
- Exact Telegram market parsing may be API-fragile and time-consuming.

## Next Workflow To Build

### 1. Sale Candidate Planner

Create a command that turns research rows into sale candidates:

```bash
gifts-sales sales plan \
  --owner-peer self \
  --market telegram \
  --min-confidence high \
  --limit 20
```

Output should include:

- gift id;
- title;
- slug;
- model/backdrop/symbol;
- exact Portals listing floor if available;
- Telegram internal market signal if available;
- suggested price;
- destination market;
- required action:
  - list on Telegram;
  - send to Portals;
  - skip;
  - needs exact check.

### 2. Bulk Telegram Listing

Build an approval-first bulk Telegram listing flow:

```bash
gifts-sales sales create-telegram-listings \
  --candidate-file data/candidates.csv \
  --create-approvals
```

Rules:

- dry-run by default while testing;
- max number of gifts per run;
- max/min price constraints;
- skip transferred gifts;
- skip gifts not owned by `self`;
- require approval before real listing.

### 3. Bulk Portals Transfer

Build an approval-first bulk Portals transfer flow:

```bash
gifts-sales sales create-portals-transfers \
  --candidate-file data/candidates.csv \
  --create-approvals
```

Rules:

- use `PORTALS_RECIPIENT` or explicit `--to`;
- dry-run first;
- require approval before transfer;
- mark gifts as transferred locally only after Telegram transfer succeeds;
- after transfer, run a Portals refresh/check step.

### 4. Portals Appearance Check

After sending gifts to Portals, add a check step:

```bash
gifts-sales sales check-portals-arrivals \
  --since-hours 24
```

Goal:

- identify gifts transferred to Portals;
- confirm whether they appear in the Portals account/interface;
- only then prepare Portals listing actions.

## Safety Requirements

- Never sell, transfer, or list without dry-run/approval in early workflows.
- Never automate paid transfer checkout until we understand the exact fee and
  confirmation flow.
- Keep all write operations in the single-writer job queue.
- Log every transfer/listing attempt and result.
- Keep price research separate from execution state.

## Open Questions

- What exact Portals recipient should receive gifts?
- After transfer, how quickly does Portals show the gift?
- Does Portals expose an endpoint for current account inventory?
- Can Portals listing be done through API, bot, or only UI?
- For Telegram market listings, what price source should be trusted first:
  exact Telegram resale options, Portals exact listings, or an external service?
