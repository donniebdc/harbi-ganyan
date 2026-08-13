# -*- coding: utf-8 -*-
"""
explain.py — Koşu tahminini kısa Türkçe açıklama kartlarına dönüştürür.

Phase 1: Yalnızca export alanlarından kural tabanlı çıkarım.
  - güven seviyesi, koşu tipi, alan büyüklüğü, AGF uyumu

Phase 2 (ileride): Gerçek feature sinyalleri — pist uyumu, form trend,
  jokey geçmişi, hız figürü. Bu dosya değiştirilmeden yeni bir resolver
  eklenerek genişletilebilir.

v3_export.py tarafından çağrılır; tahmin motoruna dokunmaz.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .predictor import RacePrediction
    from .agf_radar import AgfRadarResult
    from .race_difficulty import DifficultyResult

# ---------------------------------------------------------------------------
# Kart yapısı
# ---------------------------------------------------------------------------

# tip sabitleri
TIP_GUVEN   = "guven"
TIP_AGF     = "agf"
TIP_KARAKTER = "karakter"

# renk sabitleri — Flutter'da ZorlukRozeti ile aynı palet
RENK_YESIL   = "yesil"
RENK_MAVI    = "mavi"
RENK_SARI    = "sari"
RENK_TURUNCU = "turuncu"
RENK_KIRMIZI = "kirmizi"


@dataclass
class AciklamaKarti:
    tip:   str   # TIP_GUVEN / TIP_AGF / TIP_KARAKTER
    metin: str   # Kullanıcıya gösterilecek Türkçe metin
    renk:  str   # RENK_* sabitlerinden biri


# ---------------------------------------------------------------------------
# Kural motoru — Phase 1
# ---------------------------------------------------------------------------

def _guven_karti(guven: str, gap: float) -> AciklamaKarti:
    gap_str = f"{gap:.0f}" if gap else ""

    if guven == "surdirekt":
        return AciklamaKarti(
            tip=TIP_GUVEN,
            metin=f"Modelin bugün en net ayrıştırdığı koşulardan biri (+{gap_str} puan fark).",
            renk=RENK_YESIL,
        )
    if guven == "yuksek_guvenli":
        return AciklamaKarti(
            tip=TIP_GUVEN,
            metin=f"Model net tercih yaptı. İlk iki aday arasında belirgin analiz farkı var (+{gap_str} puan).",
            renk=RENK_MAVI,
        )
    if guven == "guvenli":
        return AciklamaKarti(
            tip=TIP_GUVEN,
            metin="Dengeli bir analiz tablosu. Model bu koşuda net sıralama yapabiliyor.",
            renk=RENK_SARI,
        )
    # riskli
    return AciklamaKarti(
        tip=TIP_GUVEN,
        metin="Analiz sinyalleri dağınık — belirsizlik seviyesi yüksek.",
        renk=RENK_KIRMIZI,
    )


def _agf_karti(
    agf_model_uyum: bool,
    model_fav_agf_poz: int | None,
    agf_fav_model_sira: int | None,
    agf_fav_hno: int | None,
    agf_fav_pct: float,
    model_fav_hno: int | None,
) -> AciklamaKarti | None:

    # Model favori == AGF#1
    if model_fav_hno is not None and model_fav_hno == agf_fav_hno:
        return AciklamaKarti(
            tip=TIP_AGF,
            metin="Model ve AGF dağılımı aynı adayı öne çıkarıyor.",
            renk=RENK_YESIL,
        )

    # Model favori AGF'de üstte (poz ≤ 2) ama AGF#1 farklı at
    if model_fav_agf_poz is not None and model_fav_agf_poz <= 2:
        return AciklamaKarti(
            tip=TIP_AGF,
            metin=f"Model favorisi AGF dağılımında da {model_fav_agf_poz}. sırada — analiz sinyalleri paralel.",
            renk=RENK_MAVI,
        )

    # Model favori AGF'de çok düşük (poz ≥ 5) — karşıt seçim
    if model_fav_agf_poz is not None and model_fav_agf_poz >= 5:
        return AciklamaKarti(
            tip=TIP_AGF,
            metin=f"Model ve AGF dağılımı ayrışıyor — model bu adayı 1. sıraya koyarken AGF dağılımı {model_fav_agf_poz}. sıraya yerleştiriyor.",
            renk=RENK_TURUNCU,
        )

    # AGF#1 modelde çok geride
    if agf_fav_model_sira is not None and agf_fav_model_sira > 3:
        return AciklamaKarti(
            tip=TIP_AGF,
            metin=f"AGF öne çıkan aday (No:{agf_fav_hno}) model sıralamasında {agf_fav_model_sira}. konumda — model farklı bir analiz yapıyor.",
            renk=RENK_TURUNCU,
        )

    # AGF#1 modelde 2. ya da 3. — yakın ama ayrışma var
    if agf_fav_model_sira is not None and agf_fav_model_sira in (2, 3):
        return AciklamaKarti(
            tip=TIP_AGF,
            metin="Model favorisi ile AGF öne çıkan aday yakın konumda — iki güçlü analiz sinyali.",
            renk=RENK_MAVI,
        )

    return None


def _karakter_karti(
    race_type: str,
    n_at: int,
    zorluk_etiketi: str,
) -> AciklamaKarti | None:

    if n_at >= 14:
        return AciklamaKarti(
            tip=TIP_KARAKTER,
            metin=f"{n_at} atlı büyük saha, tahmin belirsizliğini artırıyor.",
            renk=RENK_TURUNCU,
        )

    if race_type == "handikap" and n_at >= 10:
        return AciklamaKarti(
            tip=TIP_KARAKTER,
            metin="Kalabalık handikap koşusu — bu tip koşularda analiz belirsizliği görece yüksek.",
            renk=RENK_SARI,
        )

    if race_type in ("kv_grup", "grup"):
        return AciklamaKarti(
            tip=TIP_KARAKTER,
            metin="Kaliteli alan. Bu tip koşularda model tarihsel olarak daha net ayrışım yapıyor.",
            renk=RENK_YESIL,
        )

    if race_type == "maiden" and n_at >= 10:
        return AciklamaKarti(
            tip=TIP_KARAKTER,
            metin="Büyük maiden sahasında geçmiş veri sinyalleri bu koşuda daha sınırlı ayrışıyor.",
            renk=RENK_SARI,
        )

    if zorluk_etiketi == "Çok Zor":
        return AciklamaKarti(
            tip=TIP_KARAKTER,
            metin="Bu koşu istatistiksel olarak en yüksek belirsizlik tiplerinden biri.",
            renk=RENK_KIRMIZI,
        )

    return None


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

def compute(
    race: "RacePrediction",
    agf_radar_result: "AgfRadarResult | None",
    zorluk_result: "DifficultyResult | None",
    guven: str = "riskli",
) -> list[AciklamaKarti]:
    """
    Koşu için 1-3 açıklama kartı üretir.

    Parameters:
        race:             RacePrediction (predictor.py çıktısı — değiştirilmez)
        agf_radar_result: AgfRadarResult veya None (AGF yoksa None geçilebilir)
        zorluk_result:    DifficultyResult veya None
        guven:            v3_export'un hesapladığı güven etiketi (string)

    Çıktı: 1-3 AciklamaKarti — her zaman en az 1 kart (güven kartı)
    """
    kartlar: list[AciklamaKarti] = []

    # 1. Güven kartı (her zaman)
    gap = race.norm_score_gap if race is not None else 0.0
    kartlar.append(_guven_karti(guven, gap))

    # 2. AGF kartı (AGF mevcut ise)
    if agf_radar_result is not None and agf_radar_result.agf_mevcut:
        # Modelin favori atını bul (rank=1)
        model_fav_hno: int | None = None
        sorted_horses = sorted(race.horses, key=lambda h: h.rank)
        if sorted_horses:
            model_fav_hno = sorted_horses[0].horse.horse_no

        agf_karti = _agf_karti(
            agf_model_uyum=agf_radar_result.agf_model_uyum,
            model_fav_agf_poz=agf_radar_result.model_fav_agf_poz,
            agf_fav_model_sira=agf_radar_result.agf_fav_model_sira,
            agf_fav_hno=agf_radar_result.agf_fav_hno,
            agf_fav_pct=agf_radar_result.agf_fav_pct,
            model_fav_hno=model_fav_hno,
        )
        if agf_karti is not None:
            kartlar.append(agf_karti)

    # 3. Koşu karakteri kartı (opsiyonel)
    race_type    = getattr(race, "race_type", "") or ""
    runner_count = getattr(race, "runner_count", 0) or 0
    zorluk_etiket = zorluk_result.zorluk_etiketi if zorluk_result else ""

    # race_type → bucket (confidence.py ile tutarlı)
    from .confidence import race_type_bucket
    bucket = race_type_bucket(race_type, getattr(race, "race_group", "") or "")

    karakter = _karakter_karti(bucket, runner_count, zorluk_etiket)
    if karakter is not None:
        kartlar.append(karakter)

    return kartlar


# ---------------------------------------------------------------------------
# Serileştirme
# ---------------------------------------------------------------------------

def to_list(kartlar: list[AciklamaKarti]) -> list[dict]:
    """JSON-serializable list — export payload'una eklenir."""
    return [
        {"tip": k.tip, "metin": k.metin, "renk": k.renk}
        for k in kartlar
    ]
