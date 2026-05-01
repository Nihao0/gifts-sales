# Project Checkpoint

Last updated: 2026-05-01

This file is the short re-entry point for the project. Read it first in a new
session before opening the longer notes in `docs/work-context.md`.

## Project Goal

Build a Telegram collectible-gifts sales assistant.

Target flow:

1. Scan gifts visible in a Telegram profile.
2. Determine which gift collections and concrete attributes actually exist in
   that profile.
3. Fetch market data only for those relevant gifts:
   - Portals floors and listings;
   - Telegram internal marketplace prices;
   - later GetGems/on-chain data.
4. Rank possible sale candidates.
5. Ask the user for approval.
6. Send/list/sell through the right market executor.
7. Eventually expose this through a user-friendly Telegram bot or small web UI.

## Current Repository

- Local path: `/Users/sega/gifts sales`
- GitHub: `https://github.com/Nihao0/gifts-sales`
- Branch: `main`
- Latest pushed checkpoint before this note: `1d1f232`
- Runtime: Python 3.12, Typer CLI, Telethon, SQLAlchemy async, SQLite.
- Local DB: `data/gifts.db`
- Telegram session: `data/session`

Secrets are intentionally not documented here. They live in local `.env`, which
is ignored by git.

## What Already Works

Telegram/account:

- Telegram login via Telethon works.
- Current local session successfully connected and scanned profiles.
- The session can request Portals Mini App auth data and save it to `.env`.

Gift inventory:

- `gifts-sales gifts scan` scans the logged-in account.
- `gifts-sales gifts scan --peer @some_profile` scans visible gifts from another
  profile using the logged-in session.
- `gifts-sales gifts list-local --owner-peer @some_profile` filters stored gifts
  by profile owner.
- `gifts-sales gifts export --owner-peer @some_profile ...` exports profile data.

Portals research:

- `gifts-sales markets portals auth --write-env` fetches Mini App auth.
- `gifts-sales markets portals floors --save` fetches collection floors.
- `gifts-sales markets portals filter-floors --gift-name "Toy Bear" --save`
  fetches model/backdrop/symbol floors for a collection.
- `gifts-sales markets portals sync-floors --from-local --owner-peer @profile`
  fetches floors only for collection titles that already exist locally.
- `gifts-sales markets portals portfolio-report --owner-peer @profile` ranks
  local gifts by saved Portals attribute-floor signals and explains collection,
  model, symbol, and backdrop floors separately.
- `portfolio-report --include-unmatched --output ...` exports every local gift,
  including gifts that do not yet have saved Portals market data.

Write operations:

- Telegram internal list/delist exists.
- Transfer to a configured Portals recipient exists for free transfer flows.
- Paid checkout flows are intentionally not automated yet.
- Approval request infrastructure exists and should remain the gate for
  risky/paid/write actions.

## Live Test Results

Target profile used for collection:

- `@segamegahigh`

Scan result:

- Command: `gifts-sales gifts scan --peer @segamegahigh`
- Result: `2686` visible gifts fetched and stored.
- After cleanup, local DB contains `2686` distinct rows for
  `owner_peer='@segamegahigh'`.
- `2027` rows have collection titles.
- `2025` rows have slugs.

Important bug found and fixed:

- Visible-profile gifts can arrive without `saved_id` and `msg_id`.
- Old logic used `@segamegahigh:0`, causing thousands of gifts to collapse into
  one DB row.
- Fixed fallback identity:
  `owner_peer:visible:{index}:{gift_id}:{date}`.

Portals live API behavior:

- Working base URL: `https://portal-market.com/api`
- Current `collections/filters` response shape:
  `collections -> <short_name> -> models/backdrops/symbols`.
- Parser supports both this live shape and older `floor_prices`/`floorPrices`
  shapes.

Portals checks:

- `filter-floors --gift-name "Toy Bear"` returned `394` attribute floors.
- `sync-floors --from-local --owner-peer @segamegahigh --limit 5` saved `1799`
  floor rows.
