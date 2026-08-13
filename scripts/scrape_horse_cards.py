from __future__ import annotations

"""
Scrape TJK horse-card race history by AtKodu.

Safety rules:
- The raw horse-card table is full career history as of fetch time.
- Model features must later filter rows strictly before the prediction date.
- Betting/money columns such as Gny and Ikramiye are not stored.
- This script does not read Sonuclar JSON.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import requests

from harbi_v3.paths import HORSE_CARDS_RAW_DIR, PROGRAM_RAW_DIR, ensure_dirs


CARD_URL = "https://www.tjk.org/TR/YarisSever/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId={code}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DROP_COLUMNS = {
    "Gny",
    "Ikramiye",
    "İkramiye",
    "Kazanç",
    "K. No-K. Adı",
    "K. No-K. AdÄ±",
}


def _extract_code(training_video: str) -> str | None:
    text = str(training_video or "")
    query = re.search(r"Atkodu=(\d+)", text)
    if query:
        return query.group(1)
    mp4 = re.search(r"/(\d+)-(\d+)\.mp4(?:\?|$)", text)
    if mp4:
        return mp4.group(2)
    return None


def collect_program_codes(program_dir: Path = PROGRAM_RAW_DIR) -> dict[str, dict]:
    codes: dict[str, dict] = {}
    for path in sorted(program_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for hip, hip_data in (data.get("hippodromes") or {}).items():
            for race in ((hip_data.get("details") or {}).get("races") or []):
                for horse in race.get("horses") or []:
                    code = _extract_code(str(horse.get("trainingVideo") or ""))
                    if not code:
                        continue
                    codes.setdefault(code, {
                        "horse_name": str(horse.get("name") or "").strip(),
                        "first_seen_program": path.stem,
                        "first_seen_hip": hip,
                    })
    return codes


def _clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def parse_history_table(html: str) -> list[dict]:
    tables = pd.read_html(StringIO(html))
    if len(tables) < 2:
        return []
    history = tables[1].copy()
    keep_cols = [
        col for col in history.columns
        if str(col) not in DROP_COLUMNS and not str(col).startswith("Unnamed:")
        and not str(col).startswith("K. No-K.")
    ]
    history = history[keep_cols]
    rows = []
    for row in history.to_dict(orient="records"):
        cleaned = {str(k): _clean_value(v) for k, v in row.items()}
        rows.append(cleaned)
    return rows


def _get_with_retry(
    session: requests.Session, url: str, retries: int = 4, backoff: float = 1.5
) -> requests.Response | None:
    """Gecici baglanti hatalarinda (RemoteDisconnected, timeout) backoff ile yeniden dener.
    Kalici basarisizlikta None doner; cagiran tarafi cokmez."""
    for attempt in range(retries):
        try:
            return session.get(url, timeout=25)
        except requests.exceptions.RequestException as exc:
            if attempt == retries - 1:
                print(f"  retry exhausted ({type(exc).__name__})")
                return None
            time.sleep(backoff * (attempt + 1))
    return None


def fetch_card(session: requests.Session, code: str, delay: float = 0.2) -> dict | None:
    url = CARD_URL.format(code=code)
    response = _get_with_retry(session, url)
    time.sleep(delay)
    if response is None or response.status_code != 200:
        return None
    try:
        rows = parse_history_table(response.text)
    except Exception as exc:
        print(f"  parse error ({type(exc).__name__})")
        return None
    if not rows:
        return None
    return {
        "atkodu": code,
        "source_url": url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "history_rows": rows,
    }


def _load_codes_file(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        raw_codes = data.get("codes") or data.get("atkodu_list") or []
    else:
        raw_codes = data
    return [str(code).strip() for code in raw_codes if str(code).strip()]


def scrape_cards(
    limit: int | None = None,
    force: bool = False,
    delay: float = 0.2,
    start_index: int = 0,
    codes_file: Path | None = None,
) -> tuple[int, int, int]:
    ensure_dirs()
    HORSE_CARDS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    code_map = collect_program_codes()
    codes = _load_codes_file(codes_file) if codes_file else sorted(code_map)
    if start_index:
        codes = codes[start_index:]
    if limit is not None:
        codes = codes[:limit]

    session = requests.Session()
    session.headers.update(HEADERS)

    attempted = saved = skipped = 0
    for code in codes:
        out_path = HORSE_CARDS_RAW_DIR / f"{code}.json"
        if out_path.exists() and not force:
            skipped += 1
            continue
        attempted += 1
        try:
            payload = fetch_card(session, code, delay=delay)
        except Exception as exc:
            print(f"{code}: error {type(exc).__name__}; devam")
            continue
        if not payload:
            print(f"{code}: no card data")
            continue
        payload["program_identity"] = code_map.get(code, {})
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved += 1
        if saved % 100 == 0:
            print(f"{code}: saved {len(payload['history_rows'])} rows (toplam saved={saved})")
    return attempted, saved, skipped


def collect_day_codes(day, program_dir: Path = PROGRAM_RAW_DIR) -> dict[str, dict]:
    """Sadece belirli bir gunun programindaki atlarin atkodularini dondurur.

    DATA LEAK SAFETY: Bu fonksiyon yalnizca program verisini okur (atkodu cikarmak
    icin). Cekilen at kartlari TJK'nin o anda sundugu tam kariyer gecmisini icerir.
    Ancak card_features(as_of=day) filtresinde r.race_date < as_of kosulu
    ZORUNLU olarak uygulanir, bu nedenle tahmin gunu veya sonrasindaki
    sonuclar hicbir zaman feature olarak kullanilmaz.
    """
    from datetime import date as _date
    if isinstance(day, str):
        day = _date.fromisoformat(day)
    iso = day.strftime("%Y-%m-%d")
    path = program_dir / f"{iso}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    codes: dict[str, dict] = {}
    for hip, hip_data in (data.get("hippodromes") or {}).items():
        for race in ((hip_data.get("details") or {}).get("races") or []):
            for horse in (race.get("horses") or []):
                code = _extract_code(str(horse.get("trainingVideo") or ""))
                if not code:
                    continue
                codes.setdefault(code, {
                    "horse_name": str(horse.get("name") or "").strip(),
                    "program_date": iso,
                    "hip": hip,
                })
    return codes


def refresh_cards_for_day(
    day,
    delay: float = 0.25,
    verbose: bool = True,
) -> tuple[int, int, int]:
    """O gunun programindaki tum atlarin kartlarini gunceller (force=True).

    Bu fonksiyon tahmin.py tarafindan her tahmin uretiminden ONCE cagrilir.
    Amac: son kosularin derece/sehir/pist bilgisini karta yansitmak, boylece
    a2_card_*quality_diff feature'larinin guncel veriden beslenmesini saglamak.

    DATA LEAK SAFETY:
      - Burada cekilen ham kart JSON'u TJK'nin o anda yayinladigi kariyer
        gecmisinin TAMAMINI icerir (tahmin gununu gecmis kos varsa dahil).
      - Feature uretiminde card_features(atkodu, as_of=day, ...) cagrisi
        r.race_date < as_of filtresini ZORUNLU olarak uygular; tahmin gunu
        veya sonrasindaki satirlar HICBIR ZAMAN feature olarak kullanilmaz.
      - Bu nedenle kart icerigi ne kadar guncel olursa olsun sizinti olmaz.
    """
    ensure_dirs()
    HORSE_CARDS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    day_codes = collect_day_codes(day)
    if not day_codes:
        if verbose:
            print(f"  [kart-guncelle] {day}: program bulunamadi, atlanıyor.")
        return 0, 0, 0

    session = requests.Session()
    session.headers.update(HEADERS)

    attempted = saved = failed = 0
    total = len(day_codes)
    for i, (code, meta) in enumerate(sorted(day_codes.items()), 1):
        out_path = HORSE_CARDS_RAW_DIR / f"{code}.json"
        attempted += 1
        try:
            payload = fetch_card(session, code, delay=delay)
        except Exception as exc:
            if verbose:
                print(f"  [{i}/{total}] {code} ({meta.get('horse_name','?')}): hata {type(exc).__name__}")
            failed += 1
            continue
        if not payload:
            if verbose:
                print(f"  [{i}/{total}] {code} ({meta.get('horse_name','?')}): veri yok")
            failed += 1
            continue
        payload["program_identity"] = meta
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved += 1
        if verbose and (saved % 20 == 0 or i == total):
            print(f"  [{i}/{total}] kaydedildi: {saved} at, {failed} basarisiz")

    # In-process lru_cache'i temizle — yeni dosyalar okunabilsin
    try:
        from harbi_v3.horse_cards import load_card_races
        load_card_races.cache_clear()
    except Exception:
        pass

    if verbose:
        print(f"  [kart-guncelle] tamamlandi: {saved} guncellendi, {failed} basarisiz / {total} at")
    return attempted, saved, failed


def ensure_cards_for_day(
    day,
    max_age_days: int = 7,
    delay: float = 0.25,
    verbose: bool = True,
) -> tuple[int, int, int]:
    """O gunun programindaki atlardan eksik veya bayat kartlari ceker.

    Kural:
      - Kart dosyasi yoksa: cek (eksik).
      - Kart dosyasi max_age_days'den eskiyse: yenile (bayat — at bu arada
        kosu yapmis olabilir, form/quality_diff featurelari guncel olmali).
      - Kart dosyasi tazeyse: atla.

    Default max_age_days=7: haftadan eski kart guncel sayilmaz.
    refresh_cards_for_day(force) tum atlari her seferinde ceker;
    bu fonksiyon sadece gerekenlerle sinirlidir.
    """
    import time as _time

    ensure_dirs()
    HORSE_CARDS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    day_codes = collect_day_codes(day)
    if not day_codes:
        if verbose:
            print(f"  [kart-kontrol] {day}: program bulunamadi, atlaniyor.")
        return 0, 0, 0

    now = _time.time()
    max_age_sec = max_age_days * 86400
    to_fetch: dict[str, dict] = {}
    missing_cnt = stale_cnt = fresh_cnt = 0
    for k, v in day_codes.items():
        path = HORSE_CARDS_RAW_DIR / f"{k}.json"
        if not path.exists():
            to_fetch[k] = v
            missing_cnt += 1
        elif (now - path.stat().st_mtime) > max_age_sec:
            to_fetch[k] = v
            stale_cnt += 1
        else:
            fresh_cnt += 1

    if not to_fetch:
        if verbose:
            print(f"  [kart-kontrol] {day}: {fresh_cnt} kart taze, guncelleme yok.")
        return 0, 0, 0

    if verbose:
        parts = []
        if missing_cnt:
            parts.append(f"{missing_cnt} eksik")
        if stale_cnt:
            parts.append(f"{stale_cnt} bayat (>{max_age_days}g)")
        print(f"  [kart-kontrol] {day}: {', '.join(parts)} / {len(day_codes)} at — cekiliyor...")

    session = requests.Session()
    session.headers.update(HEADERS)

    attempted = saved = failed = 0
    total = len(to_fetch)
    for i, (code, meta) in enumerate(sorted(to_fetch.items()), 1):
        out_path = HORSE_CARDS_RAW_DIR / f"{code}.json"
        attempted += 1
        try:
            payload = fetch_card(session, code, delay=delay)
        except Exception as exc:
            if verbose:
                print(f"  [{i}/{total}] {code} ({meta.get('horse_name','?')}): hata {type(exc).__name__}")
            failed += 1
            continue
        if not payload:
            if verbose:
                print(f"  [{i}/{total}] {code} ({meta.get('horse_name','?')}): veri yok")
            failed += 1
            continue
        payload["program_identity"] = meta
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved += 1
        if verbose and (saved % 10 == 0 or i == total):
            print(f"  [{i}/{total}] kaydedildi: {saved} at, {failed} basarisiz")

    try:
        from harbi_v3.horse_cards import load_card_races
        load_card_races.cache_clear()
    except Exception:
        pass

    if verbose:
        print(f"  [kart-kontrol] tamamlandi: {saved} guncellendi, {failed} basarisiz / {total} islendi")
    return attempted, saved, failed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--codes-file", type=Path, default=None)
    parser.add_argument("--refresh-day", type=str, default=None,
                        help="YYYY-MM-DD: sadece o gunun programindaki atlari guncelle (force=True)")
    args = parser.parse_args()

    if args.refresh_day:
        attempted, saved, failed = refresh_cards_for_day(args.refresh_day, delay=args.delay)
        print(f"attempted={attempted} saved={saved} failed={failed}")
        return 0

    attempted, saved, skipped = scrape_cards(
        limit=args.limit,
        force=args.force,
        delay=args.delay,
        start_index=args.start_index,
        codes_file=args.codes_file,
    )
    print(f"attempted={attempted} saved={saved} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
