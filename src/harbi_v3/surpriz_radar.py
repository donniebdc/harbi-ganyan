# -*- coding: utf-8 -*-
"""
surpriz_radar.py — AGF'de geride olup modelin yüksek gördüğü sürpriz adaylar.

Model pipeline'ına dokunmaz. RacePrediction + AgfRadarResult + DifficultyResult
nesnelerinden çalışır. v3_export.py tarafından çağrılır.

Sürpriz aday kriterleri:
  - model_sira <= 5
  - agf_sira >= 4  (AGF pozisyonu modelden en az 2 basamak geride)
  - model_skor >= 55
  - surpriz_skoru >= 45 (bomba_aday eşiği)
  - Hipodrom başına maks 2 aday, toplam maks 5 aday

Etiket kuralı (model_sira'ya göre):
  gizli_aday:         model_sira 1 veya 2
  analize_eklenebilir: model_sira 3
  bomba_aday:         model_sira 4 veya 5
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .predictor import RacePrediction
    from .agf_radar import AgfRadarResult
    from .race_difficulty import DifficultyResult


# ---------------------------------------------------------------------------
# Etiketler
# ---------------------------------------------------------------------------

GIZLI_ADAY          = "gizli_aday"
ANALIZE_EKLENEBILIR = "analize_eklenebilir"
BOMBA_ADAY          = "bomba_aday"

UI_ETIKET: dict[str, str] = {
    GIZLI_ADAY:          "Gizli Aday",
    ANALIZE_EKLENEBILIR: "Analize Eklenebilir",
    BOMBA_ADAY:          "Bomba Aday",
}


# ---------------------------------------------------------------------------
# Çıktı yapısı
# ---------------------------------------------------------------------------

@dataclass
class SurprizAday:
    hip:           str
    kno:           int
    saat:          str | None
    at_no:         int
    at:            str
    model_sira:    int
    model_skor:    float      # model_ana'nın JSON karşılığı
    agf_sira:      int | None # agf_poz'un JSON karşılığı
    agf_pct:       float | None
    zorluk_kodu:   str | None
    zorluk_puani:  float
    surpriz_skoru: int
    etiket:        str
    ui_etiket:     str
    gerekce:       str


@dataclass
class SurprizRadarResult:
    adaylar: list[SurprizAday] = field(default_factory=list)

    @property
    def toplam_aday(self) -> int:
        return len(self.adaylar)

    @property
    def gizli_aday(self) -> int:
        return sum(1 for a in self.adaylar if a.etiket == GIZLI_ADAY)

    @property
    def analize_eklenebilir(self) -> int:
        return sum(1 for a in self.adaylar if a.etiket == ANALIZE_EKLENEBILIR)

    @property
    def bomba_aday(self) -> int:
        return sum(1 for a in self.adaylar if a.etiket == BOMBA_ADAY)


# ---------------------------------------------------------------------------
# Puanlama
# ---------------------------------------------------------------------------

def _score(
    model_sira:         int,
    agf_sira:           int,
    model_skor:         float,
    agf_fav_model_sira: int | None,
    zorluk_kodu:        str | None,
) -> int:
    puan = 0

    if model_sira == 1:           puan += 35
    elif model_sira == 2:         puan += 28
    elif model_sira == 3:         puan += 20
    elif model_sira in (4, 5):    puan += 10

    if agf_sira >= 6:    puan += 25
    elif agf_sira >= 4:  puan += 15

    if model_skor >= 70:    puan += 20
    elif model_skor >= 60:  puan += 12
    elif model_skor >= 55:  puan += 6

    if agf_fav_model_sira is not None and agf_fav_model_sira > 3:
        puan += 10

    if zorluk_kodu == "KOLAY":     puan += 4
    elif zorluk_kodu == "ORTA":    puan += 8
    elif zorluk_kodu == "ZOR":     puan += 4
    elif zorluk_kodu == "COK_ZOR": puan -= 8

    return puan


def _etiket(model_sira: int) -> str:
    """Etiket model_sira'ya göre belirlenir (puandan bağımsız)."""
    if model_sira <= 2:   return GIZLI_ADAY
    if model_sira == 3:   return ANALIZE_EKLENEBILIR
    return BOMBA_ADAY


# ---------------------------------------------------------------------------
# Hesaplama
# ---------------------------------------------------------------------------

