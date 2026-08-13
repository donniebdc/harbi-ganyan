from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .features import HistoryMemory, feature_rows_for_day
from .leakage import audit_feature_names, write_audit
from .paths import AUDIT_DIR, REPORTS_DIR, ensure_dirs
from .records import HorseProgram, available_program_dates, distance_bucket, parse_program_horses, parse_results


@dataclass(frozen=True)
class Strategy:
    name: str
    weights: dict[str, float]
    no_history_penalty: float = 0.0
    big_field_penalty: float = 0.0
    handikap_penalty: float = 0.0
    prefer_recent: bool = False


STRATEGIES = [
    Strategy(
        name="baseline_current",
        weights={
            "horse_win_rate_past": 28.0,
            "horse_top3_rate_past": 15.0,
            "horse_avg_rank_inv_past": 10.0,
            "horse_track_win_rate_past": 12.0,
            "horse_distance_win_rate_past": 10.0,
            "jockey_win_rate_past": 8.0,
            "trainer_win_rate_past": 6.0,
            "jockey_horse_win_rate_past": 8.0,
            "trainer_jockey_win_rate_past": 3.0,
            "equipment_win_rate_past": 4.0,
            "last6_win_count": 2.5,
            "last6_top3_count": 1.0,
            "last6_avg_place_inv": 8.0,
            "handicap": 0.05,
            "kgs": 0.10,
        },
    ),
    Strategy(
        name="winner_heavy",
        weights={
            "horse_win_rate_past": 45.0,
            "horse_track_win_rate_past": 18.0,
            "horse_distance_win_rate_past": 16.0,
            "jockey_win_rate_past": 12.0,
            "trainer_win_rate_past": 8.0,
            "jockey_horse_win_rate_past": 10.0,
            "last6_win_count": 5.0,
            "last6_avg_place_inv": 6.0,
            "handicap": 0.04,
            "kgs": 0.08,
        },
    ),
    Strategy(
        name="recent_form_heavy",
        weights={
            "last6_win_count": 9.0,
            "last6_top3_count": 4.0,
            "last6_avg_place_inv": 28.0,
            "horse_top3_rate_past": 18.0,
            "horse_win_rate_past": 18.0,
            "jockey_win_rate_past": 8.0,
            "trainer_win_rate_past": 6.0,
            "handicap": 0.05,
        },
        prefer_recent=True,
    ),
    Strategy(
        name="relationship_heavy",
        weights={
            "jockey_horse_win_rate_past": 28.0,
            "trainer_jockey_win_rate_past": 18.0,
            "jockey_win_rate_past": 16.0,
            "trainer_win_rate_past": 12.0,
            "horse_win_rate_past": 18.0,
            "horse_track_win_rate_past": 10.0,
            "last6_avg_place_inv": 8.0,
        },
    ),
    Strategy(
        name="no_history_guard",
        weights={
            "horse_win_rate_past": 32.0,
            "horse_top3_rate_past": 18.0,
            "horse_avg_rank_inv_past": 12.0,
            "horse_track_win_rate_past": 14.0,
            "horse_distance_win_rate_past": 12.0,
            "jockey_win_rate_past": 12.0,
            "trainer_win_rate_past": 8.0,
            "last6_win_count": 4.0,
            "last6_avg_place_inv": 10.0,
            "handicap": 0.05,
        },
        no_history_penalty=12.0,
    ),
    Strategy(
        name="big_field_guard",
        weights={
            "horse_win_rate_past": 34.0,
            "horse_top3_rate_past": 18.0,
            "horse_track_win_rate_past": 16.0,
            "horse_distance_win_rate_past": 14.0,
            "jockey_win_rate_past": 12.0,
            "trainer_win_rate_past": 8.0,
            "last6_win_count": 4.0,
            "last6_avg_place_inv": 10.0,
            "handicap": 0.05,
        },
        no_history_penalty=8.0,
        big_field_penalty=5.0,
        handikap_penalty=4.0,
    ),
]


def _score(features: dict[str, float], strategy: Strategy) -> float:
    score = sum(float(features.get(name, 0.0) or 0.0) * weight for name, weight in strategy.weights.items())
    starts = float(features.get("horse_starts_past", 0.0) or 0.0)
    runners = float(features.get("runner_count", 0.0) or 0.0)
    if starts <= 0:
        score -= strategy.no_history_penalty
    if runners >= 14:
        score -= strategy.big_field_penalty
    return score


