from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from water_ledger.paths import ROOT


DEFAULT_EXCLUDES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "data",
    "examples",
    "node_modules",
    "outputs",
    "private",
    "venv",
    "web_app/static/design",
}

HIGH_RISK_SUFFIXES = {
    ".csv",
    ".tsv",
    ".xlsx",
    ".xls",
    ".pdf",
    ".sqlite",
    ".db",
    ".log",
}

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".sql",
    ".html",
    ".css",
    ".js",
}

PATTERNS = {
    "secret-assignment": re.compile(r"(?i)(api[_-]?key|secret|token|password|密钥)\s*[:=]\s*['\"]?[^'\"\\s]+"),
    "filename-password": re.compile(r"密码\d+"),
    "long-card-number": re.compile(r"(?<![.\w])\d{12,19}(?!\w)"),
    "phone-number-cn": re.compile(r"\b1[3-9]\d{9}\b"),
}

ALLOWLIST_TEXT = {
    "真实账单、数据库、输出和密钥默认放在 `private/`",
    "Secrets and local environment",
    "secret_key=conf_value",
}


@dataclass
class Finding:
    path: str
    kind: str
    detail: str


def should_skip(path: Path) -> bool:
    text = path.as_posix()
    return any(part in path.parts or text.startswith(part + "/") for part in DEFAULT_EXCLUDES)


def is_allowed(line: str) -> bool:
    return any(item in line for item in ALLOWLIST_TEXT)


def scan_public_workspace(root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if should_skip(rel) or not path.is_file():
            continue
        suffixes = path.suffixes
        suffix = path.suffix.lower()
        if suffix in HIGH_RISK_SUFFIXES or any(item.lower() in HIGH_RISK_SUFFIXES for item in suffixes):
            findings.append(Finding(str(rel), "high-risk-file", f"public {suffix or 'data'} file"))
        name = path.name
        for kind, pattern in PATTERNS.items():
            if pattern.search(name):
                findings.append(Finding(str(rel), kind, "matched filename"))
        if suffix not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if is_allowed(line):
                continue
            if "re.compile" in line or "re.search" in line or "decrypt(password" in line:
                continue
            for kind, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(Finding(str(rel), kind, f"line {lineno}: {line.strip()[:120]}"))
    return findings
