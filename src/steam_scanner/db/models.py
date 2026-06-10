"""SQLAlchemy database models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class App(Base):
    __tablename__ = "apps"

    appid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    has_trading_cards: Mapped[bool] = mapped_column(Boolean, default=False)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclude_reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class MarketItem(Base):
    __tablename__ = "market_items"
    __table_args__ = (UniqueConstraint("market_appid", "market_hash_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appid: Mapped[int | None] = mapped_column(BigInteger)
    market_appid: Mapped[int] = mapped_column(BigInteger, default=753)
    market_hash_name: Mapped[str] = mapped_column(Text, nullable=False)
    item_name: Mapped[str | None] = mapped_column(Text)
    item_type: Mapped[str | None] = mapped_column(Text)
    game_name: Mapped[str | None] = mapped_column(Text)
    category_game_tag: Mapped[str | None] = mapped_column(Text)
    marketable: Mapped[bool | None] = mapped_column(Boolean)
    tradable: Mapped[bool | None] = mapped_column(Boolean)
    commodity: Mapped[bool | None] = mapped_column(Boolean)
    is_card: Mapped[bool] = mapped_column(Boolean, default=False)
    is_foil: Mapped[bool] = mapped_column(Boolean, default=False)
    is_booster: Mapped[bool] = mapped_column(Boolean, default=False)
    is_background: Mapped[bool] = mapped_column(Boolean, default=False)
    is_emoticon: Mapped[bool] = mapped_column(Boolean, default=False)
    item_nameid: Mapped[str | None] = mapped_column(Text)
    market_url: Mapped[str | None] = mapped_column(Text)
    data_quality_status: Mapped[str] = mapped_column(String(64), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(back_populates="market_item")
    orderbook_snapshots: Mapped[list["OrderbookSnapshot"]] = relationship(
        back_populates="market_item"
    )


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("market_items.id", ondelete="CASCADE")
    )
    currency_code: Mapped[str] = mapped_column(String(8))
    country_code: Mapped[str] = mapped_column(String(8))
    lowest_price: Mapped[float | None] = mapped_column(Numeric)
    median_price: Mapped[float | None] = mapped_column(Numeric)
    volume: Mapped[int | None] = mapped_column(Integer)
    raw_response: Mapped[dict | None] = mapped_column(JSONB)
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    market_item: Mapped["MarketItem"] = relationship(back_populates="price_snapshots")


class OrderbookSnapshot(Base):
    __tablename__ = "orderbook_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("market_items.id", ondelete="CASCADE")
    )
    currency_code: Mapped[str] = mapped_column(String(8))
    country_code: Mapped[str] = mapped_column(String(8))
    highest_buy_order: Mapped[float | None] = mapped_column(Numeric)
    lowest_sell_order: Mapped[float | None] = mapped_column(Numeric)
    buy_order_count: Mapped[int | None] = mapped_column(Integer)
    sell_order_count: Mapped[int | None] = mapped_column(Integer)
    buy_order_graph: Mapped[list | None] = mapped_column(JSONB)
    sell_order_graph: Mapped[list | None] = mapped_column(JSONB)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    raw_response: Mapped[dict | None] = mapped_column(JSONB)
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    market_item: Mapped["MarketItem"] = relationship(back_populates="orderbook_snapshots")


class FeeCalculation(Base):
    __tablename__ = "fee_calculations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("market_items.id", ondelete="CASCADE"), nullable=True
    )
    currency_code: Mapped[str] = mapped_column(String(8))
    buyer_pays: Mapped[float | None] = mapped_column(Numeric)
    seller_receives: Mapped[float | None] = mapped_column(Numeric)
    steam_fee: Mapped[float | None] = mapped_column(Numeric)
    publisher_fee: Mapped[float | None] = mapped_column(Numeric)
    total_fee: Mapped[float | None] = mapped_column(Numeric)
    effective_fee_pct: Mapped[float | None] = mapped_column(Numeric)
    break_even_sell_price: Mapped[float | None] = mapped_column(Numeric)
    minimum_profitable_sell_price: Mapped[float | None] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OpportunityScore(Base):
    __tablename__ = "opportunity_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("market_items.id", ondelete="CASCADE")
    )
    currency_code: Mapped[str] = mapped_column(String(8))
    lowest_sell_price: Mapped[float | None] = mapped_column(Numeric)
    highest_buy_order: Mapped[float | None] = mapped_column(Numeric)
    net_spread_abs: Mapped[float | None] = mapped_column(Numeric)
    net_spread_pct: Mapped[float | None] = mapped_column(Numeric)
    volume_score: Mapped[float | None] = mapped_column(Numeric)
    depth_score: Mapped[float | None] = mapped_column(Numeric)
    competition_score: Mapped[float | None] = mapped_column(Numeric)
    volatility_score: Mapped[float | None] = mapped_column(Numeric)
    opportunity_score: Mapped[float | None] = mapped_column(Numeric)
    risk_flags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    data_quality_status: Mapped[str | None] = mapped_column(String(64))
    calculated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="running")
    last_appid: Mapped[int | None] = mapped_column(BigInteger)
    last_item_id: Mapped[int | None] = mapped_column(BigInteger)
    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class CurrencyAnalysis(Base):
    __tablename__ = "currency_analysis"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("market_items.id", ondelete="CASCADE")
    )
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    price_usd: Mapped[float | None] = mapped_column(Numeric)
    price_eur: Mapped[float | None] = mapped_column(Numeric)
    price_rub: Mapped[float | None] = mapped_column(Numeric)
    price_gbp: Mapped[float | None] = mapped_column(Numeric)
    price_brl: Mapped[float | None] = mapped_column(Numeric)
    price_cny: Mapped[float | None] = mapped_column(Numeric)
    implied_usd_eur: Mapped[float | None] = mapped_column(Numeric)
    implied_usd_rub: Mapped[float | None] = mapped_column(Numeric)
    implied_usd_gbp: Mapped[float | None] = mapped_column(Numeric)
    implied_usd_brl: Mapped[float | None] = mapped_column(Numeric)
    implied_usd_cny: Mapped[float | None] = mapped_column(Numeric)
    rounding_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_details: Mapped[dict | None] = mapped_column(JSONB)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