def compute(
    races:              list["RacePrediction"],
    agf_results:        dict[tuple[str, int], "AgfRadarResult"],
    difficulty_results: dict[tuple[str, int], "DifficultyResult"],
) -> SurprizRadarResult:
    """
    Tüm gün koşuları için sürpriz radarı üretir.

    Limitler: hipodrom başına maks 2 aday, toplam maks 5 aday.

    Parameters:
        races:              predict_for_date() çıktısı
        agf_results:        {(hip, race_no): AgfRadarResult}
        difficulty_results: {(hip, race_no): DifficultyResult}
    """
    ham_adaylar: list[SurprizAday] = []

    for race in races:
        key = (race.hip, race.race_no)
        agf  = agf_results.get(key)
        diff = difficulty_results.get(key)

        if agf is None or not agf.agf_mevcut:
            continue

        zorluk_kodu  = diff.zorluk_kodu  if diff else None
        zorluk_puani = diff.zorluk_puani if diff else 0.0

        agf_by_hno = {a.horse_no: a for a in agf.at_infolar}

        for h in race.horses:
            at_agf = agf_by_hno.get(h.horse.horse_no)
            if at_agf is None:
                continue

            agf_sira   = at_agf.agf_pozisyon
            agf_pct    = at_agf.agf_yuzde
            model_sira = h.rank
            model_skor = round(h.norm_score, 1)

            if agf_sira is None or agf_sira < 4:
                continue
            if model_sira > 5:
                continue
            if model_skor < 55:
                continue
            # AGF sırası model sırasından anlamlı şekilde geride olmalı
            if agf_sira <= model_sira:
                continue

            skor = _score(
                model_sira         = model_sira,
                agf_sira           = agf_sira,
                model_skor         = model_skor,
                agf_fav_model_sira = agf.agf_fav_model_sira,
                zorluk_kodu        = zorluk_kodu,
            )

            if skor < 45:
                continue

            et = _etiket(model_sira)
            ham_adaylar.append(SurprizAday(
                hip           = race.hip,
                kno           = race.race_no,
                saat          = race.race_hour or None,
                at_no         = h.horse.horse_no,
                at            = h.horse.horse_name,
                model_sira    = model_sira,
                model_skor    = model_skor,
                agf_sira      = agf_sira,
                agf_pct       = round(agf_pct, 1) if agf_pct is not None else None,
                zorluk_kodu   = zorluk_kodu,
                zorluk_puani  = round(zorluk_puani, 1),
                surpriz_skoru = skor,
                etiket        = et,
                ui_etiket     = UI_ETIKET[et],
                gerekce       = "Model bu adayı üst sıralarda görürken AGF dağılımında daha geride.",
            ))

    # Skora göre sırala (en yüksek önce)
    ham_adaylar.sort(key=lambda a: a.surpriz_skoru, reverse=True)

    # Kap uygula: hipodrom başına maks 2, toplam maks 5
    adaylar: list[SurprizAday] = []
    hip_sayac: dict[str, int] = {}
    for a in ham_adaylar:
        if len(adaylar) >= 5:
            break
        if hip_sayac.get(a.hip, 0) >= 2:
            continue
        adaylar.append(a)
        hip_sayac[a.hip] = hip_sayac.get(a.hip, 0) + 1

    return SurprizRadarResult(adaylar=adaylar)


# ---------------------------------------------------------------------------
# Serileştirme
# ---------------------------------------------------------------------------

def to_dict(result: SurprizRadarResult) -> dict:
    """JSON-serializable dict — payload kök seviyesine 'surpriz_radar' olarak eklenir.
    Aday yoksa da boş ama geçerli bir dict döner (hiçbir zaman null döndürmez)."""
    return {
        "toplam_aday":         result.toplam_aday,
        "gizli_aday":          result.gizli_aday,
        "analize_eklenebilir": result.analize_eklenebilir,
        "bomba_aday":          result.bomba_aday,
        "adaylar": [
            {
                "hip":           a.hip,
                "kno":           a.kno,
                "saat":          a.saat,
                "at_no":         a.at_no,
                "at":            a.at,
                "model_sira":    a.model_sira,
                "model_skor":    a.model_skor,
                "agf_sira":      a.agf_sira,
                "agf_pct":       a.agf_pct,
                "zorluk_kodu":   a.zorluk_kodu,
                "zorluk_puani":  a.zorluk_puani,
                "surpriz_skoru": a.surpriz_skoru,
                "etiket":        a.etiket,
                "ui_etiket":     a.ui_etiket,
                "gerekce":       a.gerekce,
            }
            for a in result.adaylar
        ],
    }
