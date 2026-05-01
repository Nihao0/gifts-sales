# Attribute Report Design

Date: 2026-05-01

## Goal

Make the Portals portfolio report understandable as a sale-research tool.

The user wants to answer: "Which gifts in this profile can probably be sold for
the most, and why?"

The report must start from the profile inventory, not from broad market scraping.
It should show all relevant local gifts where we have market data, explain which
attribute created the price signal, and avoid implying that a single attribute
floor is a guaranteed exact sale price.

## Selected Approach

Use the "clear valuation report" approach.

For each local gift, show:

- local gift id;
- collection title;
- slug/number;
- model;
- backdrop;
- symbol;
- collection floor;
- model floor;
- symbol floor;
- backdrop floor;
- best signal;
- confidence;
- suggested action.

The terminal view should stay compact and sorted by best signal descending. A
future export option can include the full inventory in CSV/JSON.

## Meaning Of The Report

The report is not a final listing engine. It is a research ranking.

Examples:

- If `symbol floor = 450 TON`, that means the gift has a symbol whose current
  Portals floor is high.
- It does not prove the exact gift combination will sell for 450 TON.
- The next step for high-value candidates is exact listing search and then user
  approval.

## Confidence Rules

Initial confidence is deliberately conservative:

- `high`: model floor exists and is the best signal, or multiple attribute floors
  point in the same direction.
- `medium`: symbol floor or backdrop floor is the best signal, because these can
  indicate value but may overstate exact gift value.
- `low`: only collection floor exists.
- `unknown`: no Portals data is available yet.

## Telegram Internal Market

Do not forget the internal Telegram market.

This implementation improves the Portals report only, but the data model and
report language should leave room for a second pricing source:

- Telegram internal market floor/listing price;
- Telegram resale/listing options for exact gifts where MTProto supports it;
- comparison between Portals signal and Telegram internal market signal.

The future final candidate report should combine both markets before suggesting
sale actions.

## Implementation Scope

In this step:

1. Improve `markets portals portfolio-report`.
2. Add separate collection/model/symbol/backdrop floor columns.
3. Add confidence and suggested action.
4. Keep sorting by best floor signal descending.
5. Keep current Portals sync behavior unchanged unless a small helper is needed.
6. Add tests for floor matching, confidence, and report row construction.

Out of scope for this step:

- exact Portals listing search;
- Telegram internal market connector;
- automatic listing or transfer execution;
- UI/bot layer.

## Success Criteria

- User can read the report and understand why a gift is ranked.
- Report no longer hides the difference between collection, model, symbol, and
  backdrop floors.
- High-value rows clearly say that exact listing verification is needed.
- Existing tests pass.
