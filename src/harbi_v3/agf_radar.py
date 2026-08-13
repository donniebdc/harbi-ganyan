# -*- coding: utf-8 -*-
"""
agf_radar.py — Model skor sıralaması ile TJK AGF bahis dağılımının karşılaştırması.

Her koşu için:
  - AGF#1 atın modeldeki sırası
  - Modelin favori atının AGF pozisyonu
  - Her at için AGF etiketi (uyum / karşıt / sürpriz / agf_fav)
  - Model-AGF uyum özeti

Model pipeline'ına dokunmaz; sadece RacePrediction + agf_live verisi kullanır.
v3_export.py tarafından çağrılır.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .predictor import RacePrediction

# ---------------------------------------------------------------------------
# Etiketler
# ---------------------------------------------------------------------------

# Her at için AGF-Model ilişkisi
AGF_FAV    = "agf_fav"    # Bu at AGF#1
UYUM       = "uyum"       # Model ve AGF hemfikir (ikisi de top-3'te)
KARSIT     = "karsit"     # Model favori ama AGF desteklemiyor (poz ≥ 5)
SURPRIZ    = "surpriz"    # AGF favori değil ama model yüksek skor vermiş
NOTR       = "notr"       # Diğerleri

# Etiket → Flutter'da gösterilecek kısa metin (opsiyonel, UI tercihine göre)
ETIKET_LABEL: dict[str, str] = {
    AGF_FAV: "AGF Favorisi",
    UYUM:    "Uyumlu",
    KARSIT:  "Modele Güven",
    SURPRIZ: "Sürpriz Aday",
    NOTR:    "",
}


# ---------------------------------------------------------------------------
# Çıktı yapısı
# ---------------------------------------------------------------------------

@dataclass
class AtAgfInfo:
    horse_no:       int
    agf_pozisyon:   int | None    # AGF sıralaması (1 = en çok bahis)
    agf_yuzde:      float | None  # AGF bahis yüzdesi
    model_sira:     int           # Modelin bu ata verdiği sıra (rank)
    model_ana:      float         # Modelin normalize skoru
    etiket:         str           # AGF_FAV / UYUM / KARSIT / SURPRIZ / NOTR


@dataclass
class AgfRadarResult:
    # Koşu bazında özet
    agf_model_uyum:      bool        # AGF#1 modelin top-3'ünde mi?
    model_fav_agf_poz:   int | None  # Modelin 1. atının AGF pozisyonu
    agf_fav_model_sira:  int | None  # AGF#1'in modeldeki sırası
    agf_fav_hno:         int | None  # AGF#1 at numarası
    agf_fav_pct:         float       # AGF#1 bahis yüzdesi

    # At bazında detay
    at_infolar: list[AtAgfInfo] = field(default_factory=list)

    # Verinin mevcut olup olmadığı
    agf_mevcut: bool = True


# ---------------------------------------------------------------------------
# Hesaplama
# ---------------------------------------------------------------------------

def compute(
    race: "RacePrediction",
    agf_data: dict,
) -> AgfRadarResult:
    """
    Bir koşunun AGF Radar analizini hesaplar.

    Parameters:
        race:     RacePrediction (predictor.py çıktısı — değiştirilmez)
        agf_data: load_agf() dönüş değeri — {hip: {race_no: {horse_no: info}}}
                  Yoksa (boş dict) → agf_mevcut=False, etiketler NOTR olarak döner

    Çıktı: AgfRadarResult
    """
    from .normalize import norm_text

    hip_key  = norm_text(race.hip)
    race_key = str(race.race_no)
    race_agf = agf_data.get(hip_key, {}).get(race_key, {})

    if not race_agf:
        # AGF verisi yok — sistemi kırmamak için boş sonuç
        at_infolar = [
            AtAgfInfo(
                horse_no=h.horse.horse_no,
                agf_pozisyon=None,
                agf_yuzde=None,
                model_sira=h.rank,
                model_ana=round(h.norm_score, 1),
                etiket=NOTR,
            )
            for h in race.horses
        ]
        return AgfRadarResult(
            agf_model_uyum=False,
            model_fav_agf_poz=None,
            agf_fav_model_sira=None,
            agf_fav_hno=None,
            agf_fav_pct=0.0,
            at_infolar=at_infolar,
            agf_mevcut=False,
        )

    # Modelin sıralı at listesi (rank 1'den başlar)
    sorted_horses = sorted(race.horses, key=lambda h: h.rank)

    # AGF#1 tespiti (is_favorite → position → min position)
    agf_fav_hno: int | None = None
    agf_fav_pct: float = 0.0
    agf_fav_poz: int | None = None

    for hno_str, info in race_agf.items():
        if info.get("is_favorite"):
            agf_fav_hno = int(hno_str)
            agf_fav_pct = info["percentage"]
            agf_fav_poz = info["position"]
            break

    if agf_fav_hno is None and race_agf:
        best = min(race_agf.items(), key=lambda kv: kv[1]["position"])
        agf_fav_hno = int(best[0])
        agf_fav_pct = best[1]["percentage"]
        agf_fav_poz = best[1]["position"]

    # Modelin 1. atının AGF pozisyonu
    model_fav_hno = sorted_horses[0].horse.horse_no if sorted_horses else None
    model_fav_agf_poz: int | None = None
    if model_fav_hno is not None:
        info = race_agf.get(str(model_fav_hno))
        if info:
            model_fav_agf_poz = info["position"]

    # AGF#1'in modeldeki sırası
    agf_fav_model_sira: int | None = None
    if agf_fav_hno is not None:
        for h in race.horses:
            if h.horse.horse_no == agf_fav_hno:
                agf_fav_model_sira = h.rank
                break

    # Model-AGF uyumu: AGF#1 modelin top-3'ünde mi?
    agf_model_uyum = (agf_fav_model_sira is not None and agf_fav_model_sira <= 3)

    # Her at için etiket
    at_infolar: list[AtAgfInfo] = []
    for h in sorted_horses:
        hno     = h.horse.horse_no
        hno_str = str(hno)
        agf_inf = race_agf.get(hno_str)

        agf_poz = agf_inf["position"]  if agf_inf else None
        agf_pct = agf_inf["percentage"] if agf_inf else None

        if hno == agf_fav_hno:
            etiket = AGF_FAV
        elif h.rank <= 3 and agf_poz is not None and agf_poz <= 3:
            etiket = UYUM
        elif h.rank == 1 and agf_poz is not None and agf_poz >= 5:
            etiket = KARSIT
        elif agf_poz is not None and agf_poz >= 5 and h.rank <= 3:
            etiket = SURPRIZ
        else:
            etiket = NOTR

        at_infolar.append(AtAgfInfo(
            horse_no=hno,
            agf_pozisyon=agf_poz,
            agf_yuzde=round(agf_pct, 1) if agf_pct is not None else None,
            model_sira=h.rank,
            model_ana=round(h.norm_score, 1),
            etiket=etiket,
        ))

    return AgfRadarResult(
        agf_model_uyum=agf_model_uyum,
        model_fav_agf_poz=model_fav_agf_poz,
        agf_fav_model_sira=agf_fav_model_sira,
        agf_fav_hno=agf_fav_hno,
        agf_fav_pct=round(agf_fav_pct, 1),
        at_infolar=at_infolar,
        agf_mevcut=True,
    )


# ---------------------------------------------------------------------------
# Serileştirme
# ---------------------------------------------------------------------------

def to_dict(result: AgfRadarResult) -> dict:
    """JSON-serializable dict — export payload'una eklenir."""
    return {
        "agf_mevcut":        result.agf_mevcut,
        "agf_model_uyum":    result.agf_model_uyum,
        "model_fav_agf_poz": result.model_fav_agf_poz,
        "agf_fav_model_sira": result.agf_fav_model_sira,
        "agf_fav_hno":       result.agf_fav_hno,
        "agf_fav_pct":       result.agf_fav_pct,
        "atlar": [
            {
                "horse_no":    a.horse_no,
                "agf_poz":     a.agf_pozisyon,
                "agf_pct":     a.agf_yuzde,
                "model_sira":  a.model_sira,
                "model_ana":   a.model_ana,
                "etiket":      a.etiket,
            }
            for a in result.at_infolar
        ],
    }


def at_etiket_map(result: AgfRadarResult) -> dict[int, str]:
    """horse_no → etiket haritası — analiz_puanlari'na eklemek için."""
    return {a.horse_no: a.etiket for a in result.at_infolar if a.etiket != NOTR}
