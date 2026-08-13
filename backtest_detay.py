# -*- coding: utf-8 -*-
"""
backtest_detay.py — Model bazlı FAV ve 5'li satır kazanma analizi.
Export JSON'lardaki gerçek analiz puanı sıralamasını kullanır.

Kullanım:
    python backtest_detay.py                           # tum export'lar
    python backtest_detay.py 2026-06-01 2026-06-16     # aralik
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from harbi_v3.confidence import race_type_bucket
from harbi_v3.dates import parse_date
from harbi_v3.records import load_program_day, parse_results


def _field_bucket(n: int) -> str:
    if n <= 7:   return "1-7 at"
    if n <= 10:  return "8-10 at"
    if n <= 13:  return "11-13 at"
    return "14+ at"


def run():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    export_dir = ROOT / "data" / "export_out"
    if not export_dir.exists():
        print("export_out yok, once tahmin uretin.")
        return 1

    all_files = sorted(export_dir.glob("202?-*.json"))
    # Sadece birlesik dosyalar (sehir bazli degil)
    files = [f for f in all_files if not any(c in f.stem for c in ["ANKARA", "BURSA", "ELAZIG",
        "ISTANBUL", "IZMIR", "KOCAELI", "ADANA", "DIYARBAKIR", "SANLIURFA", "ANTALYA"])]

    if args:
        start, end = parse_date(args[0]), parse_date(args[1]) if len(args) > 1 else parse_date(args[0])
        files = [f for f in files if start <= parse_date(f.stem) <= end]

    print(f"{len(files)} export dosyasi taranıyor...")

    # İstatistikler
    fav_stats: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"kazandi": 0, "toplam": 0})
    besli_stats: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"kazandi": 0, "toplam": 0})
    fav_total = besli_total = 0
    fav_wins = besli_wins = 0

    for fp in files:
        try:
            export = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        day = parse_date(fp.stem)
        winners = parse_results(day)
        prog = load_program_day(day)

        # Kosu tipi haritasi
        type_map = {}
        for hip_name, hip_data in (prog.get("hippodromes") or {}).items():
            from harbi_v3.normalize import norm_text
            hn = norm_text(hip_name)
            for race in (hip_data.get("details") or {}).get("races") or []:
                rno = int(str(race.get("number") or "0").strip() or "0")
                if rno > 0:
                    rt = str(race.get("typeDescription") or "")
                    rg = str(race.get("groupName") or race.get("name") or "")
                    type_map[(hn, rno)] = race_type_bucket(rt, rg)

        for hp_data in export.get("hipodromlar", []):
            hip = hp_data["hipodrom"]
            for k in hp_data.get("kosular", []):
                kno = k["kno"]
                ap = k.get("analiz_puanlari", [])
                if not ap or len(ap) < 3:
                    continue

                key = (hip, kno)
                result = winners.get(key)
                if not result:
                    continue

                winner_no = result.winner_no
                # Siralama: ilk 5
                top5 = [a["at_no"] for a in ap[:5]]
                fav_no = ap[0]["at_no"] if ap else 0

                bucket = type_map.get(key, "other")
                fb = _field_bucket(len(ap))
                tf = (bucket, fb)

                # FAV
                fav_stats[tf]["toplam"] += 1
                fav_total += 1
                if fav_no == winner_no:
                    fav_stats[tf]["kazandi"] += 1
                    fav_wins += 1

                # 5'li satir
                besli_stats[tf]["toplam"] += 1
                besli_total += 1
                if winner_no in top5:
                    besli_stats[tf]["kazandi"] += 1
                    besli_wins += 1

    # Rapor
    L = []
    L.append("# Model Bazli FAV ve 5'li Satir Analizi")
    L.append(f"**Taranan:** {len(files)} gun, {fav_total} kosu")
    L.append("")

    L.append("## FAV (1. sira) Kazanma Orani")
    L.append("")
    L.append("| Kosu Tipi | At Sayisi | Kazandi | Toplam | FAV % |")
    L.append("|-----------|----------|---------|--------|-------|")
    for key in sorted(fav_stats.keys()):
        s = fav_stats[key]
        if s["toplam"] < 3: continue
        pct = s["kazandi"] / s["toplam"] * 100
        L.append(f"| {key[0]:<9s} | {key[1]:<8s} | {s['kazandi']:7d} | {s['toplam']:6d} | {pct:5.1f}% |")
    L.append(f"| **Toplam** | | {fav_wins} | {fav_total} | **{fav_wins/fav_total*100:.1f}%** |")
    L.append("")

    L.append("## 5'li Satir (Ilk 5) Kazanma Orani")
    L.append("")
    L.append("| Kosu Tipi | At Sayisi | Kazandi | Toplam | 5'li % |")
    L.append("|-----------|----------|---------|--------|--------|")
    for key in sorted(besli_stats.keys()):
        s = besli_stats[key]
        if s["toplam"] < 3: continue
        pct = s["kazandi"] / s["toplam"] * 100
        L.append(f"| {key[0]:<9s} | {key[1]:<8s} | {s['kazandi']:7d} | {s['toplam']:6d} | {pct:5.1f}% |")
    L.append(f"| **Toplam** | | {besli_wins} | {besli_total} | **{besli_wins/besli_total*100:.1f}%** |")

    report = "\n".join(L)
    out_path = ROOT / "reports" / "backtest_detay_raporu.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nRapor: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
