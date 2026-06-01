# -*- coding: utf-8 -*-
"""
14+ SEGMENT-KAPILI galop ana-skor eklemesi — doğrulama.

Fikir: galop.en_iyi + galop.istikrar sinyali SADECE 14+ atlı koşularda ana skora
eklenir; <=13 koşuda baseline aynen korunur (zaten tavan, dokunma). Böylece
grid7'nin global uygularken bozduğu İlk1/<=9 metrikleri korunur, kalabalık koşuda
kazanç alınır.

Üretim kodunu DEĞİŞTİRMEZ. Çıktı: seg14_galop_dogrula_raporu.md
"""
from __future__ import annotations
import os, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pegadrom_json_ai_genis_test as T
from altili_lib import load_all_csv, winning_set, birim_fiyat
from altili_kupon_v2 import build_tier, KUPON_TIERS

OUT = Path(T.BASE) / "seg14_galop_dogrula_raporu.md"

# --- segment-kapılı variant desteği: T.variant_score'u sarmalayalım ---
_orig_variant_score = T.variant_score
def _patched_variant_score(race, no, variant):
    if isinstance(variant, dict) and variant.get("kind") == "seg14":
        if race["n_at"] >= variant.get("thresh", 14):
            return _orig_variant_score(race, no, variant["inner"])
        return _orig_variant_score(race, no, {"kind": "baseline"})
    return _orig_variant_score(race, no, variant)
T.variant_score = _patched_variant_score

GRID7 = {
    "kind": "weighted", "w_market": 0.25, "w_flow": 0.45,
    "features": [("galop.en_iyi|neutral_missing", 0.10),
                 ("galop.istikrar|neutral_missing", 0.15),
                 ("galop.en_iyi|raw_zero", 0.05)],
}
G_LIGHT = {
    "kind": "weighted", "w_market": 0.30, "w_flow": 0.50,
    "features": [("galop.en_iyi|neutral_missing", 0.05),
                 ("galop.istikrar|neutral_missing", 0.15)],
}
BASELINE = {"kind": "baseline"}
VARIANTS = [
    ("baseline", BASELINE),
    ("seg14_g7", {"kind": "seg14", "thresh": 14, "inner": GRID7}),
    ("seg12_g7", {"kind": "seg14", "thresh": 12, "inner": GRID7}),
    ("seg14_glight", {"kind": "seg14", "thresh": 14, "inner": G_LIGHT}),
]


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
    out = {}
    for vname, variant in variants:
        tiers = {ad: Counter() for ad, _, _ in KUPON_TIERS}
        tier_cost = defaultdict(float)
        tier_ret = defaultdict(float)
        anyhit = Counter()
        banko = {ad: Counter() for ad, _, _ in KUPON_TIERS}
        for (iso, hip), c in csvs.items():
            if not (T.START <= iso <= T.END):
                continue
            for alt in c["altililar"]:
                ok = all(((races_by_key.get((iso, hip, kno)) or {}).get("_norms") is not None)
                         for kno in alt["legs"])
                if not ok:
                    continue
                wsets = {kno: winning_set(c, kno) for kno in alt["legs"]}
                if any(not wsets[kno] for kno in alt["legs"]):
                    continue
                legs = T.legs_for_variant(races_by_key, iso, hip, alt["legs"], variant)
                if not legs:
                    continue
                anyhit["n"] += 1
                unit = birim_fiyat(hip)
                odeme = alt.get("odeme", 0) or 0
                ticket_any = False
                for tier in KUPON_TIERS:
                    ad = tier[0]
                    _, _, _, plan, komb = build_tier(legs, tier, unit, None, 0.50)
                    tiers[ad]["n"] += 1
                    tier_cost[ad] += komb * unit
                    if all(({a["at_no"] for a in p["secilen"]} & wsets[p["kno"]]) for p in plan):
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
                      "anyhit": anyhit, "banko": banko}
    return out


def pc(x, n):
    return "-" if not n else f"%{100*x/n:.1f}"


