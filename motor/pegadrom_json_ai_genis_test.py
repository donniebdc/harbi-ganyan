# -*- coding: utf-8 -*-
"""
Pegadrom JSON AI geniş kapsamlı test.

Kaynaklar:
- Harbi_Ganyan_Analiz/<GG-AA-YYYY>/*_Tahminler.txt
- CSV Sonuçlar
- pegadrom_skorlar.json

Üretim algoritmasını değiştirmez. Holdout kontrollü rapor üretir:
pegadrom_json_ai_genis_test_raporu.md
"""
from __future__ import annotations

import io
import itertools
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from altili_lib import BASE, norm_hip, load_all_csv, winning_set, birim_fiyat
from altili_kupon_v2 import build_tier, KUPON_TIERS


ROOT = Path(BASE)
ANALIZ_ROOT = ROOT / "Harbi_Ganyan_Analiz"
PEG_JSON = ROOT / "pegadrom_skorlar.json"
OUT = ROOT / "pegadrom_json_ai_genis_test_raporu.md"

START = "2026-04-01"
TRAIN_END = "2026-05-15"
HOLDOUT_START = "2026-05-16"
END = "2026-05-28"

STEP = 0.05
TOP_SINGLE_FOR_COMBOS = 6
TOP_TRIPLE_POOL = 4
TOP_CANDIDATES_FOR_ALTILI = 8
TOP_GRID_HOLDOUT_EVAL = 200
BANKO_THRESHOLDS = [50, 55, 60, 65, 70, 75, 80, 85]

AI_FIELDS = [
    ("ai.model", "ai", "model"),
    ("ai.veri", "ai", "veri"),
    ("ai.galop", "ai", "galop"),
    ("ai.hiz", "ai", "hiz"),
    ("ai.pist_mesafe", "ai", "pist_mesafe"),
]
GALOP_FIELDS = [
    ("galop.skor", "galop", "skor"),
    ("galop.son", "galop", "son"),
    ("galop.en_iyi", "galop", "en_iyi"),
    ("galop.tempo", "galop", "tempo"),
    ("galop.istikrar", "galop", "istikrar"),
    ("galop.pist_uyum", "galop", "pist_uyum"),
    ("galop.kayit", "galop", "kayit"),
    ("galop.galop_sayisi", "galop", "galop_sayisi"),
]


def pct(x, n, digits=1):
    return "-" if not n else f"%{100*x/n:.{digits}f}"


def tr_date_to_iso(value: str) -> str:
    return datetime.strptime(value, "%d.%m.%Y").strftime("%Y-%m-%d")


