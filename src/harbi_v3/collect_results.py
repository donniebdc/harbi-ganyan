from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests

from .dates import iter_dates
from .normalize import is_turkiye_hipodrom, norm_text
from .paths import RESULTS_RAW_DIR


RESULT_FEED = "https://ebayi.tjk.org/s/d"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
    "Referer": "https://www.google.com/",
}

def _int(value: object):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_betting_results(text: str) -> list[dict]:
    results: list[dict] = []
    for name, combo, value in re.findall(r"([^():]+)\(([^)]*)\):\s*([^:]+?TL)", text or ""):
        results.append({
            "name": name.strip(),
            "combo": combo.strip(),
            "value": value.strip(),
        })
    return results


def build_race(raw_race: dict) -> dict | None:
    raw_horses = raw_race.get("atlar") or []
    if not raw_horses:
        return None
    order = []
    coupled = defaultdict(set)
    scratched = []
    winner = None
    runners = 0
    for horse in raw_horses:
        no = _int(horse.get("NO"))
        if str(horse.get("KOSMAZ") or "").strip() in ("1", "true", "True"):
            if no:
                scratched.append(no)
            continue
        runners += 1
        rank = _int(horse.get("SONUC"))
        raw_ganyan = str(horse.get("GANYAN") or "").strip().replace(",", ".")
        try:
            ganyan_val = float(raw_ganyan) if raw_ganyan else None
        except ValueError:
            ganyan_val = None
        row = {
            "rank": rank,
            "horse_no": no,
            "horse_name": (horse.get("AD") or "").strip(),
            "time": (horse.get("DERECE") or "").strip(),
            "jockey_code": _int(horse.get("JOKEYKODU")),
            "ganyan": ganyan_val,
        }
        order.append(row)
        group = (horse.get("EKURI") or "").strip()
        if group and no:
            coupled[group].add(no)
        if rank == 1 and no:
            winner = no
    order.sort(key=lambda x: (x["rank"] is None, x["rank"] if x["rank"] is not None else 99))
    betting_text = str(
        raw_race.get("BAHISLER_TR")
        or raw_race.get("emiParasalNeticeler_tr")
        or ""
    ).strip()
    return {
        "race_no": _int(raw_race.get("NO")),
        "runner_count": runners,
        "winner": winner,
        "coupled": [sorted(v) for v in coupled.values() if len(v) >= 2],
        "scratched": scratched,
        "distance": _int(raw_race.get("MESAFE")),
        "track": (raw_race.get("PISTADI_TR") or "").strip(),
        "order": order,
        "betting_results_text": betting_text,
        "betting_results": _parse_betting_results(betting_text),
    }


def _fetch_json(session: requests.Session, url: str):
    response = session.get(url, timeout=20)
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def collect_results_day(day: date, out_dir: Path = RESULTS_RAW_DIR, force: bool = False, delay: float = 0.5) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = day.strftime("%Y-%m-%d")
    ymd = day.strftime("%Y%m%d")
    out_path = out_dir / f"{iso}.json"
    if out_path.exists() and not force:
        print(f"{iso}: results exist, skipped")
        return out_path

    session = requests.Session()
    session.headers.update(HEADERS)
    listing = _fetch_json(session, f"{RESULT_FEED}/sonuclar/{ymd}/yarislar.json")
    time.sleep(delay)
    if not isinstance(listing, list):
        print(f"{iso}: no result listing")
        return None

    result = {"date": iso, "source": "ebayi.tjk.org", "hippodromes": {}}
    for item in listing:
        place = item.get("YER") or item.get("KEY")
        if not is_turkiye_hipodrom(place):
            continue
        feed_key = str(item.get("KEY") or "").upper()
        detail = _fetch_json(session, f"{RESULT_FEED}/sonuclar/{ymd}/full/{feed_key}.json")
        time.sleep(delay)
        if not isinstance(detail, dict):
            continue
        races = {}
        for raw_race in detail.get("kosular") or []:
            race = build_race(raw_race)
            if race and race.get("winner"):
                races[str(race["race_no"])] = race
        if races:
            result["hippodromes"][norm_text(place)] = {
                "display_name": item.get("AD") or place,
                "races": races,
            }

    if not result["hippodromes"]:
        print(f"{iso}: no Turkish results")
        return None

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{iso}: saved results {out_path}")
    return out_path


def collect_results_range(start: date, end: date, out_dir: Path = RESULTS_RAW_DIR, force: bool = False, delay: float = 0.5) -> list[Path]:
    written: list[Path] = []
    for day in iter_dates(start, end):
        path = collect_results_day(day, out_dir=out_dir, force=force, delay=delay)
        if path:
            written.append(path)
    return written
