from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
PROGRAM_RAW_DIR = DATA_DIR / "program_raw"
RESULTS_RAW_DIR = DATA_DIR / "results_raw"
HORSE_CARDS_RAW_DIR = DATA_DIR / "horse_cards_raw"
FEATURES_DIR = DATA_DIR / "features"
BULLETIN_RAW_DIR = DATA_DIR / "bulletin_raw"
ALTILI_WINDOWS_RAW_DIR = DATA_DIR / "altili_windows_raw"
REPORTS_DIR = ROOT / "reports"
MODELS_DIR = ROOT / "models"
AUDIT_DIR = ROOT / "audit"
TAHMINLER_DIR = ROOT / "Tahminler"
META_DIR = DATA_DIR / "meta"


def ensure_dirs() -> None:
    for path in (
        CONFIG_DIR,
        PROGRAM_RAW_DIR,
        RESULTS_RAW_DIR,
        HORSE_CARDS_RAW_DIR,
        FEATURES_DIR,
        REPORTS_DIR,
        MODELS_DIR,
        AUDIT_DIR,
        TAHMINLER_DIR,
        BULLETIN_RAW_DIR,
        ALTILI_WINDOWS_RAW_DIR,
        META_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
