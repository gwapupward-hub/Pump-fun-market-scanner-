from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from pump_intel.db import executemany, fetch_all_dict, fetch_one_dict, jsonb

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True)
class RugSignal:
    rug_kind: str
    severity: str
    evidence: dict[str, Any]


def _drawdown(ath: float | None, current: float | None) -> float | None:
    if ath is None or ath <= 0 or current is None:
        return None
    return max(0.0, min(1.0, 1.0 - (current / ath)))


def _ms_to_dt(ms: Any) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)
    except (OSError, ValueError, OverflowError, TypeError):
        return None


def detect_rug_signals_for_mint(conn: psycopg.Connection, mint: str) -> list[RugSignal]:
    """Per-mint detector — kept for unit testing and ad-hoc inspection."""
    snaps = fetch_all_dict(
        conn,
        """
        SELECT *
        FROM token_snapshots
        WHERE mint = %s
        ORDER BY snapshot_at DESC
        LIMIT 2
        """,
        (mint,),
    )
    if not snaps:
        return []
    latest = snaps[0]
    prev = snaps[1] if len(snaps) > 1 else None
    return _signals_for(latest, prev, _creator_row(conn, latest))


def _creator_row(conn: psycopg.Connection, latest: dict) -> dict | None:
    raw = latest.get("raw_coin") or {}
    creator = str(raw.get("creator") or "")
    if not creator:
        return None
    return fetch_one_dict(conn, "SELECT * FROM creator_wallets WHERE address = %s", (creator,))


def _signals_for(latest: dict, prev: dict | None, creator_row: dict | None) -> list[RugSignal]:
    raw = latest.get("raw_coin") or {}
    signals: list[RugSignal] = []

    ath = latest.get("ath_market_cap_usd")
    cur = latest.get("market_cap_usd")
    dd = _drawdown(float(ath) if ath is not None else None, float(cur) if cur is not None else None)

    ath_at = latest.get("ath_at")
    if isinstance(ath_at, datetime) and dd is not None:
        hours_since_ath = (_now() - ath_at).total_seconds() / 3600.0
        if dd >= 0.9:
            signals.append(
                RugSignal(
                    rug_kind="ath_drawdown_90pct",
                    severity="hard",
                    evidence={"drawdown": dd, "hours_since_ath": hours_since_ath},
                )
            )
        elif hours_since_ath <= 24 and dd >= 0.7:
            signals.append(
                RugSignal(
                    rug_kind="ath_drawdown_70pct_within_24h_of_ath",
                    severity="hard",
                    evidence={"drawdown": dd, "hours_since_ath": hours_since_ath},
                )
            )

    if (
        prev
        and latest.get("top_holder_concentration_pct") is not None
        and prev.get("top_holder_concentration_pct") is not None
    ):
        prev_top = float(prev["top_holder_concentration_pct"])
        now_top = float(latest["top_holder_concentration_pct"])
        if prev_top > 0 and (prev_top - now_top) >= 20.0:
            signals.append(
                RugSignal(
                    rug_kind="top_holder_dump",
                    severity="soft",
                    evidence={"prev_top1_pct": prev_top, "now_top1_pct": now_top},
                )
            )

    if creator_row and int(creator_row.get("hard_rug_count") or 0) + int(
        creator_row.get("soft_rug_count") or 0
    ) >= 3:
        signals.append(
            RugSignal(
                rug_kind="suspicious_creator_wallet_history",
                severity="soft",
                evidence={
                    "creator": str(raw.get("creator") or ""),
                    "hard_rug_count": int(creator_row.get("hard_rug_count") or 0),
                    "soft_rug_count": int(creator_row.get("soft_rug_count") or 0),
                },
            )
        )

    launch = _ms_to_dt(raw.get("created_timestamp"))
    if launch and cur is not None and ath is not None:
        age_hours = (_now() - launch).total_seconds() / 3600.0
        if age_hours <= 48 and float(ath) > 0 and float(cur) / float(ath) < 0.05:
            signals.append(
                RugSignal(
                    rug_kind="major_dev_sell_proxy",
                    severity="soft",
                    evidence={
                        "age_hours": age_hours,
                        "mcap_to_ath_ratio": float(cur) / float(ath),
                    },
                )
            )

    return signals


