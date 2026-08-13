# -*- coding: utf-8 -*-
"""Harbi Secim: kosu bazinda dinamik aday secimi — rev7 (Performans Odakli).

Degisiklik (rev7 — 2026-07-11):
  rev6'dan farklar:
  1. ZOR kosularda iki_aday kaldirildi (STOP2_GAP["ZOR"]=999).
     Analiz: ZOR'da 2 at verince %60 hit, 3 atta %69.5, 4 atta %78.2.
     ZOR'da minimum uc_aday garanti edilir.
  2. COK_ZOR genis liste cap dusuruldu: 14+at icin 8->6, 11+at icin 7->5.
     Analiz: COK_ZOR top-5=%83.8, top-6=%88.9 — 7-8 at bonkorce.
  3. KOLAY kosularda sürdirek olmasa da tek_at mumkun:
     s1>=75 ve g1>=30 esikleri saglaniyorsa tek_at donulur.
  4. Surdirek override MUTLAK garanti — rev6'dan degismedi.

Korunan kurallar (rev4/rev6'dan):
  - Surdirek kosusu → MUTLAK tek_at (force_nos bagimsiz)
  - force_include_nos → Surpriz radar atlari bu listeye girer
  - COK_ZOR → genis_liste (cekirdek) + ortalama-ustu birlesimi
"""
from __future__ import annotations
from typing import Optional

# -- Tek At esikleri
SINGLE_MIN_SCORE = 75.0
# KOLAY: sürdirek olmadan da tek_at; ORTA/ZOR/COK_ZOR: sadece sürdirek icin
SINGLE_GAP_BASE  = {"KOLAY": 30, "ORTA": 999, "ZOR": 999, "COK_ZOR": 999}

# -- Durma esikleri
# ZOR'da STOP2=999 → ZOR'da asla iki_aday verilmez (min uc_aday)
STOP2_GAP = {"KOLAY": 10, "ORTA": 12, "ZOR": 999, "COK_ZOR": 999}
STOP3_GAP = {"KOLAY": 7,  "ORTA":  9, "ZOR":  11, "COK_ZOR": 999}
STOP4_GAP = {"KOLAY": 5,  "ORTA":  7, "ZOR":   9, "COK_ZOR": 999}

# -- Skor alt esikleri
TWO_MIN_SCORE   = 57.0
THREE_MIN_SCORE = 50.0
FOUR_MIN_SCORE  = 44.0

# -- Genis liste at sayisi
# Normal (KOLAY/ORTA/ZOR): eski tablo, dokunulmadi
_GENIS_TABLE        = [(14, 8), (11, 7), (8, 6), (5, 5), (0, 4)]
# COK_ZOR: cap dusuruldu (8->7, 7->6) — analiz: top-7=%92.6, top-8 marjinal
_GENIS_TABLE_COK_ZOR = [(14, 7), (11, 6), (8, 5), (5, 4), (0, 4)]

_TIP_BASLIK = {
    "tek_at":      "Tek At",
    "iki_aday":    "2 Aday",
    "uc_aday":     "3 Aday",
    "dort_aday":   "4 Aday",
    "genis_liste": "Genis Liste",
}


def _tip(adet: int) -> str:
    if adet <= 1: return "tek_at"
    if adet == 2: return "iki_aday"
    if adet == 3: return "uc_aday"
    if adet == 4: return "dort_aday"
    return "genis_liste"


def _dynamic_single_gap(zorluk_kodu: Optional[str], n_at: int) -> float:
    base = float(SINGLE_GAP_BASE.get(zorluk_kodu or "ORTA", 14))
    if n_at <= 7:
        base -= 2
    elif n_at >= 14:
        base += 3
    elif n_at >= 11:
        base += 2
    return base


def _genis_adet(n_at: int, zorluk_kodu: Optional[str]) -> int:
    table = _GENIS_TABLE_COK_ZOR if zorluk_kodu == "COK_ZOR" else _GENIS_TABLE
    for min_n, adet in table:
        if n_at >= min_n:
            return adet
    return 4


