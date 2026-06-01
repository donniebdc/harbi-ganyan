# -*- coding: utf-8 -*-
"""
grid7 doğrulama — TAM EVREN (START..END, ~220 altılı) altılı backtest.

pegadrom_json_ai_genis_test.py içindeki grid7 adayı (ağır galop) holdout'ta (n=47)
çıpayı %72.3 -> %76.6 yükseltmiş ve Ortaklı'yı %21 -> %27.7 yapmıştı. Ama 47 örneklem
gürültülü. Bu script aynı varyantı TÜM tarih aralığında (1004 koşu / ~220 altılı)
baseline ile yan yana ölçer. Üretim kodunu DEĞİŞTİRMEZ.

Çıktı: grid7_altili_dogrula_raporu.md
"""
from __future__ import annotations
import io, os, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pegadrom_json_ai_genis_test as T
from altili_lib import load_all_csv, winning_set, birim_fiyat
from altili_kupon_v2 import build_tier, KUPON_TIERS

OUT = Path(T.BASE) / "Raporlar" / "grid7_altili_dogrula_raporu.md"

# grid7 = pegadrom_json_ai_genis_test_raporu.md "Ağırlık Grid" tablosu 7. satır
GRID7 = {
    "kind": "weighted", "w_market": 0.25, "w_flow": 0.45,
    "features": [
        ("galop.en_iyi|neutral_missing", 0.10),
        ("galop.istikrar|neutral_missing", 0.15),
        ("galop.en_iyi|raw_zero", 0.05),
    ],
}
# Robustluk için birkaç komşu (ağır-galop ailesi)
G_LIGHT = {  # daha hafif galop
    "kind": "weighted", "w_market": 0.30, "w_flow": 0.50,
    "features": [("galop.en_iyi|neutral_missing", 0.05),
                 ("galop.istikrar|neutral_missing", 0.15)],
}
G_HEAVY = {  # daha ağır galop
    "kind": "weighted", "w_market": 0.25, "w_flow": 0.40,
    "features": [("galop.en_iyi|neutral_missing", 0.15),
                 ("galop.istikrar|neutral_missing", 0.20)],
}
BASELINE = {"kind": "baseline"}
VARIANTS = [("baseline", BASELINE), ("grid7", GRID7),
            ("g_light", G_LIGHT), ("g_heavy", G_HEAVY)]


def prep():
    races_by_key, files = T.parse_tahmin_files()
    csvs = load_all_csv()
    peg_json = T.load_peg_json()
    eval_races = []
    for key, race in races_by_key.items():
        iso, hip, kno = key
        if not T.in_scope(iso):
            continue
        if f"{iso}|{hip}|{kno}" not in peg_json:
            continue
        c = csvs.get((iso, hip))
        if not c:
            continue
        w = c["kazanan"].get(kno)
        if w is None or w not in race["order"]:
            continue
        if not T.attach_json_features(race, peg_json):
            continue
        race["winner"] = w
        race["wset"] = winning_set(c, kno)
        T.feature_norms(race)
        eval_races.append(race)
    return races_by_key, csvs, eval_races, len(files)


def altili_full(races_by_key, csvs, variants):
    """eval_altili'nin TAM ARALIK (START..END) versiyonu."""
    out = {}
    for vname, variant in variants:
        tiers = {ad: Counter() for ad, _, _ in KUPON_TIERS}
        tier_cost = defaultdict(float)
        tier_ret = defaultdict(float)
        anyhit = Counter()
        banko = {ad: Counter() for ad, _, _ in KUPON_TIERS}
        seen = 0
        for (iso, hip), c in csvs.items():
            if not (T.START <= iso <= T.END):
                continue
            for alt in c["altililar"]:
                # tüm ayak koşuları _norms taşımalı; aksi halde atla
                ok = True
                for kno in alt["legs"]:
                    r = races_by_key.get((iso, hip, kno))
                    if not r or "_norms" not in r:
                        ok = False
                        break
                if not ok:
                    continue
                wsets = {kno: winning_set(c, kno) for kno in alt["legs"]}
                if any(not wsets[kno] for kno in alt["legs"]):
                    continue
                legs = T.legs_for_variant(races_by_key, iso, hip, alt["legs"], variant)
                if not legs:
                    continue
                seen += 1
                anyhit["n"] += 1
                unit = birim_fiyat(hip)
                odeme = alt.get("odeme", 0) or 0
                ticket_any = False
                for tier in KUPON_TIERS:
                    ad, lo, hi = tier
                    _, _, _, plan, komb = build_tier(legs, tier, unit, None, 0.50)
                    tiers[ad]["n"] += 1
                    tier_cost[ad] += komb * unit
                    hit = all(({a["at_no"] for a in p["secilen"]} & wsets[p["kno"]]) for p in plan)
                    if hit:
                        tiers[ad]["hit"] += 1
                        tier_ret[ad] += odeme
                        ticket_any = True
                    bl = next((p for p in plan if p.get("banko_lider")), None)
                    if bl:
                        banko[ad]["n"] += 1
                        if {a["at_no"] for a in bl["secilen"]} & wsets[bl["kno"]]:
                            banko[ad]["hit"] += 1
                        elif bl["width"] == 1:
                            banko[ad]["wrong_single"] += 1
                if ticket_any:
                    anyhit["hit"] += 1
        out[vname] = {"tiers": tiers, "cost": tier_cost, "return": tier_ret,
                      "anyhit": anyhit, "banko": banko, "seen": seen}
    return out


