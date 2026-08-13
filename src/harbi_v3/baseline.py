from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

from .features import FEATURE_NAMES, HistoryMemory, build_memory_before, feature_rows_for_day
from .leakage import audit_feature_names, write_audit
from .paths import AUDIT_DIR, REPORTS_DIR, ensure_dirs
from .records import parse_results


BASELINE_WEIGHTS = {
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
}


def score_features(features: dict[str, float]) -> float:
    return sum(float(features.get(name, 0.0) or 0.0) * weight for name, weight in BASELINE_WEIGHTS.items())


def score_day(day: date, memory: HistoryMemory | None = None) -> list[dict]:
    ensure_dirs()
    audit = audit_feature_names(FEATURE_NAMES)
    write_audit(AUDIT_DIR / "baseline_feature_audit.json", audit)
    audit.raise_if_failed()
    memory = memory or build_memory_before(day)
    rows = feature_rows_for_day(day, memory)
    for row in rows:
        row["baseline_score"] = round(score_features(row["features"]), 6)
    return rows


def rank_day(day: date, memory: HistoryMemory | None = None) -> dict[tuple[str, int], list[dict]]:
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in score_day(day, memory):
        grouped[(row["hip"], int(row["race_no"]))].append(row)
    for key in list(grouped):
        grouped[key].sort(key=lambda r: (-r["baseline_score"], r["horse_no"]))
    return dict(grouped)


def evaluate_day(day: date, memory: HistoryMemory | None = None) -> dict:
    ranked = rank_day(day, memory)
    results = parse_results(day)
    races = 0
    fav_hits = 0
    line5_hits = 0
    skipped = 0
    examples = []
    for key, order in ranked.items():
        result = results.get(key)
        if not result or not order:
            skipped += 1
            continue
        races += 1
        top5 = [row["horse_no"] for row in order[:5]]
        favorite = top5[0]
        fav_hit = favorite == result.winner_no
        line_hit = result.winner_no in top5
        fav_hits += int(fav_hit)
        line5_hits += int(line_hit)
        examples.append({
            "hip": key[0],
            "race_no": key[1],
            "favorite": favorite,
            "top5": top5,
            "actual": result.winner_no,
            "favorite_hit": fav_hit,
            "line5_hit": line_hit,
        })
    return {
        "date": f"{day:%Y-%m-%d}",
        "races": races,
        "skipped": skipped,
        "favorite_hits": fav_hits,
        "line5_hits": line5_hits,
        "favorite_hit_rate": fav_hits / races if races else 0.0,
        "line5_hit_rate": line5_hits / races if races else 0.0,
        "examples": examples,
    }


def write_baseline_report(day: date, report_path: Path | None = None) -> Path:
    ensure_dirs()
    result = evaluate_day(day)
    report_path = report_path or REPORTS_DIR / f"baseline_{day:%Y-%m-%d}.md"
    lines = [
        f"# V3 Baseline Raporu - {day:%Y-%m-%d}",
        "",
        "Bu rapor AGF, ganyan, oran, bahis veya dis tahmin skoru kullanmaz.",
        "",
        f"- Kosu: {result['races']}",
        f"- Atlanan: {result['skipped']}",
        f"- Harbi Ganyan Favorisi: {result['favorite_hits']}/{result['races']} ({result['favorite_hit_rate']:.2%})",
        f"- 5'li satir: {result['line5_hits']}/{result['races']} ({result['line5_hit_rate']:.2%})",
        "",
        "| Hip | Kosu | Favori | Ilk 5 | Gercek | FAV | 5LI |",
        "|---|---:|---:|---|---:|---:|---:|",
    ]
    for ex in result["examples"]:
        lines.append(
            f"| {ex['hip']} | {ex['race_no']} | {ex['favorite']} | "
            f"{'-'.join(str(x) for x in ex['top5'])} | {ex['actual']} | "
            f"{'1' if ex['favorite_hit'] else '0'} | {'1' if ex['line5_hit'] else '0'} |"
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
