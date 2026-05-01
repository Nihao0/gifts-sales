"""
PricingService — TON ↔ Stars conversion.

The configured rate comes from settings.ton_to_stars_rate. Telegram resale
options are only a best-effort fallback and do not expose a reliable TON pair.

For future GetGems integration, inject a MarketProvider that satisfies:
    Protocol:
        async def get_stars_per_ton(self) -> float: ...
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.client.telegram import TelegramClientContext
    from app.client.mtproto.types import StarsAmount
    from app.config.settings import Settings

log = get_logger(__name__)


@runtime_checkable
class MarketProvider(Protocol):
    async def get_stars_per_ton(self) -> float:
        ...


class PricingService:
    def __init__(
        self,
        tg: "TelegramClientContext | None",
        settings: "Settings",
        market_provider: MarketProvider | None = None,
    ) -> None:
        self._tg = tg
        self._settings = settings
        self._market_provider = market_provider
        self._cached_rate: float | None = None

    async def get_stars_per_ton(self, collectible_id: int | None = None) -> float:
        """Return number of Stars equivalent to 1 TON."""
        if self._settings.ton_to_stars_rate is not None:
            return self._settings.ton_to_stars_rate

        if self._market_provider is not None:
            return await self._market_provider.get_stars_per_ton()

        if self._cached_rate is not None:
            return self._cached_rate

        # Try to fetch from Telegram API when a live client is available.
        if collectible_id is not None and self._tg is not None:
            try:
                from app.client.mtproto.functions import GetStarGiftResaleOptionsRequest

                result = await self._tg.invoke(
                    GetStarGiftResaleOptionsRequest(star_gift_id=collectible_id)
                )
                # result is a Vector<StarsAmount> — use the first option as reference
                options = getattr(result, "options", None) or (list(result) if result else [])
                if options:
                    # Each StarsAmount represents one valid price point.
                    # We derive TON→Stars by looking at the first non-zero option.
                    # In practice callers pass explicit price_ton, so this is best-effort.
                    first = options[0]
                    amount = getattr(first, "amount", None)
                    if amount and amount > 0:
                        # The API does not expose the TON equivalent directly;
                        # fall through to default below.
                        pass
            except Exception as exc:
                log.warning("pricing.fetch_rate_failed", error=str(exc))

        # Conservative default: 1 TON = 200 Stars (update via .env TON_TO_STARS_RATE)
        default_rate = 200.0
        log.warning("pricing.using_default_rate", rate=default_rate)
        self._cached_rate = default_rate
        return default_rate

    def ton_to_stars(self, ton: float, rate: float) -> int:
        """Convert TON amount to integer Stars (truncated)."""
        return math.floor(ton * rate)

    def stars_to_ton(self, stars: int, rate: float) -> float:
        """Convert Stars to TON."""
        if rate == 0:
            raise ValueError("rate must be > 0")
        return stars / rate

    def make_stars_amount(self, stars: int) -> "StarsAmount":
        from app.client.mtproto.types import StarsAmount

        return StarsAmount(amount=stars, nanos=0)
