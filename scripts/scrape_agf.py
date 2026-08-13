# -*- coding: utf-8 -*-
"""
scrape_agf.py  -  TJK AGF verisini data/agf_live/ altina kaydeder.

Sadece sunum katmani icin: agf_radar.py, explain.py, daily_panel.py.
Model pipeline (program_raw, features.py, predictor.py) bu dosyaya dokunmaz.

Kullanim:
    python scripts/scrape_agf.py
    python scripts/scrape_agf.py 2026-07-07
    python scripts/scrape_agf.py 2026-07-07 --force
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

AGF_LIVE_DIR = ROOT / "data" / "agf_live"


def _parse_date(raw: str) -> date | None:
    from datetime import datetime as _dt
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return _dt.strptime(raw.strip(), fmt).date()
        except ValueError:
            pass
    return None


def scrape_day(target_date: date, force: bool = False) -> Path | None:
    """
    Hedef gun icin AGF verisini ceker ve data/agf_live/{date}.json yazar.

    Is akisi:
      1. collect_program_kombine_day() ile program_kombine_raw'dan taze veri cekilir.
      2. extract_agf_map() ile AGF haritasi cikarilir.
      3. Normalize JSON olarak agf_live/ altina kaydedilir.

    Donus: yazilan dosya yolu, ya da None (AGF alinamazsa).
    """
    from collect_program_kombine import (
        collect_program_kombine_day,
        extract_agf_map,
        PROGRAM_KOMBINE_RAW_DIR,
    )

    AGF_LIVE_DIR.mkdir(parents=True, exist_ok=True)
    iso = target_date.strftime("%Y-%m-%d")
    out_path = AGF_LIVE_DIR / f"{iso}.json"

    if out_path.exists() and not force:
        print(f"[scrape-agf] {iso}: mevcut, atlanıyor (--force ile yenile)")
        return out_path

    # 1. Ham program + AGF cekilir (program_kombine_raw'a yazilir)
    raw_force = force or (target_date >= date.today())
    result = collect_program_kombine_day(target_date, force=raw_force)
    if result is None:
        print(f"[scrape-agf] {iso}: program_kombine_raw cekilemedi — AGF alinamadi")
        return None

    # 2. AGF haritasi cikarilir
    agf_map = extract_agf_map(target_date, out_dir=PROGRAM_KOMBINE_RAW_DIR)
    if not agf_map:
        print(f"[scrape-agf] {iso}: AGF alani API yanitinda bulunamadi")
        return None

    # 3. Normalize — str key'ler, datetime damgasi
    normalized: dict[str, dict] = {}
    for hip_key, races in agf_map.items():
        normalized[hip_key] = {}
        for race_no_str, horses in races.items():
            normalized[hip_key][race_no_str] = {
                str(horse_no): {
                    "position":    info["position"],
                    "percentage":  info["percentage"],
                    "is_favorite": info["is_favorite"],
                }
                for horse_no, info in horses.items()
            }

    payload = {
        "date":         iso,
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "hippodromes":  normalized,
    }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    total_races = sum(len(r) for r in normalized.values())
    print(f"[scrape-agf] {iso}: kaydedildi -> {out_path.name}  ({len(normalized)} hipodrom, {total_races} kos)")
    return out_path


def load_agf(target_date: date) -> dict:
    """
    data/agf_live/{date}.json dosyasini yukler.

    Donus:
        {
          "ANKARA": {
            "1": {"1": {"position": 5, "percentage": 3.36, "is_favorite": False}, ...},
            "2": {...}
          }
        }

    Dosya yoksa bos dict doner — cagiran kod None kontrolu yapmak zorunda kalmaz.
    """
    iso = target_date.strftime("%Y-%m-%d")
    p = AGF_LIVE_DIR / f"{iso}.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("hippodromes", {})
    except Exception:
        return {}


def agf1_for_race(agf_data: dict, hip: str, race_no: int) -> tuple[int | None, float]:
    """
    AGF verisinden belirtilen yaris icin AGF#1 at numarasi ve yuzdesini dondurur.

    Parameters:
        agf_data: load_agf() donus degeri
        hip:      hipodrom adi (buyuk/kucuk harf farketmez, norm_text uygulanir)
        race_no:  kos numarasi (int)

    Donus: (horse_no: int, percentage: float)  ya da  (None, 0.0) bulunamazsa.
    """
    from harbi_v3.normalize import norm_text
    hip_n = norm_text(hip)
    race_data = agf_data.get(hip_n, agf_data.get(hip.upper(), {})).get(str(race_no), {})
    if not race_data:
        return None, 0.0

    # Once isFavorite olan ati ara
    for hno_str, info in race_data.items():
        if info.get("is_favorite"):
            return int(hno_str), info["percentage"]

    # Yoksa position en kucuk olan
    best = min(race_data.items(), key=lambda kv: kv[1]["position"])
    return int(best[0]), best[1]["percentage"]


def print_summary(target_date: date) -> None:
    """AGF ozet tablosunu ekrana yazar — CLI ve debug icin."""
    agf_data = load_agf(target_date)
    if not agf_data:
        print(f"AGF verisi bulunamadi: {target_date:%Y-%m-%d}")
        return

    iso = target_date.strftime("%Y-%m-%d")
    print(f"\nAGF Ozeti — {iso}")
    print("=" * 60)
    for hip, races in sorted(agf_data.items()):
        print(f"\n  {hip}")
        for rno in sorted(races, key=int):
            hno, pct = agf1_for_race(agf_data, hip, int(rno))
            horses = races[rno]
            total_horses = len(horses)
            fav_name = ""
            print(f"    Kos {rno:>2}: AGF#1 = No:{hno}  %{pct:.1f}  ({total_horses} at)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if not a.startswith("--")]

    if args:
        target_date = _parse_date(args[0])
        if target_date is None:
            print(f"Gecersiz tarih: {args[0]}")
            return 1
    else:
        target_date = date.today()
        print(f"Tarih belirtilmedi, bugun kullaniliyor: {target_date}")

    path = scrape_day(target_date, force=force)
    if path:
        print_summary(target_date)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
