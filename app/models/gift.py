from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Gift(Base):
    __tablename__ = "gifts"
    __table_args__ = (
        Index("ix_gifts_collectible_id", "collectible_id"),
        Index("ix_gifts_is_for_sale", "is_for_sale"),
        Index("ix_gifts_availability_total", "availability_total"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Telegram identity — saved_id (long) as string
    telegram_gift_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    owner_peer: Mapped[str] = mapped_column(String(128), default="self", nullable=False)

    # msg_id in user's saved gifts inbox — needed for InputSavedStarGiftUser
    msg_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    collectible_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    availability_issued: Mapped[int | None] = mapped_column(Integer, nullable=True)
    availability_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_for_sale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resale_price_stars: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resale_price_ton: Mapped[float | None] = mapped_column(Float, nullable=True)
    transferred_to: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transferred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<Gift id={self.id} telegram_gift_id={self.telegram_gift_id!r} "
            f"owner_peer={self.owner_peer!r} title={self.title!r} for_sale={self.is_for_sale}>"
        )