def _eval_day(day: date, memory: HistoryMemory, strategies: list[Strategy]) -> dict[str, dict]:
    rows = feature_rows_for_day(day, memory)
    results = parse_results(day)
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["hip"], int(row["race_no"]))].append(row)

    out = {
        s.name: {"races": 0, "fav_hits": 0, "line5_hits": 0, "skipped": 0}
        for s in strategies
    }
    for key, race_rows in grouped.items():
        result = results.get(key)
        if not result:
            for val in out.values():
                val["skipped"] += 1
            continue
        for strategy in strategies:
            scored = []
            for row in race_rows:
                scored.append((_score(row["features"], strategy), row["horse_no"]))
            scored.sort(key=lambda item: (-item[0], item[1]))
            top5 = [horse_no for _, horse_no in scored[:5]]
            out[strategy.name]["races"] += 1
            out[strategy.name]["fav_hits"] += int(top5[0] == result.winner_no)
            out[strategy.name]["line5_hits"] += int(result.winner_no in top5)
    return out


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


def _race_type_bucket(race_type: str, race_group: str) -> str:
    text = f"{race_type} {race_group}".lower()
    if "handikap" in text:
        return "handikap"
    if "maiden" in text:
        return "maiden"
    if "şart" in text or "sart" in text:
        return "sartli"
    if "kv" in text or "grup" in text or "g1" in text or "g2" in text or "g3" in text:
        return "kv_grup"
    return "other"


def _segment_keys(horses: list[HorseProgram]) -> list[tuple[str, str]]:
    if not horses:
        return []
    meta = horses[0]
    return [
        ("field", _field_bucket(len(horses))),
        ("race_type", _race_type_bucket(meta.race_type, meta.race_group)),
        ("distance", distance_bucket(meta.race_distance)),
        ("hip", meta.hip),
    ]


def _rate(stat: dict) -> float:
    races = stat.get("races", 0)
    return stat.get("fav_hits", 0) / races if races else 0.0


