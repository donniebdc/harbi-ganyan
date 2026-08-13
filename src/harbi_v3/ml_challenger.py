from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from xgboost import XGBClassifier, XGBRanker

from .bulletin import inject_bulletin_rows
from .confidence import race_type_bucket as _race_type_bucket
from .features import FEATURE_NAMES, FEATURE_SET_DEFINITIONS, HistoryMemory, add_intrarace_ranks, feature_rows_for_day
from .leakage import audit_feature_names, write_audit
from .paths import AUDIT_DIR, REPORTS_DIR, ensure_dirs
from .records import available_program_dates, distance_bucket, parse_program_horses, parse_results


@dataclass
class Row:
    month: str
    date: str
    hip: str
    race_no: int
    horse_no: int
    features: list[float]
    winner: int
    race_type: str = "other"


def build_time_safe_rows(feature_names: list[str] | None = None) -> list[Row]:
    names = feature_names if feature_names is not None else FEATURE_NAMES
    memory = HistoryMemory()
    rows: list[Row] = []
    for day in available_program_dates():
        results = parse_results(day)
        day_rows = feature_rows_for_day(day, memory)
        inject_bulletin_rows(day_rows, day)
        add_intrarace_ranks(day_rows)
        programs = parse_program_horses(day)
        race_type_map: dict[tuple[str, int], str] = {}
        for (hip_k, rno_k), horses in programs.items():
            if horses:
                race_type_map[(hip_k, rno_k)] = _race_type_bucket(horses[0].race_type, horses[0].race_group)
        for row in day_rows:
            key = (row["hip"], int(row["race_no"]))
            result = results.get(key)
            if not result:
                continue
            features = row["features"]
            rows.append(Row(
                month=f"{day:%Y-%m}",
                date=f"{day:%Y-%m-%d}",
                hip=row["hip"],
                race_no=int(row["race_no"]),
                horse_no=int(row["horse_no"]),
                features=[float(features.get(name, 0.0) or 0.0) for name in names],
                winner=int(row["horse_no"] == result.winner_no),
                race_type=race_type_map.get(key, "other"),
            ))
        for key, race_result in results.items():
            horses = programs.get(key)
            if horses:
                memory.update_race(horses, race_result.order_by_no, race_result.time_by_no)
    return rows


def _group_races(rows: list[Row]) -> dict[tuple[str, str, int], list[Row]]:
    grouped: dict[tuple[str, str, int], list[Row]] = defaultdict(list)
    for row in rows:
        grouped[(row.date, row.hip, row.race_no)].append(row)
    return grouped


def _matrix_with_groups(rows: list[Row]):
    grouped = _group_races(rows)
    x_rows = []
    y_rows = []
    groups = []
    ordered_rows = []
    for key in sorted(grouped):
        race_rows = sorted(grouped[key], key=lambda r: r.horse_no)
        groups.append(len(race_rows))
        for row in race_rows:
            x_rows.append(row.features)
            y_rows.append(row.winner)
            ordered_rows.append(row)
    return (
        np.array(x_rows, dtype=float),
        np.array(y_rows, dtype=float),
        np.array(groups, dtype=int),
        ordered_rows,
    )


def _evaluate_probs(test_rows: list[Row], probs: np.ndarray) -> dict:
    grouped: dict[tuple[str, str, int], list[tuple[Row, float]]] = defaultdict(list)
    for row, prob in zip(test_rows, probs):
        grouped[(row.date, row.hip, row.race_no)].append((row, float(prob)))
    races = fav_hits = line5_hits = 0
    for items in grouped.values():
        items.sort(key=lambda item: (-item[1], item[0].horse_no))
        winner_no = next((row.horse_no for row, _ in items if row.winner), None)
        if winner_no is None or not items:
            continue
        top5 = [row.horse_no for row, _ in items[:5]]
        races += 1
        fav_hits += int(top5[0] == winner_no)
        line5_hits += int(winner_no in top5)
    return {
        "races": races,
        "fav_hits": fav_hits,
        "line5_hits": line5_hits,
        "fav_rate": fav_hits / races if races else 0.0,
        "line5_rate": line5_hits / races if races else 0.0,
    }


