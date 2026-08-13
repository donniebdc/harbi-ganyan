from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BANNED_FEATURE_PATTERNS = [
    r"\bagf\b",
    r"ganyan",
    r"odds",
    r"oran",
    r"bahis",
    r"ikramiye",
    r"odeme",
    r"payout",
    r"finish",
    r"finishrank",
    r"sonuc",
    r"sira$",
    r"kazanan",
    r"winner",
    r"v16",
    r"\bana\b",
    r"meta_prob",
    r"pegadrom",
    r"tahminmakinesi",
    r"external",
]

BANNED_PATH_PARTS = {
    "Harbi_Ganyan_Analiz",
    "Analizler",
    "TahminSonuclari",
    "TahminSonuçları",
    "Sonuclar JSON",
    "Yedekler",
    "__pycache__",
}


@dataclass
class AuditResult:
    ok: bool
    errors: list[str]
    warnings: list[str]

    def raise_if_failed(self) -> None:
        if not self.ok:
            detail = "\n".join(f"- {e}" for e in self.errors)
            raise RuntimeError(f"Leakage audit failed:\n{detail}")


def audit_feature_names(feature_names: Iterable[str]) -> AuditResult:
    errors: list[str] = []
    compiled = [re.compile(p, re.IGNORECASE) for p in BANNED_FEATURE_PATTERNS]
    for name in feature_names:
        low = str(name)
        for pattern in compiled:
            if pattern.search(low):
                errors.append(f"Banned feature name: {name}")
                break
    return AuditResult(ok=not errors, errors=errors, warnings=[])


def audit_paths(paths: Iterable[Path]) -> AuditResult:
    errors: list[str] = []
    for path in paths:
        parts = set(path.parts)
        bad = sorted(parts.intersection(BANNED_PATH_PARTS))
        if bad:
            errors.append(f"Banned path component {bad}: {path}")
    return AuditResult(ok=not errors, errors=errors, warnings=[])


def write_audit(path: Path, result: AuditResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