def run_adaptive_strategy_search(report_path: Path | None = None) -> Path:
    ensure_dirs()
    all_feature_names = sorted({name for strategy in STRATEGIES for name in strategy.weights})
    all_feature_names.extend(["horse_starts_past", "runner_count"])
    audit = audit_feature_names(all_feature_names)
    write_audit(AUDIT_DIR / "adaptive_strategy_feature_audit.json", audit)
    audit.raise_if_failed()

    dates = available_program_dates()
    memory = HistoryMemory()
    global_perf = {s.name: {"races": 0, "fav_hits": 0, "line5_hits": 0} for s in STRATEGIES}
    segment_perf: dict[tuple[str, str, str], dict] = defaultdict(lambda: {"races": 0, "fav_hits": 0, "line5_hits": 0})
    adaptive = {"races": 0, "fav_hits": 0, "line5_hits": 0, "skipped": 0}
    oracle = {"races": 0, "fav_hits": 0, "line5_hits": 0, "skipped": 0}

    def choose_strategy(keys: list[tuple[str, str]]) -> Strategy:
        candidates = []
        for strategy in STRATEGIES:
            prior_stats = [segment_perf[(k[0], k[1], strategy.name)] for k in keys]
            enough = [s for s in prior_stats if s["races"] >= 40]
            if enough:
                races = sum(s["races"] for s in enough)
                hits = sum(s["fav_hits"] for s in enough)
                candidates.append((hits / races if races else 0.0, races, strategy.name, strategy))
            else:
                g = global_perf[strategy.name]
                candidates.append((_rate(g), g["races"], strategy.name, strategy))
        candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        return candidates[0][3]

    for day in dates:
        rows = feature_rows_for_day(day, memory)
        results = parse_results(day)
        programs = parse_program_horses(day)
        grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
        for row in rows:
            grouped[(row["hip"], int(row["race_no"]))].append(row)

        day_strategy_results = {}
        for key, race_rows in grouped.items():
            result = results.get(key)
            horses = programs.get(key) or []
            if not result or not horses:
                adaptive["skipped"] += 1
                oracle["skipped"] += 1
                continue
            keys = _segment_keys(horses)
            per_strategy = {}
            for strategy in STRATEGIES:
                scored = [(_score(row["features"], strategy), row["horse_no"]) for row in race_rows]
                scored.sort(key=lambda item: (-item[0], item[1]))
                top5 = [horse_no for _, horse_no in scored[:5]]
                per_strategy[strategy.name] = {
                    "favorite": top5[0],
                    "top5": top5,
                    "fav_hit": top5[0] == result.winner_no,
                    "line5_hit": result.winner_no in top5,
                }

            chosen = choose_strategy(keys)
            cres = per_strategy[chosen.name]
            adaptive["races"] += 1
            adaptive["fav_hits"] += int(cres["fav_hit"])
            adaptive["line5_hits"] += int(cres["line5_hit"])

            # Oracle is an upper-bound diagnostic across the currently tested strategy family.
            best_oracle = max(
                per_strategy.values(),
                key=lambda r: (int(r["fav_hit"]), int(r["line5_hit"])),
            )
            oracle["races"] += 1
            oracle["fav_hits"] += int(best_oracle["fav_hit"])
            oracle["line5_hits"] += int(best_oracle["line5_hit"])

            day_strategy_results[key] = (keys, per_strategy)

        # Update strategy performance only after the day was predicted.
        for key, (keys, per_strategy) in day_strategy_results.items():
            for strategy in STRATEGIES:
                res = per_strategy[strategy.name]
                gp = global_perf[strategy.name]
                gp["races"] += 1
                gp["fav_hits"] += int(res["fav_hit"])
                gp["line5_hits"] += int(res["line5_hit"])
                for seg_key in keys:
                    sp = segment_perf[(seg_key[0], seg_key[1], strategy.name)]
                    sp["races"] += 1
                    sp["fav_hits"] += int(res["fav_hit"])
                    sp["line5_hits"] += int(res["line5_hit"])

        for key, race_result in results.items():
            horses = programs.get(key)
            if horses:
                memory.update_race(horses, race_result.order_by_no)

    report_path = report_path or REPORTS_DIR / "v3_adaptive_strategy_raporu.md"

    def line(name: str, res: dict) -> str:
        races = res["races"]
        fav_rate = res["fav_hits"] / races if races else 0.0
        line5_rate = res["line5_hits"] / races if races else 0.0
        return f"| {name} | {races} | {res['fav_hits']}/{races} ({fav_rate:.2%}) | {res['line5_hits']}/{races} ({line5_rate:.2%}) | {res.get('skipped', 0)} |"

    rows = []
    for strategy in STRATEGIES:
        res = global_perf[strategy.name]
        races = res["races"]
        rows.append((res["fav_hits"] / races if races else 0.0, strategy.name, res))
    rows.sort(reverse=True)

    lines = [
        "# Harbi Ganyan v3 Adaptive Strategy Raporu",
        "",
        "Adaptive secim yalniz gecmis gunlerdeki segment performansini kullanir.",
        "Oracle satiri uretim adayi degildir; mevcut strateji ailesinin teorik ust sinirini gosterir.",
        "",
        "| Strateji | Kosu | Favori | 5'li | Atlanan |",
        "|---|---:|---:|---:|---:|",
        line("adaptive_past_segment", adaptive),
        line("oracle_strategy_family", oracle),
    ]
    for _, name, res in rows:
        lines.append(line(name, res))
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_strategy_search(start: date | None = None, end: date | None = None, report_path: Path | None = None) -> Path:
    ensure_dirs()
    all_feature_names = sorted({name for strategy in STRATEGIES for name in strategy.weights})
    all_feature_names.extend(["horse_starts_past", "runner_count"])
    audit = audit_feature_names(all_feature_names)
    write_audit(AUDIT_DIR / "strategy_search_feature_audit.json", audit)
    audit.raise_if_failed()

    dates = available_program_dates()
    if start:
        dates = [d for d in dates if d >= start]
    if end:
        dates = [d for d in dates if d <= end]

    totals = {
        s.name: {"races": 0, "fav_hits": 0, "line5_hits": 0, "skipped": 0}
        for s in STRATEGIES
    }
    memory = HistoryMemory()
    for day in dates:
        day_eval = _eval_day(day, memory, STRATEGIES)
        for name, res in day_eval.items():
            for key, value in res.items():
                totals[name][key] += value
        programs = parse_program_horses(day)
        results = parse_results(day)
        for key, race_result in results.items():
            horses = programs.get(key)
            if horses:
                memory.update_race(horses, race_result.order_by_no)

    rows = []
    for strategy in STRATEGIES:
        res = totals[strategy.name]
        races = res["races"]
        fav_rate = res["fav_hits"] / races if races else 0.0
        line5_rate = res["line5_hits"] / races if races else 0.0
        rows.append((fav_rate, line5_rate, strategy.name, res))
    rows.sort(reverse=True)

    report_path = report_path or REPORTS_DIR / "v3_strategy_search_raporu.md"
    lines = [
        "# Harbi Ganyan v3 Strategy Search Raporu",
        "",
        "Bu rapor AGF, ganyan, oran, bahis veya dis tahmin skoru kullanmaz.",
        "",
        "| Strateji | Kosu | Favori | 5'li | Atlanan |",
        "|---|---:|---:|---:|---:|",
    ]
    for fav_rate, line5_rate, name, res in rows:
        lines.append(
            f"| {name} | {res['races']} | {res['fav_hits']}/{res['races']} ({fav_rate:.2%}) | "
            f"{res['line5_hits']}/{res['races']} ({line5_rate:.2%}) | {res['skipped']} |"
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
