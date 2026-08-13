# -*- coding: utf-8 -*-
"""
kart_sonrasi_guncelle.py — Sonuclanan kosulardaki atlarin kartlarini gunceller.

Mantik:
  TJK at kartlari tam kariyer gecmisi iceriyor. Bir at kosunca bu gecmis
  guncellenir — ama kartı yenilemezsek o bilgi feature'lara yansimiyor.

  Bu script:
    1. Belirtilen gunun sonuc JSON'unu okur.
    2. O gunun program JSON'undan at kodu (TJK AtKodu) haritasini cikarir.
    3. Sonuclanan kosulardaki horse_no'lardan at kodlarini bulur.
    4. Sadece o at kodlarini TJK'dan yeniden ceker.
    5. Kart bulunamayanlari (zaten yok veya TJK'da data yok) atlar.

Kullanim:
    python kart_sonrasi_guncelle.py                  # bugun
    python kart_sonrasi_guncelle.py 2026-07-03       # belirli gun
    python kart_sonrasi_guncelle.py --hip ISTANBUL   # sadece bir sehir
    python kart_sonrasi_guncelle.py --race 3         # sadece N. kosu
    python kart_sonrasi_guncelle.py --dry            # ne guncellenecek goster

Bu script daily_pipeline.py --live akisindan cagrilabilir; her kosu
sonuclannca o kosunun atlari guncellenir. Boylece tum atlari haftalik
yeniden cekmek yerine sadece kosanlar guncellenir.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harbi_v3.paths import HORSE_CARDS_RAW_DIR, PROGRAM_RAW_DIR, RESULTS_RAW_DIR, ensure_dirs

CARD_URL = "https://www.tjk.org/TR/YarisSever/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId={code}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── At kodu çıkarıcı (program JSON'daki trainingVideo alanından) ──────────────

def _extract_code(training_video: str) -> str | None:
    text = str(training_video or "")
    q = re.search(r"Atkodu=(\d+)", text)
    if q:
        return q.group(1)
    mp4 = re.search(r"/(\d+)-(\d+)\.mp4(?:\?|$)", text)
    if mp4:
        return mp4.group(2)
    return None


def _build_code_map(day: date) -> dict[tuple[str, int], str]:
    """Program JSON'undan {(hip, horse_no): at_kodu} haritasini dondurur."""
    prog_path = PROGRAM_RAW_DIR / f"{day:%Y-%m-%d}.json"
    if not prog_path.exists():
        return {}
    data = json.loads(prog_path.read_text(encoding="utf-8"))
    code_map: dict[tuple[str, int], str] = {}
    for hip, hip_data in (data.get("hippodromes") or {}).items():
        for race in ((hip_data.get("details") or {}).get("races") or []):
            race_no = int(race.get("no") or race.get("race_no") or 0)
            for horse in (race.get("horses") or []):
                hno = horse.get("no") or horse.get("horse_no")
                code = _extract_code(str(horse.get("trainingVideo") or ""))
                if hno and code:
                    code_map[(hip.upper(), int(hno))] = code
    return code_map


# ── Sonuç JSON'undan gunun kosularina katilan atlari bul ────────────────────

def _find_race_horses(day: date, hip_filter: str | None, race_filter: int | None
                      ) -> list[tuple[str, int, int]]:
    """[(hip, race_no, horse_no), ...] dondurur — sonuclanan kosulardan."""
    res_path = RESULTS_RAW_DIR / f"{day:%Y-%m-%d}.json"
    if not res_path.exists():
        print(f"  Sonuc JSON bulunamadi: {res_path.name}")
        return []
    data = json.loads(res_path.read_text(encoding="utf-8"))
    entries = []
    for hip, hip_data in (data.get("hippodromes") or {}).items():
        if hip_filter and hip.upper() != hip_filter.upper():
            continue
        for rno_str, race in (hip_data.get("races") or {}).items():
            rno = int(rno_str)
            if race_filter is not None and rno != race_filter:
                continue
            for h in (race.get("order") or []):
                hno = h.get("horse_no")
                if hno:
                    entries.append((hip.upper(), rno, int(hno)))
    return entries


# ── Tek kart çekimi ───────────────────────────────────────────────────────────

def _fetch_one(session, code: str, delay: float) -> dict | None:
    import requests
    from io import StringIO
    try:
        import pandas as pd
    except ImportError:
        print("  HATA: pandas yuklu degil.")
        return None

    DROP_COLS = {"Gny", "Ikramiye", "İkramiye", "Kazanç", "K. No-K. Adı", "K. No-K. AdÄ±"}

    def _clean(v):
        if pd.isna(v):
            return None
        try:
            return v.item()
        except Exception:
            return v

    url = CARD_URL.format(code=code)
    for attempt in range(4):
        try:
            r = session.get(url, timeout=25)
            break
        except requests.exceptions.RequestException:
            if attempt == 3:
                return None
            time.sleep(1.5 * (attempt + 1))
    else:
        return None

    time.sleep(delay)
    if r.status_code != 200:
        return None
    try:
        tables = pd.read_html(StringIO(r.text))
        if len(tables) < 2:
            return None
        hist = tables[1]
        keep = [c for c in hist.columns if str(c) not in DROP_COLS
                and not str(c).startswith("Unnamed:") and not str(c).startswith("K. No-K.")]
        hist = hist[keep]
        rows = [{str(k): _clean(v) for k, v in row.items()}
                for row in hist.to_dict(orient="records")]
    except Exception:
        return None

    if not rows:
        return None
    return {
        "atkodu": code,
        "source_url": url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "history_rows": rows,
    }


