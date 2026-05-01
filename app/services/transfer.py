"""Transfer collectible gifts to another Telegram peer."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.client.mtproto.functions import TransferStarGiftRequest
from app.client.mtproto.types import InputSavedStarGiftUser
from app.client.telegram import TelegramClientContext
from app.models.gift import Gift
from app.storage.gift_repo import GiftRepository
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.config.settings import Settings

log = get_logger(__name__)


class TransferService:
    def __init__(
        self,
        tg: TelegramClientContext | None,
        gift_repo: GiftRepository,
        settings: "Settings",
    ) -> None:
        self._tg = tg
        self._gift_repo = gift_repo
        self._settings = settings

    async def transfer_gift(
        self,
        gift: Gift,
        destination_peer: str,
        dry_run: bool = False,
    ) -> None:
        """Transfer a gift to a Telegram user/channel/bot username."""
        if gift.owner_peer != "self":
            raise ValueError("Only gifts owned by the current account can be transferred.")

        if gift.transferred_at is not None:
            log.info(
                "transfer.skip.already_transferred",
                gift_id=gift.id,
                destination_peer=gift.transferred_to,
            )
            return

        log.info(
            "transfer.gift",
            gift_id=gift.id,
            telegram_gift_id=gift.telegram_gift_id,
            destination_peer=destination_peer,
            dry_run=dry_run,
        )

        if dry_run:
            return

        if gift.msg_id is None:
            raise ValueError(f"Gift {gift.id} has no msg_id — run 'gifts scan' first.")
        if self._tg is None:
            raise RuntimeError("Telegram client is required for real gift transfer.")

        to_id = await self._tg.resolve_input_peer(destination_peer)
        request = TransferStarGiftRequest(
            stargift=InputSavedStarGiftUser(msg_id=gift.msg_id),
            to_id=to_id,
        )
        await self._tg.invoke(request)
        await self._gift_repo.mark_transferred(gift.id, destination_peer)
