"""Static checks for skills fetched from outside.

Nothing here runs the skill. The scanner reads every file and reports:

- high:   things that should never be in a skill (pipe-to-shell installers,
          reverse shells, credential paths, hidden Unicode, prompt-injection
          phrases, miners). A skill with a high finding is blocked unless the
          user explicitly overrides.
- medium: things a person should look at (scripts, network or process calls,
          package installs, sudo, binaries, hidden HTML comments).

It is a filter, not a proof of safety: it catches common patterns and makes
the user look before a skill is installed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List

SCRIPT_SUFFIXES = {
    ".py", ".sh", ".bash", ".zsh", ".fish", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl",
    ".php", ".ps1", ".psm1", ".bat", ".cmd", ".lua", ".go", ".rs", ".java", ".kt",
    ".swift", ".c", ".cc", ".cpp", ".r", ".applescript",
}
MARKDOWN_SUFFIXES = {".md", ".markdown", ".txt", ".rst"}

# Direction overrides can make text/code read differently than it runs ("Trojan Source").
_BIDI_CONTROLS = re.compile("[‪-‮⁦-⁩]")
# Zero-width characters can hide text; they also appear legitimately (emoji joiners).
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")

# (severity, rule id, message, pattern, where: "any" | "script" | "text")
_RULES = [
    ("high", "pipe_to_shell", "downloads and runs code (… | sh)",
     re.compile(r"\b(curl|wget|iwr|Invoke-WebRequest)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b|\biex\s*\(", re.I), "any"),
    ("high", "encoded_exec", "runs decoded/obfuscated code",
     re.compile(r"base64\s+(-d|--decode)[^\n]*\|\s*(ba|z)?sh|\b(eval|exec)\s*\(\s*(base64|b64decode|codecs\.decode|bytes\.fromhex|__import__|atob)", re.I), "any"),
    ("high", "destructive_rm", "deletes the root or home directory",
     re.compile(r"\brm\s+-[a-z]*r[a-z]*\s+(-[a-z]+\s+)*(/|~|\$HOME)(\s|$|/\*)", re.I), "any"),
    ("high", "reverse_shell", "reverse-shell pattern",
     re.compile(r"/dev/tcp/|\bnc(at)?\s+(-[a-z]*e|-c)\s|bash\s+-i\s+>&|\bsocat\b[^\n]*exec", re.I), "any"),
    ("high", "credential_access", "touches credentials or private keys",
     re.compile(r"\.ssh/|\bid_(rsa|ed25519|ecdsa)\b|\.aws/credentials|\.netrc\b|\.git-credentials|/etc/shadow|\.gnupg/|\bkeychain\b", re.I), "any"),
    ("high", "crypto_miner", "crypto-miner reference",
     re.compile(r"\bxmrig\b|stratum\+tcp|\bcoinhive\b|\bminerd\b", re.I), "any"),
    ("high", "prompt_injection", "tries to override the assistant's instructions",
     re.compile(
         r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts?)"
         r"|disregard\s+(all\s+|the\s+|your\s+)?(system|previous|prior)\s+(prompt|instructions|rules)"
         r"|you\s+are\s+no\s+longer\s+bound|reveal\s+(your\s+|the\s+)?(system\s+prompt|hidden\s+instructions)"
         r"|do\s+not\s+(tell|inform)\s+the\s+user", re.I), "text"),
    ("medium", "secret_handling", "talks about sending secrets (check where they go)",
     re.compile(r"\b(send|post|upload|exfiltrat\w*|forward)\b[^\n]{0,80}\b(api[_ -]?keys?|tokens?|passwords?|secrets?|credentials?|private\s+keys?)\b", re.I), "any"),
    ("medium", "network_call", "makes network requests",
     re.compile(r"\brequests\.(get|post|put|delete|patch)\b|\burllib\.request\b|\bhttp\.client\b|\bfetch\(|\baxios\b|\bcurl\s|\bwget\s|Invoke-WebRequest|\bsocket\.socket\b", re.I), "script"),
    ("medium", "process_exec", "starts other programs or evaluates code",
     re.compile(r"\bsubprocess\b|\bos\.(system|popen|exec\w*)\b|\bchild_process\b|\beval\s*\(|\bexec\s*\(|Runtime\.getRuntime", re.I), "script"),
    ("medium", "package_install", "installs packages",
     re.compile(r"\bpip3?\s+install\b|\bnpm\s+(i|install|add)\b|\bapt(-get)?\s+install\b|\bbrew\s+install\b|\bgem\s+install\b|\bcargo\s+install\b", re.I), "any"),
    ("medium", "sudo", "uses sudo", re.compile(r"\bsudo\s", re.I), "any"),
    ("medium", "permissions", "loosens file permissions",
     re.compile(r"\bchmod\s+(-R\s+)?(777|a\+rwx|[ug]?\+s)\b", re.I), "any"),
    ("medium", "hidden_comment", "hidden HTML comment (not visible when rendered)",
     re.compile(r"<!--[\s\S]*?-->"), "text"),
]


@dataclass
class Finding:
    severity: str
    rule: str
    message: str
    file: str
    line: int = 0
    excerpt: str = ""


@dataclass
class FileInfo:
    path: str
    size: int
    sha256: str
    kind: str  # "instructions" | "script" | "text" | "binary"


@dataclass
class ScanReport:
    files: List[FileInfo] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    tree_sha256: str = ""

    @property
    def verdict(self) -> str:
        severities = {f.severity for f in self.findings}
        if "high" in severities:
            return "blocked"
        if "medium" in severities:
            return "review"
        return "clean"

    def counts(self) -> Dict[str, int]:
        out = {"high": 0, "medium": 0}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "counts": self.counts(),
            "tree_sha256": self.tree_sha256,
            "files": [asdict(f) for f in self.files],
            "findings": [asdict(f) for f in self.findings],
        }


def _is_text(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _kind(rel: str, is_text: bool) -> str:
    suffix = Path(rel).suffix.lower()
    if not is_text:
        return "binary"
    if Path(rel).name == "SKILL.md":
        return "instructions"
    if suffix in SCRIPT_SUFFIXES:
        return "script"
    return "text"


def tree_hash(files: List[FileInfo]) -> str:
    h = hashlib.sha256()
    for f in sorted(files, key=lambda x: x.path):
        h.update(f"{f.path}\0{f.sha256}\n".encode("utf-8"))
    return h.hexdigest()


def scan_dir(root: Path) -> ScanReport:
    """Scan every regular file under ``root`` (symlinks are never followed)."""
    root = Path(root)
    report = ScanReport()
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            report.findings.append(Finding("medium", "symlink", "symbolic link (ignored)", rel))
            continue
        if not path.is_file():
            continue
        data = path.read_bytes()
        text_ok = _is_text(data)
        kind = _kind(rel, text_ok)
        report.files.append(FileInfo(rel, len(data), hashlib.sha256(data).hexdigest(), kind))

        if kind == "binary":
            report.findings.append(Finding("medium", "binary", "binary file cannot be reviewed", rel))
            continue
        if kind == "script":
            report.findings.append(
                Finding("medium", "script", "contains a script (Bot V never runs skill scripts)", rel)
            )

        text = data.decode("utf-8")
        if text.startswith("﻿"):  # a byte-order mark at the start is harmless
            text = text[1:]
        is_textual = kind in ("instructions", "text") or Path(rel).suffix.lower() in MARKDOWN_SUFFIXES
        bidi_line = zero_width_line = 0
        for lineno, line in enumerate(text.splitlines(), 1):
            if not bidi_line and _BIDI_CONTROLS.search(line):
                bidi_line = lineno
            if not zero_width_line and _ZERO_WIDTH.search(line):
                zero_width_line = lineno
        if bidi_line:
            report.findings.append(Finding(
                "high", "bidi_unicode", "direction-changing characters (text may not read as it runs)", rel, bidi_line))
        if zero_width_line:
            report.findings.append(Finding(
                "medium", "zero_width_unicode", "invisible zero-width characters", rel, zero_width_line))
        for severity, rule, message, pattern, where in _RULES:
            if where == "script" and kind != "script":
                continue
            if where == "text" and not is_textual:
                continue
            for match in pattern.finditer(text):
                lineno = text.count("\n", 0, match.start()) + 1
                excerpt = match.group(0).strip().replace("\n", " ")[:120]
                report.findings.append(Finding(severity, rule, message, rel, lineno, excerpt))
                break  # one finding per rule per file is enough

    report.tree_sha256 = tree_hash(report.files)
    return report
