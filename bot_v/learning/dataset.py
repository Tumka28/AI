"""Training examples Bot V collects from its teacher.

Each line of ``data/learning/examples.jsonl`` is one example:

    {"id", "ts", "prompt", "answer", "rejected"?, "source", ...metadata}

``source`` says where the answer came from:

    teacher_answer      the teacher answered (the local model failed or was skipped)
    teacher_correction  the teacher rewrote a weak local answer ("rejected" = local answer)
    local_verified      the local answer was graded good by the teacher

Exports:
    SFT (supervised fine-tuning): {"messages": [system?, user, assistant]} per line,
        the chat format used by TRL, Unsloth, axolotl and LLaMA-Factory.
    DPO (preference pairs): {"prompt", "chosen", "rejected"} per line, from
        teacher corrections.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional

from bot_v.config import data_path

SOURCES = ("teacher_answer", "teacher_correction", "local_verified")


class TrainingStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else data_path("learning", "examples.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def add(
        self,
        prompt: str,
        answer: str,
        *,
        source: str,
        rejected: Optional[str] = None,
        **meta: Any,
    ) -> Dict[str, Any]:
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
        if not prompt.strip() or not answer.strip():
            raise ValueError("prompt and answer must be non-empty")
        example: Dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "ts": time.time(),
            "prompt": prompt,
            "answer": answer,
            "source": source,
        }
        if rejected:
            example["rejected"] = rejected
        example.update({k: v for k, v in meta.items() if v is not None})
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(example, ensure_ascii=False) + "\n")
        return example

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict) and item.get("prompt") and item.get("answer"):
                    yield item

    def stats(self) -> Dict[str, Any]:
        items = list(self)
        return {
            "path": str(self.path),
            "total": len(items),
            "by_source": dict(Counter(i.get("source", "?") for i in items)),
            "preference_pairs": sum(1 for i in items if i.get("rejected")),
        }

    @staticmethod
    def _key(*parts: str) -> str:
        return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()

    def export_sft(
        self,
        out: Path,
        *,
        system: Optional[str] = None,
        sources: Optional[Iterable[str]] = None,
    ) -> int:
        """Write SFT chat examples to ``out``. Returns how many were written."""
        wanted = set(sources) if sources else None
        seen = set()
        count = 0
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            for item in self:
                if wanted is not None and item.get("source") not in wanted:
                    continue
                key = self._key(item["prompt"], item["answer"])
                if key in seen:
                    continue
                seen.add(key)
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": item["prompt"]})
                messages.append({"role": "assistant", "content": item["answer"]})
                fh.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
                count += 1
        return count

    def export_dpo(self, out: Path) -> int:
        """Write preference pairs (teacher answer preferred over local)."""
        seen = set()
        count = 0
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            for item in self:
                rejected = item.get("rejected")
                if not rejected or rejected == item["answer"]:
                    continue
                key = self._key(item["prompt"], item["answer"], rejected)
                if key in seen:
                    continue
                seen.add(key)
                fh.write(
                    json.dumps(
                        {"prompt": item["prompt"], "chosen": item["answer"], "rejected": rejected},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                count += 1
        return count
