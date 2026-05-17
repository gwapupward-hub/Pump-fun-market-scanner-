from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pump_intel.db import fetch_all_dict, fetch_one_dict


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


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
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
    except (OSError, ValueError, OverflowError, TypeError):
        return None


def detect_rug_signals_for_mint(conn, mint: str) -> list[RugSignal]:
    latest = fetch_one_dict(
        conn,
        """
        SELECT *
        FROM token_snapshots
        WHERE mint = %s
        ORDER BY snapshot_at DESC
        LIMIT 1
        """,
        (mint,),
    )
    if not latest:
        return []

    prev = fetch_one_dict(
        conn,
        """
        SELECT *
        FROM token_snapshots
        WHERE mint = %s
        ORDER BY snapshot_at DESC
        OFFSET 1
        LIMIT 1
        """,
        (mint,),
    )

    raw = latest.get("raw_coin") or {}
    creator = str(raw.get("creator") or "")
    creator_row = (
        fetch_one_dict(conn, "SELECT * FROM creator_wallets WHERE address = %s", (creator,))
        if creator
        else None
    )

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

    if prev and latest.get("top_holder_concentration_pct") is not None and prev.get("top_holder_concentration_pct") is not None:
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

    if creator_row and int(creator_row.get("hard_rug_count") or 0) + int(creator_row.get("soft_rug_count") or 0) >= 3:
        signals.append(
            RugSignal(
                rug_kind="suspicious_creator_wallet_history",
                severity="soft",
                evidence={"creator": creator, "creator_row": dict(creator_row)},
            )
        )

    # Dev sell proxy: large mcap drawdown shortly after launch with thin recovery
    launch = _ms_to_dt(raw.get("created_timestamp"))
    if launch and cur is not None and ath is not None:
        age_hours = (_now() - launch).total_seconds() / 3600.0
        if age_hours <= 48 and float(ath) > 0 and float(cur) / float(ath) < 0.05:
            signals.append(
                RugSignal(
                    rug_kind="major_dev_sell_proxy",
                    severity="soft",
                    evidence={"age_hours": age_hours, "mcap_to_ath_ratio": float(cur) / float(ath)},
                )
            )

    return signals


def persist_rug_events(conn, mint: str, signals: list[RugSignal]) -> int:
    from psycopg.types.json import Json

    if not signals:
        return 0
    inserted = 0
    with conn.cursor() as cur:
        for s in signals:
            cur.execute(
                """
                SELECT 1 AS ok
                FROM rug_events
                WHERE mint = %s AND rug_kind = %s
                  AND detected_at > NOW() - interval '2 hours'
                LIMIT 1
                """,
                (mint, s.rug_kind),
            )
            if cur.fetchone():
                continue
            cur.execute(
                """
                INSERT INTO rug_events (mint, rug_kind, severity, evidence)
                VALUES (%s,%s,%s,%s)
                """,
                (mint, s.rug_kind, s.severity, Json(s.evidence)),
            )
            inserted += 1
    conn.commit()
    return inserted


def scan_recent_mints_for_rugs(conn, *, lookback_hours: int = 48) -> dict[str, int]:
    since = _now() - timedelta(hours=lookback_hours)
    rows = fetch_all_dict(
        conn,
        """
        SELECT DISTINCT mint
        FROM token_snapshots
        WHERE snapshot_at >= %s
        """,
        (since,),
    )
    total = 0
    for row in rows:
        mint = row["mint"]
        sigs = detect_rug_signals_for_mint(conn, mint)
        total += persist_rug_events(conn, mint, sigs)
    return {"rug_events_inserted": total, "mints_checked": len(rows)}