def dir_date_to_iso(value: str) -> str | None:
    try:
        return datetime.strptime(value, "%d-%m-%Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def in_scope(iso: str) -> bool:
    return START <= iso <= END


def split_name(iso: str) -> str:
    if iso <= TRAIN_END:
        return "train"
    if HOLDOUT_START <= iso <= END:
        return "holdout"
    return "out"


def seg_n(n):
    if n <= 9:
        return "<=9"
    if n <= 13:
        return "10-13"
    return "14+"


def seg_dist(m):
    if m <= 1400:
        return "kisa"
    if m <= 1800:
        return "orta"
    return "uzun"


def parse_tahmin_files():
    races = {}
    files = []
    if not ANALIZ_ROOT.exists():
        return races, files
    for date_dir in sorted(ANALIZ_ROOT.iterdir()):
        if not date_dir.is_dir():
            continue
        iso = dir_date_to_iso(date_dir.name)
        if not iso or not in_scope(iso):
            continue
        for path in date_dir.glob("*_Tahminler.txt"):
            files.append(path)
            _parse_tahmin_file(path, races)
    return races, files


def _parse_tahmin_file(path: Path, races: dict):
    cur = None
    bes_names = None
    name_to_no = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip("\n")
        if line.startswith("KO:"):
            if cur:
                _finish_race(cur, bes_names, name_to_no, races)
            p = line[3:].split("|")
            if len(p) < 8:
                cur = None
                continue
            try:
                kno = int(p[0])
                iso = tr_date_to_iso(p[2])
            except Exception:
                cur = None
                continue
            cur = {
                "kno": kno,
                "hip": norm_hip(p[1]),
                "hip_disp": p[1],
                "tarih": p[2],
                "iso": iso,
                "ag": p[3],
                "alt": p[4],
                "pist": p[5],
                "mesafe": int(p[6]) if p[6].isdigit() else 0,
                "saat": p[7],
                "kaynak": p[8] if len(p) > 8 else "",
                "atlar": [],
                "ekuri": [],
                "file": str(path),
            }
            bes_names = None
            name_to_no = {}
        elif cur and line.startswith("EKURI:"):
            cur["ekuri"] = []
            for grp in line[6:].strip().split("|"):
                nums = {int(x) for x in grp.split("-") if x.strip().isdigit()}
                if len(nums) >= 2:
                    cur["ekuri"].append(nums)
        elif cur and line.startswith("5SATIR:"):
            vals = {}
            for tok in line[7:].split("|"):
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    vals[k] = v
            bes_names = [vals.get(k) for k in ("FAV", "SUR", "YAZ", "BOM", "HAR")]
            cur["bes_names"] = vals
        elif cur and line.startswith("ATNO:"):
            d = {}
            for tok in line.split("|"):
                if ":" in tok:
                    k, v = tok.split(":", 1)
                    d[k] = v
            try:
                a = {
                    "at_no": int(d.get("ATNO", 0)),
                    "at": d.get("AT", ""),
                    "ana": float(d.get("ANA", 0) or 0),
                    "peg_galop": float(d.get("PEGGLP", 0) or 0),
                    "peg_model": float(d.get("PEGMOD", 0) or 0),
                    "flow_rank": int(float(d.get("AKIS", 0) or 0)),
                    "flow_score": float(d.get("AKS", 0) or 0),
                    "G": float(d.get("G", 0) or 0),
                    "Gn": float(d.get("Gn", 0) or 0),
                    "S": float(d.get("S", 0) or 0),
                    "AGF": float(d.get("AGF", 0) or 0),
                    "JOK": float(d.get("JOK", 0) or 0),
                }
            except Exception:
                continue
            cur["atlar"].append(a)
            name_to_no[a["at"]] = a["at_no"]
    if cur:
        _finish_race(cur, bes_names, name_to_no, races)


def _finish_race(cur, bes_names, name_to_no, races):
    cur["atlar"].sort(key=lambda a: a["ana"], reverse=True)
    cur["n_at"] = len(cur["atlar"])
    cur["fark"] = cur["atlar"][0]["ana"] - cur["atlar"][1]["ana"] if len(cur["atlar"]) >= 2 else 100
    cur["order"] = [a["at_no"] for a in cur["atlar"]]
    cur["at_by_no"] = {a["at_no"]: a for a in cur["atlar"]}
    bes = []
    if bes_names:
        for nm in bes_names:
            if nm in name_to_no:
                bes.append(name_to_no[nm])
    cur["bes"] = bes
    races[(cur["iso"], cur["hip"], cur["kno"])] = cur


def load_peg_json():
    if not PEG_JSON.exists():
        return {}
    return json.loads(PEG_JSON.read_text(encoding="utf-8"))


def attach_json_features(race, peg_json):
    key = f"{race['iso']}|{race['hip']}|{race['kno']}"
    pj = peg_json.get(key) or {}
    ai = pj.get("ai") or {}
    gal = pj.get("galop") or {}
    matched = 0
    for a in race["atlar"]:
        no = str(a["at_no"])
        if no in ai or no in gal:
            matched += 1
        row_ai = ai.get(no) or {}
        row_g = gal.get(no) or {}
        for label, _, field in AI_FIELDS:
            a[f"json_{label}"] = float(row_ai.get(field) or 0)
            a[f"json_{label}__present"] = 1 if field in row_ai and row_ai.get(field) not in (None, "") else 0
        for label, _, field in GALOP_FIELDS:
            a[f"json_{label}"] = float(row_g.get(field) or 0)
            a[f"json_{label}__present"] = 1 if field in row_g and row_g.get(field) not in (None, "") else 0
    race["json_key"] = key
    race["json_matched_at"] = matched
    return matched > 0


def norm_values(atlar, key, neutral_zero=None):
    vals = []
    for a in atlar:
        v = a.get(key, 0)
        if neutral_zero is not None and not v:
            v = neutral_zero
        vals.append(float(v))
    if not vals:
        return {}
    mn, mx = min(vals), max(vals)
    if mx == mn:
        return {a["at_no"]: 100.0 for a in atlar}
    return {a["at_no"]: (float(v) - mn) / (mx - mn) * 100.0 for a, v in zip(atlar, vals)}


def feature_norms(race):
    atlar = race["atlar"]
    norms = {
        "AGF": norm_values(atlar, "AGF"),
        "G": norm_values(atlar, "G"),
        "flow": norm_values(atlar, "flow_score"),
        "peg_galop_neutral": norm_values(atlar, "peg_galop", neutral_zero=50.0),
        "JOK": {a["at_no"]: a.get("JOK", 0) * 100 for a in atlar},
    }
    for label, _, _ in AI_FIELDS + GALOP_FIELDS:
        key = f"json_{label}"
        norms[f"{label}|raw_zero"] = norm_values(atlar, key)
        norms[f"{label}|neutral_missing"] = norm_values(atlar, key, neutral_zero=50.0)
        present_key = f"{key}__present"
        norms[f"{label}|missing_indicator"] = {a["at_no"]: 100.0 * (1 - a.get(present_key, 0)) for a in atlar}
    race["_norms"] = norms
    return norms


def base_score(race, no):
    norms = race["_norms"]
    agf_var = max(a["AGF"] for a in race["atlar"]) > 0
    g_var = max(a["G"] for a in race["atlar"]) > 0
    if agf_var:
        score = norms["AGF"].get(no, 0) * 0.40 + norms["flow"].get(no, 50) * 0.50 + norms["peg_galop_neutral"].get(no, 50) * 0.10
    elif g_var:
        score = norms["G"].get(no, 0) * 0.30 + norms["flow"].get(no, 50) * 0.70
    else:
        score = norms["flow"].get(no, 50)
    if 10 <= race["n_at"] <= 13:
        score += norms["JOK"].get(no, 0) * 0.20
    return score


def variant_score(race, no, variant):
    if variant["kind"] == "baseline":
        return base_score(race, no)
    if variant["kind"] == "weighted":
        norms = race["_norms"]
        market = "AGF" if max(a["AGF"] for a in race["atlar"]) > 0 else ("G" if max(a["G"] for a in race["atlar"]) > 0 else None)
        score = 0.0
        if market:
            score += norms[market].get(no, 0) * variant["w_market"]
            score += norms["flow"].get(no, 50) * variant["w_flow"]
            for fname, w in variant["features"]:
                score += norms[fname].get(no, 50) * w
        else:
            score += norms["flow"].get(no, 50)
        if 10 <= race["n_at"] <= 13:
            score += norms["JOK"].get(no, 0) * 0.20
        return score
    raise ValueError(variant["kind"])


def order_for_variant(race, variant):
    return [
        no for no, _ in sorted(
            ((a["at_no"], variant_score(race, a["at_no"], variant)) for a in race["atlar"]),
            key=lambda x: x[1],
            reverse=True,
        )
    ]


def five_from_order(race, order, har_rule="baseline", har_feature=None):
    top4 = list(order[:4])
    if len(order) <= 4:
        return top4
    candidates = [x for x in order[4:] if x not in top4]
    har = None
    if candidates:
        if har_rule == "feature" and har_feature:
            vals = race["_norms"].get(har_feature, {})
            har = max(candidates, key=lambda no: vals.get(no, -1))
        elif race["n_at"] >= 14:
            flow_rank = {a["at_no"]: a.get("flow_rank", 0) for a in race["atlar"]}
            flow_candidates = [no for no in candidates if flow_rank.get(no, 0) > 0]
            har = min(flow_candidates, key=lambda no: flow_rank[no]) if flow_candidates else candidates[0]
        else:
            har = candidates[0]
    return top4 + ([har] if har else [])


def eval_five(races, variant, har_rule="baseline", har_feature=None):
    c = Counter()
    segs = defaultdict(Counter)
    by_track = defaultdict(Counter)
    by_group = defaultdict(Counter)
    by_dist = defaultdict(Counter)
    har = Counter()
    for race in races:
        order = order_for_variant(race, variant)
        five = five_from_order(race, order, har_rule, har_feature)
        wset = race["wset"]
        c["n"] += 1
        for g in (1, 3, 4, 5):
            if set(order[:g]) & wset:
                c[f"i{g}"] += 1
        if set(five) & wset:
            c["bes"] += 1
        buckets = [
            (segs, seg_n(race["n_at"])),
            (by_track, race["pist"]),
            (by_group, race["ag"]),
            (by_dist, seg_dist(race["mesafe"])),
        ]
        for bucket, key in buckets:
            bucket[key]["n"] += 1
            for g in (1, 3, 4, 5):
                if set(order[:g]) & wset:
                    bucket[key][f"i{g}"] += 1
            if set(five) & wset:
                bucket[key]["bes"] += 1
        if not (set(order[:4]) & wset):
            har["top4_disi"] += 1
            if set(five[4:]) & wset:
                har["har_yakaladi"] += 1
            if race["n_at"] >= 14:
                har["top4_disi_14"] += 1
                if set(five[4:]) & wset:
                    har["har_yakaladi_14"] += 1
    return {"five": c, "segs": segs, "tracks": by_track, "groups": by_group, "dists": by_dist, "har": har}


def rank_of_feature(race, fname, winner):
    vals = race["_norms"].get(fname, {})
    if winner not in vals:
        return None
    order = [no for no, _ in sorted(vals.items(), key=lambda x: x[1], reverse=True)]
    if winner not in order:
        return None
    return order.index(winner) + 1


def eval_single_signals(races, feature_names):
    out = {}
    for fname in feature_names:
        c = Counter()
        div = Counter()
        for race in races:
            rank = rank_of_feature(race, fname, race["winner"])
            if rank is None:
                continue
            c["n"] += 1
            for g in (1, 3, 4, 5):
                if rank <= g:
                    c[f"i{g}"] += 1
            vals = race["_norms"].get(fname, {})
            order = [no for no, _ in sorted(vals.items(), key=lambda x: x[1], reverse=True)]
            sig_top2 = set(order[:2])
            base5 = set(race["order"][:5])
            agf_vals = race["_norms"].get("AGF", {})
            agf_order = [no for no, _ in sorted(agf_vals.items(), key=lambda x: x[1], reverse=True)]
            flow_order = sorted(
                [a for a in race["atlar"] if a.get("flow_rank", 0) > 0],
                key=lambda a: a["flow_rank"],
            )
            flow5 = {a["at_no"] for a in flow_order[:5]}
            if sig_top2 - base5:
                div["top2_base5_disi"] += len(sig_top2 - base5)
                if race["winner"] in sig_top2 - base5:
                    div["top2_base5_disi_win"] += 1
            if agf_order:
                agf_bottom = set(agf_order[len(agf_order)//2:])
                cand = sig_top2 & agf_bottom
                if cand:
                    div["top2_agf_alt_yari"] += len(cand)
                    if race["winner"] in cand:
                        div["top2_agf_alt_yari_win"] += 1
            cand = sig_top2 - flow5
            if cand:
                div["top2_flow5_disi"] += len(cand)
                if race["winner"] in cand:
                    div["top2_flow5_disi_win"] += 1
        out[fname] = {"rank": c, "div": div}
    return out


def metric_score(res):
    f = res["five"]
    if not f["n"]:
        return -1
    # Primary 5 satir, then 14+ 5 satir, then ilk4.
    s14 = res["segs"].get("14+", Counter())
    bes = f["bes"] / f["n"]
    seg14 = (s14["bes"] / s14["n"]) if s14["n"] else 0
    i4 = f["i4"] / f["n"]
    return bes * 1000 + seg14 * 100 + i4


def weight_partitions(k):
    # Components: market, flow, k features. Sum 20 units.
    # Included JSON features must be positive; otherwise pair/triple grids duplicate
    # lower-dimensional variants and inflate runtime/overfit surface.
    total = int(round(1.0 / STEP))
    min_market = int(round(0.20 / STEP))
    min_flow = int(round(0.25 / STEP))
    min_feature = 1
    parts = []
    def rec(pos, rem, cur):
        if pos == k + 2:
            if rem == 0:
                parts.append(cur[:])
            return
        minv = min_market if pos == 0 else (min_flow if pos == 1 else min_feature)
        for v in range(minv, rem + 1):
            if rem - v < 0:
                continue
            cur.append(v)
            rec(pos + 1, rem - v, cur)
            cur.pop()
    rec(0, total, [])
    return [[x * STEP for x in p] for p in parts]


def variant_name(variant):
    if variant["kind"] == "baseline":
        return "baseline"
    fs = "+".join(f"{name}:{w:.2f}" for name, w in variant["features"])
    return f"M:{variant['w_market']:.2f}|F:{variant['w_flow']:.2f}|{fs}"


def run_weight_grid(train, holdout, feature_names):
    baseline = {"kind": "baseline", "name": "baseline"}
    candidates = []

    def eval_variant_full(v):
        train_res = eval_five(train, v)
        hold_res = eval_five(holdout, v)
        return {"variant": v, "train": train_res, "holdout": hold_res, "train_score": metric_score(train_res)}

    def eval_variant_train(v):
        train_res = eval_five(train, v)
        return {"variant": v, "train": train_res, "train_score": metric_score(train_res)}

    base_eval = eval_variant_full(baseline)
    # Singles full.
    for fname in feature_names:
        for weights in weight_partitions(1):
            v = {"kind": "weighted", "w_market": weights[0], "w_flow": weights[1], "features": [(fname, weights[2])]}
            candidates.append(eval_variant_train(v))

    candidates.sort(key=lambda x: x["train_score"], reverse=True)
    top_single_features = []
    for row in candidates:
        fname = row["variant"]["features"][0][0]
        if fname not in top_single_features:
            top_single_features.append(fname)
        if len(top_single_features) >= TOP_SINGLE_FOR_COMBOS:
            break

    # Pairs from strong singles.
    for combo in itertools.combinations(top_single_features, 2):
        for weights in weight_partitions(2):
            v = {"kind": "weighted", "w_market": weights[0], "w_flow": weights[1],
                 "features": [(combo[0], weights[2]), (combo[1], weights[3])]}
            candidates.append(eval_variant_train(v))

    # Triples from smaller pool.
    for combo in itertools.combinations(top_single_features[:TOP_TRIPLE_POOL], 3):
        for weights in weight_partitions(3):
            v = {"kind": "weighted", "w_market": weights[0], "w_flow": weights[1],
                 "features": [(combo[0], weights[2]), (combo[1], weights[3]), (combo[2], weights[4])]}
            candidates.append(eval_variant_train(v))

    candidates.sort(key=lambda x: x["train_score"], reverse=True)
    for row in candidates[:TOP_GRID_HOLDOUT_EVAL]:
        row["holdout"] = eval_five(holdout, row["variant"])
    return base_eval, candidates, top_single_features


def run_har_tests(train, holdout, feature_names):
    baseline = {"kind": "baseline", "name": "baseline"}
    rows = []
    for fname in feature_names:
        tr = eval_five(train, baseline, har_rule="feature", har_feature=fname)
        ho = eval_five(holdout, baseline, har_rule="feature", har_feature=fname)
        rows.append({"feature": fname, "train": tr, "holdout": ho, "train_har": tr["har"]["har_yakaladi"] / (tr["har"]["top4_disi"] or 1)})
    rows.sort(key=lambda x: x["train_har"], reverse=True)
    return rows


def legs_for_variant(races_by_key, iso, hip, leg_knos, variant):
    legs = []
    for kno in leg_knos:
        r = races_by_key.get((iso, hip, kno))
        if not r:
            return None
        order = order_for_variant(r, variant)
        by_no = r["at_by_no"]
        atlar = []
        for no in order:
            src = by_no[no]
            atlar.append({
                "at_no": no,
                "at": src["at"],
                "ana": variant_score(r, no, variant),
                "agf": src.get("AGF", 0),
                "flow_rank": src.get("flow_rank", 0),
            })
        fark = atlar[0]["ana"] - atlar[1]["ana"] if len(atlar) >= 2 else 100
        legs.append({"kno": kno, "atlar": atlar, "n_at": r["n_at"], "fark": fark, "ekuri": r.get("ekuri") or []})
    return legs


def eval_altili(races_by_key, csvs, variants):
    cal = None
    out = {}
    for vname, variant in variants:
        tiers = {ad: Counter() for ad, _, _ in KUPON_TIERS}
        tier_cost = defaultdict(float)
        tier_ret = defaultdict(float)
        anyhit = Counter()
        banko = {ad: Counter() for ad, _, _ in KUPON_TIERS}
        for (iso, hip), c in csvs.items():
            if not (HOLDOUT_START <= iso <= END):
                continue
            for alt in c["altililar"]:
                legs = legs_for_variant(races_by_key, iso, hip, alt["legs"], variant)
                if not legs:
                    continue
                wsets = {kno: winning_set(c, kno) for kno in alt["legs"]}
                if any(not wsets[kno] for kno in alt["legs"]):
                    continue
                anyhit["n"] += 1
                unit = birim_fiyat(hip)
                ticket_any = False
                for tier in KUPON_TIERS:
                    ad, lo, hi = tier
                    _, _, _, plan, komb = build_tier(legs, tier, unit, cal, 0.50)
                    tiers[ad]["n"] += 1
                    tier_cost[ad] += komb * unit
                    hit = all(({a["at_no"] for a in p["secilen"]} & wsets[p["kno"]]) for p in plan)
                    if hit:
                        tiers[ad]["hit"] += 1
                        tier_ret[ad] += alt["odeme"]
                        ticket_any = True
                    bl = next((p for p in plan if p.get("banko_lider")), None)
                    if bl:
                        banko[ad]["n"] += 1
                        if {a["at_no"] for a in bl["secilen"]} & wsets[bl["kno"]]:
                            banko[ad]["hit"] += 1
                        if bl["width"] == 1 and not ({a["at_no"] for a in bl["secilen"]} & wsets[bl["kno"]]):
                            banko[ad]["wrong_single"] += 1
                if ticket_any:
                    anyhit["hit"] += 1
        out[vname] = {"tiers": tiers, "cost": tier_cost, "return": tier_ret, "anyhit": anyhit, "banko": banko}
    return out


def eval_banko_filters(holdout, feature_names):
    baseline = {"kind": "baseline", "name": "baseline"}
    rows = []
    for fname in feature_names:
        vals = []
        for th in BANKO_THRESHOLDS:
            c = Counter()
            for race in holdout:
                order = order_for_variant(race, baseline)
                leader = order[0]
                fval = race["_norms"].get(fname, {}).get(leader, 0)
                if fval < th:
                    continue
                c["n"] += 1
                if leader in race["wset"]:
                    c["hit"] += 1
            vals.append((th, c))
        best = max(vals, key=lambda x: (x[1]["hit"] / (x[1]["n"] or 1), x[1]["n"]))
        rows.append({"feature": fname, "best_threshold": best[0], "stat": best[1]})
    rows.sort(key=lambda x: (x["stat"]["hit"] / (x["stat"]["n"] or 1), x["stat"]["n"]), reverse=True)
    return rows


def summarize_eval_row(label, res):
    f = res["five"]
    s14 = res["segs"].get("14+", Counter())
    h = res["har"]
    return {
        "label": label,
        "n": f["n"],
        "i1": f["i1"],
        "i3": f["i3"],
        "i4": f["i4"],
        "i5": f["i5"],
        "bes": f["bes"],
        "seg14_n": s14["n"],
        "seg14_bes": s14["bes"],
        "har_n": h["top4_disi"],
        "har_hit": h["har_yakaladi"],
        "har14_n": h["top4_disi_14"],
        "har14_hit": h["har_yakaladi_14"],
    }


def add_table(lines, headers, rows):
    def cell(x):
        return str(x).replace("|", "\\|")
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(cell(x) for x in row) + " |")


def render_report(res):
    lines = []
    lines.append("# Pegadrom JSON AI Bloğu Geniş Kapsamlı Test Raporu")
    lines.append("")
    lines.append("Bu rapor üretim algoritmasını değiştirmeden, günlük `Harbi_Ganyan_Analiz` tahmin dosyaları üzerinden çalıştırılmıştır.")
    lines.append("")
    lines.append("## Veri Kapsamı")
    lines.append(f"- Tahmin dosyası: {res['tahmin_file_count']}")
    lines.append(f"- Parse edilen koşu: {res['race_count']}")
    lines.append(f"- JSON + CSV + sonuç eşleşen koşu: {len(res['eval_races'])}")
    lines.append(f"- Eğitim: {START} - {TRAIN_END} ({len(res['train'])} koşu)")
    lines.append(f"- Holdout: {HOLDOUT_START} - {END} ({len(res['holdout'])} koşu)")
    lines.append(f"- pegadrom_skorlar.json koşu: {res['peg_json_count']}")
    lines.append("")

    base_train = summarize_eval_row("baseline train", res["base_eval"]["train"])
    base_hold = summarize_eval_row("baseline holdout", res["base_eval"]["holdout"])
    lines.append("## Baseline")
    add_table(lines, ["Evren", "n", "İlk1", "İlk3", "İlk4", "İlk5", "5 satır", "14+ 5 satır", "HAR", "HAR 14+"], [
        ["train", base_train["n"], pct(base_train["i1"], base_train["n"]), pct(base_train["i3"], base_train["n"]),
         pct(base_train["i4"], base_train["n"]), pct(base_train["i5"], base_train["n"]), pct(base_train["bes"], base_train["n"]),
         pct(base_train["seg14_bes"], base_train["seg14_n"]), f"{base_train['har_hit']}/{base_train['har_n']} {pct(base_train['har_hit'], base_train['har_n'])}",
         f"{base_train['har14_hit']}/{base_train['har14_n']} {pct(base_train['har14_hit'], base_train['har14_n'])}"],
        ["holdout", base_hold["n"], pct(base_hold["i1"], base_hold["n"]), pct(base_hold["i3"], base_hold["n"]),
         pct(base_hold["i4"], base_hold["n"]), pct(base_hold["i5"], base_hold["n"]), pct(base_hold["bes"], base_hold["n"]),
         pct(base_hold["seg14_bes"], base_hold["seg14_n"]), f"{base_hold['har_hit']}/{base_hold['har_n']} {pct(base_hold['har_hit'], base_hold['har_n'])}",
         f"{base_hold['har14_hit']}/{base_hold['har14_n']} {pct(base_hold['har14_hit'], base_hold['har14_n'])}"],
    ])
    lines.append("")

    lines.append("## Tekil JSON Sinyal Gücü - Holdout")
    rows = []
    for fname, data in sorted(res["single_holdout"].items(), key=lambda kv: (kv[1]["rank"]["i5"] / (kv[1]["rank"]["n"] or 1)), reverse=True):
        c = data["rank"]
        d = data["div"]
        rows.append([
            fname, c["n"], pct(c["i1"], c["n"]), pct(c["i3"], c["n"]), pct(c["i4"], c["n"]), pct(c["i5"], c["n"]),
            f"{d['top2_base5_disi_win']}/{d['top2_base5_disi']} {pct(d['top2_base5_disi_win'], d['top2_base5_disi'])}",
            f"{d['top2_agf_alt_yari_win']}/{d['top2_agf_alt_yari']} {pct(d['top2_agf_alt_yari_win'], d['top2_agf_alt_yari'])}",
            f"{d['top2_flow5_disi_win']}/{d['top2_flow5_disi']} {pct(d['top2_flow5_disi_win'], d['top2_flow5_disi'])}",
        ])
    add_table(lines, ["Sinyal", "n", "İlk1", "İlk3", "İlk4", "İlk5", "Bizim 5 dışı top2 win", "AGF alt-yarı win", "Akış5 dışı win"], rows[:30])
    lines.append("")

    lines.append("## Ağırlık Grid Sonuçları")
    top_rows = []
    base_bes = base_hold["bes"] / (base_hold["n"] or 1)
    base14 = base_hold["seg14_bes"] / (base_hold["seg14_n"] or 1)
    for row in res["grid_candidates"][:20]:
        tr = summarize_eval_row("", row["train"])
        ho = summarize_eval_row("", row["holdout"])
        ho_bes = ho["bes"] / (ho["n"] or 1)
        ho14 = ho["seg14_bes"] / (ho["seg14_n"] or 1)
        top_rows.append([
            variant_name(row["variant"]),
            pct(tr["bes"], tr["n"]),
            pct(tr["seg14_bes"], tr["seg14_n"]),
            pct(ho["bes"], ho["n"]),
            f"{(ho_bes-base_bes)*100:+.2f} puan",
            pct(ho["seg14_bes"], ho["seg14_n"]),
            f"{(ho14-base14)*100:+.2f} puan",
            f"{ho['har_hit']}/{ho['har_n']} {pct(ho['har_hit'], ho['har_n'])}",
        ])
    add_table(lines, ["Aday", "Train 5", "Train 14+", "Holdout 5", "Δ5", "Holdout 14+", "Δ14+", "Holdout HAR"], top_rows)
    lines.append("")

    best_hold = max(res["grid_candidates"][:100], key=lambda r: (r["holdout"]["five"]["bes"] / (r["holdout"]["five"]["n"] or 1), r["holdout"]["segs"].get("14+", Counter())["bes"] / (r["holdout"]["segs"].get("14+", Counter())["n"] or 1)))
    best_ho = summarize_eval_row("", best_hold["holdout"])
    best_delta = (best_ho["bes"] / (best_ho["n"] or 1) - base_bes) * 100
    best14_delta = (best_ho["seg14_bes"] / (best_ho["seg14_n"] or 1) - base14) * 100
    lines.append("### En İyi Holdout Adayı")
    lines.append(f"- Aday: `{variant_name(best_hold['variant'])}`")
    lines.append(f"- Holdout 5 satır: {pct(best_ho['bes'], best_ho['n'])} ({best_delta:+.2f} puan)")
    lines.append(f"- Holdout 14+ 5 satır: {pct(best_ho['seg14_bes'], best_ho['seg14_n'])} ({best14_delta:+.2f} puan)")
    lines.append("")

    lines.append("## HAR Kullanım Yeri Testi")
    har_rows = []
    base_har_rate = base_hold["har_hit"] / (base_hold["har_n"] or 1)
    for row in res["har_tests"][:20]:
        ho = summarize_eval_row("", row["holdout"])
        rate = ho["har_hit"] / (ho["har_n"] or 1)
        har_rows.append([row["feature"], f"{ho['har_hit']}/{ho['har_n']} {pct(ho['har_hit'], ho['har_n'])}", f"{(rate-base_har_rate)*100:+.1f} puan",
                         f"{ho['har14_hit']}/{ho['har14_n']} {pct(ho['har14_hit'], ho['har14_n'])}"])
    add_table(lines, ["HAR özelliği", "Holdout HAR", "Δ HAR", "Holdout HAR 14+"], har_rows)
    lines.append("")

    lines.append("## Banko Güven Filtresi - Holdout")
    banko_rows = []
    # Baseline top1 accuracy.
    base_top1 = Counter()
    for race in res["holdout"]:
        order = order_for_variant(race, {"kind": "baseline"})
        base_top1["n"] += 1
        if order[0] in race["wset"]:
            base_top1["hit"] += 1
    base_acc = base_top1["hit"] / (base_top1["n"] or 1)
    for row in res["banko_filters"][:20]:
        c = row["stat"]
        acc = c["hit"] / (c["n"] or 1)
        banko_rows.append([row["feature"], row["best_threshold"], f"{c['hit']}/{c['n']} {pct(c['hit'], c['n'])}", f"{(acc-base_acc)*100:+.1f} puan"])
    add_table(lines, ["Filtre", "Eşik", "Doğru/toplam", "Top1 baseline'a göre"], banko_rows)
    lines.append("")

    lines.append("## Altılı Holdout Backtest")
    alt_rows = []
    for vname, data in res["altili"].items():
        anyhit = data["anyhit"]
        for ad, _, _ in KUPON_TIERS:
            c = data["tiers"][ad]
            cost = data["cost"][ad]
            ret = data["return"][ad]
            b = data["banko"][ad]
            alt_rows.append([
                vname, ad, f"{c['hit']}/{c['n']} {pct(c['hit'], c['n'])}",
                f"{cost/(c['n'] or 1):.0f} TL", f"{ret-cost:+.0f} TL",
                f"{b['hit']}/{b['n']} {pct(b['hit'], b['n'])}", b["wrong_single"],
                f"{anyhit['hit']}/{anyhit['n']} {pct(anyhit['hit'], anyhit['n'])}",
            ])
    add_table(lines, ["Varyant", "Kademe", "İsabet", "Ort. bütçe", "Net", "Çıpa doğru", "Yanlış tek banko", "3 kupondan biri"], alt_rows)
    lines.append("")

    lines.append("## Karar")
    accept_main = best_delta >= 0.3 or best14_delta >= 1.0
    best_har = max(res["har_tests"], key=lambda r: r["holdout"]["har"]["har_yakaladi"] / (r["holdout"]["har"]["top4_disi"] or 1))
    best_har_ho = summarize_eval_row("", best_har["holdout"])
    best_har_delta = (best_har_ho["har_hit"] / (best_har_ho["har_n"] or 1) - base_har_rate) * 100
    lines.append(f"- Ana skor kabul eşiği: {'GEÇTİ' if accept_main else 'GEÇMEDİ'}")
    lines.append(f"- En iyi HAR adayı: `{best_har['feature']}` ΔHAR {best_har_delta:+.1f} puan")
    lines.append("- Üretim koduna otomatik değişiklik yapılmadı; bu rapor karar girdisidir.")
    lines.append("")
    if accept_main:
        lines.append("Öneri: En iyi holdout adayı üretim dışı ikinci bir canlı izleme modunda denenebilir; doğrudan ana algoritmaya almadan önce yeni günlerde doğrulama gerekir.")
    elif best_har_delta >= 5.0:
        lines.append("Öneri: JSON AI alanı ana skor yerine yalnız HAR/kupon genişletme tarafında değerlendirilmeli.")
    else:
        lines.append("Öneri: JSON AI alanları mevcut veriyle ana skora alınmamalı; yalnız açıklama/teyit etiketi olarak tutulmalı.")
    return "\n".join(lines)


def analyze():
    print("Tahmin dosyaları okunuyor...")
    races_by_key, files = parse_tahmin_files()
    print(f"  tahmin dosyası: {len(files)}, koşu: {len(races_by_key)}")
    csvs = load_all_csv()
    peg_json = load_peg_json()
    print(f"  CSV gün/hip: {len(csvs)}, JSON koşu: {len(peg_json)}")

    eval_races = []
    for key, race in races_by_key.items():
        iso, hip, kno = key
        if not in_scope(iso):
            continue
        if f"{iso}|{hip}|{kno}" not in peg_json:
            continue
        c = csvs.get((iso, hip))
        if not c:
            continue
        w = c["kazanan"].get(kno)
        if w is None or w not in race["order"]:
            continue
        if not attach_json_features(race, peg_json):
            continue
        race["winner"] = w
        race["wset"] = winning_set(c, kno)
        feature_norms(race)
        eval_races.append(race)

    train = [r for r in eval_races if split_name(r["iso"]) == "train"]
    holdout = [r for r in eval_races if split_name(r["iso"]) == "holdout"]
    feature_names = []
    for label, _, _ in AI_FIELDS + GALOP_FIELDS:
        feature_names += [f"{label}|raw_zero", f"{label}|neutral_missing", f"{label}|missing_indicator"]

    print(f"  eşleşen koşu: {len(eval_races)} train={len(train)} holdout={len(holdout)}")
    print("Tekil sinyaller ölçülüyor...")
    single_holdout = eval_single_signals(holdout, feature_names)

    print("Ağırlık grid çalışıyor...")
    base_eval, grid_candidates, top_single_features = run_weight_grid(train, holdout, feature_names)
    print(f"  grid aday: {len(grid_candidates)}, combo havuzu: {top_single_features}")

    print("HAR testleri çalışıyor...")
    har_tests = run_har_tests(train, holdout, feature_names)
    print("Banko filtre testleri çalışıyor...")
    banko_filters = eval_banko_filters(holdout, feature_names)

    alt_variants = [("baseline", {"kind": "baseline"})]
    for idx, row in enumerate(grid_candidates[:TOP_CANDIDATES_FOR_ALTILI], 1):
        alt_variants.append((f"grid{idx}", row["variant"]))
    print("Altılı holdout backtest çalışıyor...")
    altili = eval_altili(races_by_key, csvs, alt_variants)

    res = {
        "tahmin_file_count": len(files),
        "race_count": len(races_by_key),
        "peg_json_count": len(peg_json),
        "eval_races": eval_races,
        "train": train,
        "holdout": holdout,
        "base_eval": base_eval,
        "grid_candidates": grid_candidates,
        "top_single_features": top_single_features,
        "single_holdout": single_holdout,
        "har_tests": har_tests,
        "banko_filters": banko_filters,
        "altili": altili,
    }
    OUT.write_text(render_report(res), encoding="utf-8")
    print(f"Rapor yazıldı: {OUT}")
    return res


if __name__ == "__main__":
    analyze()
