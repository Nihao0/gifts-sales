# Markets Research: Portals vs GetGems

Date: 2026-04-30

## Summary

There are two different integration classes:

1. Telegram/off-chain gift markets: Portals, Telegram marketplace, MRKT/Tonnel-style markets.
2. TON/on-chain NFT markets: GetGems.

They should not share the same executor. Telegram/off-chain actions use Telegram Mini App auth or MTProto/userbot flows. GetGems actions are TON wallet transactions against marketplace sale contracts.

## Portals

Public official developer documentation was not found. There are community clients for the Portals Marketplace API, notably `bleach-hub/portalsmp`, but this is an unofficial/private-API wrapper.

Observed capabilities from the community wrapper:

- search listed gifts with filters: name, model, backdrop, symbol, price, sort.
- retrieve floors and collection data.
- retrieve owned Portals gifts.
- list a gift for sale.
- bulk list gifts.
- buy a gift.
- make/cancel/edit offers.
- withdraw Portals balance to TON wallet.

Important auth model:

- Portals requests appear to require Telegram Mini App auth data (`Authorization: tma ...`).
- The wrapper documents two ways to obtain auth data:
  - manually from Telegram Web network requests;
  - programmatically via Telegram login/API credentials.

Risk assessment:

- Because this is not an official API contract, endpoints can change without notice.
- It is suitable for a separate experimental connector behind approvals and dry-run.
- It should not be mixed into the current MTProto gift-transfer service until we isolate auth, rate limits, and failure modes.

Recommended MVP:

- Add a read-only Portals market data connector first:
  - search gifts;
  - floors;
  - market activity;
  - my Portals gifts.
- Add write actions only later:
  - list;
  - buy;
  - change price;
  - offers.
- Require approvals for all write actions.

## GetGems

GetGems is on-chain. I did not find an official REST/GraphQL API for listing NFTs for sale. The official/public path is smart contracts and wallet-signed TON transactions.

Reliable public sources:

- GetGems help says selling requires signing in, entering a price, and confirming a blockchain transaction through a crypto wallet. It notes a 5% marketplace commission and recommends keeping around 0.3+ TON available for operations.
- GetGems help links to TON NFT standards and GetGems marketplace smart contracts.
- `getgems-io/nft-contracts` publishes marketplace and sale contracts, including fixed-price sale v4 and auction contracts.

Known contract details from `getgems-io/nft-contracts`:

- Marketplace fee is 5%.
- Marketplace fee address: `EQCjk1hh952vWaE9bRguFkAhDAL5jj3xj9p0uPWrFBq_GEMS`
- Marketplace address: `EQBYTuYbLf8INxFtD8tQeNk5ZLy-nAX9ahQbG_yl1qQ-GEMS`
- Current fixed-price contract: `nft-fixprice-sale-v4r1.fc`
- Fixed-price sale v4 code hash base64: `a5WmQYucnSNZBF0edVm41UmuDlBvJMqrWPowyPsf64Y=`
- Fixed-price sale v4 code hash hex: `6B95A6418B9C9D2359045D1E7559B8D549AE0E506F24CAAB58FA30C8FB1FEB86`

Implication:

- Listing on GetGems means deploying/initializing a sale contract and transferring the NFT to it, or using an existing marketplace flow that produces those transactions.
- This requires TON wallet integration, not Telegram userbot MTProto.

Recommended MVP:

1. Read-only on-chain connector:
   - resolve wallet NFTs via TonAPI/TON Center;
   - identify Telegram gift NFTs;
   - fetch collection/floor/activity from public indexers or GetGems/private GraphQL only if stable.
2. Transaction planner:
   - build a proposed fixed-price sale transaction;
   - estimate fees;
   - display sale price, 5% fee, net proceeds, gas reserve.
3. Manual signing first:
   - output TonConnect deeplink/transaction payload;
   - user signs with wallet.
4. Agentic wallet later:
   - separate low-balance wallet;
   - approvals and hard limits;
   - only list/cancel under policy.

## Architecture Recommendation

Add a new `markets/` layer:

- `markets/portals.py`: private API connector, initially read-only.
- `markets/getgems.py`: on-chain planner, initially no private key.
- `markets/ton.py`: TON indexer/wallet abstraction.
- `services/market_research.py`: normalize floors, listings, volumes, and spreads.
- `services/market_execution.py`: create approval requests for buy/list/cancel.

Keep executors separate:

- Telegram gift executor: current MTProto queue.
- Portals executor: Mini App auth/private API queue.
- GetGems executor: TON wallet transaction queue.

Every write action should go through approvals until we have enough production evidence.

## Sources

- Portals community API wrapper: https://github.com/bleach-hub/portalsmp
- GetGems selling help: https://getgems.helpscoutdocs.com/article/15-how-do-i-sell-my-nft-on-getgems
- GetGems smart contracts help: https://getgems.helpscoutdocs.com/article/79-smart-contracts
- GetGems contracts: https://github.com/getgems-io/nft-contracts
