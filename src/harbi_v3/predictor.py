from __future__ import annotations

"""
Leakage-safe single-day prediction engine.

Kurallar:
- Memory: hedef tarihten ONCEKI tum gunler
- Model: hedef tarihten onceki verilerle egitilir
- Hedef gune ait program: sadece feature uretimi icin kullanilir
- Sonuc verisi: hedef gun icin KULLANILMAZ (sızıntı olmaz)
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from xgboost import XGBClassifier, XGBRanker

from .dates import parse_date
from .bulletin import inject_bulletin_rows
from .confidence import race_type_bucket
from .features import FEATURE_NAMES, HistoryMemory, add_intrarace_ranks, feature_rows_for_day
from .horse_cards import A2_CARD_FEATURE_NAMES
from .leakage import audit_feature_names
from .normalize import norm_text
from .paths import MODELS_DIR, PROGRAM_RAW_DIR, RESULTS_RAW_DIR
from .records import (
    HorseProgram,
    available_program_dates,
    load_program_day,
    parse_program_horses,
    parse_results,
)

_RANKER_PARAMS = {
    "n_estimators": 400,
    "max_depth": 4,
    "learning_rate": 0.025,
    "subsample": 0.85,
    "colsample_bytree": 0.8,
    "min_child_weight": 3,
    "reg_lambda": 3.0,
    "objective": "rank:pairwise",
    "eval_metric": "ndcg@5",
    "random_state": 20260612,
    "n_jobs": 4,
}

# Top-5 classifier: "bu at ilk 5'e girer mi?" sorusuna cevap verir.
# Büyük sahalarda win ranker ile blend edilerek 5'li satır isabetini artırır.
_CLASSIFIER_PARAMS = {
    "n_estimators": 250,
    "max_depth": 4,
    "learning_rate": 0.03,
    "subsample": 0.85,
    "colsample_bytree": 0.8,
    "min_child_weight": 2,
    "reg_lambda": 2.0,
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "random_state": 20260612,
    "n_jobs": 4,
}


def _latest_result_date(results_dir: Path = RESULTS_RAW_DIR) -> date | None:
    latest: date | None = None
    for path in results_dir.glob("*.json"):
        try:
            day = parse_date(path.stem)
        except ValueError:
            continue
        if latest is None or day > latest:
            latest = day
    return latest


@dataclass
class HorsePrediction:
    horse: HorseProgram
    jockey_short: str
    is_apprentice: bool
    score: float
    norm_score: float
    rank: int
    starts_past: int
    win_rate_past: float


@dataclass
class RacePrediction:
    hip: str
    race_no: int
    race_type: str
    race_group: str
    race_track: str
    race_distance: int
    race_hour: str
    runner_count: int
    horses: list[HorsePrediction]
    norm_score_gap: float = 0.0  # #1 ile #2 arasındaki normalize skor farkı
    surdirek_source: str = "production"
    surdirek_source_horse_no: int | None = None
    surdirek_source_gap: float = 0.0


def _load_race_meta(day: date, program_dir: Path = PROGRAM_RAW_DIR) -> dict[tuple[str, int], dict]:
    """Raw JSON'dan saat ve jokey bilgisi (apprentice flag dahil) ceker."""
    data = load_program_day(day, program_dir)
    out: dict[tuple[str, int], dict] = {}
    for hip, hip_data in (data.get("hippodromes") or {}).items():
        hip_norm = norm_text(hip)
        for race in (hip_data.get("details") or {}).get("races") or []:
            race_no = int(str(race.get("number") or "0").strip() or "0")
            if race_no <= 0:
                continue
            jockeys: dict[int, dict] = {}
            for horse in race.get("horses") or []:
                hno = int(str(horse.get("number") or "0").strip() or "0")
                if hno <= 0:
                    continue
                j = horse.get("jockey") or {}
                jockeys[hno] = {
                    "name": str(j.get("name") or "").strip(),
                    "apprentice": bool(j.get("apprentice", False)),
                }
            out[(hip_norm, race_no)] = {
                "hour": str(race.get("hour") or ""),
                "jockeys": jockeys,
            }
    return out


