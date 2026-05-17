from __future__ import annotations

import logging
from datetime import UTC, datetime

from pump_intel.clients.pump_client import load_coins_for_scan_sync
from pump_intel.config import get_settings
from pump_intel.db.models import Token
from pump_intel.db.session import init_db, session_scope
from pump_intel.services.ai_summary_service import enrich_report_with_ai
from pump_intel.services.creator_intel import refresh_creator_rollups
from pump_intel.services.daily_report_service import build_daily_report
from pump_intel.services.ingestion_service import persist_coin_snapshot
from pump_intel.services.rug_detection_service import evaluate_creator_history, evaluate_token
from pump_intel.services.scoring_service import score_token
from pump_intel.services.winner_classification_service import apply_classification

log = logging.getLogger(__name__)


def run_daily_pipeline() -> int:
    """Full ingest → detect → classify → score → report cycle. Returns number of tokens processed."""
    settings = get_settings()
    init_db()
    coins = load_coins_for_scan_sync(settings)
    log.info("Loaded %d coins for scan", len(coins))

    scanned_ids: list[int] = []
    with session_scope() as session:
        for coin in coins:
            if not coin.mint:
                continue
            tok = persist_coin_snapshot(session, coin)
            scanned_ids.append(tok.id)

        for tid in scanned_ids:
            tok = session.get(Token, tid)
            if tok:
                evaluate_token(session, tok)

        for tid in scanned_ids:
            tok = session.get(Token, tid)
            if tok:
                apply_classification(session, tok)

        refresh_creator_rollups(session)

        for tid in scanned_ids:
            tok = session.get(Token, tid)
            if tok:
                evaluate_creator_history(session, tok)

        for tid in scanned_ids:
            tok = session.get(Token, tid)
            if tok:
                apply_classification(session, tok)
                score_token(session, tok)

        refresh_creator_rollups(session)

        report_date = datetime.now(tz=UTC).date()
        rep = build_daily_report(session, report_date=report_date, scanned_token_ids=scanned_ids)
        enrich_report_with_ai(session, rep)

    log.info("Daily pipeline complete (%d tokens)", len(scanned_ids))
    return len(scanned_ids)
