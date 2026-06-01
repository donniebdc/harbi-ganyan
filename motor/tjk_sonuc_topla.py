# -*- coding: utf-8 -*-
"""
TJK SONUÇ TOPLAYICI  (resmi TJK feed -> JSON sonuç arşivi)
================================================================================
Sonuçları TJK'nın resmi statik JSON feed'inden çeker:
    https://ebayi.tjk.org/s/d/sonuclar/<YYYYMMDD>/yarislar.json      (hipodrom listesi)
    https://ebayi.tjk.org/s/d/sonuclar/<YYYYMMDD>/full/<KEY>.json    (tam sonuç)

Pegadrom'a göre üstün: at_no DOĞRUDAN gelir (köprü yok), kombine bahis ikramiyeleri
(GANYAN, İKİLİ, SIRALI İKİLİ, ÜÇLÜ, PLASE, ÇİFTE, 3'LÜ/5'Lİ/6'LI GANYAN, 7'Lİ PLASE)
`emiParasalNeticeler_tr` alanında bulunur. CSV'nin kapsamadığı tarihleri de kapsar.

Çıktı: `Sonuclar JSON/<YYYY-MM-DD>.json` — `altili_lib.load_all_json` ile uyumlu
(kazanan, ekuri, n_at, siralama) + ek alanlar (bahisler, kosmaz, mesafe, pist).

Kullanım:
    python tjk_sonuc_topla.py 2026-02-01 2026-03-31
    python tjk_sonuc_topla.py 15.05.2026 15.05.2026 --force
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests

FEED = "https://ebayi.tjk.org/s/d"
DEFAULT_OUT = "Sonuclar JSON"
DEFAULT_DELAY = 0.5
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/151.0",
           "Referer": "https://www.google.com/"}

PROJ_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Yerli (Türkiye) hipodrom KEY'leri — feed yabancı hipodromları da listeler.
TR_KEYS = {"ISTANBUL", "ANKARA", "IZMIR", "BURSA", "ADANA", "ELAZIG", "ELAZIĞ",
           "DIYARBAKIR", "KOCAELI", "SANLIURFA", "BALIKESIR", "ANTALYA", "MERSIN",
           "KAYSERI", "GAZIANTEP", "SIVAS", "BATMAN", "MUS"}


def parse_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError("Tarih: YYYY-MM-DD / GG.AA.YYYY / YYYYMMDD")


def _tutar(s: str):
    """'12.948,06' -> 12948.06 ; '2,30' -> 2.30."""
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


# emiParasalNeticeler_tr: "TİP(kombo): tutarTL TİP2(...): ...TL ... AGF:1"
RE_BAHIS = re.compile(r"([0-9A-ZÇĞİÖŞÜa-zçğıöşü'’.\s]+?)\(([0-9,/\s]+)\)\s*:\s*([\d.]+,\d+)\s*TL")

def parse_bahisler(metin: str):
    """emiParasalNeticeler_tr metnini [{'tip','kombinasyon','tutar'}] listesine çevirir."""
    out = []
    for m in RE_BAHIS.finditer(metin or ""):
        tip = re.sub(r"\s+", " ", m.group(1)).strip()
        tip = re.sub(r"^\d+\s*TL\s*", "", tip).strip()   # önceki tutardan sızan '77TL ' artığı
        kombo = re.sub(r"\s+", "", m.group(2))
        out.append({"tip": tip, "kombinasyon": kombo, "tutar": _tutar(m.group(3))})
    return out


def _int(s):
    try:
        return int(str(s).strip())
    except (ValueError, TypeError):
        return None


def build_kosu(k: dict) -> dict | None:
    atlar_raw = k.get("atlar") or []
    if not atlar_raw:
        return None
    siralama = []
    ekuri_g = defaultdict(set)
    kosmaz = []
    kazanan = None
    kosanlar = 0
    for a in atlar_raw:
        no = _int(a.get("NO"))
        kosmaz_flg = str(a.get("KOSMAZ") or "").strip() in ("1", "true", "True")
        if kosmaz_flg:
            if no:
                kosmaz.append(no)
            continue
        kosanlar += 1
        sonuc = _int(a.get("SONUC"))
        siralama.append({
            "sira": sonuc, "at_no": no, "at": (a.get("AD") or "").strip(),
            "derece": (a.get("DERECE") or "").strip(), "ganyan": _tutar(a.get("GANYAN")),
            "jokey_kodu": _int(a.get("JOKEYKODU")), "agf": _tutar(a.get("AGF1")),
        })
        ek = (a.get("EKURI") or "").strip()
        if ek and no:
            ekuri_g[ek].add(no)
        if sonuc == 1 and no:
            kazanan = no
    siralama.sort(key=lambda x: (x["sira"] is None, x["sira"] if x["sira"] is not None else 99))
    ekuri = [sorted(v) for v in ekuri_g.values() if len(v) >= 2]
    # Berabere (dead-heat): resmi GANYAN(n) ödemesi birden çok at için varsa hepsi birinci.
    bahisler = parse_bahisler(k.get("emiParasalNeticeler_tr"))
    ganyan_kaz = [_int(b["kombinasyon"]) for b in bahisler
                  if b["tip"] == "GANYAN" and _int(b["kombinasyon"])]
    kazananlar = sorted(set(([kazanan] if kazanan else []) + ganyan_kaz))
    if kazanan is None and ganyan_kaz:
        kazanan = ganyan_kaz[0]
    return {
        "no": _int(k.get("NO")), "n_at": kosanlar, "kazanan": kazanan,
        "kazananlar": kazananlar, "ekuri": ekuri, "kosmaz": kosmaz,
        "mesafe": _int(k.get("MESAFE")), "pist": (k.get("PISTADI_TR") or "").strip(),
        "siralama": siralama,
        "bahisler": {"raw": (k.get("emiParasalNeticeler_tr") or "").strip(),
                     "kalemler": bahisler},
    }


def fetch_json(session: requests.Session, url: str):
    r = session.get(url, timeout=20)
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def collect_range(start: datetime, end: datetime, out_dir: Path, delay: float, force: bool) -> None:
    session = requests.Session()
    session.headers.update(HEADERS)
    out_dir.mkdir(parents=True, exist_ok=True)
    current = start
    gun_yaz = gun_atla = kosu_yaz = hata = 0

    while current <= end:
        date_iso = current.strftime("%Y-%m-%d")
        ymd = current.strftime("%Y%m%d")
        json_path = out_dir / f"{date_iso}.json"
        if json_path.exists() and not force:
            gun_atla += 1
            print(f"{date_iso}: var, atlandı")
            current += timedelta(days=1)
            continue

        liste = fetch_json(session, f"{FEED}/sonuclar/{ymd}/yarislar.json")
        time.sleep(delay)
        if not isinstance(liste, list) or not liste:
            print(f"{date_iso}: liste yok")
            current += timedelta(days=1)
            continue
        tr_hips = [h for h in liste if (h.get("KEY") or "").upper() in TR_KEYS]
        if not tr_hips:
            print(f"{date_iso}: yerli hipodrom yok")
            current += timedelta(days=1)
            continue

        gun = {"tarih": date_iso, "kaynak": "tjk", "hipodromlar": {}}
        print(f"{date_iso}: " + ", ".join(h["KEY"] for h in tr_hips))
        for h in tr_hips:
            key = h["KEY"].upper()
            data = fetch_json(session, f"{FEED}/sonuclar/{ymd}/full/{key}.json")
            time.sleep(delay)
            if not isinstance(data, dict):
                print(f"  {key}: full yok"); continue
            kosular = {}
            for k in data.get("kosular") or []:
                kv = build_kosu(k)
                if kv and kv.get("kazanan"):
                    kosular[str(kv["no"])] = kv
                    kosu_yaz += 1
            if kosular:
                gun["hipodromlar"][key] = {"ad": (h.get("AD") or "").strip(), "kosular": kosular}
                print(f"  {key}: {len(kosular)} koşu")

        if gun["hipodromlar"]:
            json_path.write_text(json.dumps(gun, ensure_ascii=False, indent=1), encoding="utf-8")
            gun_yaz += 1
        current += timedelta(days=1)

    print(f"\nTamamlandı. Gün yazılan: {gun_yaz}, atlanan: {gun_atla}, koşu: {kosu_yaz}, hata: {hata}")
    print(f"Çıktı: {out_dir.resolve()}")


def main() -> None:
    ap = argparse.ArgumentParser(description="TJK resmi feed'inden sonuçları JSON olarak toplar.")
    ap.add_argument("baslangic", type=parse_date)
    ap.add_argument("bitis", type=parse_date)
    ap.add_argument("--out", default=None)
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.bitis < args.baslangic:
        raise SystemExit("Bitiş başlangıçtan önce olamaz.")
    out_dir = Path(args.out) if args.out else Path(PROJ_BASE) / DEFAULT_OUT
    collect_range(args.baslangic, args.bitis, out_dir, args.delay, args.force)


if __name__ == "__main__":
    main()
