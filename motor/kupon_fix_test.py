# -*- coding: utf-8 -*-
"""
KUPON FIX TESTİ — '5-satır tabanı' düzeltmesi vs baseline (220 altılı, YENİ bütçeler).

baseline: mevcut greedy kupon.
fix varyantları: bes_floor (banko_kac + floor_bonus) — akış-güvenilir BOM/HAR'ı kupona
  taşır, bütçe-nötr. floor_flow/floor_bonus parametreleri taranır.

Ölçüt: 6/6 isabet, kazanılan (baseline kaçırdı→fix tuttu), KAYBEDİLEN (baseline tuttu→
fix kaçırdı), net, ortalama bedel. Üretim kodu davranışı bes_floor=False'da korunur.
Çıktı: kupon_fix_test_raporu.md
"""
from __future__ import annotations
import os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from altili_lib import BASE, load_all_csv, winning_set, birim_fiyat
from altili_kupon_v2 import build_tier, KUPON_TIERS, load_cal
import kupon_kacan_analiz as KK   # parse + leg yardımcıları

OUT = os.path.join(BASE, "Raporlar", "kupon_fix_test_raporu.md")

VARIANTS = [
    ("baseline", {}),
    ("fix_f3_b4",  {"bes_floor": True, "floor_flow": 3, "floor_bonus": 4.0, "banko_kac": True}),
    ("fix_f3_b8",  {"bes_floor": True, "floor_flow": 3, "floor_bonus": 8.0, "banko_kac": True}),
    ("fix_f2_b6",  {"bes_floor": True, "floor_flow": 2, "floor_bonus": 6.0, "banko_kac": True}),
    ("floor_only", {"bes_floor": True, "floor_flow": 3, "floor_bonus": 6.0, "banko_kac": False}),
    ("banko_only", {"bes_floor": True, "floor_flow": 3, "floor_bonus": 1.0, "banko_kac": True}),
]


def coupon_hit(legs_r, plan, wsets):
    for p, r in zip(plan, legs_r):
        if not ({a["at_no"] for a in p["secilen"]} & wsets[r["kno"]]):
            return False
    return True


def main():
    print("Tahminler parse ediliyor...")
    races = KK.parse_tahminler_dir()
    csvs = load_all_csv()
    cal = load_cal()
    print(f"  koşu: {len(races)}, CSV: {len(csvs)}")

    # her tier x varyant icin sonuc topla; ayrica baseline hit-set'i tutup gain/loss hesapla
    # key: altili kimligi
    res = {ad: {vn: {"n": 0, "hit": 0, "komb": 0, "bedel": 0.0, "hitset": set()}
                for vn, _ in VARIANTS} for ad, _, _ in KUPON_TIERS}

    for (iso, hip), c in csvs.items():
        for alt in c["altililar"]:
            legs_r, ok = [], True
            for kno in alt["legs"]:
                r = races.get((iso, hip, kno))
                if not r or not r["atlar"]:
                    ok = False; break
                legs_r.append(r)
            if not ok:
                continue
            wsets = {kno: winning_set(c, kno) for kno in alt["legs"]}
            if any(not wsets[kno] for kno in alt["legs"]):
                continue
            legs = [KK.leg_from_race(r) for r in legs_r]
            birim = birim_fiyat(hip)
            aid = (iso, hip, alt["idx"], alt["legs"][0])
            for tier in KUPON_TIERS:
                ad = tier[0]
                for vn, kw in VARIANTS:
                    _, _, _, plan, komb = build_tier(legs, tier, birim, cal, 0.50, **kw)
                    R = res[ad][vn]
                    R["n"] += 1
                    R["komb"] += komb
                    R["bedel"] += komb * birim
                    if coupon_hit(legs_r, plan, wsets):
                        R["hit"] += 1
                        R["hitset"].add(aid)

    L = ["# Kupon Fix Testi — '5-satır tabanı' (YENİ bütçeler)", ""]
    L.append("Bütçe kademeleri: " + ", ".join(f"{ad} {lo}-{hi}" for ad, lo, hi in KUPON_TIERS))
    L.append("")
    for ad, _, _ in KUPON_TIERS:
        base = res[ad]["baseline"]
        n = base["n"]
        L.append(f"## {ad}  (altılı n={n})")
        L.append("| Varyant | 6/6 isabet | Ort. bedel | Kazanılan | Kaybedilen | Net |")
        L.append("|---|---|---|---|---|---|")
        for vn, _ in VARIANTS:
            R = res[ad][vn]
            gained = len(R["hitset"] - base["hitset"])
            lost = len(base["hitset"] - R["hitset"])
            net = R["hit"] - base["hit"]
            bedel = R["bedel"] / R["n"] if R["n"] else 0
            L.append(f"| {vn} | {R['hit']}/{n} %{100*R['hit']/n:.1f} | {bedel:.0f} TL | "
                     f"{'+' if vn!='baseline' else ''}{gained if vn!='baseline' else '-'} | "
                     f"{lost if vn!='baseline' else '-'} | "
                     f"{'+' if net>=0 and vn!='baseline' else ''}{net if vn!='baseline' else '-'} |")
        L.append("")

    open(OUT, "w", encoding="utf-8").write("\n".join(L))
    print(f"Rapor yazıldı: {OUT}")
    print("\n".join(L))


if __name__ == "__main__":
    main()
