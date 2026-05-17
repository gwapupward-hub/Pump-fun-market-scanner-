from __future__ import annotations

from pump_intel.types import TradeAggregate


def aggregate_trades(
    trades: list[dict], creator_wallet: str, sol_usd: float | None
) -> TradeAggregate:
    buy_sol = 0.0
    sell_sol = 0.0
    largest_sell = 0.0
    dev_sell_sol = 0.0
    count = 0
    for t in trades:
        count += 1
        is_buy = t.get("is_buy")
        if is_buy is None:
            hint = str(t.get("txType") or t.get("type") or t.get("side") or "").lower()
            if "sell" in hint:
                is_buy = False
            elif "buy" in hint:
                is_buy = True
        sol_amt = float(t.get("sol_amount") or t.get("solAmount") or 0)
        user = str(t.get("user") or t.get("trader") or "")
        if is_buy is True:
            buy_sol += sol_amt
        elif is_buy is False:
            sell_sol += sol_amt
            largest_sell = max(largest_sell, sol_amt)
            if user == creator_wallet:
                dev_sell_sol += sol_amt
        else:
            count -= 1
            continue

    usd_rate = sol_usd if sol_usd and sol_usd > 0 else None
    buy_usd = buy_sol * usd_rate if usd_rate else None
    sell_usd = sell_sol * usd_rate if usd_rate else None
    largest_sell_usd = largest_sell * usd_rate if usd_rate else None

    dev_sell_detected = dev_sell_sol >= 5.0 or (
        sell_sol > 0 and dev_sell_sol / sell_sol >= 0.25 and dev_sell_sol >= 1.0
    )

    return TradeAggregate(
        buy_volume_usd=buy_usd,
        sell_volume_usd=sell_usd,
        trade_count=count,
        largest_sell_notional_usd=largest_sell_usd,
        dev_sell_detected=dev_sell_detected,
    )
