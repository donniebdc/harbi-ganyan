# -*- coding: utf-8 -*-
"""5 satir basarisini altili kupona tasima analizi.

Bu script uretim kodunu degistirmez. Guncel tahmin arsivi, TJK JSON sonuclari ve
guncel kupon kurucuyu kullanarak sunlari olcer:
  - Mevcut ic ice kuponlarda 5/6 kalanlarin neden kactigi
  - Kacan kazananlarin 5 satir icinde olup olmadigi
  - Ayni butceyle secim sirasi 5-satir oncelikli olsaydi sonuc
  - Riskli ayaklarda butce yettikce 5 satira kadar genisletme sonucu

Cikti: Raporlar/altili_bes_satir_derin_analiz_raporu.md
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from altili_lib import BASE, birim_fiyat, load_results, winning_set
from altili_kupon_v2 import (
    KUPON_TIERS,
    TIER_POLICY,
    banko_score,
    build_tier,
    build_nested_tiers,
    load_cal,
    select_with_ekuri,
)
import kupon_kacan_analiz as KK


OUT = os.path.join(BASE, "Raporlar", "altili_bes_satir_derin_analiz_raporu.md")
LINE_LABELS = ["FAV", "SUR", "YAZ", "BOM", "HAR"]
TIERS_2500 = [
    ("Simitçi 6'lısı", 400, 600),
    ("Harbi Ganyan 6'lısı", 1000, 1600),
    ("Ortaklı 6'lı", 1600, 2500),
]
GRID_BUDGETS = [2200, 2300, 2400, 2500, 2600, 2800, 3000]
GRID_PROFILES = {
    "dengeli": [7.0, 8.0, 10.0, 9.5, 9.0],
    "favori_oncelik": [10.0, 9.0, 8.0, 6.5, 6.0],
    "orta_uc": [5.5, 7.0, 10.5, 10.0, 9.0],
    "surpriz_agir": [4.0, 6.0, 9.0, 11.0, 11.5],
    "yaz_bom_har": [4.0, 5.0, 11.0, 10.5, 10.0],
}


@dataclass(frozen=True)
class AltKey:
    iso: str
    hip: str
    idx: int
    start: int


def komb(widths):
    p = 1
    for w in widths:
        p *= max(1, int(w))
    return p


def at_map(r):
    return {a["at_no"]: a for a in r["atlar"]}


def order_for_race(r, mode):
    """Secim sirasi: mevcut ANA veya 5-satir oncelikli + ANA kalan."""
    if mode == "ana":
        return list(r["atlar"])
    amap = at_map(r)
    ordered = []
    seen = set()
    for no in r.get("bes_nos") or []:
        if no is not None and no in amap and no not in seen:
            ordered.append(amap[no])
            seen.add(no)
    for a in r["atlar"]:
        if a["at_no"] not in seen:
            ordered.append(a)
            seen.add(a["at_no"])
    return ordered


def rebuild_plan(legs_r, widths, base_plan, order_mode="ana"):
    plan = []
    for r, w, old in zip(legs_r, widths, base_plan):
        ordered = order_for_race(r, order_mode)
        selected = select_with_ekuri(ordered, min(w, len(ordered)), r.get("ekuri") or [])
        p = dict(old)
        p["width"] = w
        p["secilen"] = selected
        p["ekuri"] = r.get("ekuri") or []
        p["ekuri_isim"] = {
            a["at_no"]: a["at"]
            for a in r["atlar"]
            if any(a["at_no"] in g for g in (r.get("ekuri") or []))
        }
        plan.append(p)
    return plan


def rebuild_plan_from_sets(legs_r, selected_sets, base_plan):
    plan = []
    for r, selected, old in zip(legs_r, selected_sets, base_plan):
        ordered = order_for_race(r, "bes")
        selected_objs = [a for a in ordered if a["at_no"] in selected]
        p = dict(old)
        p["width"] = len(selected_objs)
        p["secilen"] = selected_objs
        p["ekuri"] = r.get("ekuri") or []
        p["ekuri_isim"] = {
            a["at_no"]: a["at"]
            for a in r["atlar"]
            if any(a["at_no"] in g for g in (r.get("ekuri") or []))
        }
        plan.append(p)
    return plan


def bes_line_of(r, wset):
    for i, no in enumerate(r.get("bes_nos") or []):
        if no is not None and no in wset:
            return LINE_LABELS[i]
    return None


def ana_rank(r, no):
    for i, a in enumerate(r["atlar"], 1):
        if a["at_no"] == no:
            return i
    return None


def best_rank(r, wset):
    vals = [ana_rank(r, no) for no in wset]
    vals = [v for v in vals if v is not None]
    return min(vals) if vals else None


def plan_hit(plan, legs_r, wsets):
    return all({a["at_no"] for a in p["secilen"]} & wsets[r["kno"]] for p, r in zip(plan, legs_r))


def dogru_say(plan, legs_r, wsets):
    return sum(1 for p, r in zip(plan, legs_r)
               if {a["at_no"] for a in p["secilen"]} & wsets[r["kno"]])


def miss_details(plan, legs_r, wsets):
    out = []
    for i, (p, r) in enumerate(zip(plan, legs_r)):
        sec = {a["at_no"] for a in p["secilen"]}
        if not (sec & wsets[r["kno"]]):
            out.append((i, p, r, wsets[r["kno"]]))
    return out


def flow_surprise_rank(r, flow_limit=5):
    """5 satirdaki BOM/HAR veya ANA rank 4/5 icinde akisi guclu en derin rank."""
    deepest = 0
    for rank in (4, 5):
        if len(r["atlar"]) >= rank:
            fr = int(r["atlar"][rank - 1].get("flow_rank") or 0)
            if 0 < fr <= flow_limit:
                deepest = rank
    return deepest


def risk_score(r):
    """Kazanan bilgisi kullanmadan ayak genisletme onceligi."""
    n = r["n_at"]
    fark = r["fark"]
    flow_deep = flow_surprise_rank(r, 5)
    score = 0.0
    if n >= 14:
        score += 35
    elif n >= 12:
        score += 25
    elif n >= 10:
        score += 15
    if fark < 8:
        score += 25
    elif fark < 15:
        score += 18
    elif fark < 25:
        score += 10
    if flow_deep:
        score += 18 + flow_deep
    return score


def widen_risky(legs_r, base_plan, tier, birim, prev_widths=None, order_mode="bes"):
    """Butce icinde riskli ayaklari min 5'e yaklastirir; kazanan bilgisi kullanmaz."""
    _, _, hi = tier
    max_komb = int(hi / birim)
    widths = [p["width"] for p in base_plan]
    if prev_widths:
        widths = [max(w, pw) for w, pw in zip(widths, prev_widths)]
    locked = {i for i, p in enumerate(base_plan) if p.get("banko_lider") and p["width"] == 1}
    targets = []
    for i, r in enumerate(legs_r):
        if i in locked:
            continue
        target = min(5, r["n_at"])
        if widths[i] >= target:
            continue
        score = risk_score(r)
        if score >= 25:
            targets.append((score, i, target))
    targets.sort(reverse=True)
    changed = True
    while changed:
        changed = False
        for _, i, target in targets:
            if widths[i] >= target:
                continue
            cand = list(widths)
            cand[i] += 1
            if komb(cand) <= max_komb:
                widths = cand
                changed = True
    return rebuild_plan(legs_r, widths, base_plan, order_mode=order_mode), widths


