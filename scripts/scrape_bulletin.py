"""
scrape_bulletin.py — atyarisi.com bülten skorlarını çeker.

Kaynak: https://tjkbulten.atyarisi.com/api
  GET /v1/ProgramHippodromes?date=YYYY-MM-DD → programId + koşu sayısı
  GET /v1/GetHorseAnalysisByProgramAndRace?programId={id}&raceNo={n}
       → {horseNo, generalScore, currentScore, hourlyScore, analysisNote}

Çıktı: data/bulletin_raw/YYYY-MM-DD.json
  generalScore  → bulletin_genel  (7 bülten ortalaması)
  currentScore  → bulletin_guncel (Güncel Teknik Koşu Gazetesi)
  hourlyScore   → bulletin_saatli (Puanlı Koşu Bülteni)

Kullanım:
  python scripts/scrape_bulletin.py                   # bugün
  python scripts/scrape_bulletin.py 2026-06-12        # tek gün
  python scripts/scrape_bulletin.py 2026-01-01 2026-06-12  # tarih aralığı
  python scripts/scrape_bulletin.py --force 2026-06-12     # mevcut dosyanın üzerine yaz
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

BASE_URL = "https://tjkbulten.atyarisi.com/api"
BULLETIN_DIR = Path(__file__).resolve().parents[1] / "data" / "bulletin_raw"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HarbiGanyan/3.0)",
    "Accept": "application/json",
}
SLEEP_BETWEEN_REQUESTS = 0.4  # saniye


def _get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("sc") == 200:
        return data.get("d") or {}
    raise ValueError(f"API sc={data.get('sc')} — {path} {params}")


def fetch_hippodromes(day: date) -> list[dict]:
    """
    Verilen tarihteki yerli TJK hipodromlarını döndürür.
    Her eleman: {"program_id": int, "code": str, "race_count": int}
    """
    date_str = day.strftime("%Y-%m-%d")
    cards = _get("/v1/ProgramHippodromes", {"date": date_str})
    if not isinstance(cards, list):
        return []
    result = []
    for card in cards:
        hip = card.get("hippodrome") or {}
        if hip.get("isForeign"):
            continue
        code = str(hip.get("code") or "").strip()
        if not code or code == "KARMA":
            continue
        total_day = int(card.get("totalDay") or 0)
        if total_day <= 0:
            continue
        result.append({
            "program_id": int(card["id"]),
            "code": code,
            "race_count": total_day,
        })
    return result


def fetch_race_scores(program_id: int, race_no: int) -> list[dict]:
    """
    Bir koşunun tüm atlarının bülten skorlarını döndürür.
    Her eleman: {"horse_no": int, "genel": float|None, "guncel": float|None, "saatli": float|None}
    """
    time.sleep(SLEEP_BETWEEN_REQUESTS)
    try:
        d = _get("/v1/GetHorseAnalysisByProgramAndRace", {
            "programId": program_id,
            "raceNo": race_no,
        })
    except Exception as e:
        print(f"      ! API hatası koşu {race_no}: {e}", flush=True)
        return []

    horses = d.get("horses") or []
    result = []
    for h in horses:
        horse_no = h.get("horseNo")
        if not horse_no:
            continue

        def _f(val: object) -> float | None:
            if val is None or val == "-":
                return None
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        result.append({
            "horse_no": int(horse_no),
            "genel":  _f(h.get("generalScore")),
            "guncel": _f(h.get("currentScore")),
            "saatli": _f(h.get("hourlyScore")),
        })
    return result


def scrape_day(day: date, force: bool = False) -> bool:
    """
    Bir gün için bülten verisi çekip kaydeder.
    Zaten varsa force=False ise atlanır.
    Döndürür: True=kaydedildi, False=atlandı.
    """
    BULLETIN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BULLETIN_DIR / f"{day:%Y-%m-%d}.json"

    if out_path.exists() and not force:
        print(f"  {day} — mevcut, atlandı ({out_path.name})", flush=True)
        return False

    print(f"  {day} — hipodromlar alınıyor…", flush=True)
    try:
        hippodromes = fetch_hippodromes(day)
    except Exception as e:
        print(f"  {day} — hipodrom hatası: {e}", flush=True)
        return False

    if not hippodromes:
        print(f"  {day} — yerli hipodrom bulunamadı, atlandı", flush=True)
        return False

    out: dict = {
        "date": day.strftime("%Y-%m-%d"),
        "hippodromes": {},
    }

    for hip in hippodromes:
        code = hip["code"]
        pid = hip["program_id"]
        n_races = hip["race_count"]
        print(f"    {code} (id={pid}, {n_races} koşu)…", flush=True)

        races_out: dict[str, dict] = {}
        for race_no in range(1, n_races + 1):
            scores = fetch_race_scores(pid, race_no)
            if scores:
                races_out[str(race_no)] = {"horses": scores}

        if races_out:
            out["hippodromes"][code] = {"races": races_out}

    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    total_horses = sum(
        len(r["horses"])
        for h in out["hippodromes"].values()
        for r in h["races"].values()
    )
    print(f"  {day} — kaydedildi ({len(out['hippodromes'])} hipodrom, {total_horses} at-koşu)", flush=True)
    return True


def _parse_date(s: str) -> date:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Tanımsız tarih formatı: {s}")


def main(argv: list[str]) -> None:
    force = "--force" in argv
    args = [a for a in argv if not a.startswith("-")]

    if not args:
        days = [date.today()]
    elif len(args) == 1:
        days = [_parse_date(args[0])]
    else:
        start = _parse_date(args[0])
        end = _parse_date(args[1])
        days = []
        d = start
        while d <= end:
            days.append(d)
            d += timedelta(days=1)

    print(f"Toplam {len(days)} gün taranacak. force={force}", flush=True)
    saved = skipped = 0
    for day in days:
        ok = scrape_day(day, force=force)
        if ok:
            saved += 1
        else:
            skipped += 1

    print(f"\nBitti: {saved} kaydedildi, {skipped} atlandı.", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