- The first `portfolio-report --owner-peer @segamegahigh --limit 15` found
  `208` matched local gifts using the saved floor data.
- The improved report can export all `2686` profile gifts with
  `--include-unmatched --output data/segamegahigh_portals_report.csv`.
- Full profile Portals sync later requested all `82` local collection titles,
  received attribute floors for `81` collections, and saved `26255` floor rows.
- After the full sync, `data/segamegahigh_portals_report.csv` contained:
  - `2686` total local gift rows;
  - `2025` rows with a Portals best-floor signal;
  - `1582` high-confidence rows;
  - `424` medium-confidence rows;
  - `19` low-confidence rows;
  - `661` unknown rows, mostly gifts without Telegram title metadata.
- Important correction: Portals `collections/filters` values are attribute
  filter hints, not guaranteed exact sale/listing floors. Example:
  `Durov’s Cap / Black` appeared as `19.99` in filters, but exact listing search
  with `collection_ids` returned the real listed floor of `60000 TON`.
- `nfts/search` must use Portals collection ids (`collection_ids=...`), not the
  older `filter_by_collections` parameter. The client now resolves collection ids
  via `/collections` before exact listing search.

Verification:

- `ruff check app tests` passes.
- `pytest -q` passes with `69 passed`.

## Important Product Decision

The correct market-research strategy is profile-first, not market-first.

Do not scrape every market broadly as the default workflow. First scan the
profile and build the list of actual collections and attributes present. Then
fetch only the market data needed for those gifts.

Recommended pipeline:

1. Scan profile.
2. Extract unique gift collections.
3. Extract exact attributes from Telegram raw JSON:
   - model from `StarGiftAttributeModel`;
   - backdrop from `StarGiftAttributeBackdrop`;
   - symbol/pattern from `StarGiftAttributePattern`.
4. Fetch Portals data for only those collections.
5. Fetch Telegram internal market data for only those collections or collectible
   IDs where the API supports it.
6. Match each local gift to:
   - collection floor;
   - model floor;
   - symbol floor;
   - backdrop floor;
   - exact listing prices if available.
7. Produce a candidate list with confidence and reason.
8. Require user approval before transfer/listing/sale.

## Current Commands To Resume Work

Scan profile:

```bash
.venv/bin/gifts-sales gifts scan --peer @segamegahigh
```

Sync a small Portals sample:

```bash
.venv/bin/gifts-sales markets portals sync-floors \
  --from-local \
  --owner-peer @segamegahigh \
  --limit 5
```

Sync all local profile collections:

```bash
.venv/bin/gifts-sales markets portals sync-floors \
  --from-local \
  --owner-peer @segamegahigh \
  --limit 1000 \
  --no-render
```

Show ranked report:

```bash
.venv/bin/gifts-sales markets portals portfolio-report \
  --owner-peer @segamegahigh \
  --limit 25
```

Export every profile gift, including rows where market data has not been synced:

```bash
.venv/bin/gifts-sales markets portals portfolio-report \
  --owner-peer @segamegahigh \
  --include-unmatched \
  --output data/segamegahigh_portals_report.csv \
  --format csv
```

Run checks:

```bash
.venv/bin/ruff check app tests
.venv/bin/pytest -q
```

## Current Limitation Of The Report

`portfolio-report` is only a research signal.

It now shows collection/model/symbol/backdrop filter hints separately and then
marks the strongest saved hint. A high symbol/model/backdrop hint can indicate
value, but it is not the same as an exact listed price for the full combination
of model + backdrop + symbol.

Before listing, the pricing engine should combine:

- exact Portals listings for the same gift if available;
- collection floor;
- model floor;
- symbol floor;
- backdrop floor;
- rarity/supply from raw Portals data;
- current Telegram internal marketplace resale options where available;
- user-configured minimum acceptable price;
- approval status.

Concrete example to remember:

```bash
.venv/bin/gifts-sales markets portals search \
  --gift-name "Durov’s Cap" \
  --backdrop Black \
  --sort price_asc \
  --limit 5
```

This returned one exact Portals listing at `60000 TON`, while the filter hint for
the same backdrop was `19.99`. Exact listing search wins for sale decisions.

