# -*- coding: utf-8 -*-
"""
race_difficulty.py — Koşu zorluk endeksi.

Model pipeline'ına dokunmaz. Yalnızca RacePrediction çıktısından hesaplanır.
v3_export.py tarafından her koşu için çağrılır; sonuç nullable dict olarak
export JSON'una eklenir.

Zorluk = tahmin güçlüğü (kullanıcıya gösterilen bilgilendirme etiketi).
100 puanlık ölçek: 4 bağımsız faktörün toplamı.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .predictor import RacePrediction

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

# Koşu tipi katkısı (max 30 puan)
_TIP_PUAN: dict[str, float] = {
    "handikap":    30.0,
    "maiden":      22.0,
    "satis":       18.0,
    "other":       15.0,
    "sartli":      12.0,
    "sartli_arap": 12.0,
    "grup":         8.0,
    "kv_grup":      6.0,
}

# Etiket eşikleri (zorluk_puani ≥ eşik → (etiket, kod))
# Kod: Flutter'da Türkçe karakter / büyük-küçük harf problemi yaşamamak için
_ETIKETLER: list[tuple[float, str, str]] = [
    (72.0, "Çok Zor", "COK_ZOR"),
    (48.0, "Zor",     "ZOR"),
    (24.0, "Orta",    "ORTA"),
    (0.0,  "Kolay",   "KOLAY"),
]


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _n_at_katkisi(n: int) -> float:
    """At sayısı katkısı — 0-35 puan. 5 at → 0, 16+ at → 35 (doğrusal)."""
    return min(max(n - 5, 0) / 11.0, 1.0) * 35.0


def _tip_katkisi(bucket: str) -> float:
    """Koşu tipi katkısı — 0-30 puan."""
    return _TIP_PUAN.get(bucket, _TIP_PUAN["other"])


def _gap_katkisi(gap: float) -> float:
    """Skor gap katkısı — 0-25 puan. Gap dar → zor; 30+ → kolay."""
    # gap = norm_score_gap (0-100 ölçeğinde 1. ile 2. at farkı)
    return max(0.0, 1.0 - gap / 30.0) * 25.0


def _kume_katkisi(scores: list[float]) -> float:
    """Üst 3 atın puan yakınlığı — 0-10 puan. Yakın küme → zor."""
    if len(scores) < 2:
        return 0.0
    top3 = sorted(scores, reverse=True)[:3]
    spread = top3[0] - top3[-1]  # 1. ile 3. (ya da 2.) arasındaki açıklık
    # spread < 5 → yüksek katkı; spread > 25 → sıfır
    return max(0.0, 1.0 - spread / 25.0) * 10.0


def _etiket(puan: float) -> tuple[str, str]:
    for esik, ad, kod in _ETIKETLER:
        if puan >= esik:
            return ad, kod
    return "Kolay", "KOLAY"


# ---------------------------------------------------------------------------
# Hesaplama
# ---------------------------------------------------------------------------

@dataclass
class DifficultyResult:
    zorluk_puani:   float   # 0-100 (100 = en zor)
    zorluk_etiketi: str     # "Kolay" / "Orta" / "Zor" / "Çok Zor"
    zorluk_kodu:    str     # "KOLAY" / "ORTA" / "ZOR" / "COK_ZOR"
    n_at:           int
    kos_tipi:       str
    skor_gap:       float
    kume_yogunlugu: float   # üst-3 spread, küçük = yoğun küme


def compute(race: "RacePrediction") -> DifficultyResult:
    """
    Bir koşunun zorluk endeksini hesaplar.

    Girdi: RacePrediction (predictor.py çıktısı — değiştirilmez)
    Çıktı: DifficultyResult

    Hiçbir model ağırlığı, feature ya da tahmin skoru değiştirilmez.
    """
    from .confidence import race_type_bucket

    bucket = race_type_bucket(race.race_type or "", race.race_group or "")
    n      = race.runner_count
    gap    = race.norm_score_gap

    scores  = [h.norm_score for h in race.horses]
    top3    = sorted(scores, reverse=True)[:3]
    top3_spread = top3[0] - top3[min(2, len(top3) - 1)]

    f_nat  = _n_at_katkisi(n)
    f_tip  = _tip_katkisi(bucket)
    f_gap  = _gap_katkisi(gap)
    f_kume = max(0.0, 1.0 - top3_spread / 25.0) * 10.0

    puan = round(f_nat + f_tip + f_gap + f_kume, 1)
    puan = min(puan, 100.0)
    etiket, kod = _etiket(puan)

    return DifficultyResult(
        zorluk_puani   = puan,
        zorluk_etiketi = etiket,
        zorluk_kodu    = kod,
        n_at           = n,
        kos_tipi       = bucket,
        skor_gap       = round(gap, 1),
        kume_yogunlugu = round(top3_spread, 1),
    )


def to_dict(result: DifficultyResult) -> dict:
    """JSON-serializable dict — export payload'una eklenir."""
    return {
        "zorluk_puani":   result.zorluk_puani,
        "zorluk_etiketi": result.zorluk_etiketi,
        "zorluk_kodu":    result.zorluk_kodu,
        "n_at":           result.n_at,
        "kos_tipi":       result.kos_tipi,
        "skor_gap":       result.skor_gap,
        "kume_yogunlugu": result.kume_yogunlugu,
    }