def _normalize_day(all_scores: list[float]) -> list[float]:
    """Günün tüm atları üzerinden 0-100 normalizasyonu (koşu-agnostik)."""
    mn, mx = min(all_scores), max(all_scores)
    if mx <= mn:
        return [50.0] * len(all_scores)
    return [(s - mn) / (mx - mn) * 100.0 for s in all_scores]


# ── Asimptotik 0-100 puanlama ──
# Sigmoid dönüşüm: 0 ve 100'e asla ulaşılmaz.
# Koşu tipi tavanı YOK — dominant favori handikap'ta da 90+ alabilir.
# Amaç: Modelin ham skorunu dürüstçe yansıtmak, yapay sınır koymamak.

_SIGMOID_SCALE = 0.8  # sigmoid dikliği (büyüdükçe uçlara yaklaşır)


def _calibrate_race_scores(
    blended: list[float],
    race_type_bucket: str,
    runner_count: int,
) -> list[float]:
    """Sigmoid asimptotik dönüşüm: ham skor → 0-100.
    Tip-bazlı tavan YOK. Her at modelin gördüğü değeri alır.
    """
    arr = np.array(blended, dtype=float)
    mn, mx = arr.min(), arr.max()
    if mx <= mn:
        return [50.0] * len(blended)
    centered = (arr - arr.mean()) / (arr.std() + 1e-8)
    scores = 100.0 / (1.0 + np.exp(-centered * _SIGMOID_SCALE))
    return scores.tolist()


# Tip-bazlı temel blend agirligi (tarihsel 5'li satir isabet oranlarindan).
# PRODUCTION VARSAYILANI — degerlendirme sweep'i bunu override edebilir, ama
# production predict_for_date her zaman bu varsayilani kullanir.
_DEFAULT_BLEND_BASE = {
    "handikap": 0.50,   # en zor → classifier'a en çok güven
    "maiden":  0.38,
    "other":   0.30,
    "sartli":  0.22,
    "kv_grup": 0.12,    # en kolay → ranker'a güven
}


def _blend_alpha(
    race_type_bucket: str,
    runner_count: int,
    base_map: dict[str, float] | None = None,
    small_field_max: int = 7,
    field_div: float = 12.0,
) -> float:
    """Classifier blend ağırlığı: koşu tipi × saha boyutu.

    Handikap'ta ranker daha güvenilmezdir (sürpriz %9.9) → classifier ağırlığı yüksek.
    KV/Grup'ta ranker daha iyidir → classifier ağırlığı düşük.

    Parametreler degerlendirme/sweep icindir; varsayilanlar production davranisini korur.
    """
    if runner_count <= small_field_max:
        return 0.0  # küçük saha: saf ranker, favori odaklı

    bm = base_map if base_map is not None else _DEFAULT_BLEND_BASE
    base = bm.get(race_type_bucket, 0.30)

    # Saha boyutu çarpanı: büyüdükçe classifier daha da önemli
    field_scale = min((runner_count - small_field_max) / field_div, 1.0)

    return base * field_scale


def _calibrate_for_large_fields(
    race_norm: dict[tuple[str, int], list[float]],
    race_raw: dict[tuple[str, int], tuple[list[dict], list[float], list[float]]],
    race_buckets: dict[tuple[str, int], str],
) -> dict[tuple[str, int], list[float]]:
    """Tip-bazlı tutarlılık bonusu: handikap'ta güçlü, kv_grup'ta hafif.

    Elit koşularda (kv_grup) favoriler zaten önde gelir — bonus minimal.
    Handikap'ta tutarlı plase atları yukarı çekilir.
    """
    calibrated: dict[tuple[str, int], list[float]] = {}
    for key in sorted(race_norm):
        rows, _, _ = race_raw[key]
        norms = list(race_norm[key])
        runner_count = len(rows)
        if runner_count < 9:
            calibrated[key] = norms
            continue

        bucket = race_buckets.get(key, "other")

        # Tip-bazlı bonus çarpanı
        type_mult = {
            "handikap": 1.5,   # en güçlü bonus
            "maiden":  1.1,
            "other":   0.9,
            "sartli":  0.6,
            "kv_grup": 0.3,    # en zayıf bonus (ranker zaten iyi)
        }.get(bucket, 0.9)

        alpha = min((runner_count - 8) / 15.0, 0.50) * type_mult

        for i, row in enumerate(rows):
            f = row["features"]
            top3_shrunk = float(f.get("horse_top3_rate_past_shrunk", 0.0) or 0.0)
            wr_shrunk = float(f.get("horse_win_rate_past_shrunk", 0.0) or 0.0)
            starts = float(f.get("horse_starts_past", 0.0) or 0.0)

            consistency = max(0.0, top3_shrunk - 0.15)
            experience = min(starts / 10.0, 1.0)
            placer_signal = max(0.0, top3_shrunk - wr_shrunk - 0.08)

            bonus = consistency * experience * alpha * 5.0
            bonus += placer_signal * experience * alpha * 3.0

            norms[i] = norms[i] + max(0.0, bonus)

        calibrated[key] = norms
    return calibrated