def main():
    print("Veri hazırlanıyor...")
    races_by_key, csvs, eval_races, nfiles = prep()
    print(f"  tahmin dosyası: {nfiles}, eval koşu: {len(eval_races)}")
    print("5-satır ölçülüyor...")
    five = {vn: T.eval_five(eval_races, v) for vn, v in VARIANTS}
    print("Altılı backtest...")
    alt = altili_full(races_by_key, csvs, VARIANTS)

    L = []
    L.append("# 14+ Segment-Kapılı Galop — Doğrulama")
    L.append("")
    L.append(f"- Eval koşu: {len(eval_races)} | Aralık: {T.START}..{T.END}")
    L.append("- 14+ koşularda galop ana-skora eklenir; <=13 koşuda baseline korunur.")
    L.append("- Üretim kodu DEĞİŞTİRİLMEDİ; karar girdisidir.")
    L.append("")
    L.append("## 5-Satır Genel")
    L.append("| Varyant | İlk1 | İlk3 | İlk4 | İlk5 | 5 satır | HAR |")
    L.append("|---|---|---|---|---|---|---|")
    for vn, _ in VARIANTS:
        f = five[vn]["five"]; h = five[vn]["har"]
        L.append(f"| {vn} | {pc(f['i1'],f['n'])} | {pc(f['i3'],f['n'])} | {pc(f['i4'],f['n'])} | "
                 f"{pc(f['i5'],f['n'])} | {pc(f['bes'],f['n'])} | "
                 f"{h['har_yakaladi']}/{h['top4_disi']} {pc(h['har_yakaladi'],h['top4_disi'])} |")
    L.append("")
    L.append("## 5-Satır Segment Bazlı (5 satır isabeti)")
    L.append("| Varyant | <=9 | 10-13 | 14+ |")
    L.append("|---|---|---|---|")
    for vn, _ in VARIANTS:
        segs = five[vn]["segs"]
        cells = []
        for sk in ("<=9", "10-13", "14+"):
            s = segs.get(sk, Counter())
            cells.append(f"{pc(s['bes'],s['n'])} (n={s['n']})")
        L.append(f"| {vn} | {cells[0]} | {cells[1]} | {cells[2]} |")
    L.append("")
    L.append("## Altılı (Tam Evren, 212)")
    L.append("| Varyant | Kademe | İsabet | Çıpa doğru | Yanlış tek banko | 3 kupondan biri |")
    L.append("|---|---|---|---|---|---|")
    for vn, _ in VARIANTS:
        a = alt[vn]; ah = a["anyhit"]
        for tier in KUPON_TIERS:
            ad = tier[0]; t = a["tiers"][ad]; b = a["banko"][ad]
            L.append(f"| {vn} | {ad} | {t['hit']}/{t['n']} {pc(t['hit'],t['n'])} | "
                     f"{b['hit']}/{b['n']} {pc(b['hit'],b['n'])} | {b['wrong_single']} | "
                     f"{ah['hit']}/{ah['n']} {pc(ah['hit'],ah['n'])} |")
    L.append("")
    L.append("## Özet (baseline -> seg14_g7)")
    bl = five["baseline"]; s7 = five["seg14_g7"]
    for sk in ("<=9", "10-13", "14+"):
        b = bl["segs"].get(sk, Counter()); s = s7["segs"].get(sk, Counter())
        L.append(f"- {sk} 5 satır: {pc(b['bes'],b['n'])} -> {pc(s['bes'],s['n'])}")
    L.append(f"- HAR: {pc(bl['har']['har_yakaladi'],bl['har']['top4_disi'])} -> "
             f"{pc(s7['har']['har_yakaladi'],s7['har']['top4_disi'])}")
    aab = alt["baseline"]["anyhit"]; aas = alt["seg14_g7"]["anyhit"]
    L.append(f"- Altılı 3-kupondan-biri: {aab['hit']}/{aab['n']} -> {aas['hit']}/{aas['n']}")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"Rapor yazıldı: {OUT}")
    print("\n".join(L[-9:]))


if __name__ == "__main__":
    main()