## Next Implementation Plan

High priority:

1. Add exact Portals listing verification for all profile collections and sale
   candidates:
   - do not limit exact checks to `Durov’s Cap`;
   - iterate through every collection represented in the scanned profile;
   - for each candidate gift, query exact Portals listings with `collection_ids`
     plus available model/backdrop/symbol filters;
   - store exact listing snapshots separately from filter hints;
   - prefer exact listing floor over `collections/filters` hints for any sale
     decision;
   - record whether the exact match was collection-only, model-only,
     backdrop-only, symbol-only, or full model+backdrop+symbol;
   - include exact listing price and confidence in the candidate report.

2. Work on the Portals gift-transfer/listing workflow:
   - confirm the correct Portals recipient/account for transferring gifts;
   - verify the Telegram transfer path for collectible gifts that must move into
     Portals before they appear in the Portals market;
   - keep `send-to-portals --dry-run` as the first step for every gift;
   - after transfer, poll/refresh Portals to detect that the gift appeared in
     the Portals inventory/market tooling;
   - only then create a listing plan with price and approval;
   - do not automate paid transfer checkout until the exact flow and fees are
     understood and explicitly approved.

3. Add a dedicated `research` command group or service layer so the workflow is
   explicit:
   - `research scan-profile --peer @segamegahigh`;
   - `research sync-portals --owner-peer @segamegahigh`;
   - `research verify-portals-listings --owner-peer @segamegahigh`;
   - `research sync-telegram-market --owner-peer @segamegahigh`;
   - `research report --owner-peer @segamegahigh`.

4. Improve Portals sync so it defaults to relevant local profile gifts:
   - avoid broad market scans;
   - dedupe collection names;
   - store one latest snapshot per collection/attribute where possible;
   - make terminal output compact by default.

5. Add a pricing/candidate table or view:
   - local gift id;
   - owner peer;
   - title;
   - slug;
   - model/backdrop/symbol;
   - best filter hint;
   - exact Portals listing floor;
   - Telegram internal market floor;
   - confidence;
   - suggested listing price;
   - suggested destination market;
   - transfer/listing status;
   - reason.

6. Add Telegram internal marketplace research:
   - inspect which MTProto methods can return resale/listing options for the
     exact local gifts;
   - handle current `INPUT_METHOD_INVALID...` error gracefully;
   - persist useful internal-market snapshots.

7. Add approval-first sell workflow:
   - plan candidates;
   - create approval requests;
   - user approves manually;
   - executor transfers/lists only approved items;
   - record transfer result and listing result separately.

Keep the sale path in mind while improving research: every report row should
eventually be convertible into a sale candidate with exact listing verification,
suggested price, market destination, and approval status.

Medium priority:

6. Build a user layer:
   - Telegram bot is likely the fastest first UI;
   - commands/buttons: refresh profile, refresh market data, show top, approve,
     reject, send to Portals, list on Telegram;
   - later a small web dashboard can be added for dense portfolio tables.

7. Add exact Portals listing search for selected candidates:
   - use collection + model + backdrop + symbol where endpoint supports it;
   - store listings separately from floors;
   - compare exact listing floor against attribute-only floor.

8. Add safety policies:
   - max number of actions per run;
   - min price;
   - never buy automatically;
   - never use paid transfer checkout without explicit approval;
   - keep write operations behind a single queue.

Later:

9. Research GetGems/on-chain:
   - wallet NFT discovery;
   - GetGems API/indexer behavior;
   - fixed-price sale contract flow;
   - TonConnect/manual signing;
   - isolated low-balance agent wallet only after approvals are proven.

## Safety Notes

- Portals API appears private/unstable, so keep connector defensive and
  read-only until the behavior is stable.
- Do not log or commit `.env`, Telegram session files, API hash, phone, or
  Portals auth data.
- Gifts scanned from another profile are for analysis. The logged-in account
  cannot sell or transfer gifts owned by another account unless those gifts are
  actually moved to it.
- Paid operations must stay approval-gated.