def train_models(
    all_x: list[list[float]],
    all_y_rank: list[int],
    all_y_cls: list[int],
    all_groups: list[int],
) -> tuple[XGBRanker, XGBClassifier]:
    """Production recetesiyle ranker + top-5 classifier egitir.

    predict_for_date ve degerlendirme harness'i ORTAK bu fonksiyonu kullanir;
    boylece egitim recetesi tek yerdedir (kopya/sapma olmaz).
    """
    X_train = np.array(all_x, dtype=float)
    groups = np.array(all_groups, dtype=int)
    ranker = XGBRanker(**_RANKER_PARAMS)
    clf = XGBClassifier(**_CLASSIFIER_PARAMS)
    ranker.fit(X_train, np.array(all_y_rank, dtype=float), group=groups)
    clf.fit(X_train, np.array(all_y_cls, dtype=int))
    return ranker, clf


def train_classifier(all_x: list[list[float]], labels: list[int]) -> XGBClassifier:
    """Shared binary classifier recipe for auxiliary leak-safe targets."""
    clf = XGBClassifier(**_CLASSIFIER_PARAMS)
    clf.fit(np.array(all_x, dtype=float), np.array(labels, dtype=int))
    return clf


def score_races(
    race_raw: dict[tuple[str, int], tuple[list[dict], list[float], list[float]]],
    program_lookup: dict[tuple[str, int, int], "HorseProgram"],
    names: list[str],
    blend_base: dict[str, float] | None = None,
    small_field_max: int = 7,
    field_div: float = 12.0,
) -> dict[tuple[str, int], list[float]]:
    """Ham (ranker, classifier) skorlardan tip-bazli blend + kalibre 0-100 uretir.

    predict_for_date ve harness ORTAK bunu kullanir -> blend/kalibrasyon tek yerde.
    blend_base/small_field_max/field_div degerlendirme sweep'i icindir; varsayilanlar
    production davranisini BIREBIR korur. Donen: (hip,race_no) -> norm_scores.
    """
    race_blended: dict[tuple[str, int], list[float]] = {}
    race_buckets: dict[tuple[str, int], str] = {}
    for key in sorted(race_raw):
        rows, rank_scores, clf_probs = race_raw[key]
        runner_count = len(rows)
        first_hno = int(rows[0]["horse_no"])
        hp = program_lookup.get((key[0], key[1], first_hno))
        bucket = race_type_bucket(hp.race_type if hp else "", hp.race_group if hp else "")
        race_buckets[key] = bucket
        alpha = _blend_alpha(bucket, runner_count, blend_base, small_field_max, field_div)
        if alpha == 0.0:
            blended = list(rank_scores)
        else:
            r_min, r_max = min(rank_scores), max(rank_scores)
            if r_max > r_min:
                r_norm = [(s - r_min) / (r_max - r_min) for s in rank_scores]
            else:
                r_norm = [0.5] * len(rank_scores)
            blended = [(1.0 - alpha) * rn + alpha * cp for rn, cp in zip(r_norm, clf_probs)]
        race_blended[key] = blended

    race_norm: dict[tuple[str, int], list[float]] = {}
    for key in sorted(race_blended):
        race_norm[key] = _calibrate_race_scores(
            race_blended[key], race_buckets[key], len(race_blended[key]),
        )
    race_norm = _calibrate_for_large_fields(race_norm, race_raw, race_buckets)
    return race_norm