def bes_transfer_score(r, slot_idx, banko_break, profile=None, risk_mult=1.0):
    slot_base = (profile or GRID_PROFILES["dengeli"])[slot_idx]
    return slot_base + risk_mult * risk_score(r) / 10.0 + (1.5 if banko_break else 0.0)


def build_nested_bes_transfer(legs_r, legs, birim, cal, tiers=None, protect_strong_banko=False,
                              profile=None, risk_mult=1.0):
    """Ic ice kuralini koruyarak eksik 5-satir atlarini butce icinde kupona ekler.

    Alt kuponun secimleri ust kuponda aynen kalir. Her tier once mevcut nested kuponu
    baz alir, sonra en yuksek skor/maliyet oranli eksik 5-satir atini ekleyerek butce
    tavanina kadar genisler. Kazanan bilgisi kullanmaz.
    """
    tiers = tiers or KUPON_TIERS
    base = build_nested_tiers(legs, tiers, birim, cal, 0.50, TIER_POLICY)
    out = []
    prev_sets = None
    for tier, built in zip(tiers, base):
        ad, lo, hi = tier
        _, _, _, base_plan, _ = built
        max_k = int(hi / birim)
        selected_sets = [{a["at_no"] for a in p["secilen"]} for p in base_plan]
        if prev_sets:
            selected_sets = [set(s) | set(ps) for s, ps in zip(selected_sets, prev_sets)]

        while True:
            cur_widths = [len(s) for s in selected_sets]
            cur_k = komb(cur_widths)
            best = None
            for i, r in enumerate(legs_r):
                if cur_widths[i] >= r["n_at"]:
                    continue
                p = base_plan[i]
                strong_banko = (
                    protect_strong_banko
                    and p.get("banko_lider")
                    and cur_widths[i] == 1
                    and r["n_at"] <= 7
                    and r["fark"] >= 35
                )
                if strong_banko:
                    continue
                for slot_idx, no in enumerate(r.get("bes_nos") or []):
                    if no is None or no in selected_sets[i]:
                        continue
                    if no not in at_map(r):
                        continue
                    cand_widths = list(cur_widths)
                    cand_widths[i] += 1
                    new_k = komb(cand_widths)
                    if new_k > max_k:
                        continue
                    cost_ratio = new_k / max(cur_k, 1)
                    score = bes_transfer_score(r, slot_idx, bool(p.get("banko_lider")), profile, risk_mult) / cost_ratio
                    if best is None or score > best[0]:
                        best = (score, i, no)
            if best is None:
                break
            _, i, no = best
            selected_sets[i].add(no)

        plan = rebuild_plan_from_sets(legs_r, selected_sets, base_plan)
        kmb = komb([len(s) for s in selected_sets])
        out.append((ad, lo, hi, plan, kmb))
        prev_sets = selected_sets
    return out


def add_bes_to_existing_plan(legs_r, base_plan, hi, birim, protect_strong_banko=False,
                             profile=None, risk_mult=1.0, max_add_per_leg=99):
    """Mevcut planı bozmadan, sadece eksik 5-satir atlarini ekler."""
    max_k = int(hi / birim)
    selected_sets = [{a["at_no"] for a in p["secilen"]} for p in base_plan]
    while True:
        cur_widths = [len(s) for s in selected_sets]
        cur_k = komb(cur_widths)
        best = None
        for i, r in enumerate(legs_r):
            if cur_widths[i] >= r["n_at"]:
                continue
            if cur_widths[i] - len(base_plan[i]["secilen"]) >= max_add_per_leg:
                continue
            p = base_plan[i]
            strong_banko = (
                protect_strong_banko
                and p.get("banko_lider")
                and cur_widths[i] == 1
                and r["n_at"] <= 7
                and r["fark"] >= 35
            )
            if strong_banko:
                continue
            for slot_idx, no in enumerate(r.get("bes_nos") or []):
                if no is None or no in selected_sets[i] or no not in at_map(r):
                    continue
                cand_widths = list(cur_widths)
                cand_widths[i] += 1
                new_k = komb(cand_widths)
                if new_k > max_k:
                    continue
                cost_ratio = new_k / max(cur_k, 1)
                score = bes_transfer_score(r, slot_idx, bool(p.get("banko_lider")), profile, risk_mult) / cost_ratio
                if best is None or score > best[0]:
                    best = (score, i, no)
        if best is None:
            break
        _, i, no = best
        selected_sets[i].add(no)
    return rebuild_plan_from_sets(legs_r, selected_sets, base_plan), komb([len(s) for s in selected_sets])


