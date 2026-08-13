from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .baseline import rank_day
from .features import HistoryMemory
from .records import HorseProgram, available_program_dates, distance_bucket, parse_program_horses, parse_results
from .paths import REPORTS_DIR, ensure_dirs


@dataclass
class SegmentStat:
    races: int = 0
    fav_hits: int = 0
    line5_hits: int = 0

    def add(self, fav_hit: bool, line5_hit: bool) -> None:
        self.races += 1
        self.fav_hits += int(fav_hit)
        self.line5_hits += int(line5_hit)

    @property
    def fav_rate(self) -> float:
        return self.fav_hits / self.races if self.races else 0.0

    @property
    def line5_rate(self) -> float:
        return self.line5_hits / self.races if self.races else 0.0


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
    t = (track or "").strip().lower()
    if "çim" in t or "cim" in t:
        return "cim"
    if "kum" in t:
        return "kum"
    if "sentetik" in t:
        return "sentetik"
    return t or "unknown"


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


def _confidence_bucket(favorite_row: dict) -> str:
    starts = float((favorite_row.get("features") or {}).get("horse_starts_past", 0.0) or 0.0)
    if starts <= 0:
        return "00_no_history"
    if starts <= 2:
        return "01_low_history"
    if starts <= 5:
        return "02_mid_history"
    return "03_high_history"


def collect_baseline_race_rows(start: date | None = None, end: date | None = None) -> list[dict]:
    dates = available_program_dates()
    if start:
        dates = [d for d in dates if d >= start]
    if end:
        dates = [d for d in dates if d <= end]

    memory = HistoryMemory()
    rows: list[dict] = []
    for day in dates:
        programs = parse_program_horses(day)
        results = parse_results(day)
        ranked = rank_day(day, memory)
        for key, order in ranked.items():
            result = results.get(key)
            horses = programs.get(key) or []
            if not result or not order or not horses:
                continue
            meta: HorseProgram = horses[0]
            top5 = [row["horse_no"] for row in order[:5]]
            favorite = order[0]
            rows.append({
                "date": f"{day:%Y-%m-%d}",
                "month": f"{day:%Y-%m}",
                "hip": key[0],
                "race_no": key[1],
                "track": _track_bucket(meta.race_track),
                "distance": meta.race_distance,
                "distance_bucket": distance_bucket(meta.race_distance),
                "race_type": _race_type_bucket(meta.race_type, meta.race_group),
                "field_bucket": _field_bucket(len(horses)),
                "runner_count": len(horses),
                "favorite_no": favorite["horse_no"],
                "winner_no": result.winner_no,
                "fav_hit": favorite["horse_no"] == result.winner_no,
                "line5_hit": result.winner_no in top5,
                "confidence_bucket": _confidence_bucket(favorite),
                "favorite_score": favorite.get("baseline_score", 0.0),
            })
        for key, race_result in results.items():
            horses = programs.get(key)
            if horses:
                memory.update_race(horses, race_result.order_by_no)
    return rows


def _segment_table(rows: list[dict], field: str, min_races: int = 40) -> list[tuple[str, SegmentStat]]:
    stats: dict[str, SegmentStat] = defaultdict(SegmentStat)
    for row in rows:
        stats[str(row.get(field) or "unknown")].add(row["fav_hit"], row["line5_hit"])
    return sorted(
        ((name, stat) for name, stat in stats.items() if stat.races >= min_races),
        key=lambda item: (item[1].fav_rate, -item[1].races, item[0]),
    )


def write_segment_report(start: date | None = None, end: date | None = None) -> Path:
    ensure_dirs()
    rows = collect_baseline_race_rows(start, end)
    total = SegmentStat()
    for row in rows:
        total.add(row["fav_hit"], row["line5_hit"])

    report_path = REPORTS_DIR / "v3_segment_zayiflik_raporu.md"
    lines = [
        "# Harbi Ganyan v3 Segment Zayiflik Raporu",
        "",
        "Bu rapor AGF, ganyan, oran, bahis veya dis tahmin skoru kullanmaz.",
        "",
        "## Genel",
        "",
        f"- Kosu: {total.races}",
        f"- Harbi Ganyan Favorisi: {total.fav_hits}/{total.races} ({total.fav_rate:.2%})",
        f"- 5'li satir: {total.line5_hits}/{total.races} ({total.line5_rate:.2%})",
        "",
    ]

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
        lines.extend([
            f"## {title}",
            "",
            "| Segment | Kosu | Favori | 5'li |",
            "|---|---:|---:|---:|",
        ])
        for name, stat in _segment_table(rows, field):
            lines.append(
                f"| {name} | {stat.races} | {stat.fav_hits}/{stat.races} ({stat.fav_rate:.2%}) | "
                f"{stat.line5_hits}/{stat.races} ({stat.line5_rate:.2%}) |"
            )
        lines.append("")

    weak = []
    for field, title in segment_fields[:-1]:
        for name, stat in _segment_table(rows, field):
            weak.append((stat.fav_rate, stat.races, title, name, stat))
    weak.sort(key=lambda x: (x[0], -x[1]))
    lines.extend([
        "## En Zayif 20 Segment",
        "",
        "| Kirilim | Segment | Kosu | Favori | 5'li |",
        "|---|---|---:|---:|---:|",
    ])
    for _, _, title, name, stat in weak[:20]:
        lines.append(
            f"| {title} | {name} | {stat.races} | {stat.fav_hits}/{stat.races} ({stat.fav_rate:.2%}) | "
            f"{stat.line5_hits}/{stat.races} ({stat.line5_rate:.2%}) |"
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path

