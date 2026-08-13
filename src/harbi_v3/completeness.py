from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .dates import iter_dates
from .paths import PROGRAM_RAW_DIR, REPORTS_DIR, RESULTS_RAW_DIR, ensure_dirs


def check_completeness(start: date, end: date, program_dir: Path = PROGRAM_RAW_DIR, results_dir: Path = RESULTS_RAW_DIR) -> dict:
    rows = []
    for day in iter_dates(start, end):
        program_ok = (program_dir / f"{day:%Y-%m-%d}.json").exists()
        result_ok = (results_dir / f"{day:%Y-%m-%d}.json").exists()
        rows.append({
            "date": f"{day:%Y-%m-%d}",
            "program": program_ok,
            "results": result_ok,
            "complete": program_ok and result_ok,
        })
    return {
        "start": f"{start:%Y-%m-%d}",
        "end": f"{end:%Y-%m-%d}",
        "days": len(rows),
        "complete_days": sum(1 for r in rows if r["complete"]),
        "program_days": sum(1 for r in rows if r["program"]),
        "result_days": sum(1 for r in rows if r["results"]),
        "missing": [r for r in rows if not r["complete"]],
        "rows": rows,
    }


def write_completeness_report(start: date, end: date) -> Path:
    ensure_dirs()
    status = check_completeness(start, end)
    path = REPORTS_DIR / "v3_data_completeness.md"
    lines = [
        "# Harbi Ganyan v3 Veri Tamamlik Raporu",
        "",
        f"- Aralik: {status['start']} -> {status['end']}",
        f"- Gun: {status['days']}",
        f"- Program snapshot: {status['program_days']}/{status['days']}",
        f"- Sonuc snapshot: {status['result_days']}/{status['days']}",
        f"- Tam gun: {status['complete_days']}/{status['days']}",
        "",
        "## Eksik Gunler",
        "",
        "| Tarih | Program | Sonuc |",
        "|---|---:|---:|",
    ]
    for row in status["missing"][:300]:
        lines.append(
            f"| {row['date']} | {'1' if row['program'] else '0'} | {'1' if row['results'] else '0'} |"
        )
    if len(status["missing"]) > 300:
        lines.append(f"| ... | ... | ... |")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def lab_window_ending(end: date, warmup_months: int = 12, test_months: int = 4) -> tuple[date, date]:
    # Conservative 31-day month approximation for collection windows.
    days = (warmup_months + test_months) * 31
    return end - timedelta(days=days), end

