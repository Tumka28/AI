"""Command line for Bot V's training data.

    python -m bot_v.learning stats
    python -m bot_v.learning export --format sft --out data/learning/train_sft.jsonl
    python -m bot_v.learning export --format dpo --out data/learning/train_dpo.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from bot_v.learning.dataset import SOURCES, TrainingStore


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bot_v.learning")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats", help="show how many examples were collected")
    exp = sub.add_parser("export", help="write a fine-tuning dataset")
    exp.add_argument("--format", choices=("sft", "dpo"), default="sft")
    exp.add_argument("--out", required=True, help="output .jsonl file")
    exp.add_argument("--system", default=None, help="system prompt to add to SFT examples")
    exp.add_argument(
        "--source", action="append", choices=SOURCES,
        help="only these sources (SFT, repeatable); default: all",
    )
    args = parser.parse_args(argv)

    store = TrainingStore()
    if args.cmd == "stats":
        print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
        return 0
    if args.format == "sft":
        n = store.export_sft(args.out, system=args.system, sources=args.source)
    else:
        n = store.export_dpo(args.out)
    print(f"wrote {n} {args.format} examples to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
