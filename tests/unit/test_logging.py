from __future__ import annotations

import json
import logging

from pump_intel.logging import configure_logging, new_correlation_id


def test_json_log_includes_correlation_id(capsys):
    configure_logging(level="INFO", fmt="json")
    cid = new_correlation_id()
    logging.getLogger("test").info("hello world", extra={"k": "v"})
    out = capsys.readouterr().out.strip().splitlines()[-1]
    parsed = json.loads(out)
    assert parsed["msg"] == "hello world"
    assert parsed["correlation_id"] == cid
    assert parsed["k"] == "v"


def test_text_format(capsys):
    configure_logging(level="INFO", fmt="text")
    logging.getLogger("test").info("plain text line")
    out = capsys.readouterr().out
    assert "plain text line" in out