def _field_bucket(n: int) -> str:
    if n <= 7:
        return "01_7_or_less"
    if n <= 10:
        return "02_8_10"
    if n <= 13:
        return "03_11_13"
    if n <= 16:
        return "04_14_16"
    return "05_17_plus"


def _track_bucket(track: str) -> str:
    text = (track or "").strip().lower()
    if "cim" in text or "çim" in text:
        return "cim"
    if "kum" in text:
        return "kum"
    if "sentetik" in text:
        return "sentetik"
    return text or "unknown"


def _confidence_bucket(starts: float) -> str:
    if starts <= 0:
        return "00_no_history"
    if starts <= 2:
        return "01_low_history"
    if starts <= 5:
        return "02_mid_history"
    return "03_high_history"


def _prediction_rows(test_rows: list[Row], scores: np.ndarray, feature_names: list[str] | None = None) -> list[dict]:
    grouped: dict[tuple[str, str, int], list[tuple[Row, float]]] = defaultdict(list)
    for row, score in zip(test_rows, scores):
        grouped[(row.date, row.hip, row.race_no)].append((row, float(score)))

    out: list[dict] = []
    program_cache = {}
    for key, items in grouped.items():
        date_s, hip, race_no = key
        items.sort(key=lambda item: (-item[1], item[0].horse_no))
        winner_no = next((row.horse_no for row, _ in items if row.winner), None)
        if winner_no is None or not items:
            continue
        day = items[0][0].date
        if day not in program_cache:
            from .dates import parse_date
            program_cache[day] = parse_program_horses(parse_date(day))
        horses = program_cache.get(day, {}).get((hip, race_no), [])
        meta = horses[0] if horses else None
        selected = items[0][0]
        top_score = items[0][1]
        second_score = items[1][1] if len(items) > 1 else top_score
        top5 = [row.horse_no for row, _ in items[:5]]
        names = feature_names if feature_names is not None else FEATURE_NAMES
        starts_idx = names.index("horse_starts_past") if "horse_starts_past" in names else -1
        selected_starts = selected.features[starts_idx] if starts_idx < len(selected.features) else 0.0
        runner_count = len(items)
        out.append({
            "date": date_s,
            "month": selected.month,
            "hip": hip,
            "race_no": race_no,
            "predicted_no": selected.horse_no,
            "winner_no": winner_no,
            "fav_hit": selected.horse_no == winner_no,
            "line5_hit": winner_no in top5,
            "top_score": top_score,
            "score_margin": top_score - second_score,
            "runner_count": runner_count,
            "field_bucket": _field_bucket(runner_count),
            "confidence_bucket": _confidence_bucket(float(selected_starts or 0.0)),
            "track": _track_bucket(meta.race_track if meta else ""),
            "distance_bucket": distance_bucket(meta.race_distance if meta else 0),
            "race_type": _race_type_bucket(meta.race_type if meta else "", meta.race_group if meta else ""),
        })
    return out


