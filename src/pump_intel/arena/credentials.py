from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CREDENTIALS_PATH = Path(".arena-credentials")


@dataclass(frozen=True, slots=True)
class ArenaCredentials:
    api_key: str
    agent_id: str


def load_credentials(path: Path | str | None = None) -> ArenaCredentials:
    """Load arena credentials from a JSON file.

    Resolution order: explicit `path` arg → `ARENA_CREDENTIALS_PATH` env →
    `.arena-credentials` in CWD.
    """
    chosen = path or os.environ.get("ARENA_CREDENTIALS_PATH") or DEFAULT_CREDENTIALS_PATH
    p = Path(chosen).expanduser()
    if not p.exists():
        raise FileNotFoundError(
            f"arena credentials not found at {p}; register first per "
            f"https://arena.dev.fun/skills/arena.md"
        )
    raw = json.loads(p.read_text())
    try:
        return ArenaCredentials(api_key=raw["apiKey"], agent_id=raw["agentId"])
    except (KeyError, TypeError) as e:
        raise ValueError(f"arena credentials at {p} missing required keys: {e}") from e
