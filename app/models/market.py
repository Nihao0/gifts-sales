from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MarketFloor(Base):
    __tablename__ = "market_floors"
    __table_args__ = (
        Index("ix_market_floors_market_gift", "market", "gift_name"),
        Index("ix_market_floors_captured_at", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    gift_name: Mapped[str] = mapped_column(String(256), nullable=False)
    model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    backdrop: Mapped[str | None] = mapped_column(String(256), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(256), nullable=True)
    floor_price_ton: Mapped[float | None] = mapped_column(Float, nullable=True)
    listed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class MarketListing(Base):
    __tablename__ = "market_listings"
    __table_args__ = (
        Index("ix_market_listings_market_gift", "market", "gift_name"),
        Index("ix_market_listings_external_id", "market", "external_id"),
        Index("ix_market_listings_captured_at", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tg_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gift_name: Mapped[str] = mapped_column(String(256), nullable=False)
    model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    backdrop: Mapped[str | None] = mapped_column(String(256), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(256), nullable=True)
    price_ton: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