def compute(
    analiz_puanlari: list,
    n_at: int = 0,
    zorluk_kodu: Optional[str] = None,
    is_surdirek: bool = False,
    surdirek_horse_no: Optional[int] = None,
    force_include_nos: Optional[list] = None,
) -> dict:
    """Harbi Secim dict doner — rev6 A Sistem + Surdirek Garantisi.

    is_surdirek=True + surdirek_horse_no → MUTLAK tek_at (force_nos bagimsiz)
    is_surdirek=False                    → min 2 at garantili; tek_at donmez
    force_include_nos                    → bu at numaralari secim listesine eklenir
    COK_ZOR                              → genis_liste cekirdek + ortalama-ustu
    """
    force_nos = set(force_include_nos or [])
    sirali    = sorted(analiz_puanlari, key=lambda x: x.get("sira", 99))
    if not sirali:
        return {"tip": "genis_liste", "ui_baslik": "Genis Liste", "adet": 0,
                "adaylar": [], "gerekce": "Analiz verisi yok."}

    n  = n_at or len(sirali)
    zk = zorluk_kodu

    def _aday(p, sira_idx):
        return {"at_no": p["at_no"], "at": p.get("at", ""),
                "model_sira": sira_idx + 1,
                "model_skor": round(float(p.get("ana", 0)), 1)}

    def _sonuc(tip, adaylar, gerekce=""):
        return {"tip": tip, "ui_baslik": _TIP_BASLIK.get(tip, tip),
                "adet": len(adaylar), "adaylar": adaylar, "gerekce": gerekce}

    # -- Ortalama hesapla (COK_ZOR icin kullaniliyor)
    scores    = [float(p.get("ana", 0)) for p in sirali]
    avg       = sum(scores) / len(scores) if scores else 0.0
    above_nos = {p["at_no"] for p in sirali if float(p.get("ana", 0)) >= avg}

    def _add_above_avg(sonuc_dict):
        """Sadece COK_ZOR icin: ortalama ustu adaylari ekle."""
        mevcut = {a["at_no"] for a in sonuc_dict["adaylar"]}
        eksik  = above_nos - mevcut
        if not eksik:
            return sonuc_dict
        for i, p in enumerate(sirali):
            if p["at_no"] in eksik:
                sonuc_dict["adaylar"].append(_aday(p, i))
        sonuc_dict["adaylar"].sort(key=lambda a: a["model_sira"])
        adet = len(sonuc_dict["adaylar"])
        sonuc_dict["adet"]      = adet
        t = _tip(adet)
        sonuc_dict["tip"]       = t
        sonuc_dict["ui_baslik"] = _TIP_BASLIK.get(t, t)
        return sonuc_dict

    def _ensure_force(sonuc_dict):
        """force_include_nos'daki atlar listede yoksa ekle (surpriz radar)."""
        if not force_nos:
            return sonuc_dict
        mevcut = {a["at_no"] for a in sonuc_dict["adaylar"]}
        eksik  = force_nos - mevcut
        if not eksik:
            return sonuc_dict
        for i, p in enumerate(sirali):
            if p["at_no"] in eksik:
                sonuc_dict["adaylar"].append(_aday(p, i))
        sonuc_dict["adaylar"].sort(key=lambda a: a["model_sira"])
        adet = len(sonuc_dict["adaylar"])
        sonuc_dict["adet"] = adet
        t = _tip(adet)
        if sonuc_dict["tip"] == "tek_at" and adet > 1:
            sonuc_dict["tip"]       = "iki_aday"
            sonuc_dict["ui_baslik"] = _TIP_BASLIK["iki_aday"]
        else:
            sonuc_dict["tip"]       = t
            sonuc_dict["ui_baslik"] = _TIP_BASLIK.get(t, t)
        return sonuc_dict

    # 1. Surdirek override — MUTLAK GARANTI (force_nos bagimsiz)
    if is_surdirek and surdirek_horse_no:
        idx = next((i for i, p in enumerate(sirali) if p["at_no"] == surdirek_horse_no), None)
        if idx is not None:
            return _sonuc("tek_at", [_aday(sirali[idx], idx)], "Gunun Surdirek kosusu.")

    def gap(i):
        return scores[i] - scores[i + 1] if i + 1 < len(scores) else 999.0

    s1, g1 = scores[0], gap(0)

    # 2a. Sürdirek tek_at — surpriz cakismasi olmayan surdirek kosularinda
    if is_surdirek and not force_nos and zk != "COK_ZOR":
        if s1 >= SINGLE_MIN_SCORE and g1 >= _dynamic_single_gap(zk, n):
            return _sonuc("tek_at", [_aday(sirali[0], 0)],
                          "Surdirek: model ilk adayi one cikariyor.")

    # 2b. Guvenilir tek_at — KOLAY kosularda sürdirek olmadan da mumkun
    # Kriter: s1>=75 ve g1>=30 (backtest: KOLAY top-1=%100)
    if not force_nos and zk == "KOLAY" and s1 >= SINGLE_MIN_SCORE and g1 >= _dynamic_single_gap(zk, n):
        return _sonuc("tek_at", [_aday(sirali[0], 0)],
                      "Guvenilir kos: model acik ara one cikiyor.")

    # 3. COK_ZOR: cekirdek genis_liste + ortalama-ustu (rev4'ten korunan)
    if zk == "COK_ZOR":
        adet  = min(_genis_adet(n, zk), len(sirali))
        temel = _sonuc("genis_liste",
                       [_aday(sirali[i], i) for i in range(adet)],
                       "Cok zor kos — genis liste + ort.ustu.")
        return _ensure_force(_add_above_avg(temel))

    s2 = scores[1] if len(scores) > 1 else 0.0
    s3 = scores[2] if len(scores) > 2 else 0.0
    s4 = scores[3] if len(scores) > 3 else 0.0
    g2 = gap(1); g3 = gap(2); g4 = gap(3)

    bg2 = float(STOP2_GAP.get(zk, 12))
    bg3 = float(STOP3_GAP.get(zk, 9))
    bg4 = float(STOP4_GAP.get(zk, 7))

    # 4. Cekirdek: 2 Aday (A sistem — sadece cekirdek, ortalama-ustu ekleme yok)
    if s2 >= TWO_MIN_SCORE and g2 >= bg2:
        temel = _sonuc("iki_aday",
                       [_aday(sirali[i], i) for i in range(min(2, len(sirali)))],
                       "2 aday cekirdek.")
        return _ensure_force(temel)

    # 5. Cekirdek: 3 Aday
    if s3 >= THREE_MIN_SCORE and g3 >= bg3:
        temel = _sonuc("uc_aday",
                       [_aday(sirali[i], i) for i in range(min(3, len(sirali)))],
                       "3 aday cekirdek.")
        return _ensure_force(temel)

    # 6. Cekirdek: 4 Aday
    if s4 >= FOUR_MIN_SCORE and g4 >= bg4:
        temel = _sonuc("dort_aday",
                       [_aday(sirali[i], i) for i in range(min(4, len(sirali)))],
                       "4 aday cekirdek.")
        return _ensure_force(temel)

    # 7. Cekirdek: Genis Liste (sert cap — ortalama-ustu ekleme yok)
    adet  = min(_genis_adet(n, zk), len(sirali))
    temel = _sonuc("genis_liste",
                   [_aday(sirali[i], i) for i in range(adet)],
                   "Kosu belirsiz, genis liste.")
    return _ensure_force(temel)
