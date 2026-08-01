# -*- coding: utf-8 -*-
"""Yarış öncesi canlı giriş takibi — TJK'dan güncel giriş tablosu + snapshot diff.

Amaç: üretim anındaki giriş tablosu ile şu anki giriş tablosunu karşılaştırıp
jokey değişikliği / koşmaz (çıkan) at / pist-mesafe değişikliğini tespit etmek.
Değişiklik varsa daily_pipeline tüm günü yeniden üretir + revize bildirimi gönderir.

Snapshot şekli:
  { hip: { kno(int): { "pist":..., "mesafe":..., "saat":...,
                       "atlar": { at_no(int): {"jokey":..., "aktif": bool} } } } }
Dosya: backend/export/out/<iso>_giris.json
"""
from __future__ import annotations
import os
import sys
import json
from pathlib import Path

import requests

BACKEND_DIR = Path(os.environ.get("HG_BACKEND_DIR") or Path(__file__).resolve().parents[1])
V3_SRC = Path(os.environ.get("HG_V3_ROOT") or "/opt/harbi_ganyan_v3") / "src"
sys.path.insert(0, str(BACKEND_DIR))
if str(V3_SRC) not in sys.path:
    sys.path.insert(0, str(V3_SRC))

from harbi_v3.normalize import is_turkiye_hipodrom, norm_text  # noqa: E402

OUT_DIR = BACKEND_DIR / "export" / "out"


def normalize_sehir(name: str) -> str:
    return norm_text(name)


def normalize_jokey(name: str) -> str:
    return norm_text(name) if name else ""


_TJK_H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
    'X-Requested-With': 'XMLHttpRequest', 'platformId': '1',
    'Origin': 'https://www.atyarisi.com', 'Referer': 'https://www.atyarisi.com/',
}


def _pist(pr: str) -> str:
    pr = (pr or 'Kum')
    low = pr.lower()
    if 'çim' in low or 'cim' in low:
        return 'Çim'
    if any(s in low for s in ['sentetik', 'awt']):
        return 'Sentetik'
    return 'Kum'


def mevcut_giris(iso: str) -> dict:
    """TJK'dan o günün GÜNCEL giriş tablosunu çeker. iso=YYYY-MM-DD."""
    snap: dict = {}
    try:
        r = requests.get(
            f"https://tjkbulten.atyarisi.com/api/v1/ProgramHippodromes?date={iso}",
            headers=_TJK_H, timeout=15)
        if r.status_code != 200:
            return snap
        cj = r.json()
        hips = cj.get('d', cj) if isinstance(cj, dict) else cj
    except Exception:
        return snap
    if not isinstance(hips, list):
        return snap
    for hp in hips:
        pid = hp.get('id') or hp.get('programId')
        if not pid:
            continue
        hobj = hp.get('hippodrome', {})
        sad = (hobj.get('place') or hobj.get('name') or hp.get('place')
               or hp.get('name') or '')
        if not is_turkiye_hipodrom(sad):
            continue
        hip = normalize_sehir(sad)
        try:
            rd = requests.get(
                f"https://tjkbulten.atyarisi.com/api/v2/ProgramDetails?programId={pid}",
                headers=_TJK_H, timeout=15)
            if rd.status_code != 200:
                continue
            dj = rd.json()
        except Exception:
            continue
        inner = dj.get('d', dj)
        races = inner.get('races', []) if isinstance(inner, dict) else []
        kosular = {}
        for race in races:
            if not isinstance(race, dict):
                continue
            kno = race.get('number')
            if not isinstance(kno, int):
                continue
            atlar = {}
            for h in race.get('horses', []) or []:
                try:
                    ano = int(h.get('number') or 0)
                except (ValueError, TypeError):
                    continue
                if ano <= 0:
                    continue
                jobj = h.get('jockey', {}) or {}
                jok = normalize_jokey(jobj.get('name') or jobj.get('jockeyLongName') or '')
                atlar[ano] = {"jokey": jok, "aktif": h.get('status') is not False}
            kosular[kno] = {
                "pist": _pist(race.get('raceCourseType', 'Kum')),
                "mesafe": str(race.get('distance') or ''),
                "saat": race.get('hour', '') or '',
                "atlar": atlar,
            }
        if kosular:
            snap[hip] = kosular
    return snap


def snapshot_yolu(iso: str) -> Path:
    return OUT_DIR / f"{iso}_giris.json"


def snapshot_kaydet(iso: str, snap: dict):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_yolu(iso).write_text(
        json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")


def snapshot_yukle(iso: str) -> dict:
    f = snapshot_yolu(iso)
    if not f.exists():
        return {}
    try:
        ham = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for hip, kosular in ham.items():
        out[hip] = {}
        for kno_s, kv in kosular.items():
            atlar = {int(a): v for a, v in (kv.get("atlar") or {}).items()}
            out[hip][int(kno_s)] = {**kv, "atlar": atlar}
    return out


def diff(eski: dict, yeni: dict) -> list[dict]:
    """Üretim-anı (eski) ile güncel (yeni) giriş tablosunu karşılaştırır.
    Döner: [{hip, kno, tur, sebep}]. tur ∈ {kosmaz, jokey, pist}."""
    degisim = []
    for hip, k_yeni in yeni.items():
        k_eski = eski.get(hip)
        if not k_eski:
            continue
        for kno, kv_yeni in k_yeni.items():
            kv_eski = k_eski.get(kno)
            if not kv_eski:
                continue
            if (kv_eski.get("pist") != kv_yeni.get("pist")
                    or kv_eski.get("mesafe") != kv_yeni.get("mesafe")):
                degisim.append({"hip": hip, "kno": kno, "tur": "pist",
                                "sebep": f"{kno}. koşu pist/mesafe değişti"})
            at_eski = kv_eski.get("atlar") or {}
            at_yeni = kv_yeni.get("atlar") or {}
            for ano, av_eski in at_eski.items():
                av_yeni = at_yeni.get(ano)
                if av_yeni is None or (av_eski.get("aktif") and not av_yeni.get("aktif")):
                    degisim.append({"hip": hip, "kno": kno, "tur": "kosmaz",
                                    "sebep": f"{kno}. koşuda {ano} numara yarıştan çıkarıldı"})
                    continue
                je, jy = av_eski.get("jokey") or "", av_yeni.get("jokey") or ""
                if je and jy and je != jy:
                    degisim.append({"hip": hip, "kno": kno, "tur": "jokey",
                                    "sebep": f"{kno}. koşuda {ano} numara jokey değişikliği"})
    return degisim
