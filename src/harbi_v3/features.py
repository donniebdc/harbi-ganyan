from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .dates import iter_dates
from .horse_cards import A2_CARD_FEATURE_NAMES, card_features
from .normalize import norm_text
from .paths import PROGRAM_RAW_DIR, RESULTS_RAW_DIR
from .records import HorseProgram, distance_bucket, parse_program_horses, parse_results


def _key(value: object) -> str:
    return norm_text(value)


def _race_type_bucket(race_type: str, race_group: str) -> str:
    text = f"{race_type} {race_group}".lower()
    if "handikap" in text:
        return "handikap"
    if "maiden" in text:
        return "maiden"
    if "şart" in text or "sart" in text:
        if "dhöw" in text or "dhö" in text or "dht" in text:
            return "sartli_arap"
        return "sartli"
    if "satiş" in text or "satış" in text or "satis" in text:
        return "satis"
    if "kv" in text:
        return "kv_grup"
    if ("grup" in text
            or "g1" in text or "g2" in text or "g3" in text
            or "g 1" in text or "g 2" in text or "g 3" in text):
        return "grup"
    return "other"


def _parse_class_num(race_type: str, race_group: str) -> int:
    """ŞARTLI N → N,  KV-N → 50+N,  diğer → 0.

    ŞARTLI numarası: küçük = iyi sınıf, büyük = zayıf sınıf.
    class_num_drop = last - current > 0  → at daha zayıf sınıfa indi (avantaj).
    """
    text = race_type + " " + race_group
    # ŞARTLI N (unicode Ş veya ASCII S)
    m = re.search(r'[ŞşSs][Aa][Rr][Tt][Ll][Iiıİ][\s/]*(\d+)', text)
    if m:
        return int(m.group(1))
    # KV-N veya KV N
    m2 = re.search(r'\bKV[-\s](\d+)', text, re.IGNORECASE)
    if m2:
        return 50 + int(m2.group(1))
    return 0


def _field_bucket_count(runner_count: int) -> str:
    if runner_count <= 7:
        return "01_7_or_less"
    if runner_count <= 10:
        return "02_8_10"
    if runner_count <= 13:
        return "03_11_13"
    if runner_count <= 16:
        return "04_14_16"
    return "05_17_plus"


def _start_box_bucket(start_box: int, runner_count: int) -> str:
    if start_box <= 0 or runner_count <= 0:
        return "unknown"
    ratio = start_box / runner_count
    if ratio <= 0.33:
        return "inside"
    if ratio <= 0.67:
        return "middle"
    return "outside"


def _age_number(age_text: str) -> float:
    digits = "".join(ch for ch in (age_text or "") if ch.isdigit())
    if not digits:
        return 0.0
    try:
        return float(digits[:2])
    except ValueError:
        return 0.0


@dataclass
class Stat:
    starts: int = 0
    wins: int = 0
    top3: int = 0
    top5: int = 0
    rank_sum: float = 0.0

    def add(self, rank: int) -> None:
        if rank <= 0:
            return
        self.starts += 1
        self.wins += int(rank == 1)
        self.top3 += int(rank <= 3)
        self.top5 += int(rank <= 5)
        self.rank_sum += rank

    def win_rate(self) -> float:
        return self.wins / self.starts if self.starts else 0.0

    def top3_rate(self) -> float:
        return self.top3 / self.starts if self.starts else 0.0

    def top5_rate(self) -> float:
        return self.top5 / self.starts if self.starts else 0.0

    def avg_rank_inv(self) -> float:
        if not self.starts:
            return 0.0
        avg_rank = self.rank_sum / self.starts
        return 1.0 / max(avg_rank, 1.0)


