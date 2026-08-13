from __future__ import annotations

"""
bulletin.py  –  Bulten/editorial skor yukleyicisi.

JSON formati (data/bulletin_raw/YYYY-MM-DD.json):
{
  "date": "2026-06-12",
  "hippodromes": {
    "BURSA": {
      "races": {
        "1": {
          "horses": [
            {"horse_no": 2, "horse_name": "BLACKFYRE", "genel": 85.0, "guncel": 88.0, "saatli": 82.0}
          ]
        }
      }
    }
  }
}

At numaralari TJK program verisindeki at numaralariyla eslestirilir.
Horse name kullanilmaz (bülten sitenin farkli yazim sekli olabilir); sadece
(hip, race_no, horse_no) üçlüsü key olarak kullanilir.
"""

import json
from datetime import date
from pathlib import Path

from .normalize import norm_text
from .paths import BULLETIN_RAW_DIR


def load_bulletin_day(day: date, bulletin_dir: Path = BULLETIN_RAW_DIR) -> dict:
    path = bulletin_dir / f"{day:%Y-%m-%d}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_bulletin_scores(
    day: date,
    bulletin_dir: Path = BULLETIN_RAW_DIR,
) -> dict[tuple[str, int, int], dict[str, float]]:
    """
    Dönüş: {(hip_norm, race_no, horse_no): {"genel": x, "guncel": x, "saatli": x}}
    Eksik veri → boş dict (predictor tarafında 0.0 default uygulanır).
    """
    data = load_bulletin_day(day, bulletin_dir)
    out: dict[tuple[str, int, int], dict[str, float]] = {}
    for hip, hip_data in (data.get("hippodromes") or {}).items():
        hip_norm = norm_text(hip)
        for race_no_s, race_data in (hip_data.get("races") or {}).items():
            try:
                race_no = int(race_no_s)
            except (ValueError, TypeError):
                continue
            for horse in (race_data.get("horses") or []):
                try:
                    horse_no = int(horse.get("horse_no") or 0)
                except (ValueError, TypeError):
                    continue
                if horse_no <= 0:
                    continue
                scores: dict[str, float] = {}
                for field in ("genel", "guncel", "saatli"):
                    raw = horse.get(field)
                    if raw is not None:
                        try:
                            scores[field] = float(raw)
                        except (ValueError, TypeError):
                            pass
                if scores:
                    out[(hip_norm, race_no, horse_no)] = scores
    return out


def inject_bulletin_rows(rows: list[dict], day: date, bulletin_dir: Path = BULLETIN_RAW_DIR) -> None:
    """Bülten skorlarını row feature dict'lerine in-place enjekte eder."""
    bulletin = parse_bulletin_scores(day, bulletin_dir)
    if not bulletin:
        return
    for row in rows:
        key = (row["hip"], int(row["race_no"]), int(row["horse_no"]))
        scores = bulletin.get(key, {})
        row["features"]["bulletin_genel"]  = scores.get("genel",  0.0)
        row["features"]["bulletin_guncel"] = scores.get("guncel", 0.0)
        row["features"]["bulletin_saatli"] = scores.get("saatli", 0.0)
