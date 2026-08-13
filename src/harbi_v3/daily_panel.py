# -*- coding: utf-8 -*-
"""
daily_panel.py — Günlük analiz paneli özeti.

Günün tüm koşu tahminlerinden tek geçişte üretilir.
Model pipeline'ına dokunmaz; RacePrediction + AgfRadarResult + DifficultyResult
nesnelerinden çalışır.

v3_export.py tarafından build_day_payload() içinde çağrılır.
Çıktı export JSON'unun kök seviyesine "daily_panel" anahtarıyla eklenir.

v1 kapsamı:
  - Günün Sürdireği
  - En net ayrışan koşular (yüksek güven)
  - En zor koşular
  - AGF/model uyum ve ayrışma sayıları
  - "Düşük AGF / yüksek model" aday sayısı
  - Günün genel zorluk özeti
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .predictor import RacePrediction
    from .agf_radar import AgfRadarResult
    from .race_difficulty import DifficultyResult

# ---------------------------------------------------------------------------
# Yardımcı yapılar
# ---------------------------------------------------------------------------

@dataclass
class KosuKarti:
    """Panel listelerinde tek koşuyu temsil eder."""
    hip:            str
    kno:            int
    race_type:      str
    n_at:           int
    guven:          str
    zorluk_kodu:    str | None
    zorluk_puani:   float
    norm_score_gap: float
    agf_model_uyum: bool | None   # None → AGF mevcut değil
    # Sadece agf_ayrismalari listesinde dolu gelir
    model_fav_no:       int | None = None
    model_fav_name:     str | None = None
    model_fav_agf_poz:  int | None = None
    agf_fav_hno:        int | None = None
    agf_fav_model_sira: int | None = None


@dataclass
class DailyPanelResult:
    # Özet sayaçlar
    toplam_kosu:      int
    kolay:            int
    orta:             int
    zor:              int
    cok_zor:          int
    agf_mevcut_kosu:  int   # AGF verisi olan koşu sayısı
    agf_uyumlu_kosu:  int   # AGF#1 model top-3 içinde
    agf_ayrisan_kosu: int   # dikkat çeken model-AGF ayrışması
    surpriz_aday:     int   # "surpriz" etiketli at en az 1 olan koşu sayısı

    # Listeler
    one_cikanlar:   list[KosuKarti]   # Yüksek / Çok Yüksek güvenli koşular
    zor_kosular:    list[KosuKarti]   # Zor + Çok Zor
    agf_ayrismalari: list[KosuKarti]  # AGF ve model ayrışan koşular
    surdirekt:      KosuKarti | None  # Günün sürdireği (en yüksek gap'li yüksek güven)


# ---------------------------------------------------------------------------
# Hesaplama
# ---------------------------------------------------------------------------

def compute(
    races: list["RacePrediction"],
    agf_results: dict[tuple[str, int], "AgfRadarResult"],
    difficulty_results: dict[tuple[str, int], "DifficultyResult"],
    guven_map: dict[tuple[str, int], str],
    surpriz_race_keys: set[tuple[str, int]],
) -> DailyPanelResult:
    """
    Günlük panel özetini üretir.

    Parameters:
        races:              predict_for_date() çıktısı
        agf_results:        {(hip, race_no): AgfRadarResult}
        difficulty_results: {(hip, race_no): DifficultyResult}
        guven_map:          {(hip, race_no): guven_str}
        surpriz_race_keys:  En az 1 "surpriz" etiketli at içeren koşuların anahtarları

    Çıktı: DailyPanelResult
    """
    toplam = len(races)
    kolay = orta = zor = cok_zor = 0
    agf_mevcut = agf_uyumlu = agf_ayrisan = 0
    surpriz_kosu = 0

    one_cikanlar: list[KosuKarti] = []
    zor_kosular:  list[KosuKarti] = []
    agf_ayrismalari: list[KosuKarti] = []
    surdirekt_aday: KosuKarti | None = None
    surdirekt_gap: float = -1.0

    from .confidence import race_type_bucket

    for race in races:
        key = (race.hip, race.race_no)
        diff = difficulty_results.get(key)
        agf  = agf_results.get(key)
        guven = guven_map.get(key, "riskli")
        bucket = race_type_bucket(race.race_type or "", race.race_group or "")

        # Zorluk dağılımı
        kod = diff.zorluk_kodu if diff else None
        puan = diff.zorluk_puani if diff else 0.0
        if kod == "KOLAY":   kolay += 1
        elif kod == "ORTA":  orta += 1
        elif kod == "ZOR":   zor += 1
        elif kod == "COK_ZOR": cok_zor += 1

        # AGF uyum/ayrışma
        # "Dikkat çeken ayrışma": model fav AGF'de 4+. sırada
        # VEYA AGF#1 model sıralamasında 4+. sırada
        _dikkat = agf and agf.agf_mevcut and (
            (agf.model_fav_agf_poz is not None and agf.model_fav_agf_poz >= 4)
            or (agf.agf_fav_model_sira is not None and agf.agf_fav_model_sira > 3)
        )
        if agf and agf.agf_mevcut:
            agf_mevcut += 1
            if agf.agf_model_uyum:
                agf_uyumlu += 1
            if _dikkat:
                agf_ayrisan += 1

        # Sürpriz aday sayısı
        if key in surpriz_race_keys:
            surpriz_kosu += 1

        kart = KosuKarti(
            hip=race.hip,
            kno=race.race_no,
            race_type=bucket,
            n_at=race.runner_count,
            guven=guven,
            zorluk_kodu=kod,
            zorluk_puani=puan,
            norm_score_gap=race.norm_score_gap,
            agf_model_uyum=agf.agf_model_uyum if (agf and agf.agf_mevcut) else None,
        )

        # Öne çıkanlar: yüksek veya çok yüksek güven
        if guven in ("surdirekt", "yuksek_guvenli"):
            one_cikanlar.append(kart)

        # Zor koşular
        if kod in ("ZOR", "COK_ZOR"):
            zor_kosular.append(kart)

        # AGF ayrışmaları — dikkat çeken koşular (agf_ayrisan ile tutarlı)
        if _dikkat:
            sorted_h = sorted(race.horses, key=lambda h: h.rank)
            _fav = sorted_h[0] if sorted_h else None
            agf_ayrismalari.append(KosuKarti(
                hip=kart.hip, kno=kart.kno, race_type=kart.race_type,
                n_at=kart.n_at, guven=kart.guven,
                zorluk_kodu=kart.zorluk_kodu, zorluk_puani=kart.zorluk_puani,
                norm_score_gap=kart.norm_score_gap, agf_model_uyum=kart.agf_model_uyum,
                model_fav_no=_fav.horse.horse_no if _fav else None,
                model_fav_name=_fav.horse.horse_name if _fav else None,
                model_fav_agf_poz=agf.model_fav_agf_poz,
                agf_fav_hno=agf.agf_fav_hno,
                agf_fav_model_sira=agf.agf_fav_model_sira,
            ))

        # Sürdirek adayı: en yüksek gap'li "surdirekt" koşu
        if guven == "surdirekt" and race.norm_score_gap > surdirekt_gap:
            surdirekt_gap = race.norm_score_gap
            surdirekt_aday = kart

    # Listeler gap'e göre sıralı (en güvenilir önce)
    one_cikanlar.sort(key=lambda k: k.norm_score_gap, reverse=True)
    # Zor koşular zorluk puanına göre (en zor önce)
    zor_kosular.sort(key=lambda k: k.zorluk_puani, reverse=True)

    return DailyPanelResult(
        toplam_kosu=toplam,
        kolay=kolay,
        orta=orta,
        zor=zor,
        cok_zor=cok_zor,
        agf_mevcut_kosu=agf_mevcut,
        agf_uyumlu_kosu=agf_uyumlu,
        agf_ayrisan_kosu=agf_ayrisan,
        surpriz_aday=surpriz_kosu,
        one_cikanlar=one_cikanlar[:5],
        zor_kosular=zor_kosular[:5],
        agf_ayrismalari=agf_ayrismalari[:5],
        surdirekt=surdirekt_aday,
    )


# ---------------------------------------------------------------------------
# Serileştirme
# ---------------------------------------------------------------------------

def _kart_to_dict(k: KosuKarti) -> dict:
    d: dict = {
        "hip":            k.hip,
        "kno":            k.kno,
        "race_type":      k.race_type,
        "n_at":           k.n_at,
        "guven":          k.guven,
        "zorluk_kodu":    k.zorluk_kodu,
        "zorluk_puani":   round(k.zorluk_puani, 1),
        "norm_score_gap": round(k.norm_score_gap, 1),
        "agf_model_uyum": k.agf_model_uyum,
    }
    # AGF ayrışma detayları — sadece agf_ayrismalari listesinde dolu
    if k.model_fav_no is not None:
        d["model_fav_no"]       = k.model_fav_no
        d["model_fav_name"]     = k.model_fav_name
        d["model_fav_agf_poz"]  = k.model_fav_agf_poz
        d["agf_fav_hno"]        = k.agf_fav_hno
        d["agf_fav_model_sira"] = k.agf_fav_model_sira
    return d


def to_dict(result: DailyPanelResult) -> dict:
    """JSON-serializable dict — export payload kök seviyesine eklenir."""
    return {
        "daily_panel": {
            "ozet": {
                "toplam_kosu":      result.toplam_kosu,
                "kolay":            result.kolay,
                "orta":             result.orta,
                "zor":              result.zor,
                "cok_zor":          result.cok_zor,
                "agf_mevcut_kosu":  result.agf_mevcut_kosu,
                "agf_uyumlu_kosu":  result.agf_uyumlu_kosu,
                "agf_ayrisan_kosu": result.agf_ayrisan_kosu,
                "surpriz_aday":     result.surpriz_aday,
            },
            "surdirek":       _kart_to_dict(result.surdirekt) if result.surdirekt else None,
            "one_cikanlar":   [_kart_to_dict(k) for k in result.one_cikanlar],
            "zor_kosular":    [_kart_to_dict(k) for k in result.zor_kosular],
            "agf_ayrismalari": [_kart_to_dict(k) for k in result.agf_ayrismalari],
        }
    }