def predict_for_date(
    target_date: date,
    feature_names: list[str] | None = None,
    min_train_days: int = 30,
    city: str | None = None,
    program_dir: Path = PROGRAM_RAW_DIR,
    model_dir: Path = MODELS_DIR,
) -> list[RacePrediction]:
    """
    Hedef tarih icin sızıntısız tahmin uretir.

    Args:
        target_date: Tahmin yapilacak tarih
        feature_names: Kullanilacak feature isimleri (None = tumu)
        min_train_days: Minimum egitim gun sayisi
        city: None → tum sehirler, \"ISTANBUL\" → sadece o sehir
        program_dir: Program dosyalarinin oldugu dizin
        model_dir: Kaydedilmis/egitilecek modellerin dizini

    Dondurulan deger: hipodrom bazinda sirali RacePrediction listesi.
    """
    names = feature_names if feature_names is not None else FEATURE_NAMES
    audit_feature_names(names).raise_if_failed()
    missing_a2 = [name for name in A2_CARD_FEATURE_NAMES if name not in names]
    if missing_a2:
        raise RuntimeError(
            "Production prediction requires A2 horse-card features; "
            f"missing {len(missing_a2)} feature(s): {', '.join(missing_a2[:5])}"
        )
    memory = HistoryMemory()

    # ---- Egitim verisi: hedef tarihten onceki tum gunler ----
    # Iki model icin ortak feature'lar, farkli etiketler:
    #   Ranker  → winner (rank==1)
    #   Classifier → top-5 (rank<=5)
    all_x: list[list[float]] = []
    all_y_rank: list[int] = []
    all_groups: list[int] = []
    all_y_cls: list[int] = []  # top-5 etiketleri (classifier)
    all_y_top2: list[int] = []  # sürdirek source-policy için top-2 classifier
    all_y_win: list[int] = []
    total_train_days = 0

    for day in sorted(available_program_dates()):
        if day >= target_date:
            break
        results = parse_results(day)
        day_rows = feature_rows_for_day(day, memory, program_dir=program_dir)
        inject_bulletin_rows(day_rows, day)
        add_intrarace_ranks(day_rows)
        race_groups: dict[tuple[str, int], list] = defaultdict(list)
        for row in day_rows:
            key = (row["hip"], int(row["race_no"]))
            result = results.get(key)
            if not result:
                continue
            feat = [float(row["features"].get(n, 0.0) or 0.0) for n in names]
            rank = result.order_by_no.get(int(row["horse_no"]), 99)
            label_rank = int(row["horse_no"] == result.winner_no)
            label_cls = int(1 <= rank <= 5)
            label_top2 = int(1 <= rank <= 2)
            race_groups[key].append((feat, label_rank, label_cls, label_top2))

        for key, items in race_groups.items():
            if len(items) < 2:
                continue
            all_groups.append(len(items))
            for feat, label_rank, label_cls, label_top2 in items:
                all_x.append(feat)
                all_y_rank.append(label_rank)
                all_y_cls.append(label_cls)
                all_y_top2.append(label_top2)
                all_y_win.append(label_rank)

        programs = parse_program_horses(day)
        for key, race_result in results.items():
            horses = programs.get(key)
            if horses:
                memory.update_race(horses, race_result.order_by_no, race_result.time_by_no)
        total_train_days += 1

    if total_train_days < min_train_days or not all_x:
        return []

    # ---- Model egitimi (çift-model: ranker + top-5 classifier) ----
    model_dir.mkdir(parents=True, exist_ok=True)

    # Historical/backtest targets must not load _lokalson, because it may have
    # been trained after the target date. Live/future targets still prefer it.
    ranker_lokalson = model_dir / "ranker_lokalson.json"
    clf_lokalson = model_dir / "clf_lokalson.json"
    clf_win_lokalson = model_dir / "clf_win_lokalson.json"
    clf_top2_lokalson = model_dir / "clf_top2_lokalson.json"
    ranker_path = model_dir / f"ranker_{target_date}.json"
    clf_path = model_dir / f"clf_{target_date}.json"
    clf_win_path = model_dir / f"clf_win_{target_date}.json"
    clf_top2_path = model_dir / f"clf_top2_{target_date}.json"
    latest_result = _latest_result_date()
    allow_lokalson = latest_result is None or target_date > latest_result

    ranker = XGBRanker(**_RANKER_PARAMS)
    clf = XGBClassifier(**_CLASSIFIER_PARAMS)
    clf_win = XGBClassifier(**_CLASSIFIER_PARAMS)
    clf_top2 = XGBClassifier(**_CLASSIFIER_PARAMS)

    loaded = False
    model_pairs = [(ranker_path, clf_path)]
    if allow_lokalson:
        model_pairs.insert(0, (ranker_lokalson, clf_lokalson))
    for rp, cp in model_pairs:
        if rp.exists() and cp.exists():
            ranker.load_model(str(rp))
            clf.load_model(str(cp))
            loaded = True
            break

    if not loaded:
        ranker, clf = train_models(all_x, all_y_rank, all_y_cls, all_groups)

        # Tarih bazlı kaydet (VDS için)
        ranker.save_model(str(ranker_path))
        clf.save_model(str(clf_path))
        # _lokalson kopyası (lokal için — her zaman son eğitilen model)
        if allow_lokalson:
            ranker.save_model(str(ranker_lokalson))
            clf.save_model(str(clf_lokalson))

    win_loaded = False
    win_paths = [clf_win_path]
    if allow_lokalson:
        win_paths.insert(0, clf_win_lokalson)
    for cp in win_paths:
        if cp.exists():
            clf_win.load_model(str(cp))
            win_loaded = True
            break
    if not win_loaded:
        clf_win = train_classifier(all_x, all_y_win)
        clf_win.save_model(str(clf_win_path))
        if allow_lokalson:
            clf_win.save_model(str(clf_win_lokalson))

    top2_loaded = False
    top2_paths = [clf_top2_path]
    if allow_lokalson:
        top2_paths.insert(0, clf_top2_lokalson)
    for cp in top2_paths:
        if cp.exists():
            clf_top2.load_model(str(cp))
            top2_loaded = True
            break
    if not top2_loaded:
        clf_top2 = train_classifier(all_x, all_y_top2)
        clf_top2.save_model(str(clf_top2_path))
        if allow_lokalson:
            clf_top2.save_model(str(clf_top2_lokalson))

    # ---- Hedef gun feature'lari ----
    target_rows = feature_rows_for_day(target_date, memory, program_dir=program_dir)
    inject_bulletin_rows(target_rows, target_date)
    add_intrarace_ranks(target_rows)

    if city:
        city_norm = city.upper()
        target_rows = [r for r in target_rows if r["hip"] == city_norm]

    race_meta = _load_race_meta(target_date, program_dir=program_dir)
    target_programs = parse_program_horses(target_date, program_dir=program_dir)

    # horse_no -> HorseProgram lookup
    program_lookup: dict[tuple[str, int, int], HorseProgram] = {}
    for (hip, race_no), horses in target_programs.items():
        for h in horses:
            program_lookup[(hip, race_no, h.horse_no)] = h

    # feature_name index for starts
    starts_idx = names.index("horse_starts_past") if "horse_starts_past" in names else -1
    win_idx = names.index("horse_win_rate_past") if "horse_win_rate_past" in names else -1

    # Group target rows by race
    target_races: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in target_rows:
        key = (row["hip"], int(row["race_no"]))
        target_races[key].append(row)

    # ---- 1. geçiş: her koşunun ham skorlarını topla (ranker + classifier) ----
    race_raw: dict[tuple[str, int], tuple[list[dict], list[float], list[float]]] = {}
    race_source_probs: dict[tuple[str, int], list[float]] = {}
    for (hip, race_no) in sorted(target_races):
        rows = sorted(target_races[(hip, race_no)], key=lambda r: int(r["horse_no"]))
        X_test = np.array(
            [[float(r["features"].get(n, 0.0) or 0.0) for n in names] for r in rows],
            dtype=float,
        )
        rank_scores = ranker.predict(X_test).tolist()
        clf_probs = clf.predict_proba(X_test)[:, 1].tolist()  # top-5 olasılığı
        source_probs = clf_win.predict_proba(X_test)[:, 1].tolist()
        race_raw[(hip, race_no)] = (rows, rank_scores, clf_probs)
        race_source_probs[(hip, race_no)] = source_probs

    race_norm = score_races(race_raw, program_lookup, names)

    # ---- 2. geçiş: RacePrediction nesneleri oluştur ----
    results_out: list[RacePrediction] = []

    for (hip, race_no) in sorted(race_raw):
        rows, rank_scores, clf_probs = race_raw[(hip, race_no)]
        norm_scores = race_norm[(hip, race_no)]
        source_probs = race_source_probs.get((hip, race_no), [])
        # Ranking: norm_score'a göre (blend edilmiş + kalibre edilmiş)
        ranked = sorted(
            zip(rows, rank_scores, norm_scores), key=lambda t: -t[2]
        )

        meta = race_meta.get((hip, race_no), {})
        hour = meta.get("hour", "")
        jockey_map = meta.get("jockeys", {})

        first_horse = program_lookup.get((hip, race_no, int(rows[0]["horse_no"])))
        race_type = first_horse.race_type if first_horse else ""
        race_group = first_horse.race_group if first_horse else ""
        race_track = first_horse.race_track if first_horse else ""
        race_distance = first_horse.race_distance if first_horse else 0
        runner_count = len(rows)

        horse_preds: list[HorsePrediction] = []
        for rank_i, (row, raw_score, n_score) in enumerate(ranked):
            hno = int(row["horse_no"])
            hp = program_lookup.get((hip, race_no, hno))
            feat_vec = [float(row["features"].get(n, 0.0) or 0.0) for n in names]
            starts = int(feat_vec[starts_idx]) if starts_idx >= 0 else 0
            wr = feat_vec[win_idx] if win_idx >= 0 else 0.0
            j_info = jockey_map.get(hno, {})
            horse_preds.append(HorsePrediction(
                horse=hp if hp else _dummy_horse(hno, row.get("horse_name", ""), hip, race_no, race_track, race_distance, race_type, race_group, target_date),
                jockey_short=j_info.get("name", hp.jockey_name if hp else ""),
                is_apprentice=j_info.get("apprentice", False),
                score=raw_score,
                norm_score=round(n_score, 1),
                rank=rank_i + 1,
                starts_past=starts,
                win_rate_past=wr,
            ))

        norm_gap = 0.0
        if len(norm_scores) >= 2:
            sorted_ns = sorted(norm_scores, reverse=True)
            norm_gap = round(sorted_ns[0] - sorted_ns[1], 1)
        source_horse_no: int | None = None
        source_gap = 0.0
        if len(source_probs) >= 2:
            source_order = sorted(range(len(rows)), key=lambda i: -source_probs[i])
            source_horse_no = int(rows[source_order[0]]["horse_no"])
            source_gap = round(float(source_probs[source_order[0]] - source_probs[source_order[1]]) * 100.0, 4)
        results_out.append(RacePrediction(
            hip=hip,
            race_no=race_no,
            race_type=race_type,
            race_group=race_group,
            race_track=race_track,
            race_distance=race_distance,
            race_hour=hour,
            runner_count=runner_count,
            horses=horse_preds,
            norm_score_gap=norm_gap,
            surdirek_source="win",
            surdirek_source_horse_no=source_horse_no,
            surdirek_source_gap=source_gap,
        ))

    return results_out


def _dummy_horse(hno: int, name: str, hip: str, race_no: int, track: str, dist: int, rtype: str, rgroup: str, day: date) -> HorseProgram:
    return HorseProgram(
        run_date=day, hip=hip, race_no=race_no, horse_no=hno,
        horse_name=name, jockey_name="", trainer_name="", owner_name="",
        sire_name="", dam_sire_name="", equipment="",
        equipment_added=(), equipment_removed=(), age_text="",
        weight=0.0, handicap=0.0, kgs=0.0, last20=0.0,
        last6_places=(), last6_tracks=(),
        race_track=track, race_distance=dist,
        race_type=rtype, race_group=rgroup,
        start_box=0, runner_count=0,
    )
