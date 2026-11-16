"""Keep the local Bot V checkout up to date with GitHub.

Only safe, automatic updates:
- the checkout is on the ``main`` branch,
- no tracked file has local changes,
- the update is a fast-forward (nothing local that GitHub does not have).

Otherwise nothing is touched and the reason is reported.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from bot_v.config import PROJECT_ROOT

BRANCH = "main"
REMOTE = "origin"
FETCH_EVERY_SECONDS = 10  # pressing F5 repeatedly does not hammer GitHub

_fetch_lock = threading.Lock()
_last_fetch: Dict[str, float] = {}


class UpdateError(RuntimeError):
    pass


def _git(repo: Path, *args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    git = shutil.which("git")
    if git is None:
        raise UpdateError("git is not installed")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # never hang waiting for a password
    try:
        return subprocess.run([git, *args], cwd=repo, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        raise UpdateError(f"git {args[0]} timed out") from exc


def _out(repo: Path, *args: str, timeout: float = 60) -> str:
    res = _git(repo, *args, timeout=timeout)
    if res.returncode != 0:
        raise UpdateError(f"git {' '.join(args)} failed: {(res.stderr or res.stdout).strip()[:300]}")
    return res.stdout.strip()


def is_checkout(repo: Path = PROJECT_ROOT) -> bool:
    return (Path(repo) / ".git").exists() and shutil.which("git") is not None


def requirements_hash(repo: Path = PROJECT_ROOT) -> str:
    h = hashlib.sha256()
    for path in sorted(Path(repo).glob("requirements*.txt")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def fetch(repo: Path = PROJECT_ROOT, force: bool = False) -> bool:
    """git fetch origin main, at most every FETCH_EVERY_SECONDS. Returns True if fetched."""
    key = str(Path(repo).resolve())
    with _fetch_lock:
        if not force and time.time() - _last_fetch.get(key, 0) < FETCH_EVERY_SECONDS:
            return False
        _last_fetch[key] = time.time()
    res = _git(repo, "fetch", "--quiet", REMOTE, BRANCH, timeout=30)
    if res.returncode != 0:
        raise UpdateError(f"cannot reach GitHub: {(res.stderr or '').strip()[:200]}")
    return True


def status(repo: Path = PROJECT_ROOT, do_fetch: bool = True, force: bool = False) -> Dict[str, Any]:
    """Where the checkout stands compared with GitHub's main branch."""
    repo = Path(repo)
    info: Dict[str, Any] = {"can_update": False, "behind": 0, "ahead": 0}
    if not is_checkout(repo):
        return {**info, "reason": "not a git checkout (or git is missing)"}
    try:
        if do_fetch:
            fetch(repo, force=force)
        branch = _out(repo, "rev-parse", "--abbrev-ref", "HEAD")
        head = _out(repo, "rev-parse", "HEAD")
        remote = _out(repo, "rev-parse", f"{REMOTE}/{BRANCH}")
        behind = int(_out(repo, "rev-list", "--count", f"HEAD..{REMOTE}/{BRANCH}"))
        ahead = int(_out(repo, "rev-list", "--count", f"{REMOTE}/{BRANCH}..HEAD"))
        dirty = [line[3:] for line in _out(repo, "status", "--porcelain", "--untracked-files=no").splitlines()]
    except UpdateError as exc:
        return {**info, "reason": str(exc)}

    info.update({"branch": branch, "head": head[:7], "remote_head": remote[:7],
                 "behind": behind, "ahead": ahead, "dirty": dirty})
    if behind == 0:
        info["reason"] = "up to date"
    elif branch != BRANCH:
        info["reason"] = f"on branch {branch!r}, updates only run on {BRANCH!r}"
    elif dirty:
        info["reason"] = f"local changes in {len(dirty)} file(s); commit or stash them first"
    elif ahead:
        info["reason"] = f"{ahead} local commit(s) not on GitHub; cannot fast-forward"
    else:
        info["can_update"] = True
        info["reason"] = f"{behind} new commit(s) on GitHub"
    return info


def apply(repo: Path = PROJECT_ROOT) -> Dict[str, Any]:
    """Fast-forward to GitHub's main if it is safe. Never overwrites local work."""
    repo = Path(repo)
    info = status(repo, do_fetch=True, force=True)
    if not info["can_update"]:
        return {"updated": False, **info}
    old = _out(repo, "rev-parse", "HEAD")
    req_before = requirements_hash(repo)
    res = _git(repo, "merge", "--ff-only", f"{REMOTE}/{BRANCH}")
    if res.returncode != 0:
        return {"updated": False, **info, "reason": f"update failed: {(res.stderr or res.stdout).strip()[:300]}"}
    new = _out(repo, "rev-parse", "HEAD")
    files: List[str] = _out(repo, "diff", "--name-only", old, new).splitlines()
    return {
        "updated": True,
        "from": old[:7],
        "to": new[:7],
        "commits": info["behind"],
        "files": files[:100],
        "requirements_changed": requirements_hash(repo) != req_before,
    }


def pip_install(repo: Path = PROJECT_ROOT, python: Optional[str] = None) -> bool:
    """Install the requirements again (after they changed). Returns True on success."""
    import sys

    files = [f for f in ("requirements-dev.txt", "requirements-openjarvis.txt") if (Path(repo) / f).exists()]
    if not files:
        files = ["requirements.txt"]
    cmd = [python or sys.executable, "-m", "pip", "install", "--quiet"]
    for f in files:
        cmd += ["-r", f]
    return subprocess.run(cmd, cwd=repo).returncode == 0
