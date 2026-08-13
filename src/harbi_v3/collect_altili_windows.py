from __future__ import annotations

import html
import json
import re
import time
from datetime import date
from pathlib import Path

import requests

from .normalize import norm_text
from .paths import ALTILI_WINDOWS_RAW_DIR

PROGRAM_PAGE = "https://www.tjk.org/TR/YarisSever/Info/Sehir/GunlukYarisProgrami"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
    "Accept": "text/html, */*; q=0.01",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.tjk.org/TR/YarisSever/Info/Page/GunlukYarisProgrami",
}

# norm_text()-normalized hippodrome name -> tjk.org SehirId
SEHIR_ID: dict[str, int] = {
    "adana": 1,
    "izmir": 2,
    "istanbul": 3,
    "bursa": 4,
    "ankara": 5,
    "sanliurfa": 6,
    "elazig": 7,
    "diyarbakir": 8,
    "kocaeli": 9,
    "antalya": 10,
}

SEHIR_ADI: dict[str, str] = {
    "adana": "Adana",
    "izmir": "İzmir",
    "istanbul": "İstanbul",
    "bursa": "Bursa",
    "ankara": "Ankara",
    "sanliurfa": "Şanlıurfa",
    "elazig": "Elazığ",
    "diyarbakir": "Diyarbakır",
    "kocaeli": "Kocaeli",
    "antalya": "Antalya",
}

RACE_DETAILS_MARKER = '<div class="race-details"'
ALTILI_MARKER_RE = re.compile(
    r"(?:(\d)\.\s*)?6'L[İI]\s+GANYAN\s+Bu\s+ko[şs]udan\s+ba[şs]lar"
)


def _fetch_html(session: requests.Session, sehir_key: str, day: date) -> str | None:
    sehir_id = SEHIR_ID[sehir_key]
    sehir_adi = SEHIR_ADI[sehir_key]
    tarih = day.strftime("%d/%m/%Y")
    params = {
        "SehirId": sehir_id,
        "QueryParameter_Tarih": tarih,
        "SehirAdi": sehir_adi,
        "Era": "today",
    }
    last_error = None
    for attempt in range(3):
        try:
            response = session.get(PROGRAM_PAGE, params=params, headers=HEADERS, timeout=30)
            if response.status_code != 200:
                return None
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep((attempt + 1) * 2)  # 2, 4 saniye backoff
    # 3 deneme basarisiz -> None (cagiran handle eder)
    print(f"  [_fetch_html] {sehir_key} {day} 3 deneme basarisiz: {last_error}")
    return None


def _parse_start_races(html_text: str) -> dict[str, int]:
    """HTML sayfasini race-details bloklarina ayirir, her blokta 6'LI GANYAN
    'Bu kosudan baslar' isaretini arar. Doner: {"1": race_no, "2": race_no}.
    Numarasiz isaret havuz 1 sayilir. AGF/oran metni asla okunmaz, parser
    sadece bu sabit ifadeyi arar."""
    blocks = html_text.split(RACE_DETAILS_MARKER)[1:]  # ilk parca header, atla
    start_races: dict[str, int] = {}
    for race_no, block in enumerate(blocks, start=1):
        decoded = html.unescape(block)
        for match in ALTILI_MARKER_RE.finditer(decoded):
            pool = match.group(1) or "1"
            if pool not in start_races:
                start_races[pool] = race_no
    return start_races


def collect_altili_windows_day(
    day: date,
    out_dir: Path = ALTILI_WINDOWS_RAW_DIR,
    force: bool = False,
    delay: float = 0.5,
) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = day.strftime("%Y-%m-%d")
    out_path = out_dir / f"{iso}.json"
    if out_path.exists() and not force:
        print(f"{iso}: altili windows exist, skipped")
        return out_path

    session = requests.Session()
    result = {"date": iso, "source": "tjk.org/GunlukYarisProgrami", "hippodromes": {}}

    for sehir_key in SEHIR_ID:
        html_text = _fetch_html(session, sehir_key, day)
        time.sleep(delay)
        if not html_text:
            continue
        blocks = html_text.count(RACE_DETAILS_MARKER)
        if blocks == 0:
            continue  # bu hipodrom o gun kosmuyor
        start_races = _parse_start_races(html_text)
        if start_races:
            hip_key = norm_text(SEHIR_ADI[sehir_key])
            result["hippodromes"][hip_key] = {"start_races": start_races}

    if not result["hippodromes"]:
        print(f"{iso}: no altili windows found")
        return None

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{iso}: saved altili windows {out_path}")
    return out_path


def load_altili_windows_day(day: date, windows_dir: Path = ALTILI_WINDOWS_RAW_DIR) -> dict:
    path = windows_dir / f"{day:%Y-%m-%d}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