def persist_rug_events(conn: psycopg.Connection, mint: str, signals: list[RugSignal]) -> int:
    if not signals:
        return 0
    inserted = 0
    with conn.cursor() as cur:
        for s in signals:
            cur.execute(
                """
                SELECT 1 FROM rug_events
                WHERE mint = %s AND rug_kind = %s
                  AND detected_at > NOW() - interval '2 hours'
                LIMIT 1
                """,
                (mint, s.rug_kind),
            )
            if cur.fetchone():
                continue
            cur.execute(
                "INSERT INTO rug_events (mint, rug_kind, severity, evidence) VALUES (%s,%s,%s,%s)",
                (mint, s.rug_kind, s.severity, jsonb(s.evidence)),
            )
            inserted += 1
    return inserted


def scan_recent_mints_for_rugs(
    conn: psycopg.Connection, *, lookback_hours: int = 48
) -> dict[str, int]:
    """Pull the two most recent snapshots per active mint in one query, then score in Python."""
    since = _now() - timedelta(hours=lookback_hours)
    rows = fetch_all_dict(
        conn,
        """
        WITH active AS (
            SELECT DISTINCT mint FROM token_snapshots WHERE snapshot_at >= %s
        ),
        ranked AS (
            SELECT ts.*, row_number() OVER (PARTITION BY ts.mint ORDER BY ts.snapshot_at DESC) AS rn
            FROM token_snapshots ts
            JOIN active a ON a.mint = ts.mint
        )
        SELECT *
        FROM ranked
        WHERE rn <= 2
        """,
        (since,),
    )

    by_mint: dict[str, list[dict]] = {}
    for r in rows:
        by_mint.setdefault(r["mint"], []).append(r)

    if not by_mint:
        return {"rug_events_inserted": 0, "mints_checked": 0}

    creators = {
        str((mint_rows[0].get("raw_coin") or {}).get("creator") or "")
        for mint_rows in by_mint.values()
    }
    creators.discard("")
    creator_index: dict[str, dict] = {}
    if creators:
        crows = fetch_all_dict(
            conn,
            "SELECT * FROM creator_wallets WHERE address = ANY(%s::text[])",
            (list(creators),),
        )
        creator_index = {c["address"]: c for c in crows}

    payload: list[tuple[Any, ...]] = []
    for mint, mint_rows in by_mint.items():
        latest = mint_rows[0]
        prev = mint_rows[1] if len(mint_rows) > 1 else None
        creator_addr = str((latest.get("raw_coin") or {}).get("creator") or "")
        sigs = _signals_for(latest, prev, creator_index.get(creator_addr))
        for s in sigs:
            payload.append((mint, s.rug_kind, s.severity, jsonb(s.evidence)))

    if not payload:
        return {"rug_events_inserted": 0, "mints_checked": len(by_mint)}

    # Dedup against recent events in one round-trip before insert.
    affected_mints = sorted({p[0] for p in payload})
    recent = fetch_all_dict(
        conn,
        """
        SELECT mint, rug_kind
        FROM rug_events
        WHERE mint = ANY(%s::text[])
          AND detected_at > NOW() - interval '2 hours'
        """,
        (affected_mints,),
    )
    seen = {(r["mint"], r["rug_kind"]) for r in recent}
    fresh = [row for row in payload if (row[0], row[1]) not in seen]
    if not fresh:
        return {"rug_events_inserted": 0, "mints_checked": len(by_mint)}

    executemany(
        conn,
        "INSERT INTO rug_events (mint, rug_kind, severity, evidence) VALUES (%s,%s,%s,%s)",
        fresh,
    )
    log.info(
        "rug scan complete",
        extra={"mints_checked": len(by_mint), "rug_events_inserted": len(fresh)},
    )
    return {"rug_events_inserted": len(fresh), "mints_checked": len(by_mint)}


# Re-export for legacy callers / tests
__all__ = [
    "RugSignal",
    "detect_rug_signals_for_mint",
    "persist_rug_events",
    "scan_recent_mints_for_rugs",
]
