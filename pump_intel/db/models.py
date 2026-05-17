from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TokenClassification(str, enum.Enum):
    loser = "loser"
    micro_winner = "micro_winner"
    bonding_winner = "bonding_winner"
    graduated_winner = "graduated_winner"
    viral_winner = "viral_winner"
    soft_rug = "soft_rug"
    hard_rug = "hard_rug"
    abandoned = "abandoned"


class MigrationStatus(str, enum.Enum):
    unknown = "unknown"
    bonding = "bonding"
    migrating = "migrating"
    graduated = "graduated"


class RugSignal(str, enum.Enum):
    major_dev_sell = "major_dev_sell"
    drawdown_70pct_24h = "drawdown_70pct_24h"
    drawdown_90pct = "drawdown_90pct"
    top_holder_dump = "top_holder_dump"
    suspicious_creator_history = "suspicious_creator_history"
    socials_missing = "socials_missing"


class CreatorWallet(Base):
    __tablename__ = "creator_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_address: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    tokens_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rugs_linked: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    graduates_linked: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reputation_score: Mapped[float] = mapped_column(Float, default=50.0, server_default="50")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, server_default="{}")

    tokens: Mapped[list[Token]] = relationship(back_populates="creator")


class Token(Base):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mint_address: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticker: Mapped[str | None] = mapped_column(String(64), nullable=True)
    creator_wallet_id: Mapped[int | None] = mapped_column(ForeignKey("creator_wallets.id"), nullable=True)
    launch_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    classification: Mapped[TokenClassification | None] = mapped_column(
        Enum(TokenClassification, name="token_classification", native_enum=False, length=32),
        nullable=True,
    )
    intel_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped[CreatorWallet | None] = relationship(back_populates="tokens")
    snapshots: Mapped[list[TokenSnapshot]] = relationship(back_populates="token")
    socials: Mapped[list[TokenSocial]] = relationship(back_populates="token")
    holder_snapshots: Mapped[list[HolderSnapshot]] = relationship(back_populates="token")
    trade_summaries: Mapped[list[TradeSummary]] = relationship(back_populates="token")
    rug_events: Mapped[list[RugEvent]] = relationship(back_populates="token")


class TokenSnapshot(Base):
    __tablename__ = "token_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    market_cap: Mapped[float | None] = mapped_column(Numeric(24, 6), nullable=True)
    ath_market_cap: Mapped[float | None] = mapped_column(Numeric(24, 6), nullable=True)
    time_to_ath_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bonding_curve_progress: Mapped[float | None] = mapped_column(Numeric(8, 5), nullable=True)
    migration_status: Mapped[MigrationStatus] = mapped_column(
        Enum(MigrationStatus, name="migration_status", native_enum=False, length=32),
        default=MigrationStatus.unknown,
        server_default=MigrationStatus.unknown.value,
    )
    volume_24h: Mapped[float | None] = mapped_column(Numeric(24, 6), nullable=True)
    holder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_holder_concentration: Mapped[float | None] = mapped_column(Numeric(8, 5), nullable=True)
    buy_sell_ratio: Mapped[float | None] = mapped_column(Numeric(12, 5), nullable=True)
    drawdown_from_ath: Mapped[float | None] = mapped_column(Numeric(8, 5), nullable=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")

    token: Mapped[Token] = relationship(back_populates="snapshots")


class TokenSocial(Base):
    __tablename__ = "token_socials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    x_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    telegram_present: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    website_present: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    token: Mapped[Token] = relationship(back_populates="socials")

    __table_args__ = (UniqueConstraint("token_id", "platform", name="uq_token_social_platform"),)


class HolderSnapshot(Base):
    __tablename__ = "holder_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    holder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_holder_concentration: Mapped[float | None] = mapped_column(Numeric(8, 5), nullable=True)
    top5_concentration: Mapped[float | None] = mapped_column(Numeric(8, 5), nullable=True)

    token: Mapped[Token] = relationship(back_populates="holder_snapshots")


class TradeSummary(Base):
    __tablename__ = "trade_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    buy_volume: Mapped[float | None] = mapped_column(Numeric(24, 6), nullable=True)
    sell_volume: Mapped[float | None] = mapped_column(Numeric(24, 6), nullable=True)
    trade_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creator_sell_volume_estimate: Mapped[float | None] = mapped_column(Numeric(24, 6), nullable=True)
    buy_sell_ratio: Mapped[float | None] = mapped_column(Numeric(12, 5), nullable=True)

    token: Mapped[Token] = relationship(back_populates="trade_summaries")


class RugEvent(Base):
    __tablename__ = "rug_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    signal: Mapped[RugSignal] = mapped_column(
        Enum(RugSignal, name="rug_signal", native_enum=False, length=48), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")

    token: Mapped[Token] = relationship(back_populates="rug_events")


class DailyMarketReport(Base):
    __tablename__ = "daily_market_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    coins_scanned: Mapped[int] = mapped_column(Integer, default=0)
    structured_stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    ai_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WinnerPattern(Base):
    __tablename__ = "winner_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("daily_market_reports.id", ondelete="CASCADE"), index=True)
    pattern_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    pattern_key: Mapped[str] = mapped_column(String(256), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    supporting_mints: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")

    report: Mapped[DailyMarketReport] = relationship()