def five_full(eval_races, variants):
    """5-satır metrikleri tam evrende (train+holdout)."""
    out = {}
    for vname, variant in variants:
        res = T.eval_five(eval_races, variant)
        out[vname] = res
    return out


def pc(x, n):
    return "-" if not n else f"%{100*x/n:.1f}"


def main():
    print("Veri hazırlanıyor...")
    races_by_key, csvs, eval_races, nfiles = prep()
    print(f"  tahmin dosyası: {nfiles}, eval koşu: {len(eval_races)}")
    print("5-satır (tam evren) ölçülüyor...")
    five = five_full(eval_races, VARIANTS)
    print("Altılı (tam evren) backtest...")
    alt = altili_full(races_by_key, csvs, VARIANTS)

    L = []
    L.append("# grid7 Doğrulama — Tam Evren Altılı Backtest")
    L.append("")
    L.append(f"- Eval koşu: {len(eval_races)}")
    L.append(f"- Altılı (baseline seen): {alt['baseline']['seen']}")
    L.append(f"- Aralık: {T.START} .. {T.END}")
    L.append("- Üretim kodu DEĞİŞTİRİLMEDİ; bu rapor karar girdisidir.")
    L.append("")
    L.append("## grid7 tanımı")
    L.append("```")
    L.append("M:0.25 F:0.45 galop.en_iyi|neutral_missing:0.10 "
             "galop.istikrar|neutral_missing:0.15 galop.en_iyi|raw_zero:0.05")
    L.append("```")
    L.append("")

    # 5-satır karşılaştırma
    L.append("## 5-Satır (Tam Evren)")
    L.append("| Varyant | n | İlk1 | İlk3 | İlk4 | İlk5 | 5 satır | 14+ n | 14+ 5satır | HAR |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for vname, _ in VARIANTS:
        f = five[vname]["five"]
        s14 = five[vname]["segs"].get("14+", Counter())
        h = five[vname]["har"]
        L.append(f"| {vname} | {f['n']} | {pc(f['i1'],f['n'])} | {pc(f['i3'],f['n'])} | "
                 f"{pc(f['i4'],f['n'])} | {pc(f['i5'],f['n'])} | {pc(f['bes'],f['n'])} | "
                 f"{s14['n']} | {pc(s14['bes'],s14['n'])} | "
                 f"{h['har_yakaladi']}/{h['top4_disi']} {pc(h['har_yakaladi'],h['top4_disi'])} |")
    L.append("")

    # Altılı karşılaştırma
    L.append("## Altılı (Tam Evren)")
    L.append("| Varyant | Kademe | İsabet | Çıpa doğru | Yanlış tek banko | Net | 3 kupondan biri |")
    L.append("|---|---|---|---|---|---|---|")
    for vname, _ in VARIANTS:
        a = alt[vname]
        ah = a["anyhit"]
        for tier in KUPON_TIERS:
            ad = tier[0]
            t = a["tiers"][ad]
            b = a["banko"][ad]
            net = a["return"][ad] - a["cost"][ad]
            L.append(f"| {vname} | {ad} | {t['hit']}/{t['n']} {pc(t['hit'],t['n'])} | "
                     f"{b['hit']}/{b['n']} {pc(b['hit'],b['n'])} | {b['wrong_single']} | "
                     f"{net:+.0f} TL | {ah['hit']}/{ah['n']} {pc(ah['hit'],ah['n'])} |")
    L.append("")

    # Özet
    L.append("## Özet")
    bl = alt["baseline"]; g7 = alt["grid7"]
    for tier in KUPON_TIERS:
        ad = tier[0]
        b_hit = bl["tiers"][ad]["hit"]; g_hit = g7["tiers"][ad]["hit"]
        n = bl["tiers"][ad]["n"]
        L.append(f"- {ad}: baseline {b_hit}/{n} -> grid7 {g_hit}/{n} "
                 f"({'+' if g_hit>=b_hit else ''}{g_hit-b_hit} altılı)")
    bc = bl["banko"][KUPON_TIERS[1][0]]; gc = g7["banko"][KUPON_TIERS[1][0]]
    L.append(f"- Çıpa doğruluk (Harbi): baseline {pc(bc['hit'],bc['n'])} -> "
             f"grid7 {pc(gc['hit'],gc['n'])}")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"Rapor yazıldı: {OUT}")
    # konsola da özet
    print("\n".join(L[-12:]))


if __name__ == "__main__":
    main()