def run_xgb_monthly_walkforward(min_train_months: int = 3) -> Path:
    ensure_dirs()
    audit = audit_feature_names(FEATURE_NAMES)
    write_audit(AUDIT_DIR / "ml_challenger_feature_audit.json", audit)
    audit.raise_if_failed()

    rows = build_time_safe_rows()
    months = sorted({row.month for row in rows})
    month_results = []
    total = {"races": 0, "fav_hits": 0, "line5_hits": 0}

    params = {
        "n_estimators": 180,
        "max_depth": 3,
        "learning_rate": 0.045,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "min_child_weight": 4,
        "reg_lambda": 5.0,
        "objective": "binary:logistic",
        "eval_metric": "logloss",
        "random_state": 20260612,
        "n_jobs": 4,
    }

    for idx, month in enumerate(months):
        train_months = months[:idx]
        if len(train_months) < min_train_months:
            continue
        train_rows = [row for row in rows if row.month in train_months]
        test_rows = [row for row in rows if row.month == month]
        if not train_rows or not test_rows:
            continue
        x_train = np.array([row.features for row in train_rows], dtype=float)
        y_train = np.array([row.winner for row in train_rows], dtype=int)
        x_test = np.array([row.features for row in test_rows], dtype=float)
        model = XGBClassifier(**params)
        model.fit(x_train, y_train)
        probs = model.predict_proba(x_test)[:, 1]
        res = _evaluate_probs(test_rows, probs)
        res["month"] = month
        month_results.append(res)
        for key in total:
            total[key] += res[key]

    races = total["races"]
    fav_rate = total["fav_hits"] / races if races else 0.0
    line5_rate = total["line5_hits"] / races if races else 0.0

    report_path = REPORTS_DIR / "v3_ml_xgb_walkforward_raporu.md"
    lines = [
        "# Harbi Ganyan v3 XGB Monthly Walk-Forward Raporu",
        "",
        "Bu rapor AGF, ganyan, oran, bahis veya dis tahmin skoru kullanmaz.",
        "",
        "## Ozet",
        "",
        f"- Test ayi: {len(month_results)}",
        f"- Kosu: {races}",
        f"- Harbi Ganyan Favorisi: {total['fav_hits']}/{races} ({fav_rate:.2%})",
        f"- 5'li satir: {total['line5_hits']}/{races} ({line5_rate:.2%})",
        "",
        "## Aylik Sonuclar",
        "",
        "| Ay | Kosu | Favori | 5'li |",
        "|---|---:|---:|---:|",
    ]
    for res in month_results:
        lines.append(
            f"| {res['month']} | {res['races']} | {res['fav_hits']}/{res['races']} ({res['fav_rate']:.2%}) | "
            f"{res['line5_hits']}/{res['races']} ({res['line5_rate']:.2%}) |"
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_xgbranker_monthly_walkforward(min_train_months: int = 3) -> Path:
    ensure_dirs()
    audit = audit_feature_names(FEATURE_NAMES)
    write_audit(AUDIT_DIR / "ml_ranker_feature_audit.json", audit)
    audit.raise_if_failed()

    rows = build_time_safe_rows()
    months = sorted({row.month for row in rows})
    month_results = []
    total = {"races": 0, "fav_hits": 0, "line5_hits": 0}

    params = {
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

    for idx, month in enumerate(months):
        train_months = months[:idx]
        if len(train_months) < min_train_months:
            continue
        train_rows = [row for row in rows if row.month in train_months]
        test_rows = [row for row in rows if row.month == month]
        if not train_rows or not test_rows:
            continue
        x_train, y_train, train_groups, _ = _matrix_with_groups(train_rows)
        x_test = np.array([row.features for row in test_rows], dtype=float)
        model = XGBRanker(**params)
        model.fit(x_train, y_train, group=train_groups)
        scores = model.predict(x_test)
        res = _evaluate_probs(test_rows, scores)
        res["month"] = month
        month_results.append(res)
        for key in total:
            total[key] += res[key]

    races = total["races"]
    fav_rate = total["fav_hits"] / races if races else 0.0
    line5_rate = total["line5_hits"] / races if races else 0.0

    report_path = REPORTS_DIR / "v3_ml_xgbranker_walkforward_raporu.md"
    lines = [
        "# Harbi Ganyan v3 XGBRanker Monthly Walk-Forward Raporu",
        "",
        "Bu rapor AGF, ganyan, oran, bahis veya dis tahmin skoru kullanmaz.",
        "",
        "## Ozet",
        "",
        f"- Test ayi: {len(month_results)}",
        f"- Kosu: {races}",
        f"- Harbi Ganyan Favorisi: {total['fav_hits']}/{races} ({fav_rate:.2%})",
        f"- 5'li satir: {total['line5_hits']}/{races} ({line5_rate:.2%})",
        "",
        "## Aylik Sonuclar",
        "",
        "| Ay | Kosu | Favori | 5'li |",
        "|---|---:|---:|---:|",
    ]
    for res in month_results:
        lines.append(
            f"| {res['month']} | {res['races']} | {res['fav_hits']}/{res['races']} ({res['fav_rate']:.2%}) | "
            f"{res['line5_hits']}/{res['races']} ({res['line5_rate']:.2%}) |"
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


_RANKER_PARAMS_DEFAULT = {
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

# Koşu tipine özel hiperparametreler. Belirtilmeyen tipler default kullanır.
# AGF analizi: handikap en zor (sürpriz %9.9), kv_grup en tahmin edilebilir.
_RANKER_PARAMS_BY_TYPE = {
    "handikap": {**_RANKER_PARAMS_DEFAULT, "max_depth": 5, "n_estimators": 500, "reg_lambda": 4.0},
    "maiden":   {**_RANKER_PARAMS_DEFAULT, "max_depth": 4, "n_estimators": 450},
    "kv_grup":  {**_RANKER_PARAMS_DEFAULT, "max_depth": 3, "n_estimators": 350, "reg_lambda": 2.0},
    "sartli":   _RANKER_PARAMS_DEFAULT,
    "other":    _RANKER_PARAMS_DEFAULT,
}

# Bir tipin kendi verisiyle eğitilmesi için aylık minimum train satırı.
# Altındaysa o ay tüm-tip (genel) modele düşülür — "her tip mutlaka tahmin" korunur.
_MIN_TYPE_TRAIN_ROWS = 1200


def collect_xgbranker_predictions(
    min_train_months: int = 3,
    feature_names: list[str] | None = None,
    per_type: bool = False,
) -> list[dict]:
    ensure_dirs()
    names = feature_names if feature_names is not None else FEATURE_NAMES
    audit = audit_feature_names(names)
    write_audit(AUDIT_DIR / "ml_ranker_prediction_feature_audit.json", audit)
    audit.raise_if_failed()

    rows = build_time_safe_rows(feature_names=names)
    months = sorted({row.month for row in rows})
    predictions: list[dict] = []

    for idx, month in enumerate(months):
        train_months = months[:idx]
        if len(train_months) < min_train_months:
            continue
        train_rows = [row for row in rows if row.month in train_months]
        test_rows = [row for row in rows if row.month == month]
        if not train_rows or not test_rows:
            continue

        if not per_type:
            x_train, y_train, train_groups, _ = _matrix_with_groups(train_rows)
            x_test = np.array([row.features for row in test_rows], dtype=float)
            model = XGBRanker(**_RANKER_PARAMS_DEFAULT)
            model.fit(x_train, y_train, group=train_groups)
            scores = model.predict(x_test)
            predictions.extend(_prediction_rows(test_rows, scores, feature_names=names))
            continue

        # ---- Per-tip model: her race_type ayrı eğitilir ----
        all_test_rows: list[Row] = []
        all_scores: list[float] = []
        race_types = sorted({row.race_type for row in test_rows})
        for rtype in race_types:
            type_test = [row for row in test_rows if row.race_type == rtype]
            if not type_test:
                continue
            type_train = [row for row in train_rows if row.race_type == rtype]
            # Yetersiz tip verisi → genel modele düş (her tip mutlaka tahmin edilir)
            if len(type_train) < _MIN_TYPE_TRAIN_ROWS:
                type_train = train_rows
            params = _RANKER_PARAMS_BY_TYPE.get(rtype, _RANKER_PARAMS_DEFAULT)
            x_train, y_train, train_groups, _ = _matrix_with_groups(type_train)
            x_test = np.array([row.features for row in type_test], dtype=float)
            model = XGBRanker(**params)
            model.fit(x_train, y_train, group=train_groups)
            scores = model.predict(x_test)
            all_test_rows.extend(type_test)
            all_scores.extend(scores.tolist())
        predictions.extend(_prediction_rows(all_test_rows, np.array(all_scores), feature_names=names))
    return predictions


def _rate(hit: int, total: int) -> float:
    return hit / total if total else 0.0


def _segment_summary(rows: list[dict], field: str, min_races: int = 40) -> list[tuple[str, int, int, int]]:
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for row in rows:
        bucket = str(row.get(field) or "unknown")
        stats[bucket][0] += 1
        stats[bucket][1] += int(row["fav_hit"])
        stats[bucket][2] += int(row["line5_hit"])
    return sorted(
        ((name, vals[0], vals[1], vals[2]) for name, vals in stats.items() if vals[0] >= min_races),
        key=lambda item: (_rate(item[2], item[1]), -item[1], item[0]),
    )


def write_xgbranker_segment_report(min_train_months: int = 3) -> Path:
    predictions = collect_xgbranker_predictions(min_train_months=min_train_months)
    races = len(predictions)
    fav_hits = sum(int(row["fav_hit"]) for row in predictions)
    line5_hits = sum(int(row["line5_hit"]) for row in predictions)

    margins = sorted(float(row["score_margin"]) for row in predictions)
    thresholds = []
    for keep_pct in (10, 20, 30, 40, 50, 60, 70, 80):
        idx = max(0, min(len(margins) - 1, int(len(margins) * (100 - keep_pct) / 100)))
        thresholds.append((keep_pct, margins[idx]))

    report_path = REPORTS_DIR / "v3_ml_xgbranker_segment_raporu.md"
    lines = [
        "# Harbi Ganyan v3 XGBRanker Segment ve Guven Raporu",
        "",
        "Bu rapor AGF, ganyan, oran, bahis veya dis tahmin skoru kullanmaz.",
        "",
        "Not: Bu rapordaki filtreler ayni out-of-sample tahmin kayitlari uzerinden kesfedilen adaylardir; uretim kurali olmak icin ayri holdout dogrulamasi gerekir.",
        "",
        "## Genel",
        "",
        f"- Kosu: {races}",
        f"- Harbi Ganyan Favorisi: {fav_hits}/{races} ({_rate(fav_hits, races):.2%})",
        f"- 5'li satir: {line5_hits}/{races} ({_rate(line5_hits, races):.2%})",
        "",
        "## Guven Marji Filtreleri",
        "",
        "| Tutulan Kosu Dilimi | Esik | Kosu | Favori | 5'li |",
        "|---|---:|---:|---:|---:|",
    ]
    for keep_pct, threshold in thresholds:
        kept = [row for row in predictions if float(row["score_margin"]) >= threshold]
        total = len(kept)
        fav = sum(int(row["fav_hit"]) for row in kept)
        top5 = sum(int(row["line5_hit"]) for row in kept)
        lines.append(f"| En guvenli %{keep_pct} | {threshold:.6f} | {total} | {fav}/{total} ({_rate(fav, total):.2%}) | {top5}/{total} ({_rate(top5, total):.2%}) |")

    segment_fields = [
        ("race_type", "Kosu Tipi"),
        ("track", "Pist"),
        ("distance_bucket", "Mesafe"),
        ("field_bucket", "Saha Boyutu"),
        ("hip", "Hipodrom"),
        ("confidence_bucket", "Favori Gecmis Guveni"),
        ("month", "Ay"),
    ]
    for field, title in segment_fields:
        lines.extend(["", f"## {title}", "", "| Segment | Kosu | Favori | 5'li |", "|---|---:|---:|---:|"])
        for name, total, fav, top5 in _segment_summary(predictions, field):
            lines.append(f"| {name} | {total} | {fav}/{total} ({_rate(fav, total):.2%}) | {top5}/{total} ({_rate(top5, total):.2%}) |")

    candidates = []
    for keep_pct, threshold in thresholds:
        for max_runner in (7, 10, 13, 16, 99):
            for require_history in (False, True):
                for race_type in ("any", "sartli", "kv_grup", "maiden", "handikap"):
                    kept = [
                        row for row in predictions
                        if float(row["score_margin"]) >= threshold
                        and int(row["runner_count"]) <= max_runner
                        and (not require_history or row["confidence_bucket"] != "00_no_history")
                        and (race_type == "any" or row["race_type"] == race_type)
                    ]
                    total = len(kept)
                    if total < 250:
                        continue
                    fav = sum(int(row["fav_hit"]) for row in kept)
                    top5 = sum(int(row["line5_hit"]) for row in kept)
                    candidates.append((_rate(fav, total), total, keep_pct, threshold, max_runner, require_history, race_type, fav, top5))
    candidates.sort(key=lambda item: (-item[0], -item[1]))
    lines.extend([
        "",
        "## %35 Hedefi Icin Aday Filtreler",
        "",
        "| Favori Orani | Kosu | Filtre | Favori | 5'li |",
        "|---:|---:|---|---:|---:|",
    ])
    for rate, total, keep_pct, threshold, max_runner, require_history, race_type, fav, top5 in candidates[:30]:
        filt = f"guvenli %{keep_pct}, margin>={threshold:.6f}, runner<={max_runner}"
        if require_history:
            filt += ", gecmissiz favori yok"
        if race_type != "any":
            filt += f", tip={race_type}"
        lines.append(f"| {rate:.2%} | {total} | {filt} | {fav}/{total} | {top5}/{total} ({_rate(top5, total):.2%}) |")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def write_pertype_confidence_policy_report(
    min_train_months: int = 3,
    min_calibration_months: int = 4,
    target_rate: float = 0.50,
    min_cal_races: int = 40,
    report_suffix: str = "_pertip",
    feature_names: list[str] | None = None,
    runner_max: int | None = None,
) -> Path:
    """
    Tip-bazlı sızıntısız güven politikası.

    Her ay, her koşu tipi için ayrı margin eşiği seçilir; eşik yalnızca o tipin
    önceki out-of-sample aylarındaki margin dağılımından gelir. Tek global
    target_rate kullanılır: bir tip kendi geçmişinde hedefi tutturuyorsa o ay
    emit edilir, tutturamıyorsa skip. Böylece kolay tipler (kv_grup, other)
    otomatik seçilir, zor tipler (handikap) elenir.
    """
    predictions = collect_xgbranker_predictions(
        min_train_months=min_train_months,
        feature_names=feature_names,
        per_type=True,
    )
    if runner_max is not None:
        predictions = [r for r in predictions if int(r["runner_count"]) <= runner_max]
    months = sorted({row["month"] for row in predictions})
    keep_pcts = (10, 15, 20, 30, 40, 50)
    race_types = sorted({row["race_type"] for row in predictions})

    type_totals: dict[str, dict] = defaultdict(lambda: {"races": 0, "fav": 0, "line5": 0})
    total_races = total_fav = total_line5 = 0
    month_rows: list[dict] = []

    for idx, month in enumerate(months):
        prior_months = months[:idx]
        if len(prior_months) < min_calibration_months:
            continue
        for rtype in race_types:
            calibration = [r for r in predictions if r["month"] in prior_months and r["race_type"] == rtype]
            current = [r for r in predictions if r["month"] == month and r["race_type"] == rtype]
            if not calibration or not current:
                continue
            margins = sorted(float(r["score_margin"]) for r in calibration)
            candidates = []
            for keep_pct in keep_pcts:
                thr_idx = max(0, min(len(margins) - 1, int(len(margins) * (100 - keep_pct) / 100)))
                threshold = margins[thr_idx]
                cal_kept = [r for r in calibration if float(r["score_margin"]) >= threshold]
                cal_total = len(cal_kept)
                cal_fav = sum(int(r["fav_hit"]) for r in cal_kept)
                cal_rate = _rate(cal_fav, cal_total)
                if cal_total >= min_cal_races and cal_rate >= target_rate:
                    candidates.append((keep_pct, threshold, cal_total, cal_fav, cal_rate))
            if not candidates:
                continue
            keep_pct, threshold, cal_total, cal_fav, cal_rate = max(candidates, key=lambda it: it[0])
            kept = [r for r in current if float(r["score_margin"]) >= threshold]
            races = len(kept)
            if races == 0:
                continue
            fav = sum(int(r["fav_hit"]) for r in kept)
            line5 = sum(int(r["line5_hit"]) for r in kept)
            total_races += races
            total_fav += fav
            total_line5 += line5
            type_totals[rtype]["races"] += races
            type_totals[rtype]["fav"] += fav
            type_totals[rtype]["line5"] += line5
            month_rows.append({
                "month": month, "race_type": rtype, "keep_pct": keep_pct,
                "threshold": threshold, "cal_rate": cal_rate,
                "races": races, "fav": fav, "line5": line5,
            })

    report_path = REPORTS_DIR / f"v3_ml_xgbranker_confidence_policy{report_suffix}_raporu.md"
    lines = [
        "# Harbi Ganyan v3 Tip-Bazlı Sızıntısız Güven Politikası Raporu",
        "",
        "Bu rapor AGF, ganyan, oran, bahis veya dis tahmin skoru kullanmaz.",
        "",
        "Kural: Her ay her koşu tipi için marj eşiği yalnızca o tipin önceki",
        "out-of-sample aylarından seçilir. Tek global hedef; tutturamayan tip o ay skip.",
        "",
        "## Ozet",
        "",
        f"- Hedef favori orani: {target_rate:.2%}",
        f"- Tahmin verilen kosu: {total_races}",
        f"- Harbi Ganyan Favorisi: {total_fav}/{total_races} ({_rate(total_fav, total_races):.2%})",
        f"- 5'li satir: {total_line5}/{total_races} ({_rate(total_line5, total_races):.2%})",
        "",
        "## Koşu Tipi Kırılımı",
        "",
        "| Tip | Kosu | Favori | 5'li |",
        "|---|---:|---:|---:|",
    ]
    for rtype in sorted(type_totals, key=lambda t: -type_totals[t]["fav"] / max(type_totals[t]["races"], 1)):
        t = type_totals[rtype]
        lines.append(
            f"| {rtype} | {t['races']} | {t['fav']}/{t['races']} ({_rate(t['fav'], t['races']):.2%}) | "
            f"{t['line5']}/{t['races']} ({_rate(t['line5'], t['races']):.2%}) |"
        )
    lines.extend(["", "## Aylık-Tip Politika Sonuçları", "",
                  "| Ay | Tip | Dilim | Kalib. | Kosu | Favori | 5'li |",
                  "|---|---|---:|---:|---:|---:|---:|"])
    for row in month_rows:
        lines.append(
            f"| {row['month']} | {row['race_type']} | %{row['keep_pct']} | {row['cal_rate']:.2%} | "
            f"{row['races']} | {row['fav']}/{row['races']} ({_rate(row['fav'], row['races']):.2%}) | "
            f"{row['line5']}/{row['races']} ({_rate(row['line5'], row['races']):.2%}) |"
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def write_xgbranker_confidence_policy_report(
    min_train_months: int = 3,
    min_calibration_months: int = 4,
    target_rate: float = 0.35,
    runner_max: int | None = None,
    report_suffix: str = "",
    feature_names: list[str] | None = None,
    per_type: bool = False,
) -> Path:
    predictions = collect_xgbranker_predictions(
        min_train_months=min_train_months,
        feature_names=feature_names,
        per_type=per_type,
    )
    if runner_max is not None:
        predictions = [row for row in predictions if int(row["runner_count"]) <= runner_max]
    months = sorted({row["month"] for row in predictions})
    keep_pcts = (10, 20, 30, 40, 50, 60, 70, 80)
    month_rows = []
    total_races = total_fav = total_line5 = 0

    for idx, month in enumerate(months):
        prior_months = months[:idx]
        if len(prior_months) < min_calibration_months:
            continue
        calibration = [row for row in predictions if row["month"] in prior_months]
        current = [row for row in predictions if row["month"] == month]
        if not calibration or not current:
            continue
        margins = sorted(float(row["score_margin"]) for row in calibration)
        candidates = []
        for keep_pct in keep_pcts:
            threshold_idx = max(0, min(len(margins) - 1, int(len(margins) * (100 - keep_pct) / 100)))
            threshold = margins[threshold_idx]
            cal_kept = [row for row in calibration if float(row["score_margin"]) >= threshold]
            cal_total = len(cal_kept)
            cal_fav = sum(int(row["fav_hit"]) for row in cal_kept)
            cal_rate = _rate(cal_fav, cal_total)
            if cal_total >= 200 and cal_rate >= target_rate:
                candidates.append((keep_pct, threshold, cal_total, cal_fav, cal_rate))
        if candidates:
            # Prefer the widest historical coverage that still met the target.
            keep_pct, threshold, cal_total, cal_fav, cal_rate = max(candidates, key=lambda item: item[0])
            decision = "emit"
            kept = [row for row in current if float(row["score_margin"]) >= threshold]
        else:
            keep_pct, threshold, cal_total, cal_fav, cal_rate = (0, 0.0, 0, 0, 0.0)
            decision = "skip"
            kept = []
        races = len(kept)
        fav = sum(int(row["fav_hit"]) for row in kept)
        line5 = sum(int(row["line5_hit"]) for row in kept)
        total_races += races
        total_fav += fav
        total_line5 += line5
        month_rows.append({
            "month": month,
            "decision": decision,
            "keep_pct": keep_pct,
            "threshold": threshold,
            "cal_total": cal_total,
            "cal_fav": cal_fav,
            "cal_rate": cal_rate,
            "races": races,
            "fav": fav,
            "line5": line5,
        })

    report_path = REPORTS_DIR / f"v3_ml_xgbranker_confidence_policy{report_suffix}_raporu.md"
    lines = [
        "# Harbi Ganyan v3 XGBRanker Sizintisiz Guven Politikasi Raporu",
        "",
        "Bu rapor AGF, ganyan, oran, bahis veya dis tahmin skoru kullanmaz.",
        "",
        "Kural: Her ay icin marj esigi yalnizca onceki out-of-sample aylarin tahmin kayitlarindan secilir; ayni ayin sonucu esik seciminde kullanilmaz.",
        "",
        "## Ozet",
        "",
        f"- Hedef favori orani: {target_rate:.2%}",
        f"- Kalibrasyon baslangici: {min_calibration_months} onceki test ayi",
        f"- Tahmin verilen kosu: {total_races}",
        f"- Harbi Ganyan Favorisi: {total_fav}/{total_races} ({_rate(total_fav, total_races):.2%})",
        f"- 5'li satir: {total_line5}/{total_races} ({_rate(total_line5, total_races):.2%})",
        "",
        "## Aylik Politika Sonuclari",
        "",
        "| Ay | Karar | Secilen Dilim | Kalibrasyon | Kosu | Favori | 5'li |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in month_rows:
        cal = f"{row['cal_fav']}/{row['cal_total']} ({row['cal_rate']:.2%})" if row["cal_total"] else "-"
        selected = f"%{row['keep_pct']} / {row['threshold']:.6f}" if row["decision"] == "emit" else "-"
        races = row["races"]
        fav = row["fav"]
        line5 = row["line5"]
        lines.append(
            f"| {row['month']} | {row['decision']} | {selected} | {cal} | {races} | "
            f"{fav}/{races} ({_rate(fav, races):.2%}) | {line5}/{races} ({_rate(line5, races):.2%}) |"
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
