from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pump_intel.db.models import (
    CreatorWallet,
    HolderSnapshot,
    MigrationStatus,
    Token,
    TokenSnapshot,
    TokenSocial,
    TradeSummary,
)
from pump_intel.schemas.coin import NormalizedCoin

log = logging.getLogger(__name__)


def _migration_enum(s: str | None) -> MigrationStatus:
    if not s:
        return MigrationStatus.unknown
    key = s.lower()
    if key in ("graduated", "migrated", "complete", "raydium"):
        return MigrationStatus.graduated
    if key in ("bonding", "in_curve", "incurve"):
        return MigrationStatus.bonding
    if key in ("migrating",):
        return MigrationStatus.migrating
    return MigrationStatus.unknown


def _drawdown(mcap: float | None, ath: float | None) -> float | None:
    if mcap is None or ath is None or ath <= 0:
        return None
    return float(max(0.0, min(1.0, 1.0 - (mcap / ath))))


def get_or_create_creator(session: Session, wallet: str | None) -> CreatorWallet | None:
    if not wallet:
        return None
    q = select(CreatorWallet).where(CreatorWallet.wallet_address == wallet)
    cw = session.execute(q).scalar_one_or_none()
    if cw:
        cw.last_seen_at = datetime.now(tz=UTC)
        return cw
    cw = CreatorWallet(wallet_address=wallet)
    session.add(cw)
    session.flush()
    return cw


def upsert_token(session: Session, coin: NormalizedCoin, creator: CreatorWallet | None) -> Token:
    q = select(Token).where(Token.mint_address == coin.mint)
    tok = session.execute(q).scalar_one_or_none()
    if tok is None:
        tok = Token(mint_address=coin.mint)
        session.add(tok)
        session.flush()
    tok.name = coin.name
    tok.ticker = coin.ticker
    tok.launch_timestamp = coin.launch_at
    if creator is not None:
        tok.creator_wallet_id = creator.id
    return tok


def persist_coin_snapshot(session: Session, coin: NormalizedCoin) -> Token:
    creator = get_or_create_creator(session, coin.creator_wallet)
    tok = upsert_token(session, coin, creator)

    dd = _drawdown(coin.market_cap, coin.ath_market_cap)
    snap = TokenSnapshot(
        token_id=tok.id,
        captured_at=datetime.now(tz=UTC),
        market_cap=coin.market_cap,
        ath_market_cap=coin.ath_market_cap,
        time_to_ath_seconds=coin.time_to_ath_seconds,
        bonding_curve_progress=coin.bonding_curve_progress,
        migration_status=_migration_enum(coin.migration_status),
        volume_24h=coin.volume_24h,
        holder_count=coin.holder_count,
        top_holder_concentration=coin.top_holder_concentration,
        buy_sell_ratio=coin.buy_sell_ratio,
        drawdown_from_ath=dd,
        raw=coin.raw,
    )
    session.add(snap)

    _upsert_socials(session, tok.id, coin)

    hs = HolderSnapshot(
        token_id=tok.id,
        captured_at=snap.captured_at,
        holder_count=coin.holder_count,
        top_holder_concentration=coin.top_holder_concentration,
        top5_concentration=None,
    )
    session.add(hs)

    end = snap.captured_at
    start = end - timedelta(hours=24)
    ts = TradeSummary(
        token_id=tok.id,
        window_start=start,
        window_end=end,
        buy_volume=None,
        sell_volume=None,
        trade_count=None,
        creator_sell_volume_estimate=None,
        buy_sell_ratio=coin.buy_sell_ratio,
    )
    session.add(ts)

    session.flush()
    return tok


def _upsert_socials(session: Session, token_id: int, coin: NormalizedCoin) -> None:
    rows: list[tuple[str, str | None, dict[str, Any]]] = [
        ("twitter", coin.twitter_url, {"x_verified": coin.x_verified}),
        ("telegram", coin.telegram_url, {"telegram_present": bool(coin.telegram_url)}),
        ("website", coin.website_url, {"website_present": bool(coin.website_url)}),
    ]
    for platform, url, flags in rows:
        q = select(TokenSocial).where(TokenSocial.token_id == token_id, TokenSocial.platform == platform)
        social = session.execute(q).scalar_one_or_none()
        now = datetime.now(tz=UTC)
        if social is None:
            social = TokenSocial(
                token_id=token_id,
                platform=platform,
                url=url,
                x_verified=bool(flags.get("x_verified")) if platform == "twitter" else False,
                telegram_present=bool(flags.get("telegram_present")) if platform == "telegram" else False,
                website_present=bool(flags.get("website_present")) if platform == "website" else False,
                first_seen_at=now,
                last_seen_at=now,
                is_active=True,
            )
            session.add(social)
        else:
            prev_url = social.url
            social.last_seen_at = now
            social.url = url
            social.is_active = True
            if platform == "twitter":
                social.x_verified = bool(flags.get("x_verified"))
            if platform == "telegram":
                social.telegram_present = bool(coin.telegram_url)
            if platform == "website":
                social.website_present = bool(coin.website_url)
            if prev_url and not url:
                social.is_active = False


_WS = re.compile(r"\s+")


def token_display_name(tok: Token) -> str:
    parts = [p for p in (tok.name, tok.ticker) if p]
    return _WS.sub(" ", " ".join(parts)).strip() or tok.mint_address
