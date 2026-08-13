# -*- coding: utf-8 -*-
"""
analiz_backtest.py — Detaylı Analiz Puanı Backtest Raporu.

Kullanım:
    python analiz_backtest.py                          # 24.09.2025 -> bugun
    python analiz_backtest.py 2026-01-01 2026-06-01    # aralik

Rapor: reports/analiz_backtest_raporu.md
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from harbi_v3.features import HistoryMemory, feature_rows_for_day, add_intrarace_ranks
from harbi_v3.bulletin import inject_bulletin_rows
from harbi_v3.confidence import race_type_bucket
from harbi_v3.dates import parse_date
from harbi_v3.normalize import norm_text
from harbi_v3.records import available_program_dates, load_program_day, parse_results, parse_program_horses


def _field_bucket(n: int) -> str:
    if n <= 7:   return "1-7 at"
    if n <= 10:  return "8-10 at"
    if n <= 13:  return "11-13 at"
    return "14+ at"


def run_backtest(start_date: date, end_date: date) -> dict:
    memory = HistoryMemory()
    all_dates = sorted(available_program_dates())
    target_dates = [d for d in all_dates if start_date <= d <= end_date]

    # İstatistik yapıları
    rank_stats: dict[tuple[str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    rank_total: dict[tuple[str, str], int] = defaultdict(int)
    city_stats: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    city_total: dict[str, int] = defaultdict(int)
    jockey_by_rate: dict[str, list[bool]] = defaultdict(list)
    fav_miss_ranks: list[int] = []
    surprise_by_type: dict[str, list[int]] = defaultdict(list)
    total_races = 0

    print(f"{len(target_dates)} gun taranıyor...")

    for di, day in enumerate(target_dates):
        if di % 20 == 0:
            print(f"  {day} ({di + 1}/{len(target_dates)})")

        program_data = load_program_day(day)
        results = parse_results(day)
        if not results:
            continue

        day_rows = feature_rows_for_day(day, memory)
        inject_bulletin_rows(day_rows, day)
        add_intrarace_ranks(day_rows)

        # Hipodrom -> kosu -> atlar
        race_groups: dict[tuple, list] = defaultdict(list)
        for row in day_rows:
            key = (row["hip"], int(row["race_no"]))
            race_groups[key].append(row)

        # Program'dan koşu tipi oku
        type_map: dict[tuple[str, int], str] = {}
        for hip_name, hip_data in (program_data.get("hippodromes") or {}).items():
            hip_norm = norm_text(hip_name)
            for race in (hip_data.get("details") or {}).get("races") or []:
                rno = int(str(race.get("number") or "0").strip() or "0")
                if rno > 0:
                    rt = str(race.get("typeDescription") or "").strip()
                    rg = str(race.get("groupName") or race.get("name") or "").strip()
                    type_map[(hip_norm, rno)] = race_type_bucket(rt, rg)

        for (hip, race_no), rows in race_groups.items():
            result = results.get((hip, race_no))
            if not result or len(rows) < 2:
                continue

            total_races += 1
            bucket = type_map.get((hip, race_no), "other")
            field_b = _field_bucket(len(rows))
            tf_key = (bucket, field_b)

            # Analiz puanı proxy'si: horse_top3_rate_past
            ranked = sorted(rows, key=lambda r: float(r["features"].get("horse_top3_rate_past", 0) or 0), reverse=True)
            winner_rank = next((i + 1 for i, r in enumerate(ranked)
                                if int(r["horse_no"]) == result.winner_no), 99)

            rank_stats[tf_key][winner_rank] += 1
            rank_total[tf_key] += 1
            city_stats[hip][winner_rank] += 1
            city_total[hip] += 1

            # Jokey analizi
            fav_jr = float(ranked[0]["features"].get("jockey_win_rate_past", 0) or 0)
            jockey_by_rate[f"{int(fav_jr * 100 // 5) * 5}%"].append(winner_rank == 1)

            if winner_rank > 1:
                fav_miss_ranks.append(winner_rank)
                surprise_by_type[bucket].append(winner_rank)

        programs = parse_program_horses(day)
        for key, race_result in results.items():
            horses = programs.get(key)
            if horses:
                memory.update_race(horses, race_result.order_by_no, race_result.time_by_no)

    return {
        "total_races": total_races,
        "total_days": len(target_dates),
        "rank_stats": dict(rank_stats),
        "rank_total": dict(rank_total),
        "city_stats": dict(city_stats),
        "city_total": dict(city_total),
        "jockey_by_rate": dict(jockey_by_rate),
        "fav_miss_ranks": fav_miss_ranks,
        "surprise_by_type": dict(surprise_by_type),
    }


def _pct(n: int, t: int) -> str:
    return f"{n / t * 100:5.1f}%" if t > 0 else "    -"


def _generate_report(r: dict, start: date, end: date) -> str:
    L = []
    L.append(f"# Analiz Puani Backtest Raporu")
    L.append(f"**Tarih:** {start:%d.%m.%Y} - {end:%d.%m.%Y}  |  **Kosu:** {r['total_races']}  |  **Gun:** {r['total_days']}")
    L.append("")

    # ── A) Sıra × Tip × At Sayısı ──
    L.append("## A) Sira x Kosu Tipi x At Sayisi Kirilimi")
    L.append("")
    L.append("| Kosu Tipi | At Sayisi | 1.sira | 2.sira | 3.sira | 4-5.sira | 6+.sira | Toplam |")
    L.append("|-----------|----------|--------|--------|--------|----------|---------|--------|")
    for key in sorted(r["rank_stats"].keys()):
        st = r["rank_stats"][key]
        t = r["rank_total"][key]
        if t < 5: continue
        r1, r2, r3 = st.get(1, 0), st.get(2, 0), st.get(3, 0)
        r45 = sum(st.get(k, 0) for k in [4, 5])
        r6p = sum(st.get(k, 0) for k in range(6, 100))
        L.append(f"| {key[0]:<9s} | {key[1]:<8s} | {_pct(r1,t)} | {_pct(r2,t)} | {_pct(r3,t)} | {_pct(r45,t)} | {_pct(r6p,t)} | {t} |")
    L.append("")

    # ── Şehir kırılımı ──
    L.append("## Sehir Bazli FAV Isabeti")
    L.append("")
    L.append("| Sehir | 1.sira | Toplam | FAV % |")
    L.append("|-------|--------|--------|-------|")
    for city in sorted(r["city_stats"].keys()):
        st = r["city_stats"][city]
        t = r["city_total"][city]
        r1 = st.get(1, 0)
        L.append(f"| {city:<14s} | {r1:6d} | {t:6d} | {_pct(r1,t)} |")
    L.append("")

    # ── B) Jokey ──
    L.append("## B) Jokey Win Rate vs FAV Isabeti")
    L.append("")
    L.append("| Jokey WR | Kosu | FAV Kazanma % |")
    L.append("|----------|------|---------------|")
    for bucket in sorted(r["jockey_by_rate"].keys(), key=lambda x: int(x.replace("%", ""))):
        outcomes = r["jockey_by_rate"][bucket]
        if len(outcomes) < 10: continue
        L.append(f"| {bucket:<8s} | {len(outcomes):4d} | {_pct(sum(outcomes), len(outcomes))} |")
    L.append("")

    # ── C) Eksik Tahmin ──
    L.append("## C) FAV Kaybedince Kazananin Sirasi")
    L.append("")
    fmr = r["fav_miss_ranks"]
    if fmr:
        L.append(f"- FAV kaybettigi kosu: **{len(fmr)}** ({len(fmr)/r['total_races']*100:.1f}%)")
        L.append(f"- Kazanan ortalama sira: **{np.mean(fmr):.1f}**")
        L.append("")
        L.append("| Kazanan Sirasi | Adet | % |")
        L.append("|---------------|------|---|")
        from collections import Counter
        for rank, count in sorted(Counter(fmr).items()):
            L.append(f"| {rank}. sira | {count:4d} | {_pct(count, len(fmr))} |")
    L.append("")

    # ── D) Sürprizli tipler ──
    L.append("## D) En Surprizli Kosu Tipleri (FAV disi kazanan %)")
    L.append("")
    L.append("| Kosu Tipi | Toplam | FAV disi | % |")
    L.append("|-----------|--------|----------|---|")
    for bucket in sorted(r["surprise_by_type"].keys()):
        ranks = r["surprise_by_type"][bucket]
        total_t = sum(r["rank_total"].get((bucket, fb), 0) for fb in
                      ["1-7 at", "8-10 at", "11-13 at", "14+ at"])
        if total_t > 0:
            L.append(f"| {bucket:<9s} | {total_t:6d} | {len(ranks):8d} | {_pct(len(ranks), total_t)} |")

    return "\n".join(L)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) >= 2:
        s, e = parse_date(args[0]), parse_date(args[1])
    elif len(args) == 1:
        s, e = parse_date(args[0]), date.today()
    else:
        s, e = parse_date("2025-09-24"), date.today()

    print(f"Backtest: {s} -> {e}")
    r = run_backtest(s, e)
    report = _generate_report(r, s, e)

    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "analiz_backtest_raporu.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"Rapor: {out_path}")
    print(f"Kosu: {r['total_races']}, Gun: {r['total_days']}")
    if r["total_races"] > 0:
        r1_total = sum(st.get(1, 0) for st in r["rank_stats"].values())
        print(f"Genel FAV: {r1_total}/{r['total_races']} = {r1_total/r['total_races']*100:.1f}%")
    print(report[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
