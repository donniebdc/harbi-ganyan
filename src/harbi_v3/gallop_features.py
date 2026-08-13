# -*- coding: utf-8 -*-
"""
gallop_features.py — Galop verisinden 16 feature hesaplar.

Ana fonksiyon: compute_gallop_features(horse_entries, normalizer, race_date, race_city, race_distance, race_jockey)

Eksik veri durumunda tum feature'lar 0.0 doner.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .gallop_raw import GallopEntry
from .gallop_norm import GallopNormalizer


# Son 30 gunluk galop penceresi
GALLOP_WINDOW_DAYS = 30

# Hangi mesafeler feature olarak cikarilacak
GALLOP_DISTANCES = ("400", "600", "800", "1000")


GALLOP_FEATURE_NAMES = [
    "gallop_days_ago",
    "gallop_count_30d",
    "gallop_same_city",
    "gallop_same_jockey",
    "gallop_400_best_z",
    "gallop_600_best_z",
    "gallop_800_best_z",
    "gallop_1000_best_z",
    "gallop_best_distance_match",
    "gallop_400_trend",
    "gallop_intensity_avg",
    "gallop_has_HC",
    "gallop_ic_kulvar_ratio",
    "gallop_weight_avg_kg",
    "gallop_400_raw",
    "gallop_samples_400",
]


def _filter_last_30d(entries: list[GallopEntry], race_date: date) -> list[GallopEntry]:
    """Son 30 gun icindeki galoplari filtreler."""
    cutoff = race_date
    # date subtraction with manual calculation
    from datetime import timedelta
    window_start = cutoff - timedelta(days=GALLOP_WINDOW_DAYS)
    return [e for e in entries if window_start <= e.gallop_date < cutoff]


def compute_gallop_features(
    horse_entries: list[GallopEntry],
    normalizer: GallopNormalizer,
    race_date: date,
    race_city: str,
    race_distance: int,
    race_jockey: str = "",
) -> dict[str, float]:
    """Bir at icin galop feature'larini hesaplar.

    Args:
        horse_entries: Bu ata ait TUM galop kayitlari
        normalizer: Bayes shrinkage normalizasyon motoru (guncel istatistiklerle)
        race_date: Yaris tarihi
        race_city: Yaris sehri (normalize edilmemis haliyle)
        race_distance: Yaris mesafesi (metre)
        race_jockey: Yaris jokeyi

    Returns:
        16 feature iceren dict. Eksik veri → 0.0
    """
    f: dict[str, float] = {name: 0.0 for name in GALLOP_FEATURE_NAMES}

    # Son 30 gunu filtrele
    recent = _filter_last_30d(horse_entries, race_date)
    if not recent:
        # Hic galop yoksa tum feature'lar 0
        return f

    # Kronolojik sirala: en yeni sonda (tum recent[-1] kullanimlari dogru kaydi gosterir)
    recent = sorted(recent, key=lambda e: e.gallop_date)

    # ── Temel metrikler ──
    # 1. Son galop kac gun once
    latest = recent[-1].gallop_date
    f["gallop_days_ago"] = float((race_date - latest).days)

    # 2. Son 30 gundeki galop sayisi
    f["gallop_count_30d"] = float(len(recent))

    # 3. Son galop yaris sehriyle ayni yerde mi
    race_city_norm = race_city.lower().replace("ı", "i").replace("ş", "s")
    last_city = recent[-1].city.lower().replace("ı", "i").replace("ş", "s") if recent else ""
    f["gallop_same_city"] = 1.0 if last_city and last_city == race_city_norm else 0.0

    # 4. Galop jokeyi = yaris jokeyi mi
    race_j_norm = race_jockey.lower().replace("ı", "i").replace("ş", "s").replace(".", "")
    last_j = recent[-1].jockey.lower().replace("ı", "i").replace("ş", "s").replace(".", "") if recent else ""
    f["gallop_same_jockey"] = 1.0 if last_j and last_j == race_j_norm else 0.0

    # ── Mesafe bazli en iyi z-score'lar ──
    for dk in GALLOP_DISTANCES:
        best_z, best_raw, samples = normalizer.best_zscore(recent, dk, default_z=0.0)
        f[f"gallop_{dk}_best_z"] = best_z
        if dk == "400":
            f["gallop_400_raw"] = best_raw
            # Atin kendi 400m galop sayisi (sehir degil)
            own_400 = sum(1 for e in recent if e.distance_400 > 0)
            f["gallop_samples_400"] = float(own_400)

    # 5. En iyi galop mesafesi yaris mesafesine uygun mu
    race_dist_bucket = _distance_to_gallop_bucket(race_distance)
    if race_dist_bucket:
        # Hangi mesafede en iyi z-score var? (0.0 = veri yok → atla)
        best_dist = None
        best_z_val = None
        for dk in GALLOP_DISTANCES:
            z = f[f"gallop_{dk}_best_z"]
            if z != 0.0 and (best_z_val is None or z < best_z_val):
                best_z_val = z
                best_dist = dk
        if best_dist:
            f["gallop_best_distance_match"] = 1.0 if best_dist == race_dist_bucket else 0.0

    # ── Trend ──
    # 6. Son 3 galopun 400m z-score trendi
    # recent zaten kronolojik sirali
    z_400_list = []
    for e in recent:
        t = e.distance_400
        if t > 0:
            z, _, _ = normalizer.normalize(t, e.city, "400", e.intensity)
            z_400_list.append(z)
    if len(z_400_list) >= 3:
        # Son 3'un trendi: son - ilk (negatif = iyilesiyor, hizlaniyor)
        last3 = z_400_list[-3:]
        f["gallop_400_trend"] = last3[-1] - last3[0]
    elif len(z_400_list) >= 2:
        last2 = z_400_list[-2:]
        f["gallop_400_trend"] = last2[-1] - last2[0]

    # ── Intensite ──
    # 7. Ortalama efor
    intensities = [e.intensity for e in recent if e.intensity >= 0]
    if intensities:
        f["gallop_intensity_avg"] = sum(intensities) / len(intensities)

    # 8. Yuksek eforlu galop var mi (HC=2 veya C=3)
    has_high = any(e.intensity >= 2 for e in recent)
    f["gallop_has_HC"] = 1.0 if has_high else 0.0

    # 9. Ic kulvar orani
    ic_count = sum(1 for e in recent if "ic" in e.track_type.lower() or "iç" in e.track_type.lower())
    f["gallop_ic_kulvar_ratio"] = ic_count / len(recent) if recent else 0.0

    # 10. Ortalama galop kilosu
    weights = [e.weight for e in recent if e.weight > 0]
    if weights:
        f["gallop_weight_avg_kg"] = sum(weights) / len(weights)

    return f


def _distance_to_gallop_bucket(distance_m: int) -> str:
    """Yaris mesafesini galop mesafe kademesine esler."""
    if distance_m <= 400:
        return "400"
    elif distance_m <= 600:
        return "600"
    elif distance_m <= 800:
        return "800"
    elif distance_m <= 1000:
        return "1000"
    elif distance_m <= 1200:
        return "1200"
    elif distance_m <= 1400:
        return "1400"
    return ""