def _first_n_set(r, n, order_mode="ana"):
    return {a["at_no"] for a in order_for_race(r, order_mode)[:min(n, r["n_at"])]}


def custom_expand_plan(legs_r, base_plan, hi, birim, mode, profile=None):
    """Kullanıcının istediği 3 özel test için analiz amaçlı kupon kurar."""
    max_k = int(hi / birim)
    scores = [banko_score(KK.leg_from_race(r)) for r in legs_r]
    banko_idx = max(range(len(legs_r)), key=lambda i: scores[i])
    second_idx = None
    if mode == "banko_plus_iki_fav":
        cand = [i for i in range(len(legs_r)) if i != banko_idx]
        second_idx = max(cand, key=lambda i: scores[i]) if cand else None

    selected_sets = []
    for i, r in enumerate(legs_r):
        if i == banko_idx:
            selected_sets.append(_first_n_set(r, 1, "ana"))
        elif i == second_idx:
            selected_sets.append(_first_n_set(r, 2, "ana"))
        else:
            selected_sets.append(_first_n_set(r, 2, "bes"))

    def can_add(i):
        if i == banko_idx:
            return False
        if mode == "banko_plus_iki_fav" and i == second_idx:
            return False
        return True

    # Test-3: handikap/maiden/sartli ayaklara once hedef genislik ver.
    if mode == "tip_genis":
        for target in (5, 6, 7):
            changed = True
            while changed:
                changed = False
                for i, r in enumerate(legs_r):
                    if r.get("race_type") not in {"handikap", "maiden", "sartli"}:
                        continue
                    if len(selected_sets[i]) >= min(target, r["n_at"]):
                        continue
                    for a in order_for_race(r, "bes"):
                        if a["at_no"] in selected_sets[i]:
                            continue
                        cand = [set(s) for s in selected_sets]
                        cand[i].add(a["at_no"])
                        if komb([len(s) for s in cand]) <= max_k:
                            selected_sets = cand
                            changed = True
                        break

    # Genel 5-satir aktarimi: eksik 5 satir atlarini skor/maliyet ile ekle.
    while True:
        cur_widths = [len(s) for s in selected_sets]
        cur_k = komb(cur_widths)
        best = None
        for i, r in enumerate(legs_r):
            if not can_add(i) or cur_widths[i] >= r["n_at"]:
                continue
            for slot_idx, no in enumerate(r.get("bes_nos") or []):
                if no is None or no in selected_sets[i] or no not in at_map(r):
                    continue
                cand_widths = list(cur_widths)
                cand_widths[i] += 1
                new_k = komb(cand_widths)
                if new_k > max_k:
                    continue
                type_bonus = 2.0 if (mode == "tip_genis" and r.get("race_type") in {"handikap", "maiden", "sartli"}) else 0.0
                score = (bes_transfer_score(r, slot_idx, False, profile or GRID_PROFILES["surpriz_agir"], 0.5)
                         + type_bonus) / (new_k / max(cur_k, 1))
                if best is None or score > best[0]:
                    best = (score, i, no)
        if best is None:
            break
        _, i, no = best
        selected_sets[i].add(no)

    plan = rebuild_plan_from_sets(legs_r, selected_sets, base_plan)
    return plan, komb([len(s) for s in selected_sets])


def build_current(legs, birim, cal, banko_esik=0.50):
    return build_nested_tiers(legs, KUPON_TIERS, birim, cal, banko_esik, TIER_POLICY)


def build_ortakli_floor(legs, birim, cal):
    policies = dict(TIER_POLICY)
    policies["Ortaklı 6'lı"] = {"bes_floor": True, "floor_flow": 3, "floor_bonus": 6.0, "banko_kac": True}
    return build_nested_tiers(legs, KUPON_TIERS, birim, cal, 0.50, policies)


def build_flow5(legs, birim, cal):
    policies = {
        "Simitçi 6'lısı": {"bes_floor": True, "floor_flow": 5, "floor_bonus": 8.0, "banko_kac": False},
        "Harbi Ganyan 6'lısı": {"bes_floor": True, "floor_flow": 5, "floor_bonus": 8.0, "banko_kac": True},
        "Ortaklı 6'lı": {"bes_floor": True, "floor_flow": 5, "floor_bonus": 8.0, "banko_kac": True},
    }
    return build_nested_tiers(legs, KUPON_TIERS, birim, cal, 0.50, policies)


def build_banko070(legs, birim, cal):
    return build_nested_tiers(legs, KUPON_TIERS, birim, cal, 0.70, TIER_POLICY)


def build_banko080(legs, birim, cal):
    return build_nested_tiers(legs, KUPON_TIERS, birim, cal, 0.80, TIER_POLICY)


def pct(a, b):
    return f"%{100*a/b:.1f}" if b else "%0.0"


def period_of(iso):
    if iso < "2026-04-01":
        return "Şubat-Mart"
    if iso < "2026-05-01":
        return "Nisan"
    if iso <= "2026-05-15":
        return "Mayıs 1-15"
    return "Mayıs 16-30"


