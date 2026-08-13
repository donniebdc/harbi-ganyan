from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .baseline import evaluate_day
from .features import HistoryMemory
from .leakage import audit_feature_names, write_audit
from .paths import AUDIT_DIR, REPORTS_DIR, ensure_dirs
from .records import available_program_dates, parse_program_horses, parse_results


BASELINE_FEATURES = [
    "horse_track_win_rate_past",
    "horse_distance_score_past",
    "horse_recent_form_past",
    "jockey_horse_synergy_past",
    "trainer_jockey_synergy_past",
    "equipment_change_score_past",
    "rest_days_bucket",
    "class_transition_score_past",
    "weight_delta",
    "age",
]


@dataclass
class LabConfig:
    warmup_months: int = 12
    test_months: int = 4
    seed: int = 20260612


def run_walkforward_stub(start: date | None = None, end: date | None = None) -> Path:
    """Create the first deterministic lab report skeleton.

    Feature engineering and models are intentionally not implemented in this
    scaffold. This function verifies the leakage gate and writes the official
    report shell that future model runs must fill.
    """
    ensure_dirs()
    audit = audit_feature_names(BASELINE_FEATURES)
    write_audit(AUDIT_DIR / "latest_leakage_audit.json", audit)
    audit.raise_if_failed()

    report_path = REPORTS_DIR / "v3_walkforward_raporu.md"
    lines = [
        "# Harbi Ganyan v3 Walk-Forward Raporu",
        "",
        "Durum: iskelet kuruldu; feature engineering ve model calismasi sonraki adimda doldurulacak.",
        "",
        "## Kilit Kurallar",
        "",
        "- AGF, ganyan, oran, bahis ve dis tahmin skorları yok.",
        "- Ana metrik: Harbi Ganyan Favorisi kazanma orani.",
        "- Ikinci metrik: 5'li satir basarisi.",
        "- Dogrulama: 12 ay warmup + son 4 ay strict walk-forward.",
        "- Leakage audit: PASS.",
        "",
        "## Planlanan Motorlar",
        "",
        "| Motor | Durum | Ana hedef |",
        "|---|---:|---|",
        "| Interpretable baseline | bekliyor | favori + 5'li satir |",
        "| Gradient boosting classifier | bekliyor | favori |",
        "| Ranking model | bekliyor | 5'li siralama |",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_baseline_walkforward(start: date | None = None, end: date | None = None) -> Path:
    ensure_dirs()
    audit = audit_feature_names(BASELINE_FEATURES)
    write_audit(AUDIT_DIR / "latest_leakage_audit.json", audit)
    audit.raise_if_failed()

    dates = available_program_dates()
    if start:
        dates = [d for d in dates if d >= start]
    if end:
        dates = [d for d in dates if d <= end]

    memory = HistoryMemory()
    day_results = []
    for day in dates:
        day_results.append(evaluate_day(day, memory))
        programs = parse_program_horses(day)
        results = parse_results(day)
        for key, race_result in results.items():
            horses = programs.get(key)
            if horses:
                memory.update_race(horses, race_result.order_by_no)
    races = sum(x["races"] for x in day_results)
    skipped = sum(x["skipped"] for x in day_results)
    fav_hits = sum(x["favorite_hits"] for x in day_results)
    line5_hits = sum(x["line5_hits"] for x in day_results)
    fav_rate = fav_hits / races if races else 0.0
    line5_rate = line5_hits / races if races else 0.0

    report_path = REPORTS_DIR / "v3_walkforward_raporu.md"
    lines = [
        "# Harbi Ganyan v3 Walk-Forward Raporu",
        "",
        "Durum: baseline walk-forward iskeleti calisiyor; ML challenger modelleri bekliyor.",
        "",
        "## Leakage Audit",
        "",
        "- Durum: PASS",
        "- AGF/ganyan/oran/bahis/dis tahmin skoru feature olarak kullanilmaz.",
        "- Her gunun baseline hafizasi sadece o gunden onceki ortak program+sonuc gunlerinden kurulur.",
        "",
        "## Ozet",
        "",
        f"- Gun sayisi: {len(day_results)}",
        f"- Kosu: {races}",
        f"- Atlanan: {skipped}",
        f"- Harbi Ganyan Favorisi: {fav_hits}/{races} ({fav_rate:.2%})",
        f"- 5'li satir: {line5_hits}/{races} ({line5_rate:.2%})",
        "",
        "## Gunluk Sonuclar",
        "",
        "| Tarih | Kosu | Atlanan | Favori | 5'li |",
        "|---|---:|---:|---:|---:|",
    ]
    for res in day_results:
        lines.append(
            f"| {res['date']} | {res['races']} | {res['skipped']} | "
            f"{res['favorite_hits']}/{res['races']} ({res['favorite_hit_rate']:.2%}) | "
            f"{res['line5_hits']}/{res['races']} ({res['line5_hit_rate']:.2%}) |"
        )
    lines.extend([
        "",
        "## Motor Durumlari",
        "",
        "| Motor | Durum | Ana hedef |",
        "|---|---:|---|",
        "| Interpretable baseline | aktif | favori + 5'li satir |",
        "| Gradient boosting classifier | bekliyor | favori |",
        "| Ranking model | bekliyor | 5'li siralama |",
        "",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
