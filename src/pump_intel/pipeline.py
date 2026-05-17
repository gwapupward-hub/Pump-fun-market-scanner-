from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from psycopg import Connection

from pump_intel.classification.service import classify_token
from pump_intel.config import Settings
from pump_intel.db import connection as dbconn
from pump_intel.db import repository as repo
from pump_intel.ingestion.service import IngestionService
from pump_intel.ingestion.trades import aggregate_trades
from pump_intel.rug_detection.service import RugDetectionService, persist_events
from pump_intel.types import NormalizedCoin


@dataclass
class PipelineResult:
    coins_scanned: int
    report_date: datetime


def _parse_holders(raw: list[dict[str, Any]] | None) -> tuple[list[tuple[int, str, float]], float | None]:
    if not raw:
        return [], None
    rows: list[tuple[int, str, float]] = []
    for idx, h in enumerate(raw[:25], start=1):
        w = str(h.get("address") or h.get("wallet") or h.get("owner") or "")
        pct = h.get("percentage") or h.get("pct") or h.get("percent") or h.get("uiAmount")
        try:
            pct_f = float(pct) if pct is not None else 0.0
        except (TypeError, ValueError):
            pct_f = 0.0
        rows.append((idx, w, pct_f))
    top5 = sum(p for _, _, p in rows[:5])
    concentration = top5 / 100.0 if top5 > 1.0 else top5
    return rows, concentration


def _holder_rows_for_db(rows: list[tuple[int, str, float]]) -> list[tuple[int, str, float]]:
    return [(r[0], r[1], r[2]) for r in rows if r[1]]


class MarketIntelligencePipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.ingestion = IngestionService(self.settings)
        self.rug = RugDetectionService()

    def close(self) -> None:
        self.ingestion.close()

    def run(self, conn: Connection) -> PipelineResult:
        raw = self.ingestion.collect_coins()
        coins: list[NormalizedCoin] = self.ingestion.normalize_all(raw)

        sol_usd = self.ingestion.client.fetch_sol_price_usd() or self.settings.sol_usd_fallback

        ranked = sorted(
            coins,
            key=lambda c: float(c.usd_market_cap or 0.0),
            reverse=True,
        )
        enrich_set = {c.mint for c in ranked[: self.settings.enrich_trades_top_n]}

        now = datetime.now(tz=UTC)
        scanned = 0

        for coin in coins:
            scanned += 1
            token_id = repo.upsert_token(conn, coin)
            repo.ensure_creator_wallet(conn, coin.creator)

            prior_socials = repo.fetch_prior_socials(conn, token_id)

            trade_agg = None
            if coin.mint in enrich_set:
                trades = self.ingestion.client.fetch_trades_sample(coin.mint, limit=250)
                if trades:
                    trade_agg = aggregate_trades(trades, coin.creator, sol_usd)

            holders_raw = None
            if coin.mint in enrich_set:
                holders_raw = self.ingestion.client.fetch_top_holders(coin.mint)

            holder_rows, concentration = _parse_holders(holders_raw)
            coin.holder_count = len(holder_rows) if holder_rows else coin.holder_count
            coin.top_holder_concentration = concentration
            if trade_agg:
                coin.volume_24h_usd = (trade_agg.buy_volume_usd or 0) + (
                    trade_agg.sell_volume_usd or 0
                )
            if trade_agg and trade_agg.sell_volume_usd and trade_agg.sell_volume_usd > 0:
                coin.buy_sell_ratio = (trade_agg.buy_volume_usd or 0) / trade_agg.sell_volume_usd

            ath = float(coin.ath_usd_mcap or float(coin.usd_market_cap or 0.0) or 1.0)
            cur = float(coin.usd_market_cap or 0.0)
            ath_ratio = cur / ath if ath > 0 else 0.0

            creator_rug_rate = repo.creator_rug_rate(conn, coin.creator)

            signals = self.rug.evaluate(
                conn,
                token_id,
                coin,
                prior_socials,
                trade_dev_sell=bool(trade_agg and trade_agg.dev_sell_detected),
            )

            cls, score = classify_token(
                coin,
                ath_ratio=ath_ratio,
                creator_rug_rate=creator_rug_rate,
                drawdown=signals.drawdown,
                drawdown_24h=signals.drawdown_24h,
                social_removed=signals.social_removed,
                dev_sell=signals.dev_sell,
                top_holder_dump=signals.top_holder_dump,
            )

            snap_id = repo.insert_token_snapshot(conn, token_id, coin, cls, score, trade_agg)

            if holder_rows:
                repo.insert_holder_snapshots(conn, snap_id, _holder_rows_for_db(holder_rows))

            persist_events(conn, token_id, signals)
            repo.replace_token_socials(conn, token_id, coin)

        repo.refresh_creator_aggregates(conn)

        return PipelineResult(coins_scanned=scanned, report_date=now)


def run_pipeline(settings: Settings | None = None) -> PipelineResult:
    cfg = settings or Settings()
    conn = dbconn.connect(cfg.database_url)
    try:
        dbconn.migrate(conn)
        pipe = MarketIntelligencePipeline(cfg)
        try:
            result = pipe.run(conn)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            pipe.close()
    finally:
        conn.close()