# ── Ana işlev ─────────────────────────────────────────────────────────────────

def update_cards_after_results(
    day: date,
    hip_filter: str | None = None,
    race_filter: int | None = None,
    delay: float = 0.3,
    max_age_hours: float = 6.0,
    dry: bool = False,
    verbose: bool = True,
) -> tuple[int, int, int]:
    """Sonuclanan kosulardaki atlarin kartlarini gunceller.

    max_age_hours: Kart dosyasi bu saatten daha yeni ise yeniden cekilmez.
    Boylece her 5 dk tetiklendiginde ayni atlar tekrar cekilmez.
    """
    import requests

    ensure_dirs()
    HORSE_CARDS_RAW_DIR.mkdir(parents=True, exist_ok=True)

    code_map = _build_code_map(day)
    if not code_map:
        if verbose:
            print(f"  [kart-sonrasi] {day}: program JSON bulunamadi, at kodlari cikarilmiyor.")
        return 0, 0, 0

    race_horses = _find_race_horses(day, hip_filter, race_filter)
    if not race_horses:
        if verbose:
            print(f"  [kart-sonrasi] {day}: sonuclanan kosu bulunamadi.")
        return 0, 0, 0

    now = time.time()
    max_age_sec = max_age_hours * 3600

    # horse_no -> at kodu eslesimi
    to_update: dict[str, str] = {}  # {at_kodu: horse_name}
    missing_code: list[tuple] = []
    skipped_fresh = 0
    for hip, rno, hno in race_horses:
        code = code_map.get((hip, hno))
        if not code:
            missing_code.append((hip, rno, hno))
            continue
        # max_age_hours'dan yeni ise atlat
        card_path = HORSE_CARDS_RAW_DIR / f"{code}.json"
        if card_path.exists() and (now - card_path.stat().st_mtime) < max_age_sec:
            skipped_fresh += 1
            continue
        to_update[code] = f"{hip} K{rno} No{hno}"

    if verbose:
        if missing_code:
            print(f"  [kart-sonrasi] {day}: {len(missing_code)} at icin kod bulunamadi "
                  f"(ekuri/scratch olabilir)")
        if skipped_fresh:
            print(f"  [kart-sonrasi] {day}: {skipped_fresh} at karti taze (<{max_age_hours}s), atlandi")
        if not to_update:
            print(f"  [kart-sonrasi] {day}: guncellenecek kart yok.")
            return 0, 0, 0
        print(f"  [kart-sonrasi] {day}: {len(to_update)} at karti guncellenecek"
              + (" (DRY RUN)" if dry else ""))

    if dry:
        for code, label in sorted(to_update.items()):
            print(f"    {code}: {label}")
        return len(to_update), 0, 0

    session = requests.Session()
    session.headers.update(HEADERS)

    updated = failed = 0
    total = len(to_update)
    for i, (code, label) in enumerate(sorted(to_update.items()), 1):
        out_path = HORSE_CARDS_RAW_DIR / f"{code}.json"
        payload = _fetch_one(session, code, delay)
        if not payload:
            if verbose:
                print(f"  [{i}/{total}] {code} ({label}): veri alinamadi")
            failed += 1
            continue
        payload["program_identity"] = {"label": label, "program_date": f"{day:%Y-%m-%d}"}
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        updated += 1
        if verbose and (updated % 20 == 0 or i == total):
            print(f"  [{i}/{total}] guncellendi: {updated} at, {failed} basarisiz")

    # lru_cache temizle
    try:
        from harbi_v3.horse_cards import load_card_races
        load_card_races.cache_clear()
    except Exception:
        pass

    if verbose:
        print(f"  [kart-sonrasi] tamamlandi: {updated} guncellendi, {failed} basarisiz / {total}")
    return total, updated, failed


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sonuclanan kosulardaki atlarin at kartlarini guncelle."
    )
    parser.add_argument("tarih", nargs="?", default=None,
                        help="YYYY-MM-DD (default: bugun)")
    parser.add_argument("--hip", default=None, help="Sadece belirtilen hipodrom")
    parser.add_argument("--race", type=int, default=None, help="Sadece N. kosu")
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--max-age-hours", type=float, default=6.0,
                        help="Kartı bu saatten yeni olan atları atla (default: 6)")
    parser.add_argument("--dry", action="store_true", help="Sadece goster, cekme")
    args = parser.parse_args()

    day = date.fromisoformat(args.tarih) if args.tarih else date.today()
    total, updated, failed = update_cards_after_results(
        day, hip_filter=args.hip, race_filter=args.race,
        delay=args.delay, max_age_hours=args.max_age_hours, dry=args.dry,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
