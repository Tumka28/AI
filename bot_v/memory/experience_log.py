"""Experience log: every task Bot V handles, as JSON lines.

This is Bot V's record of what it did, which backend did it, and how it went.
It is the raw material for later self-improvement (teacher answers,
fine-tuning datasets), so entries are plain JSON and easy to filter.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from bot_v.config import data_path


class ExperienceLog:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else data_path("experience.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, kind: str, **fields: Any) -> Dict[str, Any]:
        entry = {"ts": time.time(), "kind": kind, **fields}
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return entry

    def tail(self, n: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
