from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from psycopg import Connection

from pump_intel.ai_summary.service import generate_ai_markdown
from pump_intel.config import Settings
from pump_intel.db import repository as repo

_TOKEN = re.compile(r"[a-z0-9]{3,}", re.I)


@dataclass
class ReportArtifacts:
    report_id: int
    stats: dict[str, Any]
    structured_markdown: str
    ai_markdown: str | None
    markdown_path: Path


class DailyReportService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def _fetch_day_snapshots(self, conn: Connection, d: date) -> list[dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC'")
            cur.execute(
                """
                WITH day_snaps AS (
                  SELECT *
                  FROM token_snapshots
                  WHERE snapshot_at::date = %(d)s
                ),
                ranked AS (
                  SELECT *,
                    ROW_NUMBER() OVER (PARTITION BY token_id ORDER BY snapshot_at DESC) AS rn
                  FROM day_snaps
                )
                SELECT r.*, t.mint_address, t.name, t.symbol, t.creator_wallet
                FROM ranked r
                JOIN tokens t ON t.id = r.token_id
                WHERE r.rn = 1
                """,
                {"d": d},
            )
            return list(cur.fetchall())

    def _theme_tokens(self, name: str) -> list[str]:
        return _TOKEN.findall(name.lower())

    def build(self, conn: Connection, report_day: date, coins_scanned: int) -> ReportArtifacts:
        rows = self._fetch_day_snapshots(conn, report_day)
        if not rows:
            stats = {
                "report_date": str(report_day),
                "total_coins_scanned_run": coins_scanned,
                "snapshots_for_day": 0,
                "note": "No snapshots recorded for this UTC day yet.",
            }
            md = f"# Pump.fun market report — {report_day}\n\n_No snapshot rows for this UTC day._\n"
            ai_md = generate_ai_markdown(self.settings, stats, md)
            rid = repo.insert_daily_report(
                conn,
                datetime.combine(report_day, datetime.min.time(), tzinfo=timezone.utc),
                stats,
                md,
                ai_md,
            )
            path = self._write_file(report_day, md, ai_md)
            return ReportArtifacts(rid, stats, md, ai_md, path)

        ath_values = [float(r["ath_usd_mcap"] or 0) for r in rows if r.get("ath_usd_mcap")]
        tta = [int(r["time_to_ath_seconds"]) for r in rows if r.get("time_to_ath_seconds")]

        dd_after: list[float] = []
        for r in rows:
            ath = float(r.get("ath_usd_mcap") or 0)
            cur = float(r.get("usd_market_cap") or 0)
            if ath > 0:
                dd_after.append(max(0.0, 1.0 - cur / ath))

        winners = sorted(
            [
                r
                for r in rows
                if r["classification"]
                in ("micro_winner", "bonding_winner", "graduated_winner", "viral_winner")
            ],
            key=lambda r: float(r.get("ath_usd_mcap") or 0),
            reverse=True,
        )[:15]
        rugs = sorted(
            [r for r in rows if r["classification"] in ("soft_rug", "hard_rug")],
            key=lambda r: float(r.get("ath_usd_mcap") or 0),
            reverse=True,
        )[:15]

        fastest = sorted(
            [r for r in rows if r.get("time_to_ath_seconds")],
            key=lambda r: int(r["time_to_ath_seconds"]),
        )[:10]

        themes: Counter[str] = Counter()
        for r in winners:
            themes.update(self._theme_tokens(str(r.get("name") or "")))

        ticker_lens = [len(str(r.get("symbol") or "")) for r in rows]

        ath_by_x: list[float] = []
        ath_by_no_x: list[float] = []
        for r in rows:
            raw = r.get("raw_coin")
            uname = None
            if isinstance(raw, dict):
                uname = raw.get("username")
            athv = float(r.get("ath_usd_mcap") or r.get("usd_market_cap") or 0)
            if isinstance(uname, str) and uname.strip():
                ath_by_x.append(athv)
            else:
                ath_by_no_x.append(athv)

        creator_stats: dict[str, dict[str, float]] = defaultdict(
            lambda: {"wins": 0.0, "rugs": 0.0, "score": 0.0}
        )
        for r in rows:
            cw = str(r.get("creator_wallet") or "")
            cls = str(r.get("classification") or "")
            if cls in ("micro_winner", "bonding_winner", "graduated_winner", "viral_winner"):
                creator_stats[cw]["wins"] += 1
            if cls in ("soft_rug", "hard_rug"):
                creator_stats[cw]["rugs"] += 1
            creator_stats[cw]["score"] += float(r.get("intel_score") or 0)

        top_creators = sorted(
            creator_stats.items(),
            key=lambda kv: (kv[1]["wins"] - kv[1]["rugs"], kv[1]["score"]),
            reverse=True,
        )[:12]

        stats: dict[str, Any] = {
            "report_date": str(report_day),
            "total_coins_scanned_run": coins_scanned,
            "distinct_tokens_snapshotted": len(rows),
            "avg_usd_mcap": mean([float(r.get("usd_market_cap") or 0) for r in rows]) if rows else 0,
            "avg_ath_usd": mean(ath_values) if ath_values else 0,
            "avg_time_to_ath_seconds": mean(tta) if tta else None,
            "avg_drawdown_after_ath": mean(dd_after) if dd_after else None,
            "classification_counts": Counter(str(r["classification"]) for r in rows),
            "top_winner_mints": [r["mint_address"] for r in winners[:5]],
            "top_rug_mints": [r["mint_address"] for r in rugs[:5]],
            "fastest_ath_seconds": int(fastest[0]["time_to_ath_seconds"]) if fastest else None,
            "highest_ath_usd": max(ath_values) if ath_values else None,
            "avg_ticker_length": mean(ticker_lens) if ticker_lens else None,
            "avg_ath_with_x_signal": mean(ath_by_x) if ath_by_x else None,
            "avg_ath_without_x_signal": mean(ath_by_no_x) if ath_by_no_x else None,
        }

        md_lines = [
            f"# Pump.fun market intelligence — {report_day} (UTC)",
            "",
            f"- Total coins scanned this run: **{coins_scanned}**",
            f"- Distinct tokens with snapshots today: **{len(rows)}**",
            f"- Average USD market cap (latest/day): **{stats['avg_usd_mcap']:.2f}**",
            f"- Average ATH (USD): **{stats['avg_ath_usd']:.2f}**",
            f"- Average time to ATH (seconds): **{stats['avg_time_to_ath_seconds'] or 'n/a'}**",
            f"- Average drawdown after ATH (0–1): **{stats['avg_drawdown_after_ath'] or 'n/a'}**",
            f"- Fastest ATH (seconds): **{stats['fastest_ath_seconds'] or 'n/a'}**",
            f"- Highest ATH (USD): **{stats['highest_ath_usd'] or 'n/a'}**",
            "",
            "## Classification mix",
            "",
        ]
        for k, v in stats["classification_counts"].most_common():
            md_lines.append(f"- {k}: {v}")
        md_lines += ["", "## Top winners (by ATH)", ""]
        for r in winners[:10]:
            md_lines.append(
                f"- **{r['symbol']}** — {r['name']} — ATH ${float(r.get('ath_usd_mcap') or 0):,.0f} — {r['classification']}"
            )
        md_lines += ["", "## Top rugs (by ATH)", ""]
        for r in rugs[:10]:
            md_lines.append(
                f"- **{r['symbol']}** — {r['name']} — ATH ${float(r.get('ath_usd_mcap') or 0):,.0f} — {r['classification']}"
            )
        md_lines += ["", "## Fastest ATH climbs", ""]
        for r in fastest[:8]:
            md_lines.append(
                f"- **{r['symbol']}** — {int(r['time_to_ath_seconds'])}s — ATH ${float(r.get('ath_usd_mcap') or 0):,.0f}"
            )
        md_lines += ["", "## Winner name themes (tokenized)", ""]
        for word, c in themes.most_common(12):
            md_lines.append(f"- `{word}`: {c}")
        md_lines += ["", "## Creator wallet signals (heuristic)", ""]
        for addr, agg in top_creators:
            md_lines.append(
                f"- `{addr[:6]}…{addr[-4:]}` — wins {int(agg['wins'])}, rugs {int(agg['rugs'])}, score Σ {agg['score']:.1f}"
            )
        md_lines += [
            "",
            "## Social / X linkage signal vs ATH",
            "",
            f"- Avg ATH with X username signal: **{stats['avg_ath_with_x_signal'] or 'n/a'}**",
            f"- Avg ATH without X username signal: **{stats['avg_ath_without_x_signal'] or 'n/a'}**",
            "",
            "## Final market assessment (rules-based)",
            "",
            self._rules_assessment(rows, stats),
        ]
        structured = "\n".join(md_lines)

        ai_md = generate_ai_markdown(self.settings, stats, structured)

        serializable_stats = {**stats, "classification_counts": dict(stats["classification_counts"])}
        rid = repo.insert_daily_report(
            conn,
            datetime.combine(report_day, datetime.min.time(), tzinfo=timezone.utc),
            serializable_stats,
            structured,
            ai_md,
        )

        patterns = []
        for word, c in themes.most_common(20):
            patterns.append(
                {
                    "pattern_type": "name_token",
                    "pattern_value": word,
                    "occurrence_count": int(c),
                    "metadata": {"bucket": "winner_names"},
                }
            )
        for sym, cnt in Counter(str(r.get("symbol") or "")[:6] for r in winners).most_common(15):
            if sym:
                patterns.append(
                    {
                        "pattern_type": "ticker_prefix",
                        "pattern_value": sym,
                        "occurrence_count": int(cnt),
                        "metadata": {},
                    }
                )
        repo.replace_winner_patterns(conn, rid, patterns)

        path = self._write_file(report_day, structured, ai_md)
        return ReportArtifacts(rid, serializable_stats, structured, ai_md, path)

    def _rules_assessment(self, rows: list[dict[str, Any]], stats: dict[str, Any]) -> str:
        cc: Counter[str] = stats["classification_counts"]
        rugs = cc.get("soft_rug", 0) + cc.get("hard_rug", 0)
        wins = (
            cc.get("micro_winner", 0)
            + cc.get("bonding_winner", 0)
            + cc.get("graduated_winner", 0)
            + cc.get("viral_winner", 0)
        )
        if wins == 0 and rugs == 0:
            return "Mixed/neutral tape: most tokens remain early or unclassified by strict winner/rug gates."
        if rugs > wins * 1.4:
            return "Risk-heavy tape: rug classifications dominate; treat socials and drawdowns as first-class signals."
        if wins > rugs * 1.4:
            return "Speculation-rich tape: multiple bonding/viral winners; liquidity rotation likely elevated."
        return "Balanced chaos: simultaneous winner momentum and rug mechanics; weigh social verification and creator history heavily."

    def _write_file(self, report_day: date, structured: str, ai: str | None) -> Path:
        self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.reports_dir / f"report-{report_day}.md"
        body = structured
        if ai:
            body += "\n\n---\n\n## AI narrative\n\n" + ai
        path.write_text(body, encoding="utf-8")
        return path
