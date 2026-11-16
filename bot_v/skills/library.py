"""Bot V's skill library: import skills from outside, safely.

Skills use the agentskills.io layout that OpenJarvis, Hermes and OpenClaw
use: a folder with a ``SKILL.md`` whose YAML frontmatter has ``name`` and
``description``, followed by markdown instructions.

Flow:   fetch  ->  quarantine + scan  ->  person approves  ->  installed

    data/skills/quarantine/<name>/        fetched, not trusted yet
    data/skills/quarantine/<name>.json    where it came from + scan report
    data/skills/installed/<name>/         approved skills
    data/skills/skills.lock.json          provenance + file hashes of installed skills

Installed skills are instructions only: Bot V adds the relevant ones to the
model's context. It never runs scripts that come with a skill.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from bot_v.config import settings
from bot_v.skills.scanner import Finding, scan_dir

NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9]|-(?!-))*[a-z0-9]$|^[a-z0-9]$")
MAX_NAME = 64
SPEC_MAX_DESCRIPTION = 1024  # agentskills.io limit
MAX_DESCRIPTION = 4096  # longer than the spec is accepted with a finding
MAX_FILES = 200
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 5_000_000
MAX_SKILLS_PER_FETCH = 50
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}

_GITHUB_TREE = re.compile(r"^(https://github\.com/[^/]+/[^/]+?)(?:\.git)?/tree/([^/]+)(?:/(.+))?/?$")

# clone(url, dest, ref) -> commit id
Cloner = Callable[[str, Path, Optional[str]], str]


class SkillError(Exception):
    """A skill could not be fetched, approved or loaded."""


def git_clone(url: str, dest: Path, ref: Optional[str] = None, timeout: int = 180) -> str:
    """Shallow-clone a public https git repo without hooks, submodules or symlinks."""
    if not url.startswith("https://"):
        raise SkillError("only https:// git URLs are allowed")
    cmd = [
        "git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never",
        "-c", "core.symlinks=false", "clone", "--depth", "1", "--no-recurse-submodules", "--quiet",
    ]
    if ref:
        cmd += ["--branch", ref]
    cmd += ["--", url, str(dest)]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout, env=env)
        head = subprocess.run(
            ["git", "-C", str(dest), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=30, env=env,
        )
    except FileNotFoundError as exc:
        raise SkillError("git is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise SkillError(f"git clone timed out: {url}") from exc
    except subprocess.CalledProcessError as exc:
        raise SkillError(f"git clone failed: {(exc.stderr or '').strip()[:300]}") from exc
    return head.stdout.strip()


def parse_skill_md(path: Path) -> Tuple[Dict[str, Any], str]:
    """Return (frontmatter, markdown body) of a SKILL.md file."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillError(f"{path}: SKILL.md must start with a '---' frontmatter block")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                meta = yaml.safe_load("\n".join(lines[1:i])) or {}
            except yaml.YAMLError as exc:
                raise SkillError(f"{path}: invalid YAML frontmatter: {exc}") from exc
            if not isinstance(meta, dict):
                raise SkillError(f"{path}: frontmatter must be a mapping")
            return meta, "\n".join(lines[i + 1:]).strip()
    raise SkillError(f"{path}: frontmatter block is not closed with '---'")


def validate_meta(meta: Dict[str, Any]) -> Tuple[str, str, List[Finding]]:
    """Return (name, description, findings) or raise SkillError."""
    name = meta.get("name")
    description = meta.get("description")
    if not isinstance(name, str) or not name:
        raise SkillError("frontmatter needs a 'name'")
    if not isinstance(description, str) or not description.strip():
        raise SkillError(f"skill {name!r}: frontmatter needs a 'description'")
    if len(name) > MAX_NAME or not NAME_RE.match(name):
        raise SkillError(
            f"invalid skill name {name!r}: use lowercase letters, digits and single hyphens (max {MAX_NAME})"
        )
    if len(description) > MAX_DESCRIPTION:
        raise SkillError(f"skill {name!r}: description is longer than {MAX_DESCRIPTION} characters")
    findings = []
    if len(description) > SPEC_MAX_DESCRIPTION:
        findings.append(Finding(
            "medium", "spec", f"description is longer than the agentskills.io limit ({SPEC_MAX_DESCRIPTION})",
            "SKILL.md"))
    return name, description.strip(), findings


def _words(text: str) -> set:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) >= 3}