@dataclass
class HistoryMemory:
    horse: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    horse_track: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    horse_distance: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    horse_hip: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    horse_track_distance: dict[tuple[str, str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    horse_race_type: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    jockey: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    trainer: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    owner: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    sire: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    dam_sire: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    jockey_hip: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    trainer_hip: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    jockey_race_type: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    trainer_race_type: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    jockey_horse: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    trainer_jockey: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    equipment: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    start_box_bucket: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    field_bucket: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    global_stat: Stat = field(default_factory=Stat)
    last_seen: dict[str, date] = field(default_factory=dict)
    last_track: dict[str, str] = field(default_factory=dict)
    last_distance: dict[str, int] = field(default_factory=dict)
    last_distance_bucket: dict[str, str] = field(default_factory=dict)
    last_jockey: dict[str, str] = field(default_factory=dict)
    last_trainer: dict[str, str] = field(default_factory=dict)
    last_equipment: dict[str, str] = field(default_factory=dict)
    last_win_date: dict[str, date] = field(default_factory=dict)
    last_weight: dict[str, float] = field(default_factory=dict)
    last_kgs: dict[str, float] = field(default_factory=dict)
    horse_form_recent: dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=20)))
    jockey_form_recent: dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=30)))
    trainer_form_recent: dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=30)))
    # Bitiş süresi geçmişi (saniye). En yeni en sonda (kronolojik append).
    horse_time_dist: dict[tuple[str, str], deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=12)))
    horse_time_track_dist: dict[tuple[str, str, str], deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=12)))
    # ── Yeni: Going (zemin durumu) ──
    horse_going: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    horse_track_going: dict[tuple[str, str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    last_going: dict[str, str] = field(default_factory=dict)
    # ── Yeni: Pedigree genisletme ──
    mother: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    father_of_father: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    mother_of_father: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    mother_of_mother: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    breeder: dict[str, Stat] = field(default_factory=lambda: defaultdict(Stat))
    # ── Yeni: Antrenör acilari ──
    trainer_track: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    trainer_distance: dict[tuple[str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    trainer_track_distance: dict[tuple[str, str, str], Stat] = field(default_factory=lambda: defaultdict(Stat))
    # ── Yeni: Speed figure (track variant) ──
    race_time_variant: dict[tuple[str, str], deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=20)))
    # ── Yeni: Class rating ──
    last_class_level: dict[str, float] = field(default_factory=dict)
    best_class_level: dict[str, float] = field(default_factory=dict)
    # ── Yeni: Recent time for speed figure ──
    horse_time_recent: dict[tuple[str, str], deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=6)))
    # ── Yeni: Son koşu sınıf numarası (ŞARTLI N → N, KV-N → 50+N) ──
    last_race_type_num: dict[str, int] = field(default_factory=dict)
    # ── Yeni: Zaman-pencereli jokey/trainer formu (son 90 gün) ──
    jockey_form_dated: dict[str, list] = field(default_factory=lambda: defaultdict(list))
    trainer_form_dated: dict[str, list] = field(default_factory=lambda: defaultdict(list))
    # ── Yeni: Son yarış rank bilgisi (normalize için) ──
    last_race_rank: dict[str, int] = field(default_factory=dict)
    last_race_runner_count: dict[str, int] = field(default_factory=dict)

    def update_race(self, horses: list[HorseProgram], order_by_no: dict[int, int], time_by_no: dict[int, float] | None = None) -> None:
        for horse in horses:
            rank = order_by_no.get(horse.horse_no, 0)
            if not rank:
                continue
            h = _key(horse.horse_name)
            j = _key(horse.jockey_name)
            t = _key(horse.trainer_name)
            owner = _key(horse.owner_name)
            sire = _key(horse.sire_name)
            dam_sire = _key(horse.dam_sire_name)
            hip = _key(horse.hip)
            track = _key(horse.race_track)
            dist = distance_bucket(horse.race_distance)
            race_type = _race_type_bucket(horse.race_type, horse.race_group)
            equip = _key(horse.equipment)
            start_bucket = _start_box_bucket(horse.start_box, horse.runner_count)
            field_bucket = _field_bucket_count(horse.runner_count)
            self.global_stat.add(rank)
            self.horse[h].add(rank)
            self.horse_track[(h, track)].add(rank)
            self.horse_distance[(h, dist)].add(rank)
            self.horse_hip[(h, hip)].add(rank)
            self.horse_track_distance[(h, track, dist)].add(rank)
            self.horse_race_type[(h, race_type)].add(rank)
            self.jockey[j].add(rank)
            self.trainer[t].add(rank)
            self.owner[owner].add(rank)
            self.sire[sire].add(rank)
            self.dam_sire[dam_sire].add(rank)
            self.jockey_hip[(j, hip)].add(rank)
            self.trainer_hip[(t, hip)].add(rank)
            self.jockey_race_type[(j, race_type)].add(rank)
            self.trainer_race_type[(t, race_type)].add(rank)
            self.jockey_horse[(j, h)].add(rank)
            self.trainer_jockey[(t, j)].add(rank)
            self.equipment[(h, equip)].add(rank)
            self.start_box_bucket[(h, start_bucket)].add(rank)
            self.field_bucket[(h, field_bucket)].add(rank)
            self.last_seen[h] = horse.run_date
            self.last_track[h] = track
            self.last_distance[h] = horse.race_distance
            self.last_distance_bucket[h] = dist
            self.last_jockey[h] = j
            self.last_trainer[h] = t
            self.last_equipment[h] = equip
            if rank == 1:
                self.last_win_date[h] = horse.run_date
            self.last_weight[h] = horse.weight
            self.last_kgs[h] = horse.kgs
            self.horse_form_recent[h].append(rank)
            self.jockey_form_recent[j].append(rank)
            self.trainer_form_recent[t].append(rank)
            # ── Zaman-pencereli form (son 90 gün) ──
            run_dt = horse.run_date
            self.jockey_form_dated[j].append((run_dt, rank))
            self.trainer_form_dated[t].append((run_dt, rank))
            # Bellek tasarrufu: 180 günden eski kayıtları temizle
            if len(self.jockey_form_dated[j]) % 50 == 0:
                cutoff = run_dt - timedelta(days=180)
                self.jockey_form_dated[j] = [(d, r) for d, r in self.jockey_form_dated[j] if d >= cutoff]
            if len(self.trainer_form_dated[t]) % 50 == 0:
                cutoff = run_dt - timedelta(days=180)
                self.trainer_form_dated[t] = [(d, r) for d, r in self.trainer_form_dated[t] if d >= cutoff]
            # ── Son yarış rank ──
            self.last_race_rank[h] = rank
            self.last_race_runner_count[h] = horse.runner_count
            if time_by_no:
                t_sec = time_by_no.get(horse.horse_no)
                if t_sec and t_sec > 0.0:
                    self.horse_time_dist[(h, dist)].append(t_sec)
                    self.horse_time_track_dist[(h, track, dist)].append(t_sec)
                    self.horse_time_recent[(h, dist)].append(t_sec)
            # ── Yeni: Going stats ──
            going = _key(horse.going) if horse.going else ""
            if going:
                self.horse_going[(h, going)].add(rank)
                self.horse_track_going[(h, track, going)].add(rank)
                self.last_going[h] = going
            # ── Yeni: Pedigree genisletme ──
            mother_k = _key(horse.mother_name)
            fof_k = _key(horse.father_of_father_name)
            mof_k = _key(horse.mother_of_father_name)
            mom_k = _key(horse.mother_of_mother_name)
            breeder_k = _key(horse.breeder_name)
            if mother_k:
                self.mother[mother_k].add(rank)
            if fof_k:
                self.father_of_father[fof_k].add(rank)
            if mof_k:
                self.mother_of_father[mof_k].add(rank)
            if mom_k:
                self.mother_of_mother[mom_k].add(rank)
            if breeder_k:
                self.breeder[breeder_k].add(rank)
            # ── Yeni: Antrenör acilari ──
            self.trainer_track[(t, track)].add(rank)
            self.trainer_distance[(t, dist)].add(rank)
            self.trainer_track_distance[(t, track, dist)].add(rank)
            # ── Yeni: Sınıf numarası (ŞARTLI N / KV-N) ──
            self.last_race_type_num[h] = _parse_class_num(horse.race_type, horse.race_group)
            # ── Yeni: Class level ──
            import math
            class_lvl = math.log(horse.race_prize_tl + horse.race_bonus_tl + 1.0) if (horse.race_prize_tl or horse.race_bonus_tl) else 0.0
            if class_lvl > 0.0:
                prev_best = self.best_class_level.get(h, 0.0)
                if class_lvl > prev_best:
                    self.best_class_level[h] = class_lvl
                self.last_class_level[h] = class_lvl
        # ── Yeni: Race time variant (tum atlarin medyan zamani) ──
        if time_by_no:
            times = [t for t in time_by_no.values() if t and t > 0.0]
            if len(times) >= 3:
                median_time = sorted(times)[len(times) // 2]
                # track ve dist bilgisi icin ilk ati kullan
                first_h = next((h for h in horses if order_by_no.get(h.horse_no, 0)), None)
                if first_h:
                    t_key = (_key(first_h.race_track), distance_bucket(first_h.race_distance))
                    self.race_time_variant[t_key].append(median_time)


FEATURE_NAMES = [
    "horse_starts_past",
    "horse_win_rate_past",
    "horse_top3_rate_past",
    "horse_avg_rank_inv_past",
    "horse_track_win_rate_past",
    "horse_distance_win_rate_past",
    "horse_hip_win_rate_past",
    "horse_track_distance_win_rate_past",
    "horse_race_type_win_rate_past",
    "jockey_win_rate_past",
    "trainer_win_rate_past",
    "owner_win_rate_past",
    "sire_win_rate_past",
    "dam_sire_win_rate_past",
    "jockey_hip_win_rate_past",
    "trainer_hip_win_rate_past",
    "jockey_race_type_win_rate_past",
    "trainer_race_type_win_rate_past",
    "jockey_horse_win_rate_past",
    "trainer_jockey_win_rate_past",
    "equipment_win_rate_past",
    "days_since_last_start",
    "track_switch_from_last",
    "distance_bucket_switch_from_last",
    "distance_delta_abs_from_last",
    "jockey_switch_from_last",
    "trainer_switch_from_last",
    "equipment_switch_from_last",
    "last6_win_count",
    "last6_top3_count",
    "last6_avg_place_inv",
    "last6_out_of_top10",
    "last6_out_of_top10_rate",
    "equipment_added_count",
    "equipment_removed_count",
    "weight",
    "handicap",
    "kgs",
    "start_box",
    "runner_count",
    "runner_count_sq",
    "runner_count_log",
    "is_large_field",
    "best_grade_seconds",
    "has_best_grade",
    "best_grade_at_current_hip",
    # Bitiş süresi geçmişi (results_raw time alanından, walk-forward hafıza)
    "horse_avg_time_at_distance",
    "horse_has_time_at_distance",
    "horse_avg_time_at_track_dist",
    "horse_has_time_at_track_dist",
    "horse_time_trend",
    # Kullanılmayan program parametreleri (snapshot'tan, koşu öncesi bilinir)
    # Not: is_jockey_changed (%0.0) ve is_foreign_foal (%0.15) sinyalsiz olduğu için eklenmedi.
    "overweight_kg",
    "race_prize_log",
    "race_course_changed",
    "race_distance_changed",
    "bulletin_genel",
    "bulletin_guncel",
    "bulletin_saatli",
    # Form trendi (last6_places üzerinden)
    "horse_form_trend",
    "horse_last3_inv",
    # Son koşu formu (bounded deque)
    "horse_win_rate_recent",
    "horse_top3_rate_recent",
    "horse_starts_recent",
    "jockey_win_rate_recent",
    "trainer_win_rate_recent",
    "horse_consecutive_nonwin",
    # Koşu içi normalize ranklar (bulletin inject sonrası)
    "horse_win_rate_rank_in_race",
    "jockey_win_rate_rank_in_race",
    "last6_inv_rank_in_race",
    "last3_inv_rank_in_race",
    "form_trend_rank_in_race",
    "best_grade_rank_in_race",
    "horse_win_rate_recent_rank_in_race",
    "bulletin_genel_rank_in_race",
    "bulletin_guncel_rank_in_race",
    "bulletin_saatli_rank_in_race",
    "trainer_win_rate_rank_in_race",
    "horse_top3_rate_recent_rank_in_race",
    "horse_time_rank_in_race",
    "handicap_rank_in_race",
    "kgs_rank_in_race",
    # Göreceli güç feature'ları (saha-seviyesi, per-horse)
    "horse_wr_vs_field_avg",
    "horse_wr_ratio_max",
    # ── Yeni: Genişletilmiş göreceli field feature'ları ──
    "quality_diff_vs_field",
    "quality_recent_vs_field",
    "speed_figure_vs_field",
    "top3_rate_vs_field",
    "jockey_wr_vs_field",
    "trainer_wr_vs_field",
    "form_trend_vs_field",
    # ── Yeni: Ek intra-race rank'ler ──
    "going_wr_rank_in_race",
    "speed_figure_rank_in_race",
    "trainer_track_wr_rank_in_race",
    "class_level_rank_in_race",
    "effective_weight_rank_in_race",
    # Son galibiyet ve kilo değişimi (walk-forward hafıza)
    "days_since_last_win",
    "weight_delta_from_last",
    "kgs_delta_from_last",
    # Bayes shrinkage: düşük örneklemli win rate'leri popülasyon ortalamasına çeker
    "horse_win_rate_past_shrunk",
    "horse_top3_rate_past_shrunk",
    # ── Yeni: Going (zemin durumu) ──
    "horse_going_win_rate_past",
    "horse_track_going_win_rate_past",
    "going_switch_from_last",
    "track_penetrometer",
    "horse_avg_penetrometer_past",
    # ── Yeni: Program API ──
    "age_years",
    "weight_loss_kg",
    "effective_weight",
    "is_apprentice",
    "race_bonus_log",
    "race_hour_numeric",
    "season_day_numeric",
    "weather_temp_c",
    "weather_humidity_pct",
    # ── Yeni: Pedigree genisletme ──
    "mother_win_rate_past",
    "father_of_father_win_rate_past",
    "mother_of_father_win_rate_past",
    "mother_of_mother_win_rate_past",
    "breeder_win_rate_past",
    # ── Yeni: Speed figure ──
    "horse_speed_figure",
    "horse_speed_figure_recent",
    # ── Yeni: Pace profili ──
    "pace_consistency",
    "pace_tendency",
    # ── Yeni: Antrenör acilari ──
    "trainer_track_win_rate_past",
    "trainer_distance_win_rate_past",
    "trainer_track_distance_win_rate_past",
    # ── Yeni: Class rating ──
    "race_class_level",
    "horse_class_gap",
    "horse_best_class_level",
    "horse_class_ratio",
    # ── Yeni: Kilo-length duzeltmesi ──
    "weight_impact_factor",
    "weight_delta_effective",
    "effective_weight_vs_field",
    # ── Yeni: Sınıf numarası (ŞARTLI N / KV-N) ──
    "current_class_num",
    "last_class_num",
    "class_num_drop",
    "class_num_rank_in_race",
    # ── Yeni: Satış fiyatı (maiden kalite proxy) ──
    "sale_price_log",
    # ── Yeni: Zaman-pencereli jokey/trainer formu ──
    "jockey_win_rate_90d",
    "trainer_win_rate_90d",
    # ── Yeni: Son yarış rank normalize ──
    "last_rank_normalized",
    # ── Yeni: last6 aynı pist sayısı (ölü feature düzeltmesi) ──
    "last6_same_track_count",
    *A2_CARD_FEATURE_NAMES,
]


LEGACY_FEATURE_NAMES = [
    "horse_starts_past",
    "horse_win_rate_past",
    "horse_top3_rate_past",
    "horse_avg_rank_inv_past",
    "horse_track_win_rate_past",
    "horse_distance_win_rate_past",
    "jockey_win_rate_past",
    "trainer_win_rate_past",
    "jockey_horse_win_rate_past",
    "trainer_jockey_win_rate_past",
    "equipment_win_rate_past",
    "last6_win_count",
    "last6_top3_count",
    "last6_avg_place_inv",
    "equipment_added_count",
    "equipment_removed_count",
    "weight",
    "handicap",
    "kgs",
    "start_box",
    "runner_count",
]


FEATURE_BLOCKS = {
    "pedigree_owner": [
        "owner_win_rate_past",
        "sire_win_rate_past",
        "dam_sire_win_rate_past",
    ],
    "race_context": [
        "horse_hip_win_rate_past",
        "horse_track_distance_win_rate_past",
        "horse_race_type_win_rate_past",
        "jockey_hip_win_rate_past",
        "trainer_hip_win_rate_past",
        "jockey_race_type_win_rate_past",
        "trainer_race_type_win_rate_past",
    ],
    "switch_rest": [
        "days_since_last_start",
        "track_switch_from_last",
        "distance_bucket_switch_from_last",
        "distance_delta_abs_from_last",
        "jockey_switch_from_last",
        "trainer_switch_from_last",
        "equipment_switch_from_last",
    ],
    "shape_profile": [
        "start_box_bucket_win_rate_past",
        "field_bucket_win_rate_past",
        "last6_same_track_count",
        "age_number",
    ],
}


FULL_42_ARCHIVED_NAMES = [
    "horse_starts_past",
    "horse_win_rate_past",
    "horse_top3_rate_past",
    "horse_avg_rank_inv_past",
    "horse_track_win_rate_past",
    "horse_distance_win_rate_past",
    "horse_hip_win_rate_past",
    "horse_track_distance_win_rate_past",
    "horse_race_type_win_rate_past",
    "jockey_win_rate_past",
    "trainer_win_rate_past",
    "owner_win_rate_past",
    "sire_win_rate_past",
    "dam_sire_win_rate_past",
    "jockey_hip_win_rate_past",
    "trainer_hip_win_rate_past",
    "jockey_race_type_win_rate_past",
    "trainer_race_type_win_rate_past",
    "jockey_horse_win_rate_past",
    "trainer_jockey_win_rate_past",
    "equipment_win_rate_past",
    "start_box_bucket_win_rate_past",
    "field_bucket_win_rate_past",
    "days_since_last_start",
    "track_switch_from_last",
    "distance_bucket_switch_from_last",
    "distance_delta_abs_from_last",
    "jockey_switch_from_last",
    "trainer_switch_from_last",
    "equipment_switch_from_last",
    "last6_win_count",
    "last6_top3_count",
    "last6_avg_place_inv",
    "last6_same_track_count",
    "equipment_added_count",
    "equipment_removed_count",
    "age_number",
    "weight",
    "handicap",
    "kgs",
    "start_box",
    "runner_count",
]

FEATURE_SET_DEFINITIONS = {
    "default_56": FEATURE_NAMES,
    "default_40": FEATURE_NAMES,  # alias
    "default_38": FEATURE_NAMES,  # alias
    "legacy_21": LEGACY_FEATURE_NAMES,
    "full_42_archived": FULL_42_ARCHIVED_NAMES,
    "legacy_plus_race_context": LEGACY_FEATURE_NAMES + FEATURE_BLOCKS["race_context"],
    "legacy_plus_switch_rest": LEGACY_FEATURE_NAMES + FEATURE_BLOCKS["switch_rest"],
    "legacy_plus_pedigree_owner": LEGACY_FEATURE_NAMES + FEATURE_BLOCKS["pedigree_owner"],
    "legacy_plus_shape_profile": LEGACY_FEATURE_NAMES + FEATURE_BLOCKS["shape_profile"],
    "full_without_pedigree_owner": [name for name in FEATURE_NAMES if name not in FEATURE_BLOCKS["pedigree_owner"]],
    "full_without_switch_rest": [name for name in FEATURE_NAMES if name not in FEATURE_BLOCKS["switch_rest"]],
    "full_without_race_context": [name for name in FEATURE_NAMES if name not in FEATURE_BLOCKS["race_context"]],
}


def build_memory_before(as_of: date, program_dir: Path = PROGRAM_RAW_DIR, results_dir: Path = RESULTS_RAW_DIR) -> HistoryMemory:
    memory = HistoryMemory()
    for day in sorted(d for d in _available_joint_dates(program_dir, results_dir) if d < as_of):
        programs = parse_program_horses(day, program_dir)
        results = parse_results(day, results_dir)
        for key, race_result in results.items():
            horses = programs.get(key)
            if horses:
                memory.update_race(horses, race_result.order_by_no, race_result.time_by_no)
    return memory


def _available_joint_dates(program_dir: Path, results_dir: Path) -> set[date]:
    program_dates = {p.stem for p in program_dir.glob("*.json")}
    result_dates = {p.stem for p in results_dir.glob("*.json")}
    out = set()
    from .dates import parse_date
    for stem in program_dates.intersection(result_dates):
        try:
            out.add(parse_date(stem))
        except ValueError:
            continue
    return out


def _stat_features(stat: Stat) -> tuple[int, float, float, float]:
    return (stat.starts, stat.win_rate(), stat.top3_rate(), stat.avg_rank_inv())


def _shrink_rate(starts: int | float, successes: int | float, prior_mean: float, prior_weight: float = 5.0) -> float:
    """Bayes shrinkage: düşük örneklemli oranları prior_mean'e çeker."""
    s = float(starts)
    if s <= 0:
        return prior_mean
    return (float(successes) + prior_mean * prior_weight) / (s + prior_weight)


def _form_trend(places: tuple[int, ...]) -> tuple[float, float]:
    """
    Son 6 koşudan form trendi hesaplar (index0=en yeni).
    Döndürür: (trend, last3_inv)
    trend: pozitif = iyileşme (recent daha düşük yer = daha iyi)
    last3_inv: son 3 koşunun avg_place_inv
    """
    valid = [p for p in places if p > 0]
    if len(valid) < 2:
        return 0.0, 0.0
    last3_valid = valid[:3]
    last3_inv = 1.0 / max(sum(last3_valid) / len(last3_valid), 1.0)
    if len(valid) < 4:
        return 0.0, last3_inv
    mid = len(valid) // 2
    recent_avg = sum(valid[:mid]) / mid
    old_avg = sum(valid[mid:]) / (len(valid) - mid)
    trend = old_avg - recent_avg  # pozitif = son koşular daha iyi (düşük yer)
    return trend, last3_inv


def _time_trend(times: deque) -> float:
    """
    Bitiş süresi trendi. deque'de en yeni en sonda.
    Pozitif = hızlanıyor (son koşular daha düşük saniye). Veri < 4 → 0.0.
    """
    valid = list(times)
    if len(valid) < 4:
        return 0.0
    recent = valid[-3:]
    older = valid[:-3]
    recent_avg = sum(recent) / len(recent)
    older_avg = sum(older) / len(older)
    return older_avg - recent_avg


def _last6_features(places: tuple[int, ...]) -> tuple[int, int, float]:
    valid = [p for p in places if p > 0]
    if not valid:
        return 0, 0, 0.0
    win_count = sum(1 for p in valid if p == 1)
    top3_count = sum(1 for p in valid if p <= 3)
    avg_place = sum(valid) / len(valid)
    return win_count, top3_count, 1.0 / max(avg_place, 1.0)


def features_for_horse(horse: HorseProgram, memory: HistoryMemory) -> dict[str, float]:
    h = _key(horse.horse_name)
    j = _key(horse.jockey_name)
    t = _key(horse.trainer_name)
    owner = _key(horse.owner_name)
    sire = _key(horse.sire_name)
    dam_sire = _key(horse.dam_sire_name)
    hip = _key(horse.hip)
    track = _key(horse.race_track)
    dist = distance_bucket(horse.race_distance)
    race_type = _race_type_bucket(horse.race_type, horse.race_group)
    equip = _key(horse.equipment)
    start_bucket = _start_box_bucket(horse.start_box, horse.runner_count)
    field_bucket = _field_bucket_count(horse.runner_count)
    starts, horse_wr, horse_t3, horse_rank_inv = _stat_features(memory.horse[h])
    last6_win, last6_top3, last6_inv = _last6_features(horse.last6_places)
    form_trend, last3_inv = _form_trend(horse.last6_places)
    last_seen = memory.last_seen.get(h)
    days_since_last = float((horse.run_date - last_seen).days) if last_seen else 0.0
    prev_track = memory.last_track.get(h, "")
    prev_dist = memory.last_distance.get(h, 0)
    prev_dist_bucket = memory.last_distance_bucket.get(h, "")
    prev_jockey = memory.last_jockey.get(h, "")
    prev_trainer = memory.last_trainer.get(h, "")
    prev_equipment = memory.last_equipment.get(h, "")
    prev_weight = memory.last_weight.get(h, horse.weight)
    prev_kgs = memory.last_kgs.get(h, horse.kgs)
    last_w = memory.last_win_date.get(h)
    last6_same_track = sum(1 for old_track in horse.last6_tracks if _key(old_track) == track)
    # Recent form (bounded deques)
    h_recent = memory.horse_form_recent[h]
    h_recent_n = len(h_recent)
    h_recent_wins = sum(1 for r in h_recent if r == 1)
    h_recent_top3 = sum(1 for r in h_recent if r <= 3)
    h_recent_wr = h_recent_wins / h_recent_n if h_recent_n else 0.0
    h_recent_t3 = h_recent_top3 / h_recent_n if h_recent_n else 0.0
    j_recent = memory.jockey_form_recent[j]
    j_recent_n = len(j_recent)
    j_recent_wr = sum(1 for r in j_recent if r == 1) / j_recent_n if j_recent_n else 0.0
    j_recent_t3 = sum(1 for r in j_recent if r <= 3) / j_recent_n if j_recent_n else 0.0
    t_recent = memory.trainer_form_recent[t]
    t_recent_n = len(t_recent)
    t_recent_wr = sum(1 for r in t_recent if r == 1) / t_recent_n if t_recent_n else 0.0
    t_recent_t3 = sum(1 for r in t_recent if r <= 3) / t_recent_n if t_recent_n else 0.0
    # ── Yeni: Zaman-pencereli 90 günlük form ──
    cutoff_90 = horse.run_date - timedelta(days=90)
    j_90d = [r for d, r in memory.jockey_form_dated[j] if d >= cutoff_90]
    j_90d_n = len(j_90d)
    j_win_rate_90d = sum(1 for r in j_90d if r == 1) / j_90d_n if j_90d_n else 0.0
    j_top3_rate_90d = sum(1 for r in j_90d if r <= 3) / j_90d_n if j_90d_n else 0.0
    t_90d = [r for d, r in memory.trainer_form_dated[t] if d >= cutoff_90]
    t_90d_n = len(t_90d)
    t_win_rate_90d = sum(1 for r in t_90d if r == 1) / t_90d_n if t_90d_n else 0.0
    t_top3_rate_90d = sum(1 for r in t_90d if r <= 3) / t_90d_n if t_90d_n else 0.0
    # ── Yeni: Son yarış rank normalize ──
    last_r = memory.last_race_rank.get(h, 0)
    last_rc = memory.last_race_runner_count.get(h, 0)
    last_rank_norm = (last_r / last_rc) if (last_r > 0 and last_rc > 0) else 0.0
    consec_nonwin = 0.0
    for r in reversed(list(h_recent)):
        if r == 1:
            break
        consec_nonwin += 1.0
    # Bitiş süresi geçmişi
    t_dist = memory.horse_time_dist[(h, dist)]
    t_track_dist = memory.horse_time_track_dist[(h, track, dist)]
    avg_time_dist = sum(t_dist) / len(t_dist) if t_dist else 0.0
    avg_time_track_dist = sum(t_track_dist) / len(t_track_dist) if t_track_dist else 0.0
    time_trend = _time_trend(t_dist)
    # ── Yeni: Going degiskenleri ──
    going_norm = _key(horse.going) if horse.going else ""
    prev_going = memory.last_going.get(h, "")
    # ── Yeni: Apranti tespiti (horse-level veya jockey-level) ──
    jockey_apprentice = horse.is_apprentice_horse
    # ── Yeni: Pedigree key'leri ──
    mother_k = _key(horse.mother_name)
    fof_k = _key(horse.father_of_father_name)
    mof_k = _key(horse.mother_of_father_name)
    mom_k = _key(horse.mother_of_mother_name)
    breeder_k = _key(horse.breeder_name)
    # ── Yeni: Class level ──
    class_level_current = math.log(horse.race_prize_tl + horse.race_bonus_tl + 1.0) if (horse.race_prize_tl or horse.race_bonus_tl) else 0.0
    prev_class_level = memory.last_class_level.get(h, 0.0)
    # ── Yeni: Sınıf numarası ──
    current_class_num = _parse_class_num(horse.race_type, horse.race_group)
    last_class_num = memory.last_race_type_num.get(h, 0)
    result = {
        "horse_starts_past": float(starts),
        "horse_win_rate_past": horse_wr,
        "horse_top3_rate_past": horse_t3,
        "horse_avg_rank_inv_past": horse_rank_inv,
        "horse_track_win_rate_past": memory.horse_track[(h, track)].win_rate(),
        "horse_track_top3_rate_past": memory.horse_track[(h, track)].top3_rate(),
        "horse_distance_win_rate_past": memory.horse_distance[(h, dist)].win_rate(),
        "horse_distance_top3_rate_past": memory.horse_distance[(h, dist)].top3_rate(),
        "horse_hip_win_rate_past": memory.horse_hip[(h, hip)].win_rate(),
        "horse_hip_top3_rate_past": memory.horse_hip[(h, hip)].top3_rate(),
        "horse_track_distance_win_rate_past": memory.horse_track_distance[(h, track, dist)].win_rate(),
        "horse_track_distance_top3_rate_past": memory.horse_track_distance[(h, track, dist)].top3_rate(),
        "horse_race_type_win_rate_past": memory.horse_race_type[(h, race_type)].win_rate(),
        "horse_race_type_top3_rate_past": memory.horse_race_type[(h, race_type)].top3_rate(),
        "jockey_win_rate_past": memory.jockey[j].win_rate(),
        "jockey_top3_rate_past": memory.jockey[j].top3_rate(),
        "trainer_win_rate_past": memory.trainer[t].win_rate(),
        "trainer_top3_rate_past": memory.trainer[t].top3_rate(),
        "owner_win_rate_past": memory.owner[owner].win_rate(),
        "sire_win_rate_past": memory.sire[sire].win_rate(),
        "dam_sire_win_rate_past": memory.dam_sire[dam_sire].win_rate(),
        "jockey_hip_win_rate_past": memory.jockey_hip[(j, hip)].win_rate(),
        "jockey_hip_top3_rate_past": memory.jockey_hip[(j, hip)].top3_rate(),
        "trainer_hip_win_rate_past": memory.trainer_hip[(t, hip)].win_rate(),
        "trainer_hip_top3_rate_past": memory.trainer_hip[(t, hip)].top3_rate(),
        "jockey_race_type_win_rate_past": memory.jockey_race_type[(j, race_type)].win_rate(),
        "jockey_race_type_top3_rate_past": memory.jockey_race_type[(j, race_type)].top3_rate(),
        "trainer_race_type_win_rate_past": memory.trainer_race_type[(t, race_type)].win_rate(),
        "trainer_race_type_top3_rate_past": memory.trainer_race_type[(t, race_type)].top3_rate(),
        "jockey_horse_win_rate_past": memory.jockey_horse[(j, h)].win_rate(),
        "jockey_horse_top3_rate_past": memory.jockey_horse[(j, h)].top3_rate(),
        "trainer_jockey_win_rate_past": memory.trainer_jockey[(t, j)].win_rate(),
        "trainer_jockey_top3_rate_past": memory.trainer_jockey[(t, j)].top3_rate(),
        "equipment_win_rate_past": memory.equipment[(h, equip)].win_rate(),
        "equipment_top3_rate_past": memory.equipment[(h, equip)].top3_rate(),
        "start_box_bucket_win_rate_past": memory.start_box_bucket[(h, start_bucket)].win_rate(),
        "start_box_bucket_top3_rate_past": memory.start_box_bucket[(h, start_bucket)].top3_rate(),
        "field_bucket_win_rate_past": memory.field_bucket[(h, field_bucket)].win_rate(),
        "field_bucket_top3_rate_past": memory.field_bucket[(h, field_bucket)].top3_rate(),
        "days_since_last_start": days_since_last,
        "track_switch_from_last": float(bool(prev_track and prev_track != track)),
        "distance_bucket_switch_from_last": float(bool(prev_dist_bucket and prev_dist_bucket != dist)),
        "distance_delta_abs_from_last": float(abs(horse.race_distance - prev_dist)) if prev_dist else 0.0,
        "jockey_switch_from_last": float(bool(prev_jockey and prev_jockey != j)),
        "trainer_switch_from_last": float(bool(prev_trainer and prev_trainer != t)),
        "equipment_switch_from_last": float(bool(prev_equipment and prev_equipment != equip)),
        "last6_win_count": float(last6_win),
        "last6_top3_count": float(last6_top3),
        "last6_avg_place_inv": last6_inv,
        "last6_out_of_top10": float(sum(1 for p in horse.last6_places if p == 0)),
        "last6_out_of_top10_rate": float(sum(1 for p in horse.last6_places if p == 0)) / max(len(horse.last6_places), 1),
        "last6_same_track_count": float(last6_same_track),
        "equipment_added_count": float(len(horse.equipment_added)),
        "equipment_removed_count": float(len(horse.equipment_removed)),
        "age_number": _age_number(horse.age_text),
        "weight": horse.weight,
        "handicap": horse.handicap,
        "kgs": horse.kgs,
        "start_box": float(horse.start_box),
        "runner_count": float(horse.runner_count),
        "runner_count_sq": float(horse.runner_count ** 2),
        "runner_count_log": math.log(horse.runner_count + 1.0),
        "is_large_field": 1.0 if horse.runner_count >= 11 else 0.0,
        "best_grade_seconds": horse.best_grade_seconds,
        "has_best_grade": horse.has_best_grade,
        "best_grade_at_current_hip": horse.best_grade_at_current_hip,
        "horse_avg_time_at_distance": avg_time_dist,
        "horse_has_time_at_distance": 1.0 if t_dist else 0.0,
        "horse_avg_time_at_track_dist": avg_time_track_dist,
        "horse_has_time_at_track_dist": 1.0 if t_track_dist else 0.0,
        "horse_time_trend": time_trend,
        "overweight_kg": horse.overweight,
        "race_prize_log": math.log(horse.race_prize_tl + 1.0) if horse.race_prize_tl > 0 else 0.0,
        "race_course_changed": 1.0 if horse.race_course_changed else 0.0,
        "race_distance_changed": 1.0 if horse.race_distance_changed else 0.0,
        "horse_form_trend": form_trend,
        "horse_last3_inv": last3_inv,
        "horse_win_rate_recent": h_recent_wr,
        "horse_top3_rate_recent": h_recent_t3,
        "horse_starts_recent": float(h_recent_n),
        "jockey_win_rate_recent": j_recent_wr,
        "jockey_top3_rate_recent": j_recent_t3,
        "trainer_win_rate_recent": t_recent_wr,
        "trainer_top3_rate_recent": t_recent_t3,
        "horse_consecutive_nonwin": consec_nonwin,
        # Son galibiyet + kilo değişimi (walk-forward hafızadan)
        "days_since_last_win": float((horse.run_date - last_w).days) if last_w else 999.0,
        "weight_delta_from_last": horse.weight - prev_weight,
        "kgs_delta_from_last": horse.kgs - prev_kgs,
        # Bayes shrinkage: düşük örneklemli oranları global ortalamaya çeker
        # prior_weight=5 → 5 "sahte start" ekler, küçük örneklemi dengeler
        "horse_win_rate_past_shrunk": _shrink_rate(starts, memory.horse[h].wins, memory.global_stat.win_rate(), 5.0),
        "horse_top3_rate_past_shrunk": _shrink_rate(starts, memory.horse[h].top3, memory.global_stat.top3_rate(), 5.0),
        "horse_track_top3_rate_past_shrunk": _shrink_rate(memory.horse_track[(h, track)].starts, memory.horse_track[(h, track)].top3, memory.global_stat.top3_rate(), 5.0),
        "horse_distance_top3_rate_past_shrunk": _shrink_rate(memory.horse_distance[(h, dist)].starts, memory.horse_distance[(h, dist)].top3, memory.global_stat.top3_rate(), 5.0),
        "horse_hip_top3_rate_past_shrunk": _shrink_rate(memory.horse_hip[(h, hip)].starts, memory.horse_hip[(h, hip)].top3, memory.global_stat.top3_rate(), 5.0),
        "horse_track_distance_top3_rate_past_shrunk": _shrink_rate(memory.horse_track_distance[(h, track, dist)].starts, memory.horse_track_distance[(h, track, dist)].top3, memory.global_stat.top3_rate(), 5.0),
        "horse_race_type_top3_rate_past_shrunk": _shrink_rate(memory.horse_race_type[(h, race_type)].starts, memory.horse_race_type[(h, race_type)].top3, memory.global_stat.top3_rate(), 5.0),
        "jockey_top3_rate_past_shrunk": _shrink_rate(memory.jockey[j].starts, memory.jockey[j].top3, memory.global_stat.top3_rate(), 8.0),
        "trainer_top3_rate_past_shrunk": _shrink_rate(memory.trainer[t].starts, memory.trainer[t].top3, memory.global_stat.top3_rate(), 8.0),
        "jockey_hip_top3_rate_past_shrunk": _shrink_rate(memory.jockey_hip[(j, hip)].starts, memory.jockey_hip[(j, hip)].top3, memory.global_stat.top3_rate(), 8.0),
        "trainer_hip_top3_rate_past_shrunk": _shrink_rate(memory.trainer_hip[(t, hip)].starts, memory.trainer_hip[(t, hip)].top3, memory.global_stat.top3_rate(), 8.0),
        "jockey_race_type_top3_rate_past_shrunk": _shrink_rate(memory.jockey_race_type[(j, race_type)].starts, memory.jockey_race_type[(j, race_type)].top3, memory.global_stat.top3_rate(), 8.0),
        "trainer_race_type_top3_rate_past_shrunk": _shrink_rate(memory.trainer_race_type[(t, race_type)].starts, memory.trainer_race_type[(t, race_type)].top3, memory.global_stat.top3_rate(), 8.0),
        # ── Yeni: Going (zemin durumu) features ──
        "horse_going_win_rate_past": memory.horse_going[(h, going_norm)].win_rate() if going_norm else 0.0,
        "horse_track_going_win_rate_past": memory.horse_track_going[(h, track, going_norm)].win_rate() if going_norm else 0.0,
        "going_switch_from_last": float(bool(prev_going and going_norm and prev_going != going_norm)),
        "track_penetrometer": horse.penetrometer,
        "horse_avg_penetrometer_past": 0.0,  # card_features'tan gelir, placeholder
        # ── Yeni: Program API features ──
        "age_years": (horse.run_date - horse.birthdate).days / 365.25 if horse.birthdate else _age_number(horse.age_text),
        "weight_loss_kg": horse.weight_loss,
        "effective_weight": horse.weight - horse.weight_loss + horse.overweight,
        "is_apprentice": 1.0 if (horse.is_apprentice_horse or jockey_apprentice) else 0.0,
        "race_bonus_log": math.log(horse.race_bonus_tl + 1.0) if horse.race_bonus_tl > 0 else 0.0,
        "race_hour_numeric": horse.race_hour_num,
        "season_day_numeric": float(horse.season_day),
        "weather_temp_c": horse.weather_temp,
        "weather_humidity_pct": horse.weather_humidity,
        # ── Yeni: Pedigree genisletme ──
        "mother_win_rate_past": memory.mother[mother_k].win_rate() if mother_k else 0.0,
        "father_of_father_win_rate_past": memory.father_of_father[fof_k].win_rate() if fof_k else 0.0,
        "mother_of_father_win_rate_past": memory.mother_of_father[mof_k].win_rate() if mof_k else 0.0,
        "mother_of_mother_win_rate_past": memory.mother_of_mother[mom_k].win_rate() if mom_k else 0.0,
        "breeder_win_rate_past": memory.breeder[breeder_k].win_rate() if breeder_k else 0.0,
        # ── Yeni: Speed figure ──
        "horse_speed_figure": _compute_speed_figure(h, dist, track, memory),
        "horse_speed_figure_recent": _compute_recent_speed_figure(h, dist, memory),
        # ── Yeni: Pace profili ──
        "pace_consistency": _pace_consistency(horse.last6_places),
        "pace_tendency": _pace_tendency(horse.last6_places),
        # ── Yeni: Antrenör acilari ──
        "trainer_track_win_rate_past": memory.trainer_track[(t, track)].win_rate(),
        "trainer_distance_win_rate_past": memory.trainer_distance[(t, dist)].win_rate(),
        "trainer_track_distance_win_rate_past": memory.trainer_track_distance[(t, track, dist)].win_rate(),
        # ── Yeni: Class rating ──
        "race_class_level": class_level_current,
        "horse_class_gap": class_level_current - prev_class_level if prev_class_level > 0 else 0.0,
        "horse_best_class_level": memory.best_class_level.get(h, class_level_current),
        "horse_class_ratio": class_level_current / memory.best_class_level.get(h, class_level_current) if memory.best_class_level.get(h, 0.0) > 0 else 1.0,
        # ── Yeni: Kilo-length duzeltmesi ──
        "weight_impact_factor": _weight_impact_factor(horse.race_distance),
        "weight_delta_effective": (horse.weight - prev_weight) * _weight_impact_factor(horse.race_distance),
        "effective_weight_vs_field": 0.0,  # add_intrarace_ranks'te doldurulur
        # ── Yeni: Satış fiyatı (maiden için proxy kalite) ──
        "sale_price_log": math.log(horse.sale_price + 1.0) if horse.sale_price > 0 else 0.0,
        # ── Yeni: Zaman-pencereli form ──
        "jockey_win_rate_90d": j_win_rate_90d,
        "jockey_top3_rate_90d": j_top3_rate_90d,
        "trainer_win_rate_90d": t_win_rate_90d,
        "trainer_top3_rate_90d": t_top3_rate_90d,
        # ── Yeni: Son yarış rank normalize ──
        "last_rank_normalized": last_rank_norm,
        # ── Yeni: Göreceli field feature'ları (add_intrarace_ranks'te doldurulur) ──
        "quality_diff_vs_field": 0.0,
        "quality_recent_vs_field": 0.0,
        "speed_figure_vs_field": 0.0,
        "top3_rate_vs_field": 0.0,
        "jockey_wr_vs_field": 0.0,
        "trainer_wr_vs_field": 0.0,
        "form_trend_vs_field": 0.0,
        # ── Yeni: Sınıf numarası (ŞARTLI N / KV-N) ──
        "current_class_num": float(current_class_num),
        "last_class_num": float(last_class_num),
        # class_num_drop: >0 = daha zayif sinifa indi (avantaj). Cross-type anomalisi
        # (ornek: SARTLI 3 → KV-5 = 3-55 = -52) clamp ile engellenir.
        "class_num_drop": float(max(-20, min(20, last_class_num - current_class_num))) if (last_class_num != 0 and current_class_num != 0) else 0.0,
    }
    if horse.atkodu:
        a2_features, _ = card_features(
            horse.atkodu,
            horse.run_date,
            race_type,
            hip,
            track,
            dist,
            j,
            equip,
            going=going_norm,
            penetrometer=horse.penetrometer,
        )
        result.update(a2_features)
        # card_features'tan gelen penetrometre ortalamasini guncelle
        if "a2_card_avg_penetrometer" in a2_features:
            result["horse_avg_penetrometer_past"] = a2_features["a2_card_avg_penetrometer"]
    return result


def _compute_speed_figure(horse_key: str, dist_bucket: str, track: str, memory: HistoryMemory) -> float:
    """Standardize speed figure: atin ortalama zamani vs track variant (medyan).

    Pozitif = attan daha hizli (ortalamadan daha dusuk zaman), Negatif = daha yavas.
    """
    t_dist = memory.horse_time_dist[(horse_key, dist_bucket)]
    if not t_dist:
        return 0.0
    horse_avg = sum(t_dist) / len(t_dist)
    variant_key = (track, dist_bucket)
    variants = memory.race_time_variant.get(variant_key)
    if not variants:
        return 0.0
    track_median = sorted(variants)[len(variants) // 2]
    if track_median <= 0:
        return 0.0
    return (track_median - horse_avg) / track_median * 100.0


def _compute_recent_speed_figure(horse_key: str, dist_bucket: str, memory: HistoryMemory) -> float:
    """Son 3 kosunun speed figure ortalamasi."""
    recent_times = list(memory.horse_time_recent[(horse_key, dist_bucket)])
    if len(recent_times) < 2:
        return 0.0
    recent = recent_times[-3:]
    horse_avg = sum(recent) / len(recent)
    variant_key = (_key(""), dist_bucket)  # fallback - tum track'ler
    # Tum variant'lardan genel medyan bul
    all_variants = []
    for k, v in memory.race_time_variant.items():
        if k[1] == dist_bucket:
            all_variants.extend(v)
    if not all_variants:
        return 0.0
    track_median = sorted(all_variants)[len(all_variants) // 2]
    if track_median <= 0:
        return 0.0
    return (track_median - horse_avg) / track_median * 100.0


def _pace_consistency(places: tuple[int, ...]) -> float:
    """Kosu stili tutarliligi: dusuk = tutarli (oncu), yuksek = tutarsiz (kapanisci).

    last6_places stddev'sini dondurur. 0-1 arasi normalize edilmis.
    """
    valid = [p for p in places if p > 0]
    if len(valid) < 2:
        return 0.5
    mean = sum(valid) / len(valid)
    variance = sum((p - mean) ** 2 for p in valid) / len(valid)
    stddev = variance ** 0.5
    # Normalize: 0-6 arasi stddev -> 0-1
    return min(stddev / 6.0, 1.0)


def _pace_tendency(places: tuple[int, ...]) -> float:
    """+1 = front-runner egilimi, -1 = closer egilimi, 0 = notr.

    Front-runner: dusuk stddev + iyi ortalama (tutarli onde bitiren)
    Closer: yuksek stddev (bazen iyi bazen kotu)
    """
    valid = [p for p in places if p > 0]
    if len(valid) < 3:
        return 0.0
    mean = sum(valid) / len(valid)
    variance = sum((p - mean) ** 2 for p in valid) / len(valid)
    stddev = variance ** 0.5
    if stddev < 2.0 and mean <= 4.0:
        return 0.7  # front-runner
    elif stddev > 3.5:
        return -0.7  # closer
    elif stddev < 2.5 and mean <= 6.0:
        return 0.3  # stalker
    else:
        return 0.0


def _weight_impact_factor(distance: int) -> float:
    """Mesafeye gore 1 kg'in boy cinsinden etkisi.

    Sprint (<=1200m): 0.5 length/kg
    Mil (1300-1600m): 0.75 length/kg
    Orta (1700-2100m): 1.0 length/kg
    Uzun (2200m+): 1.5 length/kg
    """
    if distance <= 1200:
        return 0.5
    elif distance <= 1600:
        return 0.75
    elif distance <= 2100:
        return 1.0
    else:
        return 1.5


def _normalized_rank_desc(values: list[float]) -> list[float]:
    """0=en iyi (en yüksek değer), 1=en kötü. Eşit değerler aynı rank alır."""
    n = len(values)
    if n <= 1:
        return [0.0] * n
    sorted_unique = sorted(set(values), reverse=True)
    rank_map = {v: i / (n - 1) for i, v in enumerate(sorted_unique)}
    return [rank_map[v] for v in values]


def _normalized_rank_asc(values: list[float]) -> list[float]:
    """0=en iyi (en düşük değer), 1=en kötü. Eşit değerler aynı rank alır. inf→en kötü."""
    n = len(values)
    if n <= 1:
        return [0.0] * n
    sorted_unique = sorted(set(values))
    rank_map = {v: i / (n - 1) for i, v in enumerate(sorted_unique)}
    return [rank_map[v] for v in values]


def add_intrarace_ranks(rows: list[dict]) -> None:
    """Koşu içi normalize rank ve saha-seviyesi feature'larını in-place ekler.
    Bülten inject sonrası çağrılmalı."""
    import math

    race_groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in rows:
        race_groups[(row["hip"], int(row["race_no"]))].append(row)

    for race_rows in race_groups.values():
        if not race_rows:
            continue

        def _get(key: str) -> list[float]:
            return [float(r["features"].get(key, 0.0) or 0.0) for r in race_rows]

        wr_vals       = _get("horse_win_rate_past")
        t3r_vals      = _get("horse_top3_rate_recent")
        wr_ranks      = _normalized_rank_desc(wr_vals)
        jwr_ranks     = _normalized_rank_desc(_get("jockey_win_rate_past"))
        l6_ranks      = _normalized_rank_desc(_get("last6_avg_place_inv"))
        l3_ranks      = _normalized_rank_desc(_get("horse_last3_inv"))
        trend_ranks   = _normalized_rank_desc(_get("horse_form_trend"))
        recent_ranks  = _normalized_rank_desc(_get("horse_win_rate_recent"))
        bg_ranks      = _normalized_rank_asc([
            g if hg > 0 else float("inf")
            for g, hg in zip(_get("best_grade_seconds"), _get("has_best_grade"))
        ])
        time_ranks    = _normalized_rank_asc([
            tt if ht > 0 else float("inf")
            for tt, ht in zip(_get("horse_avg_time_at_distance"), _get("horse_has_time_at_distance"))
        ])
        bgenel_ranks  = _normalized_rank_desc(_get("bulletin_genel"))
        bguncel_ranks = _normalized_rank_desc(_get("bulletin_guncel"))
        bsaatli_ranks = _normalized_rank_desc(_get("bulletin_saatli"))
        twr_ranks     = _normalized_rank_desc(_get("trainer_win_rate_past"))
        t3r_ranks     = _normalized_rank_desc(t3r_vals)
        hcap_ranks    = _normalized_rank_desc(_get("handicap"))
        kgs_ranks     = _normalized_rank_desc(_get("kgs"))
        # ── Yeni: Ek intra-race rank'ler ──
        going_wr_ranks  = _normalized_rank_desc(_get("horse_going_win_rate_past"))
        sf_ranks        = _normalized_rank_desc(_get("horse_speed_figure"))
        ttrack_ranks    = _normalized_rank_desc(_get("trainer_track_win_rate_past"))
        class_lvl_vals  = _get("race_class_level")
        class_lvl_ranks = _normalized_rank_desc(class_lvl_vals)
        effwt_vals      = _get("effective_weight")
        effwt_ranks     = _normalized_rank_asc(effwt_vals)  # dusuk kilo = avantajli
        # class_num_drop: yüksek = daha zayıf sınıfa indi = avantaj (desc rank)
        class_drop_ranks = _normalized_rank_desc(_get("class_num_drop"))

        # ── Saha-seviyesi göreceli güç feature'ları ──
        n = len(wr_vals)
        field_avg_wr = sum(wr_vals) / n if n else 0.0
        field_max_wr = max(wr_vals) if wr_vals else 0.0
        field_avg_effwt = sum(effwt_vals) / n if n else 0.0
        # Göreceli field feature'ları için değerler
        sf_vals     = _get("horse_speed_figure")
        jwr_abs     = _get("jockey_win_rate_past")
        twr_abs     = _get("trainer_win_rate_past")
        trend_abs   = _get("horse_form_trend")
        l6_abs      = _get("last6_avg_place_inv")
        t3r_abs     = _get("horse_top3_rate_recent")
        qd_vals     = _get("a2_card_avg_quality_diff")
        qr_vals     = _get("a2_card_recent3_quality_diff")
        field_avg_sf   = sum(sf_vals)   / n if n else 0.0
        field_avg_jwr  = sum(jwr_abs)   / n if n else 0.0
        field_avg_twr  = sum(twr_abs)   / n if n else 0.0
        field_avg_trend = sum(trend_abs) / n if n else 0.0
        field_avg_l6   = sum(l6_abs)    / n if n else 0.0
        field_avg_t3r  = sum(t3r_abs)   / n if n else 0.0
        field_avg_qd   = sum(qd_vals)   / n if n else 0.0
        field_avg_qr   = sum(qr_vals)   / n if n else 0.0

        for i, row in enumerate(race_rows):
            f = row["features"]
            f["horse_win_rate_rank_in_race"]         = wr_ranks[i]
            f["jockey_win_rate_rank_in_race"]        = jwr_ranks[i]
            f["last6_inv_rank_in_race"]              = l6_ranks[i]
            f["last3_inv_rank_in_race"]              = l3_ranks[i]
            f["form_trend_rank_in_race"]             = trend_ranks[i]
            f["horse_win_rate_recent_rank_in_race"]  = recent_ranks[i]
            f["horse_top3_rate_recent_rank_in_race"] = t3r_ranks[i]
            f["trainer_win_rate_rank_in_race"]       = twr_ranks[i]
            f["best_grade_rank_in_race"]             = bg_ranks[i]
            f["horse_time_rank_in_race"]             = time_ranks[i]
            f["bulletin_genel_rank_in_race"]         = bgenel_ranks[i]
            f["bulletin_guncel_rank_in_race"]        = bguncel_ranks[i]
            f["bulletin_saatli_rank_in_race"]        = bsaatli_ranks[i]
            f["handicap_rank_in_race"]               = hcap_ranks[i]
            f["kgs_rank_in_race"]                    = kgs_ranks[i]
            # ── Yeni: Intra-race rank'ler ──
            f["going_wr_rank_in_race"]               = going_wr_ranks[i]
            f["speed_figure_rank_in_race"]           = sf_ranks[i]
            f["trainer_track_wr_rank_in_race"]       = ttrack_ranks[i]
            f["class_level_rank_in_race"]            = class_lvl_ranks[i]
            f["effective_weight_rank_in_race"]       = effwt_ranks[i]
            f["class_num_rank_in_race"]              = class_drop_ranks[i]
            # ── Göreceli güç (mevcut) ──
            horse_wr = wr_vals[i]
            f["horse_wr_vs_field_avg"] = horse_wr - field_avg_wr
            f["horse_wr_ratio_max"]    = horse_wr / field_max_wr if field_max_wr > 0 else 0.0
            f["effective_weight_vs_field"] = effwt_vals[i] - field_avg_effwt
            # ── Yeni: Genişletilmiş göreceli field feature'ları ──
            f["quality_diff_vs_field"]  = qd_vals[i]  - field_avg_qd
            f["quality_recent_vs_field"] = qr_vals[i] - field_avg_qr
            f["speed_figure_vs_field"]  = sf_vals[i]  - field_avg_sf
            f["top3_rate_vs_field"]     = t3r_abs[i]  - field_avg_t3r
            f["jockey_wr_vs_field"]     = jwr_abs[i]  - field_avg_jwr
            f["trainer_wr_vs_field"]    = twr_abs[i]  - field_avg_twr
            f["form_trend_vs_field"]    = trend_abs[i] - field_avg_trend


def feature_rows_for_day(day: date, memory: HistoryMemory, program_dir: Path = PROGRAM_RAW_DIR) -> list[dict]:
    rows = []
    for (hip, race_no), horses in parse_program_horses(day, program_dir).items():
        for horse in horses:
            rows.append({
                "date": f"{day:%Y-%m-%d}",
                "hip": hip,
                "race_no": race_no,
                "horse_no": horse.horse_no,
                "horse_name": horse.horse_name,
                "atkodu": horse.atkodu,
                "features": features_for_horse(horse, memory),
            })
    return rows