def raw_txt_summary():
    """TahminSonuçları klasöründeki render edilmiş TXT'lerden direkt durum sayımı."""
    root = None
    for name in os.listdir(BASE):
        if name.startswith("TahminSon"):
            p = os.path.join(BASE, name)
            if os.path.isdir(p):
                root = p
                break
    if not root:
        return {"files": 0, "total": 0, "dist": Counter()}
    dist = Counter()
    files = 0
    import re
    for fn in os.listdir(root):
        if not fn.lower().endswith(".txt"):
            continue
        files += 1
        text = open(os.path.join(root, fn), encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"6/6|([0-6])'TE KALDI \(([0-6])/6\)", text):
            if m.group(1):
                dist[int(m.group(2))] += 1
            else:
                dist[6] += 1
    return {"files": files, "total": sum(dist.values()), "dist": dist}


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    print("Tahmin, altılı ve sonuç evreni yükleniyor...")
    races = KK.parse_tahminler_dir()
    alt_map = KK.derive_altililar()
    results = load_results(prefer="json")
    cal = load_cal()
    txt_sum = raw_txt_summary()

    universe = []
    for (iso, hip), alts in sorted(alt_map.items()):
        c = results.get((iso, hip))
        if not c:
            continue
        for alt in alts:
            legs_r = []
            ok = True
            for kno in alt["legs"]:
                r = races.get((iso, hip, kno))
                if not r or not r.get("atlar"):
                    ok = False
                    break
                legs_r.append(r)
            if not ok:
                continue
            wsets = {kno: winning_set(c, kno) for kno in alt["legs"]}
            if any(not wsets[kno] for kno in alt["legs"]):
                continue
            legs = [KK.leg_from_race(r) for r in legs_r]
            universe.append((AltKey(iso, hip, alt["idx"], alt["legs"][0]), legs_r, legs, wsets, birim_fiyat(hip)))

    variants = {
        "mevcut": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "5satir_sira": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "banko070": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "banko070_5sira": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "banko080": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "bagimsiz": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "bagimsiz_5sira": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "icice_5satir_2200": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "icice_5satir_2200_korumali": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "icice_5satir_2500": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "icice_5satir_2500_korumali": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "ortakli_2500_sadece_ekle": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "ortakli_2500_sadece_ekle_korumali": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "test1_banko_genis_2500": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "test1_banko_genis_3000": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "test2_banko_iki_fav_2500": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "test2_banko_iki_fav_3000": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "test3_tip_genis_2500": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "test3_tip_genis_3000": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "ortakli_floor": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "flow5_floor": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
        "risk5_5satir": defaultdict(lambda: {"n": 0, "hit": 0, "dist": Counter(), "hitset": set(), "bedel": 0.0}),
    }
    miss_stats = {ad: {
        "miss1": 0, "miss1_bes": 0, "miss1_width": 0, "line": Counter(),
        "rank": Counter(), "banko": 0, "nseg": Counter(), "examples": []
    } for ad, _, _ in KUPON_TIERS}
    theoretical = {"n": 0, "bes6": 0, "bes5": 0, "bes_dist": Counter()}
    period_theory = defaultdict(lambda: {"n": 0, "bes6": 0})
    grid_stats = defaultdict(lambda: {"n": 0, "ort_hitset": set(), "any_hitset": set(), "bedel": 0.0})

    for key, legs_r, legs, wsets, birim in universe:
        theoretical["n"] += 1
        bes_hits = sum(1 for r in legs_r if bes_line_of(r, wsets[r["kno"]]))
        theoretical["bes_dist"][bes_hits] += 1
        if bes_hits == 6:
            theoretical["bes6"] += 1
        if bes_hits >= 5:
            theoretical["bes5"] += 1
        period_theory[period_of(key.iso)]["n"] += 1
        if bes_hits == 6:
            period_theory[period_of(key.iso)]["bes6"] += 1

        current = build_current(legs, birim, cal)
        banko070 = build_banko070(legs, birim, cal)
        banko080 = build_banko080(legs, birim, cal)
        ortakli = build_ortakli_floor(legs, birim, cal)
        flow5 = build_flow5(legs, birim, cal)
        bes2200 = build_nested_bes_transfer(legs_r, legs, birim, cal, KUPON_TIERS, False)
        bes2200p = build_nested_bes_transfer(legs_r, legs, birim, cal, KUPON_TIERS, True)
        bes2500 = build_nested_bes_transfer(legs_r, legs, birim, cal, TIERS_2500, False)
        bes2500p = build_nested_bes_transfer(legs_r, legs, birim, cal, TIERS_2500, True)

        prev_risk_widths = None
        current_hits_by_idx = []
        for idx0 in range(3):
            _, _, _, p0, _k0 = current[idx0]
            current_hits_by_idx.append(plan_hit(p0, legs_r, wsets))
        for idx, tier in enumerate(KUPON_TIERS):
            ad = tier[0]
            _, _, _, cur_plan, cur_komb = current[idx]
            _, _, _, b70_plan, b70_komb = banko070[idx]
            _, _, _, b80_plan, b80_komb = banko080[idx]
            _, _, _, of_plan, of_komb = ortakli[idx]
            _, _, _, f5_plan, f5_komb = flow5[idx]
            _, _, _, bs22_plan, bs22_komb = bes2200[idx]
            _, _, _, bs22p_plan, bs22p_komb = bes2200p[idx]
            _, _, _, bs25_plan, bs25_komb = bes2500[idx]
            _, _, _, bs25p_plan, bs25p_komb = bes2500p[idx]
            if idx == 2:
                safe25_plan, safe25_komb = add_bes_to_existing_plan(legs_r, cur_plan, 2500, birim, False)
                safe25p_plan, safe25p_komb = add_bes_to_existing_plan(legs_r, cur_plan, 2500, birim, True)
                t1_25_plan, t1_25_komb = custom_expand_plan(legs_r, cur_plan, 2500, birim, "banko_genis")
                t1_30_plan, t1_30_komb = custom_expand_plan(legs_r, cur_plan, 3000, birim, "banko_genis")
                t2_25_plan, t2_25_komb = custom_expand_plan(legs_r, cur_plan, 2500, birim, "banko_plus_iki_fav")
                t2_30_plan, t2_30_komb = custom_expand_plan(legs_r, cur_plan, 3000, birim, "banko_plus_iki_fav")
                t3_25_plan, t3_25_komb = custom_expand_plan(legs_r, cur_plan, 2500, birim, "tip_genis")
                t3_30_plan, t3_30_komb = custom_expand_plan(legs_r, cur_plan, 3000, birim, "tip_genis")
            else:
                safe25_plan, safe25_komb = cur_plan, cur_komb
                safe25p_plan, safe25p_komb = cur_plan, cur_komb
                t1_25_plan, t1_25_komb = cur_plan, cur_komb
                t1_30_plan, t1_30_komb = cur_plan, cur_komb
                t2_25_plan, t2_25_komb = cur_plan, cur_komb
                t2_30_plan, t2_30_komb = cur_plan, cur_komb
                t3_25_plan, t3_25_komb = cur_plan, cur_komb
                t3_30_plan, t3_30_komb = cur_plan, cur_komb
            policy = dict(TIER_POLICY.get(ad, {}))
            _, _, _, ind_plan, ind_komb = build_tier(legs, tier, birim, cal, 0.50, **policy)
            plans = {
                "mevcut": (cur_plan, cur_komb),
                "5satir_sira": (rebuild_plan(legs_r, [p["width"] for p in cur_plan], cur_plan, "bes"), cur_komb),
                "banko070": (b70_plan, b70_komb),
                "banko070_5sira": (rebuild_plan(legs_r, [p["width"] for p in b70_plan], b70_plan, "bes"), b70_komb),
                "banko080": (b80_plan, b80_komb),
                "bagimsiz": (ind_plan, ind_komb),
                "bagimsiz_5sira": (rebuild_plan(legs_r, [p["width"] for p in ind_plan], ind_plan, "bes"), ind_komb),
                "icice_5satir_2200": (bs22_plan, bs22_komb),
                "icice_5satir_2200_korumali": (bs22p_plan, bs22p_komb),
                "icice_5satir_2500": (bs25_plan, bs25_komb),
                "icice_5satir_2500_korumali": (bs25p_plan, bs25p_komb),
                "ortakli_2500_sadece_ekle": (safe25_plan, safe25_komb),
                "ortakli_2500_sadece_ekle_korumali": (safe25p_plan, safe25p_komb),
                "test1_banko_genis_2500": (t1_25_plan, t1_25_komb),
                "test1_banko_genis_3000": (t1_30_plan, t1_30_komb),
                "test2_banko_iki_fav_2500": (t2_25_plan, t2_25_komb),
                "test2_banko_iki_fav_3000": (t2_30_plan, t2_30_komb),
                "test3_tip_genis_2500": (t3_25_plan, t3_25_komb),
                "test3_tip_genis_3000": (t3_30_plan, t3_30_komb),
                "ortakli_floor": (of_plan, of_komb),
                "flow5_floor": (f5_plan, f5_komb),
            }
            risk_plan, risk_widths = widen_risky(legs_r, cur_plan, tier, birim, prev_risk_widths, "bes")
            prev_risk_widths = risk_widths
            plans["risk5_5satir"] = (risk_plan, komb(risk_widths))

            for vn, (plan, kmb) in plans.items():
                st = variants[vn][ad]
                st["n"] += 1
                st["bedel"] += kmb * birim
                ds = dogru_say(plan, legs_r, wsets)
                st["dist"][ds] += 1
                if ds == 6:
                    st["hit"] += 1
                    st["hitset"].add(key)

            md = miss_details(cur_plan, legs_r, wsets)
            if len(md) == 1:
                miss_stats[ad]["miss1"] += 1
                _, p, r, wset = md[0]
                line = bes_line_of(r, wset)
                rank = best_rank(r, wset)
                if line:
                    miss_stats[ad]["miss1_bes"] += 1
                    miss_stats[ad]["line"][line] += 1
                    if rank and p["width"] < rank:
                        miss_stats[ad]["miss1_width"] += 1
                else:
                    miss_stats[ad]["line"]["5SATIR_DISI"] += 1
                miss_stats[ad]["rank"][rank or 0] += 1
                if p.get("banko_lider"):
                    miss_stats[ad]["banko"] += 1
                nseg = "14+" if r["n_at"] >= 14 else ("12-13" if r["n_at"] >= 12 else ("10-11" if r["n_at"] >= 10 else "<=9"))
                miss_stats[ad]["nseg"][nseg] += 1
                if len(miss_stats[ad]["examples"]) < 10:
                    wno = sorted(wset)[0]
                    miss_stats[ad]["examples"].append(
                        f"{key.iso} {key.hip} alt#{key.idx} K{r['kno']}: kazanan No:{wno}, "
                        f"5satir={line or 'DIŞI'}, ANA#{rank}, width={p['width']}, "
                        f"n_at={r['n_at']}, fark={r['fark']:.1f}, banko={bool(p.get('banko_lider'))}"
                    )

        # Grid: mevcut Ortaklı kuponu bozmadan, sadece eksik 5-satır atlarını ekle.
        # Simitçi ve Harbi mevcut kalır; "herhangi biri" = mevcut S/H + grid Ortaklı.
        _, _, _, cur_ort_plan, cur_ort_komb = current[2]
        for hi in GRID_BUDGETS:
            for prof_name, prof in GRID_PROFILES.items():
                for risk_mult in (0.0, 0.5, 1.0, 1.5):
                    for max_add in (1, 2, 99):
                        for protect in (False, True):
                            gkey = (hi, prof_name, risk_mult, max_add, protect)
                            gplan, gkomb = add_bes_to_existing_plan(
                                legs_r, cur_ort_plan, hi, birim, protect,
                                profile=prof, risk_mult=risk_mult, max_add_per_leg=max_add)
                            stg = grid_stats[gkey]
                            stg["n"] += 1
                            stg["bedel"] += gkomb * birim
                            ort_hit = plan_hit(gplan, legs_r, wsets)
                            if ort_hit:
                                stg["ort_hitset"].add(key)
                            if current_hits_by_idx[0] or current_hits_by_idx[1] or ort_hit:
                                stg["any_hitset"].add(key)

    lines = []
    lines.append("# Altılı 5 Satır Aktarım Derin Analizi")
    lines.append("")
    lines.append("Kaynak evren: `Harbi_Ganyan_Analiz` tahminleri + `_Altili.txt` tanımları + `Sonuclar JSON` sonuçları.")
    lines.append(f"`TahminSonuçları` TXT sanity: {txt_sum['files']} dosya, {txt_sum['total']} kupon satırı; dağılım: " +
                 ", ".join(f"{k}/6={txt_sum['dist'][k]}" for k in sorted(txt_sum["dist"], reverse=True)))
    lines.append(f"Toplam ölçülen altılı: **{theoretical['n']}**")
    lines.append("")
    lines.append("## 1. Teorik Üst Sınır: 5 Satır Altılıyı Zaten Kapsıyor mu?")
    lines.append("")
    lines.append(f"- 5 satırın 6 ayağın tamamında kazananı bulduğu altılı: **{theoretical['bes6']} / {theoretical['n']} ({pct(theoretical['bes6'], theoretical['n'])})**")
    lines.append(f"- 5 satırın en az 5 ayağı bulduğu altılı: **{theoretical['bes5']} / {theoretical['n']} ({pct(theoretical['bes5'], theoretical['n'])})**")
    lines.append("- 5 satır ayak dağılımı: " + ", ".join(f"{k}/6={theoretical['bes_dist'][k]}" for k in range(6, -1, -1) if theoretical["bes_dist"][k]))
    lines.append("")
    lines.append("Yorum: 5 satır 6/6 kapsadığı halde kupon 6/6 değilse problem tahmin değil, kupon aktarım/dağıtım problemidir.")
    lines.append("")
    lines.append("## 2. Mevcut Sistem: 5/6 Kalan Kuponların Anatomisi")
    lines.append("")
    for ad, _, _ in KUPON_TIERS:
        st = variants["mevcut"][ad]
        ms = miss_stats[ad]
        lines.append(f"### {ad}")
        lines.append(f"- Altılı: {st['n']} | 6/6: **{st['hit']} ({pct(st['hit'], st['n'])})** | Ortalama bedel: {st['bedel']/st['n']:.0f} TL")
        lines.append("- Doğru ayak dağılımı: " + ", ".join(f"{k}/6={st['dist'][k]}" for k in range(6, 0, -1) if st["dist"][k]))
        lines.append(f"- 5/6 kalan: **{ms['miss1']}**")
        if ms["miss1"]:
            lines.append(f"- 5/6 kalanların içinde kaçan kazanan 5 satırdaydı: **{ms['miss1_bes']} ({pct(ms['miss1_bes'], ms['miss1'])})**")
            lines.append(f"- Bunların ayak genişliği kazanan ANA-rankından küçüktü: **{ms['miss1_width']}**")
            lines.append("- Kaçan 5 satır slotu: " + ", ".join(f"{k}={v}" for k, v in ms["line"].most_common()))
            lines.append("- Kaçan ANA-rank: " + ", ".join(f"#{k}={v}" for k, v in sorted(ms["rank"].items())))
            lines.append("- Kaçan saha büyüklüğü: " + ", ".join(f"{k}={v}" for k, v in ms["nseg"].items()))
            lines.append(f"- Kaçan ayak banko liderdi: **{ms['banko']}**")
        lines.append("")

    lines.append("## 3. Alternatif Kuralların Backtest Sonucu")
    lines.append("")
    lines.append("Varyantlar:")
    lines.append("- `mevcut`: bugün üretimdeki iç içe kupon + mevcut tier policy.")
    lines.append("- `5satir_sira`: aynı ayak genişlikleri ve aynı bütçe; sadece seçilecek at sırası 5 satır öncelikli.")
    lines.append("- `banko070` / `banko080`: banko güven eşiği 0.50 yerine 0.70 / 0.80; zayıf banko ayakları 2 ata çıkar.")
    lines.append("- `banko070_5sira`: 0.70 banko eşiği + 5 satır öncelikli seçim sırası.")
    lines.append("- `bagimsiz`: Simitçi/Harbi/Ortaklı kuponları iç içe değil, kendi bütçesinde ayrı kurulur.")
    lines.append("- `bagimsiz_5sira`: bağımsız kupon + 5 satır öncelikli seçim.")
    lines.append("- `icice_5satir_2200`: Simitçi ⊆ Harbi ⊆ Ortaklı korunur; bütçe yettikçe eksik 5 satır atları eklenir.")
    lines.append("- `icice_5satir_2500`: aynı aktarım, Ortaklı üst bütçe 2200 yerine 2500 TL.")
    lines.append("- `ortakli_2500_sadece_ekle`: mevcut Ortaklı 2200 kuponu aynen korunur; 2500 TL'ye kadar yalnız eksik 5 satır atları eklenir.")
    lines.append("- `test1_banko_genis`: bir doğru banko yakalama varsayımına yaklaşmak için en güçlü ayak tek at; diğer ayaklara 5 satır aktarımı.")
    lines.append("- `test2_banko_iki_fav`: en güçlü ayak banko, ikinci güçlü ayak maksimum 2 favori; kalan ayaklar geniş.")
    lines.append("- `test3_tip_genis`: handikap/maiden/şartlı koşuları önce genişletir, sonra 5 satır aktarımı yapar.")
    lines.append("- `_korumali`: çok güçlü küçük saha bankosu tek at kalır; diğer eksik 5 satır atları eklenir.")
    lines.append("- `ortakli_floor`: Ortaklı kupona da Harbi'deki 5 satır tabanı açılır.")
    lines.append("- `flow5_floor`: akış eşiği 3 yerine 5; 5 satır tabanı daha agresif.")
    lines.append("- `risk5_5satir`: bütçe yettikçe riskli ayakları 5 ata yaklaştırır ve seçimi 5 satır öncelikli yapar.")
    lines.append("")
    for ad, _, _ in KUPON_TIERS:
        base = variants["mevcut"][ad]
        lines.append(f"### {ad}")
        lines.append("| Varyant | 6/6 | 5/6 | Ortalama bedel | Net 6/6 | Kazanılan | Kaybedilen |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for vn in variants:
            st = variants[vn][ad]
            gained = len(st["hitset"] - base["hitset"])
            lost = len(base["hitset"] - st["hitset"])
            net = st["hit"] - base["hit"]
            lines.append(
                f"| {vn} | {st['hit']}/{st['n']} ({pct(st['hit'], st['n'])}) | "
                f"{st['dist'][5]} | {st['bedel']/st['n']:.0f} TL | "
                f"{net:+d} | +{gained} | -{lost} |"
            )
        lines.append("")

    lines.append("## 3.1 Üç Kupondan Herhangi Biri Tuttu mu?")
    lines.append("")
    base_any = set().union(*(variants["mevcut"][ad]["hitset"] for ad, _, _ in KUPON_TIERS))
    lines.append("| Varyant | Herhangi biri 6/6 | Net | Kazanılan | Kaybedilen |")
    lines.append("|---|---:|---:|---:|---:|")
    for vn in variants:
        anyset = set().union(*(variants[vn][ad]["hitset"] for ad, _, _ in KUPON_TIERS))
        lines.append(
            f"| {vn} | {len(anyset)}/{theoretical['n']} ({pct(len(anyset), theoretical['n'])}) | "
            f"{len(anyset)-len(base_any):+d} | +{len(anyset-base_any)} | -{len(base_any-anyset)} |"
        )
    lines.append("")

    lines.append("## 3.1B Kullanıcı İstediği 3 Özel Test")
    lines.append("")
    lines.append("| Test | Herhangi biri 6/6 | Net | Kazanılan | Kaybedilen | Ortaklı ort. bedel |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    special_tests = [
        ("Test 1 - banko + diğer ayaklar geniş 2500", "test1_banko_genis_2500"),
        ("Test 1 - banko + diğer ayaklar geniş 3000", "test1_banko_genis_3000"),
        ("Test 2 - banko + başka ayak 2 favori 2500", "test2_banko_iki_fav_2500"),
        ("Test 2 - banko + başka ayak 2 favori 3000", "test2_banko_iki_fav_3000"),
        ("Test 3 - handikap/maiden/şartlı geniş 2500", "test3_tip_genis_2500"),
        ("Test 3 - handikap/maiden/şartlı geniş 3000", "test3_tip_genis_3000"),
    ]
    for label, vn in special_tests:
        anyset = set().union(*(variants[vn][ad]["hitset"] for ad, _, _ in KUPON_TIERS))
        ort = variants[vn]["Ortaklı 6'lı"]
        lines.append(
            f"| {label} | {len(anyset)}/{theoretical['n']} ({pct(len(anyset), theoretical['n'])}) | "
            f"{len(anyset)-len(base_any):+d} | +{len(anyset-base_any)} | -{len(base_any-anyset)} | "
            f"{ort['bedel']/ort['n']:.0f} TL |"
        )
    lines.append("")

    lines.append("## 3.1A Grid Test: Ortaklı Bütçe + 5 Satır Aktarım Oranlaması")
    lines.append("")
    lines.append("Bu grid mevcut Ortaklı kuponu bozmadan yalnız eksik 5 satır atlarını ekler. Simitçi ve Harbi aynen kalır.")
    lines.append("Test edilenler: bütçe 2200/2300/2400/2500/2600/2800/3000, 5 farklı slot profili, risk katsayısı 0/0.5/1/1.5, ayak başı ekleme limiti 1/2/sınırsız, banko koruma açık/kapalı.")
    lines.append("")
    grid_rows = []
    for gkey, stg in grid_stats.items():
        hi, prof_name, risk_mult, max_add, protect = gkey
        anyset = stg["any_hitset"]
        ortset = stg["ort_hitset"]
        grid_rows.append({
            "key": gkey,
            "any": len(anyset),
            "ort": len(ortset),
            "net": len(anyset) - len(base_any),
            "gained": len(anyset - base_any),
            "lost": len(base_any - anyset),
            "bedel": stg["bedel"] / stg["n"] if stg["n"] else 0,
        })
    grid_rows.sort(key=lambda r: (r["net"], r["any"], -r["lost"], -r["bedel"]), reverse=True)
    best_grid = grid_rows[0] if grid_rows else None
    lines.append("| Sıra | Bütçe | Profil | Risk | Ayak ek limiti | Banko koruma | Herhangi biri | Ortaklı | Ort. bedel | Net | Kazanılan | Kaybedilen |")
    lines.append("|---:|---:|---|---:|---:|---|---:|---:|---:|---:|---:|---:|")
    for i, row in enumerate(grid_rows[:15], 1):
        hi, prof_name, risk_mult, max_add, protect = row["key"]
        lim = "sınırsız" if max_add == 99 else str(max_add)
        lines.append(
            f"| {i} | {hi} | {prof_name} | {risk_mult:g} | {lim} | {'evet' if protect else 'hayır'} | "
            f"{row['any']}/{theoretical['n']} ({pct(row['any'], theoretical['n'])}) | "
            f"{row['ort']}/{theoretical['n']} | {row['bedel']:.0f} TL | "
            f"{row['net']:+d} | +{row['gained']} | -{row['lost']} |"
        )
    if best_grid:
        hi, prof_name, risk_mult, max_add, protect = best_grid["key"]
        lines.append("")
        lines.append(f"En iyi grid: bütçe **{hi} TL**, profil **{prof_name}**, risk katsayısı **{risk_mult:g}**, "
                     f"ayak ek limiti **{'sınırsız' if max_add == 99 else max_add}**, "
                     f"banko koruma **{'açık' if protect else 'kapalı'}**.")
    budget_2500_rows = [r for r in grid_rows if r["key"][0] <= 2500]
    if budget_2500_rows:
        b2500 = budget_2500_rows[0]
        hi, prof_name, risk_mult, max_add, protect = b2500["key"]
        lines.append(f"2500 TL ve altı en iyi grid: bütçe **{hi} TL**, profil **{prof_name}**, "
                     f"risk katsayısı **{risk_mult:g}**, ayak ek limiti **{'sınırsız' if max_add == 99 else max_add}**, "
                     f"banko koruma **{'açık' if protect else 'kapalı'}** -> "
                     f"{b2500['any']}/{theoretical['n']} ({pct(b2500['any'], theoretical['n'])}), "
                     f"net {b2500['net']:+d}, kayıp {b2500['lost']}.")
    lines.append("")

    lines.append("## 3.2 Tarih Segmenti Kontrolü")
    lines.append("")
    lines.append("Ana adaylar için dönem kırılımı. Amaç tek döneme aşırı uyumu ayırmak.")
    lines.append("")
    best_grid_key = best_grid["key"] if best_grid else None
    lines.append("| Dönem | Mevcut herhangi biri | Sadece ekle 2500 | En iyi grid | Grid fark | Bağımsız referans | 5 satır teorik 6/6 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for per in ["Şubat-Mart", "Nisan", "Mayıs 1-15", "Mayıs 16-30"]:
        keys = {key for key, *_ in universe if period_of(key.iso) == per}
        cur_any = set().union(*(variants["mevcut"][ad]["hitset"] for ad, _, _ in KUPON_TIERS)) & keys
        safe_any = set().union(*(variants["ortakli_2500_sadece_ekle"][ad]["hitset"] for ad, _, _ in KUPON_TIERS)) & keys
        grid_any = (grid_stats[best_grid_key]["any_hitset"] & keys) if best_grid_key else set()
        ind_any = set().union(*(variants["bagimsiz"][ad]["hitset"] for ad, _, _ in KUPON_TIERS)) & keys
        th = period_theory[per]
        lines.append(
            f"| {per} | {len(cur_any)}/{len(keys)} ({pct(len(cur_any), len(keys))}) | "
            f"{len(safe_any)}/{len(keys)} ({pct(len(safe_any), len(keys))}) | "
            f"{len(grid_any)}/{len(keys)} ({pct(len(grid_any), len(keys))}) | "
            f"{len(grid_any)-len(cur_any):+d} | "
            f"{len(ind_any)}/{len(keys)} ({pct(len(ind_any), len(keys))}) | "
            f"{th['bes6']}/{th['n']} ({pct(th['bes6'], th['n'])}) |"
        )
    lines.append("")

    lines.append("## 4. Örnek 5/6 Kaçışlar")
    lines.append("")
    for ad, _, _ in KUPON_TIERS:
        lines.append(f"### {ad}")
        for ex in miss_stats[ad]["examples"]:
            lines.append(f"- {ex}")
        lines.append("")

    lines.append("## 5. Algoritmik Karar")
    lines.append("")
    lines.append("1. Üretim değişikliği sadece pozitif holdout/backtest veren varyantla yapılmalı; negatif varyantlar üretime alınmamalı.")
    lines.append("2. Kullanıcı ürün kuralı gereği üretim adayı `bagimsiz` değil; Simitçi ⊆ Harbi ⊆ Ortaklı kuralını koruyan `icice_5satir_*` varyantlarıdır.")
    lines.append("3. En güvenli üretim adayı `ortakli_2500_sadece_ekle` olmalıdır: mevcut Ortaklı kuponu bozmaz, sadece bütçe artışını eksik 5 satır atlarına harcar.")
    lines.append("4. Banko eşiği varyantları tek başına negatifse banko güven eşiği artırılmamalı; bunun yerine üst kuponda eksik 5 satır atı bütçe-içi eklenmelidir.")
    lines.append("5. Kör `flow5_floor` gibi agresif akış genişletmeleri kazandırdığı kuponlardan fazlasını kaybettiriyorsa üretime alınmamalı.")
    lines.append("")

    open(OUT, "w", encoding="utf-8").write("\n".join(lines))
    print(f"Rapor yazıldı: {OUT}")
    preview = "\n".join(lines[:80])
    print(preview.encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
