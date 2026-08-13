# -*- coding: utf-8 -*-
"""
collect_program_kombine.py  -  Kombine tahminleri icin program verisi cekilir.

collect_program.py'nin kopyasidir; tek farki:
  - "agf" ve "agf1" BANNED_RAW_KEYS listesinde YOK -> AGF verisi kaydedilir.
  - Kayit klasoru: data/program_kombine_raw/  (ana sisteme karismiyor)

Bu modul SADECE kombine.py tarafindan kullanilir.
Ana tahmin sistemi (data_pull.py, records.py, predict_for_date vb.)
bu klasoru hic bilmiyor; dolayisiyla ana modele etkisi yoktur.

Kullanim (dogrudan):
    python scripts/collect_program_kombine.py 2026-07-07
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harbi_v3.normalize import is_turkiye_hipodrom, norm_text  # noqa: E402

import requests  # noqa: E402


PROGRAM_FEED = "https://tjkbulten.atyarisi.com/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "platformId": "1",
    "Origin": "https://www.atyarisi.com",
    "Referer": "https://www.atyarisi.com/",
}

# AGF ve agf1 kasitli olarak bu listede YOK — kombine icin AGF verisi korunur.
# "status" da YOK — scratch (kosmayan at) filtresi icin gerekli.
BANNED_RAW_KEYS_KOMBINE = {
    "ganyan",
    "odds",
    "odd",
    "bahis",
    "bets",
    "bet",
    "payout",
    "ikramiye",
    "odeme",
    "isselected",
}

PROGRAM_KOMBINE_RAW_DIR = ROOT / "data" / "program_kombine_raw"


def _safe_key(key: object) -> bool:
    low = str(key or "").strip().lower()
    return not any(bad in low for bad in BANNED_RAW_KEYS_KOMBINE)


def _sanitize(value):
    """AGF dahil, diger market alanlari haric temizle."""
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items() if _safe_key(k)}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _fetch_json(session: requests.Session, url: str):
    try:
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def collect_program_kombine_day(
    day: date,
    out_dir: Path = PROGRAM_KOMBINE_RAW_DIR,
    force: bool = False,
    delay: float = 0.5,
) -> Path | None:
    """
    Gunu icin program verisini AGF dahil cekilir, data/program_kombine_raw/ altina kaydedilir.
    force=True ise mevcut dosya ezilir (yaris gunu taze AGF icin kullan).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = day.strftime("%Y-%m-%d")
    out_path = out_dir / f"{iso}.json"

    if out_path.exists() and not force:
        print(f"[kombine-program] {iso}: mevcut, atlanıyor")
        return out_path

    session = requests.Session()
    session.headers.update(HEADERS)

    hips_payload = _fetch_json(session, f"{PROGRAM_FEED}/v1/ProgramHippodromes?date={iso}")
    time.sleep(delay)
    hips = hips_payload.get("d", hips_payload) if isinstance(hips_payload, dict) else hips_payload
    if not isinstance(hips, list):
        print(f"[kombine-program] {iso}: hipodrom listesi alinamadi")
        return None

    raw: dict = {"date": iso, "source": "tjkbulten.atyarisi.com", "hippodromes": {}}

    for hp in hips:
        hobj = hp.get("hippodrome", {}) if isinstance(hp, dict) else {}
        place = hobj.get("place") or hobj.get("name") or hp.get("place") or hp.get("name")
        program_id = hp.get("id") or hp.get("programId")
        if not place or not program_id or not is_turkiye_hipodrom(place):
            continue

        detail = _fetch_json(session, f"{PROGRAM_FEED}/v2/ProgramDetails?programId={program_id}")
        time.sleep(delay)
        if not isinstance(detail, dict):
            continue

        raw["hippodromes"][norm_text(place)] = {
            "display_name": place,
            "program_id": program_id,
            "program": _sanitize(hp),
            "details": _sanitize(detail.get("d", detail)),
        }

    if not raw["hippodromes"]:
        print(f"[kombine-program] {iso}: Turkiye hipodromu bulunamadi")
        return None

    out_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[kombine-program] {iso}: kaydedildi -> {out_path}")
    return out_path


