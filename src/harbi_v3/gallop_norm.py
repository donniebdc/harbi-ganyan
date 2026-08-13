# -*- coding: utf-8 -*-
"""
gallop_norm.py — Galop sureleri icin Bayes Shrinkage normalizasyon motoru.

Katmanli normalizasyon:
  1. Sehir x mesafe istatistikleri (μ, σ, n)
  2. Bayes shrinkage: kucuk n'li gruplari ulusal ortalamaya ceker
  3. Z-score: (ham_sure - μ_shrunk) / σ_shrunk

Walk-forward uyumlu: sadece as_of tarihinden onceki veriler kullanilir.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .gallop_raw import GallopEntry, load_all_gallops_before


# Shrinkage gucleri (prior_n = "sahte galop" sayisi)
PRIOR_N = 50

# Intensity katmani icin daha zayif prior (az veri, daha hizli ogren)
PRIOR_N_INTENSITY = 30


@dataclass
class CityDistStats:
    """Bir sehir x mesafe kombinasyonunun istatistikleri."""
    n: int = 0
    sum_times: float = 0.0
    sum_sq: float = 0.0  # kareler toplami (varyans icin)

    @property
    def mean(self) -> float:
        return self.sum_times / self.n if self.n > 0 else 0.0

    @property
    def std(self) -> float:
        if self.n < 2:
            return 1.0  # default, cok kucuk orneklem
        variance = (self.sum_sq - (self.sum_times ** 2) / self.n) / (self.n - 1)
        return max(variance, 0.01) ** 0.5  # min std 0.1

    def add(self, time_sec: float) -> None:
        self.n += 1
        self.sum_times += time_sec
        self.sum_sq += time_sec ** 2


@dataclass
class GallopNormalizer:
    """Bayes shrinkage normalizasyon motoru.

    Kullanim:
        norm = GallopNormalizer()
        norm.update_from_entries(all_entries)  # tum gecmisi yukle
        z = norm.normalize(entry, distance=400)  # tek galop normalize
    """

    # (city_lower, distance_key) -> CityDistStats
    stats: dict[tuple[str, str], CityDistStats] = field(default_factory=lambda: defaultdict(CityDistStats))

    # Ulusal duzey istatistikler (tum sehirler birlestirilmis)
    national: dict[str, CityDistStats] = field(default_factory=lambda: defaultdict(CityDistStats))

    # (city_lower, distance_key, intensity) -> CityDistStats
    stats_ci: dict[tuple[str, str, int], CityDistStats] = field(default_factory=lambda: defaultdict(CityDistStats))

    _frozen: bool = False

    def update_from_entries(self, entries: list[GallopEntry]) -> int:
        """Tum galop kayitlarindan istatistikleri gunceller.

        Dondurur: eklenen toplam galop sayisi.
        """
        if self._frozen:
            return 0
        added = 0
        for e in entries:
            city = (e.city or "").lower().replace("ı", "i").replace("ş", "s")
            if not city:
                continue
            for dist_key in ("400", "600", "800", "1000"):
                t = getattr(e, f"distance_{dist_key}", 0.0)
                if t > 0:
                    self.stats[(city, dist_key)].add(t)
                    self.national[dist_key].add(t)
                    self.stats_ci[(city, dist_key, e.intensity)].add(t)
                    added += 1
        return added

    def load_history_before(self, as_of: date) -> int:
        """as_of tarihinden onceki tum galoplari yukler (walk-forward)."""
        entries = load_all_gallops_before(as_of)
        return self.update_from_entries(entries)

    def freeze(self):
        """Istatistikleri dondur (artik guncelleme yapilmaz)."""
        self._frozen = True

    def get_shrunk_stats(self, city: str, dist_key: str,
                         intensity: Optional[int] = None) -> tuple[float, float, int]:
        """Bayes shrinkage uygulanmis (μ, σ, n) dondurur.

        Kucuk orneklemli sehirleri ulusal ortalamaya ceker.
        intensity verilirse ikinci katman shrinkage: (city,dist,intensity) -> (city,dist).
        """
        city_lower = city.lower().replace("ı", "i").replace("ş", "s")
        local = self.stats.get((city_lower, dist_key))
        nat = self.national.get(dist_key)

        local_n = local.n if local else 0
        local_mean = local.mean if local else 0.0
        local_std = local.std if local else 1.0

        nat_mean = nat.mean if nat else 0.0
        nat_std = nat.std if nat else 1.0

        if local_n <= 0:
            # Hic yerel veri yok: tamamen ulusal
            cd_mean, cd_std, cd_n = nat_mean, nat_std, 0
        else:
            # Bayes shrinkage: (city,dist) -> national
            cd_mean = (local_n * local_mean + PRIOR_N * nat_mean) / (local_n + PRIOR_N)
            cd_std = (local_n * local_std + PRIOR_N * nat_std) / (local_n + PRIOR_N)
            cd_n = local_n
            cd_std = max(cd_std, 0.05)

        if intensity is None:
            return cd_mean, cd_std, cd_n

        # Ikinci katman: (city,dist,intensity) -> (city,dist) shrinkage
        ci = self.stats_ci.get((city_lower, dist_key, intensity))
        ci_n = ci.n if ci else 0
        if ci_n <= 0:
            # Intensity verisi yok: (city,dist) duzeyine dus
            return cd_mean, cd_std, cd_n
        sm = (ci_n * ci.mean + PRIOR_N_INTENSITY * cd_mean) / (ci_n + PRIOR_N_INTENSITY)
        ss = (ci_n * ci.std + PRIOR_N_INTENSITY * cd_std) / (ci_n + PRIOR_N_INTENSITY)
        return sm, max(ss, 0.05), ci_n

    def normalize(self, time_sec: float, city: str, dist_key: str,
                  intensity: Optional[int] = None) -> tuple[float, float, int]:
        """Ham sureyi z-score'a cevirir.

        Dondurur: (z_score, shrunk_mean, sample_n)
        z_score: negatif = hizli (ortalamadan iyi), pozitif = yavas
        intensity verilirse intensity-aware iki katmanli shrinkage kullanir.
        """
        if time_sec <= 0:
            return 0.0, 0.0, 0

        shrunk_mean, shrunk_std, n = self.get_shrunk_stats(city, dist_key, intensity)
        if shrunk_std <= 0:
            return 0.0, shrunk_mean, n

        z = (time_sec - shrunk_mean) / shrunk_std
        return z, shrunk_mean, n

    def best_zscore(self, entries: list[GallopEntry], dist_key: str,
                    default_z: float = 0.0) -> tuple[float, float, int]:
        """Bir atin son galoplarindaki en iyi (en dusuk) z-score'u bulur.

        Dondurur: (best_z, best_raw_time, sample_n)
        En iyi = en negatif z-score (en hizli).
        """
        best_z = default_z
        best_raw = 0.0
        best_n = 0

        for e in entries:
            t = getattr(e, f"distance_{dist_key}", 0.0)
            if t <= 0:
                continue
            z, mean, n = self.normalize(t, e.city, dist_key, e.intensity)
            if z < best_z or best_n == 0:
                best_z = z
                best_raw = t
                best_n = n

        return best_z, best_raw, best_n


def compute_speed_index(entry: GallopEntry, dist_key: str) -> float:
    """Basit hiz endeksi: m/sn cinsinden."""
    t = getattr(entry, f"distance_{dist_key}", 0.0)
    if t <= 0:
        return 0.0
    dist_m = int(dist_key)
    return dist_m / t if t > 0 else 0.0
