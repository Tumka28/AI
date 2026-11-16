"""Command line for Bot V's skill library.

    python -m bot_v.skills fetch https://github.com/anthropics/skills --subdir skills/pdf
    python -m bot_v.skills fetch ./my-skills
    python -m bot_v.skills report <name>
    python -m bot_v.skills approve <name> [--allow-high-risk]
    python -m bot_v.skills reject <name>
    python -m bot_v.skills remove <name>
    python -m bot_v.skills list
    python -m bot_v.skills verify
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from bot_v.skills.library import SkillError, SkillLibrary


def _print(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bot_v.skills")
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="fetch skills into quarantine and scan them")
    f.add_argument("source", help="https git URL or local folder")
    f.add_argument("--subdir", default=None, help="folder inside the source")
    f.add_argument("--ref", default=None, help="git branch or tag")
    for cmd in ("report", "reject", "remove"):
        sub.add_parser(cmd).add_argument("name")
    a = sub.add_parser("approve", help="install a quarantined skill")
    a.add_argument("name")
    a.add_argument("--allow-high-risk", action="store_true",
                   help="install even with high-risk findings (only after reading them)")
    sub.add_parser("list")
    sub.add_parser("verify")
    args = parser.parse_args(argv)

    lib = SkillLibrary()
    try:
        if args.cmd == "fetch":
            _print(lib.fetch(args.source, subdir=args.subdir, ref=args.ref))
        elif args.cmd == "report":
            _print(lib.report(args.name))
        elif args.cmd == "approve":
            _print(lib.approve(args.name, allow_high_risk=args.allow_high_risk, approved_by="cli"))
        elif args.cmd == "reject":
            lib.reject(args.name)
            print(f"rejected {args.name}")
        elif args.cmd == "remove":
            lib.remove(args.name)
            print(f"removed {args.name}")
        elif args.cmd == "list":
            _print(lib.list())
        elif args.cmd == "verify":
            _print(lib.verify())
    except SkillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