def extract_agf_map(day: date, out_dir: Path = PROGRAM_KOMBINE_RAW_DIR) -> dict:
    """
    data/program_kombine_raw/{date}.json dosyasindan AGF haritasi cikartir.

    TJK API'si AGF'yi her at icin su yapida dondurur:
        "agf": [{"position": 1, "percentage": 49.01, "isFavorite": true}]

    Donus degeri:
        {
          "ANKARA": {
            "1": {
              1: {"position": 5, "percentage": 3.29, "is_favorite": False},
              2: {"position": 1, "percentage": 49.01, "is_favorite": True},
              ...
            },
            "2": {...}
          }
        }

    AGF#1 = "position": 1 veya "isFavorite": True olan at.
    """
    iso = day.strftime("%Y-%m-%d")
    p = out_dir / f"{iso}.json"
    if not p.exists():
        return {}

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

    agf_map: dict = {}

    for hip_key, hip_data in data.get("hippodromes", {}).items():
        details = hip_data.get("details", {})
        races_raw = details.get("races", [])
        if not isinstance(races_raw, list):
            continue

        hip_races: dict = {}
        for race in races_raw:
            rno = race.get("number")
            if rno is None:
                continue
            rno_str = str(int(rno))

            horses_raw = race.get("horses", [])
            horse_agf: dict = {}
            for h in horses_raw:
                hno = h.get("number")
                agf_raw = h.get("agf")
                if hno is None or not isinstance(agf_raw, list) or not agf_raw:
                    continue
                entry = agf_raw[0]
                try:
                    horse_agf[int(hno)] = {
                        "position":    int(entry.get("position", 99)),
                        "percentage":  float(entry.get("percentage", 0.0)),
                        "is_favorite": bool(entry.get("isFavorite", False)),
                    }
                except (ValueError, TypeError):
                    pass

            if horse_agf:
                hip_races[rno_str] = horse_agf

        if hip_races:
            agf_map[hip_key] = hip_races

    return agf_map


def extract_scratched(day: date, out_dir: Path = PROGRAM_KOMBINE_RAW_DIR) -> dict:
    """
    Kosmayanlar (status=False) haritasini dondurur.

    Donus degeri:
        {
          "ANKARA": {"1": {3, 7}, "2": {5}},   # race_no(str) -> set of horse_no(int)
          "KOCAELI": {...}
        }

    Bu veri program_kombine_raw'dan okunur; program_raw'dan daha guncel olabilir
    cunku kombine programi yaris gununde her zaman force=True ile cekilir.
    """
    iso = day.strftime("%Y-%m-%d")
    p = out_dir / f"{iso}.json"
    if not p.exists():
        return {}

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

    scratched: dict = {}

    for hip_key, hip_data in data.get("hippodromes", {}).items():
        details = hip_data.get("details", {})
        races_raw = details.get("races", [])
        if not isinstance(races_raw, list):
            continue

        hip_scratched: dict = {}
        for race in races_raw:
            rno = race.get("number")
            if rno is None:
                continue
            rno_str = str(int(rno))

            scratched_set: set[int] = set()
            for h in race.get("horses", []):
                hno    = h.get("number")
                status = h.get("status")
                if hno is not None and status is False:
                    scratched_set.add(int(hno))

            if scratched_set:
                hip_scratched[rno_str] = scratched_set

        if hip_scratched:
            scratched[hip_key] = hip_scratched

    return scratched


def agf1_for_race(agf_map: dict, hip: str, race_no: int) -> tuple[int | None, float]:
    """
    AGF haritasindan belirtilen yaris icin AGF#1 at numarasini ve yuzdesini dondurur.

    Oncelik: isFavorite=True -> position=1 -> en dusuk position.
    Donus: (horse_no, percentage)  ya da  (None, 0.0) bulunamazsa.
    """
    hip_n = norm_text(hip)
    race_data = agf_map.get(hip_n, agf_map.get(hip, {})).get(str(race_no), {})
    if not race_data:
        return None, 0.0

    # Once isFavorite=True olan ati ara
    for hno, info in race_data.items():
        if info["is_favorite"]:
            return hno, info["percentage"]

    # Yoksa position en kucuk olan
    best_hno = min(race_data, key=lambda h: race_data[h]["position"])
    return best_hno, race_data[best_hno]["percentage"]


# ---------------------------------------------------------------------------
# CLI — dogrudan calistirma icin
# ---------------------------------------------------------------------------
def main() -> None:
    if len(sys.argv) < 2:
        today = date.today()
        print(f"Tarih belirtilmedi, bugun ({today}) kullaniliyor.")
        target = today
    else:
        raw = sys.argv[1].strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
            try:
                target = date.strptime(raw, fmt)
                break
            except ValueError:
                pass
        else:
            print(f"Gecersiz tarih: {raw}")
            sys.exit(1)

    force = "--force" in sys.argv or target >= date.today()
    path = collect_program_kombine_day(target, force=force)

    if path:
        agf_map = extract_agf_map(target)
        if not agf_map:
            print("UYARI: AGF verisi cikartılamadı — API yanitinda agf alani olmayabilir.")
            print(f"Ham JSON'a bakmak icin: {path}")
        else:
            total_races = sum(len(v) for v in agf_map.values())
            print(f"\nAGF ozeti: {len(agf_map)} hipodrom, {total_races} kos")
            for hip, races in agf_map.items():
                print(f"\n  {hip}:")
                for rno in sorted(races, key=int):
                    agf1_hno, pct = agf1_for_race(agf_map, hip, int(rno))
                    print(f"    Kos {rno}: AGF#1 = No:{agf1_hno} (%{pct:.1f})")
    else:
        print("Program verisi alinamadi.")
        sys.exit(1)


if __name__ == "__main__":
    main()