class SkillLibrary:
    def __init__(self, root: Optional[Path] = None, cloner: Optional[Cloner] = None):
        self.root = Path(root) if root else settings.data_dir / "skills"
        self.quarantine_dir = self.root / "quarantine"
        self.installed_dir = self.root / "installed"
        self.lock_path = self.root / "skills.lock.json"
        self._clone = cloner or git_clone

    # ------------------------------------------------------------- helpers
    def _ensure_dirs(self) -> None:
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.installed_dir.mkdir(parents=True, exist_ok=True)

    def _load_lock(self) -> Dict[str, Any]:
        if not self.lock_path.exists():
            return {}
        try:
            return json.loads(self.lock_path.read_text(encoding="utf-8"))
        except ValueError:
            return {}

    def _save_lock(self, lock: Dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.lock_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.lock_path)

    @staticmethod
    def _check_name(name: str) -> str:
        if not isinstance(name, str) or len(name) > MAX_NAME or not NAME_RE.match(name):
            raise SkillError(f"invalid skill name {name!r}")
        return name

    @staticmethod
    def _find_skill_dirs(base: Path) -> List[Path]:
        if (base / "SKILL.md").is_file():
            return [base]
        found = []
        for skill_md in sorted(base.rglob("SKILL.md")):
            rel = skill_md.relative_to(base)
            if any(part in SKIP_DIRS for part in rel.parts) or len(rel.parts) > 5:
                continue
            if skill_md.is_file() and not skill_md.is_symlink():
                found.append(skill_md.parent)
        return found[:MAX_SKILLS_PER_FETCH]

    @staticmethod
    def _copy_tree(src: Path, dst: Path) -> List[Finding]:
        """Copy regular files only; drop symlinks and executable bits."""
        notes: List[Finding] = []
        total = 0
        count = 0
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            if path.is_symlink():
                notes.append(Finding("medium", "symlink", "symbolic link was not copied", rel.as_posix()))
                continue
            if not path.is_file():
                continue
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                notes.append(Finding("medium", "too_large", f"file over {MAX_FILE_BYTES} bytes was not copied", rel.as_posix()))
                continue
            count += 1
            total += size
            if count > MAX_FILES or total > MAX_TOTAL_BYTES:
                raise SkillError(f"skill is too big (max {MAX_FILES} files / {MAX_TOTAL_BYTES} bytes)")
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            os.chmod(target, 0o644)
        return notes

    def _parse_source(self, source: str, subdir: Optional[str], ref: Optional[str]):
        m = _GITHUB_TREE.match(source)
        if m:
            source, ref, tree_path = m.group(1), ref or m.group(2), m.group(3)
            subdir = subdir or tree_path
        return source, subdir, ref

    # --------------------------------------------------------------- fetch
    def fetch(self, source: str, subdir: Optional[str] = None, ref: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch skills from an https git URL or a local folder into quarantine.

        Returns one entry per skill found: its name, scan verdict and counts,
        or the error that stopped it.
        """
        self._ensure_dirs()
        source, subdir, ref = self._parse_source(source.strip(), subdir, ref)
        is_remote = source.startswith(("https://", "http://", "git@", "ssh://", "file://"))

        with tempfile.TemporaryDirectory(dir=self.root, prefix=".fetch-") as tmp:
            commit = None
            if is_remote:
                checkout = Path(tmp) / "repo"
                commit = self._clone(source, checkout, ref)
            else:
                checkout = Path(source).expanduser().resolve()
                if not checkout.is_dir():
                    raise SkillError(f"not a folder or https git URL: {source}")

            base = checkout
            if subdir:
                base = (checkout / subdir).resolve()
                if not base.is_relative_to(checkout.resolve()) or not base.is_dir():
                    raise SkillError(f"subfolder not found in source: {subdir}")

            skill_dirs = self._find_skill_dirs(base)
            if not skill_dirs:
                raise SkillError("no SKILL.md found in the source")

            results = []
            for skill_dir in skill_dirs:
                rel_path = skill_dir.relative_to(checkout).as_posix() if skill_dir != checkout else ""
                try:
                    meta, _ = parse_skill_md(skill_dir / "SKILL.md")
                    name, description, spec_notes = validate_meta(meta)
                except SkillError as exc:
                    results.append({"path": rel_path, "status": "error", "error": str(exc)})
                    continue

                target = self.quarantine_dir / name
                if target.exists():
                    shutil.rmtree(target)
                target.mkdir(parents=True)
                try:
                    notes = self._copy_tree(skill_dir, target)
                except SkillError as exc:
                    shutil.rmtree(target, ignore_errors=True)
                    results.append({"name": name, "path": rel_path, "status": "error", "error": str(exc)})
                    continue

                report = scan_dir(target)
                report.findings = spec_notes + notes + report.findings
                record = {
                    "name": name,
                    "description": description,
                    "source": source if is_remote else str(checkout),
                    "subpath": rel_path,
                    "ref": ref,
                    "commit": commit,
                    "fetched_at": time.time(),
                    "report": report.to_dict(),
                }
                (self.quarantine_dir / f"{name}.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                results.append({
                    "name": name,
                    "path": rel_path,
                    "status": "quarantined",
                    "verdict": report.verdict,
                    "counts": report.counts(),
                })
            return results

    # ------------------------------------------------------------ decisions
    def report(self, name: str) -> Dict[str, Any]:
        self._check_name(name)
        meta = self.quarantine_dir / f"{name}.json"
        if not meta.exists():
            raise SkillError(f"no quarantined skill named {name!r}")
        return json.loads(meta.read_text(encoding="utf-8"))

    def approve(self, name: str, *, allow_high_risk: bool = False, approved_by: str = "user") -> Dict[str, Any]:
        """Move a quarantined skill into the installed library."""
        record = self.report(name)
        src = self.quarantine_dir / name
        if not src.is_dir():
            raise SkillError(f"quarantined files for {name!r} are missing")

        # Re-scan: the files must still be exactly what the person reviewed.
        current = scan_dir(src)
        reviewed = record["report"]
        if current.tree_sha256 != reviewed["tree_sha256"]:
            raise SkillError(f"{name!r} changed after it was scanned; fetch it again")
        if reviewed["verdict"] == "blocked" and not allow_high_risk:
            raise SkillError(
                f"{name!r} has high-risk findings; approve with allow_high_risk only after reading them"
            )

        self._ensure_dirs()
        dst = self.installed_dir / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(src), str(dst))
        (self.quarantine_dir / f"{name}.json").unlink()

        lock = self._load_lock()
        lock[name] = {
            "description": record["description"],
            "source": record["source"],
            "subpath": record.get("subpath"),
            "ref": record.get("ref"),
            "commit": record.get("commit"),
            "tree_sha256": current.tree_sha256,
            "verdict": reviewed["verdict"],
            "counts": reviewed["counts"],
            "approved_by": approved_by,
            "approved_at": time.time(),
            "high_risk_override": bool(allow_high_risk and reviewed["verdict"] == "blocked"),
        }
        self._save_lock(lock)
        return {"name": name, "status": "installed", **lock[name]}

    def reject(self, name: str) -> None:
        self._check_name(name)
        shutil.rmtree(self.quarantine_dir / name, ignore_errors=True)
        meta = self.quarantine_dir / f"{name}.json"
        if meta.exists():
            meta.unlink()

    def remove(self, name: str) -> None:
        self._check_name(name)
        shutil.rmtree(self.installed_dir / name, ignore_errors=True)
        lock = self._load_lock()
        if lock.pop(name, None) is not None:
            self._save_lock(lock)

    # ------------------------------------------------------------- reading
    def list(self) -> Dict[str, List[Dict[str, Any]]]:
        lock = self._load_lock()
        installed = [
            {"name": n, "description": e.get("description", ""), "source": e.get("source"),
             "verdict": e.get("verdict"), "commit": e.get("commit")}
            for n, e in sorted(lock.items())
        ]
        quarantined = []
        if self.quarantine_dir.exists():
            for meta in sorted(self.quarantine_dir.glob("*.json")):
                try:
                    rec = json.loads(meta.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                quarantined.append({
                    "name": rec.get("name"), "description": rec.get("description", ""),
                    "source": rec.get("source"), "verdict": rec["report"]["verdict"],
                    "counts": rec["report"]["counts"],
                })
        return {"installed": installed, "quarantined": quarantined}

    def verify(self) -> List[Dict[str, Any]]:
        """Check installed skills still match the hashes recorded at approval."""
        out = []
        for name, entry in sorted(self._load_lock().items()):
            path = self.installed_dir / name
            if not path.is_dir():
                out.append({"name": name, "ok": False, "reason": "missing"})
                continue
            ok = scan_dir(path).tree_sha256 == entry.get("tree_sha256")
            out.append({"name": name, "ok": ok, "reason": "" if ok else "files changed since approval"})
        return out

    def installed(self) -> List[Dict[str, str]]:
        """Installed skills that still match their approved hashes."""
        skills = []
        for entry in self.verify():
            if not entry["ok"]:
                continue
            try:
                meta, body = parse_skill_md(self.installed_dir / entry["name"] / "SKILL.md")
            except SkillError:
                continue
            skills.append({"name": entry["name"], "description": str(meta.get("description", "")), "body": body})
        return skills

    def relevant(self, query: str, limit: int = 2) -> List[Dict[str, str]]:
        """Pick installed skills for a request: named explicitly, or by word overlap."""
        query_words = _words(query)
        lowered = query.lower()
        scored = []
        for skill in self.installed():
            if skill["name"] in lowered:
                scored.append((100, skill))
                continue
            words = _words(skill["name"].replace("-", " ") + " " + skill["description"])
            score = len(query_words & words)
            if score >= 2:
                scored.append((score, skill))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [skill for _, skill in scored[:limit]]

    def context_for(self, query: str, limit: int = 2, max_chars: int = 4000) -> Tuple[List[str], str]:
        """(skill names, instructions block) for the relevant skills; ([], '') if none."""
        skills = self.relevant(query, limit=limit)
        if not skills:
            return [], ""
        parts = ["Installed skills that may help (follow them if they fit the request):"]
        for skill in skills:
            body = skill["body"]
            if len(body) > max_chars:
                body = body[:max_chars] + "\n[...truncated]"
            parts.append(f'<skill name="{skill["name"]}">\n{body}\n</skill>')
        return [s["name"] for s in skills], "\n\n".join(parts)
