from __future__ import annotations

from pump_intel.clients.solana_rpc import parse_largest_accounts_response


def test_parse_none():
    assert parse_largest_accounts_response(None) == (None, None, None, None)


def test_parse_rate_limited():
    holders, top1, top5, err = parse_largest_accounts_response(
        {"error": "rate_limited", "status": 429}
    )
    assert holders is None and top1 is None and top5 is None
    assert err == "rate_limited"


def test_parse_dict_error():
    holders, _, _, err = parse_largest_accounts_response({"error": {"message": "bad", "code": -32000}})
    assert holders is None
    assert err == "bad"


def test_parse_happy_path():
    resp = {
        "result": {
            "value": [
                {"uiAmount": 50},
                {"uiAmount": 30},
                {"uiAmount": 10},
                {"uiAmount": 5},
                {"uiAmount": 4},
                {"uiAmount": 1},
            ]
        }
    }
    holders, top1, top5, err = parse_largest_accounts_response(resp)
    assert err is None
    assert holders == 6
    assert top1 == 50.0  # 50 / 100 * 100
    assert top5 == 99.0  # (50+30+10+5+4) / 100 * 100


def test_parse_empty_values():
    holders, top1, top5, err = parse_largest_accounts_response({"result": {"value": []}})
    assert (holders, top1, top5, err) == (0, None, None, None)


def test_parse_malformed_amounts():
    resp = {"result": {"value": [{"uiAmount": "abc"}, {"uiAmount": None}]}}
    holders, top1, top5, err = parse_largest_accounts_response(resp)
    assert holders == 2
    assert top1 is None
    assert top5 is None
    assert err is None


def test_parse_uses_uiAmountString_fallback():
    resp = {"result": {"value": [{"uiAmountString": "10"}, {"uiAmountString": "10"}]}}
    holders, top1, _top5, err = parse_largest_accounts_response(resp)
    assert holders == 2
    assert top1 == 50.0
    assert err is None
