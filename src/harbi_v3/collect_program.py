from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import requests

from .dates import iter_dates
from .normalize import is_turkiye_hipodrom, norm_text
from .paths import PROGRAM_RAW_DIR


PROGRAM_FEED = "https://tjkbulten.atyarisi.com/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "platformId": "1",
    "Origin": "https://www.atyarisi.com",
    "Referer": "https://www.atyarisi.com/",
}

# NOTE: "status" alani BILEREK bu listede yok — at "kosmuyor" (scratch) bilgisini
# tasiyor, src/harbi_v3/records.py:parse_program_horses bunu filtrelemek icin kullaniyor.
# Bahis/market alani degil; tekrar buraya eklenirse scratch filtresi sessizce bozulur.
BANNED_RAW_KEYS = {
    "agf",
    "agf1",
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


def _safe_key(key: object) -> bool:
    low = str(key or "").strip().lower()
    return not any(bad in low for bad in BANNED_RAW_KEYS)


def sanitize_program_payload(value):
    """Remove market/betting fields from TJK program snapshots before storage."""
    if isinstance(value, dict):
        return {
            key: sanitize_program_payload(item)
            for key, item in value.items()
            if _safe_key(key)
        }
    if isinstance(value, list):
        return [sanitize_program_payload(item) for item in value]
    return value


def _fetch_json(session: requests.Session, url: str):
    response = session.get(url, timeout=20)
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _save_city_files(iso: str, raw: dict, out_dir: Path) -> list[Path]:
    """Birleşik program raw dict'ini şehir bazlı JSON dosyalarına böler.
    {out_dir}/{iso}/ISTANBUL.json, {out_dir}/{iso}/ELAZIG.json, ...
    """
    city_dir = out_dir / iso
    city_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for hip_key, hip_data in raw.get("hippodromes", {}).items():
        city_raw = {
            "date": raw["date"],
            "source": raw.get("source", ""),
            "hippodromes": {hip_key: hip_data},
        }
        city_path = city_dir / f"{hip_key}.json"
        city_path.write_text(
            json.dumps(city_raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written.append(city_path)
    if written:
        print(f"{iso}: saved {len(written)} city files -> {city_dir}")
    return written


def collect_program_day(day: date, out_dir: Path = PROGRAM_RAW_DIR, force: bool = False, delay: float = 0.5) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = day.strftime("%Y-%m-%d")
    out_path = out_dir / f"{iso}.json"
    if out_path.exists() and not force:
        print(f"{iso}: program exists, skipped")
        return out_path

    session = requests.Session()
    session.headers.update(HEADERS)
    hips_payload = _fetch_json(session, f"{PROGRAM_FEED}/v1/ProgramHippodromes?date={iso}")
    time.sleep(delay)
    hips = hips_payload.get("d", hips_payload) if isinstance(hips_payload, dict) else hips_payload
    if not isinstance(hips, list):
        print(f"{iso}: no program hippodromes")
        return None

    raw = {"date": iso, "source": "tjkbulten.atyarisi.com", "hippodromes": {}}
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
            "program": sanitize_program_payload(hp),
            "details": sanitize_program_payload(detail.get("d", detail)),
        }

    if not raw["hippodromes"]:
        print(f"{iso}: no Turkish program data")
        return None

    out_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{iso}: saved program snapshot {out_path}")

    # Şehir bazlı dosyalara böl
    _save_city_files(iso, raw, out_dir)

    return out_path


def collect_program_city(day: date, city: str, out_dir: Path = PROGRAM_RAW_DIR, force: bool = False, delay: float = 0.5) -> Path | None:
    """Tek bir şehrin program verisini TJK'den çeker ve şehir JSON'u olarak kaydeder.

    Args:
        day: Program tarihi
        city: Şehir adı (norm_text edilmiş hali: ISTANBUL, ELAZIG, ...)
        out_dir: Çıktı dizini (şehir dosyası {out_dir}/{iso}/{city}.json olarak kaydedilir)
        force: True ise mevcut dosyayı ezerek yeniden çeker
        delay: API istekleri arası bekleme (saniye)

    Returns:
        Kaydedilen şehir dosyasının yolu, başarısızsa None
    """
    from .normalize import norm_text as _norm

    iso = day.strftime("%Y-%m-%d")
    city_norm = _norm(city)
    city_dir = out_dir / iso
    city_dir.mkdir(parents=True, exist_ok=True)
    city_path = city_dir / f"{city_norm}.json"

    if city_path.exists() and not force:
        print(f"{iso}/{city_norm}: city program exists, skipped")
        return city_path

    session = requests.Session()
    session.headers.update(HEADERS)

    # Önce hippodrome listesini al, şehri bul
    hips_payload = _fetch_json(session, f"{PROGRAM_FEED}/v1/ProgramHippodromes?date={iso}")
    time.sleep(delay)
    hips = hips_payload.get("d", hips_payload) if isinstance(hips_payload, dict) else hips_payload
    if not isinstance(hips, list):
        print(f"{iso}/{city_norm}: no program hippodromes")
        return None

    target = None
    target_place = None
    for hp in hips:
        hobj = hp.get("hippodrome", {}) if isinstance(hp, dict) else {}
        place = hobj.get("place") or hobj.get("name") or hp.get("place") or hp.get("name")
        if not place or not is_turkiye_hipodrom(place):
            continue
        if _norm(place) == city_norm:
            target = hp
            target_place = place
            break

    if target is None:
        print(f"{iso}/{city_norm}: city not found in hippodrome list")
        return None

    program_id = target.get("id") or target.get("programId")
    if not program_id:
        print(f"{iso}/{city_norm}: no program_id")
        return None

    detail = _fetch_json(session, f"{PROGRAM_FEED}/v2/ProgramDetails?programId={program_id}")
    time.sleep(delay)
    if not isinstance(detail, dict):
        print(f"{iso}/{city_norm}: no program details")
        return None

    city_raw = {
        "date": iso,
        "source": "tjkbulten.atyarisi.com",
        "hippodromes": {
            city_norm: {
                "display_name": target_place,
                "program_id": program_id,
                "program": sanitize_program_payload(target),
                "details": sanitize_program_payload(detail.get("d", detail)),
            }
        },
    }

    city_path.write_text(json.dumps(city_raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{iso}/{city_norm}: saved city program -> {city_path}")

    # Ayrıca birleşik dosyayı da güncelle (varsa)
    combined_path = out_dir / f"{iso}.json"
    if combined_path.exists():
        try:
            combined = json.loads(combined_path.read_text(encoding="utf-8"))
            combined["hippodromes"][city_norm] = city_raw["hippodromes"][city_norm]
            combined_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{iso}/{city_norm}: updated combined file")
        except Exception:
            pass  # birleşik dosya güncellenemezse sorun değil

    return city_path


def collect_program_range(start: date, end: date, out_dir: Path = PROGRAM_RAW_DIR, force: bool = False, delay: float = 0.5) -> list[Path]:
    written: list[Path] = []
    for day in iter_dates(start, end):
        path = collect_program_day(day, out_dir=out_dir, force=force, delay=delay)
        if path:
            written.append(path)
    return written
