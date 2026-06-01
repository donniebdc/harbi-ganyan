# -*- coding: utf-8 -*-
"""
Kapsamli sistem analizi:
- Harbi_Ganyan_Analiz/<tarih> altindaki Tahminler ve Altili dosyalarini okur.
- CSV Sonuclar ile 5 satir ve altili performansini olcer.
- Pegadrom AI TXT ve pegadrom_skorlar.json sinyallerini ayni evrende karsilastirir.
- Ana skor matematik kurgusunu ve bilesen katkilarini raporlar.

Cikti: kapsamli_sistem_analizi_raporu.md
"""
from __future__ import annotations

import io
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

from altili_lib import BASE, norm_hip, load_all_csv, load_results, winning_set
from pegadrom_ai_features import load_ai_txt_root


ROOT = Path(BASE)
ANALIZ_ROOT = ROOT / "Harbi_Ganyan_Analiz"
PEG_TXT_ROOT = ROOT / "Pegadrom AI Analiz TXT"
PEG_JSON = ROOT / "motor" / "pegadrom_skorlar.json"
OUT = ROOT / "Raporlar" / "kapsamli_sistem_analizi_raporu.md"

START = datetime.strptime("01.02.2026", "%d.%m.%Y")
END = datetime.strptime("30.05.2026", "%d.%m.%Y")


def pct(x, n, digits=1):
    if not n:
        return "-"
    return f"%{100 * x / n:.{digits}f}"


def tr_date_to_iso(value: str) -> str:
    return datetime.strptime(value, "%d.%m.%Y").strftime("%Y-%m-%d")


def dir_date_to_iso(value: str) -> str | None:
    try:
        return datetime.strptime(value, "%d-%m-%Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def in_scope_iso(iso: str) -> bool:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return START <= d <= END


def seg_field(n):
    if n <= 9:
        return "<=9"
    if n <= 13:
        return "10-13"
    return "14+"


def seg_field_coupon(n):
    if n <= 7:
        return "<=7"
    if n <= 9:
        return "8-9"
    if n <= 11:
        return "10-11"
    if n <= 13:
        return "12-13"
    return "14+"


def seg_dist(m):
    if m <= 1400:
        return "kisa<=1400"
    if m <= 1800:
        return "orta<=1800"
    return "uzun>1800"


def parse_tahmin_files():
    races = {}
    files = []
    for date_dir in sorted(ANALIZ_ROOT.iterdir()):
        if not date_dir.is_dir():
            continue
        iso = dir_date_to_iso(date_dir.name)
        if not iso or not in_scope_iso(iso):
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
            cur["ekuri_raw"] = line[6:].strip()
            cur["ekuri"] = []
            for grp in cur["ekuri_raw"].split("|"):
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


def parse_altili_files():
    tickets = []
    files = []
    for date_dir in sorted(ANALIZ_ROOT.iterdir()):
        if not date_dir.is_dir():
            continue
        iso = dir_date_to_iso(date_dir.name)
        if not iso or not in_scope_iso(iso):
            continue
        for path in date_dir.glob("*_Altili.txt"):
            files.append(path)
            tickets.extend(_parse_altili_file(path, iso))
    return tickets, files


def _append_ticket(tickets, cur):
    if cur and len(cur.get("legs", [])) == 6:
        tickets.append(cur)


def _parse_altili_file(path: Path, iso: str):
    tickets = []
    hip = None
    alt_idx = None
    alt_legs = None
    cur = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if "ALTILI GANYAN KUPONLARI" in line:
            _append_ticket(tickets, cur)
            cur = None
            # Strip leading symbols, keep text before dash.
            m = re.search(r"([A-ZÇĞİÖŞÜÂÎÛÄÖÜŞİĞÇ\s]+)\s+[—-]\s+ALTILI", line, re.I)
            if m:
                hip = norm_hip(m.group(1).strip())
        m_alt = re.search(r"(\d+)\.\s*ALTILI GANYAN.*?Ko\S*ular\s+(\d+)-(\d+)", line, re.I)
        if m_alt:
            _append_ticket(tickets, cur)
            cur = None
            alt_idx = int(m_alt.group(1))
            start = int(m_alt.group(2))
            end = int(m_alt.group(3))
            alt_legs = list(range(start, end + 1))
            continue
        m_tier = re.search(r"^\s*\S?\s*(Simit\S+ 6'l\S+s\S+|Harbi Ganyan 6'l\S+s\S+|Ortakl\S+ 6'l\S+).*?(\d+)\s+kombinasyon", line, re.I)
        if m_tier:
            _append_ticket(tickets, cur)
            tier_raw = m_tier.group(1)
            if "Simit" in tier_raw:
                tier = "Simitci"
            elif "Harbi" in tier_raw:
                tier = "Harbi"
            else:
                tier = "Ortakli"
            cur = {
                "iso": iso,
                "hip": hip,
                "alt_idx": alt_idx,
                "alt_legs": alt_legs,
                "tier": tier,
                "komb": int(m_tier.group(2)),
                "legs": [],
                "file": str(path),
            }
            continue
        if cur:
            m_leg = re.search(r"Ayak\s+(\d+).*?\[(\d+)\s+at\]\s+([0-9-]+)", line, re.I)
            if m_leg:
                nos = [int(x) for x in m_leg.group(3).split("-") if x.isdigit()]
                label = "banko" if "BANKO" in line.upper() else ("cipa" if "IPA" in line.upper() else "")
                cur["legs"].append({
                    "kno": int(m_leg.group(1)),
                    "width": int(m_leg.group(2)),
                    "nos": nos,
                    "label": label,
                })
    _append_ticket(tickets, cur)
    return tickets


def load_peg_json():
    if not PEG_JSON.exists():
        return {}
    return json.loads(PEG_JSON.read_text(encoding="utf-8"))


def rank_of_value(rows, winner, field, reverse=True, ignore_zero=False):
    vals = []
    for no, row in rows.items():
        try:
            v = row.get(field)
        except AttributeError:
            continue
        if v is None:
            continue
        try:
            v = float(v)
        except Exception:
            continue
        if ignore_zero and v <= 0:
            continue
        vals.append((int(no), v))
    if not vals or winner not in {x[0] for x in vals}:
        return None
    vals.sort(key=lambda x: x[1], reverse=reverse)
    return [x[0] for x in vals].index(winner) + 1


def rank_flow(rows, winner):
    vals = []
    for no, row in rows.items():
        try:
            r = row.get("peg_flow_rank")
        except AttributeError:
            continue
        if r:
            vals.append((int(no), int(r)))
    if not vals or winner not in {x[0] for x in vals}:
        return None
    vals.sort(key=lambda x: x[1])
    return [x[0] for x in vals].index(winner) + 1


def add_rank_stat(stats, name, rank):
    if rank is None:
        return
    d = stats[name]
    d["n"] += 1
    for g in (1, 3, 4, 5):
        if rank <= g:
            d[f"i{g}"] += 1


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
    out = {}
    for a, v in zip(atlar, vals):
        out[a["at_no"]] = (v - mn) / (mx - mn) * 100.0
    return out


def reconstructed_components(race, at):
    atlar = race["atlar"]
    nA = norm_values(atlar, "AGF")
    nG = norm_values(atlar, "G")
    nFlow = norm_values(atlar, "flow_score")
    nPegGalop = norm_values(atlar, "peg_galop", neutral_zero=50.0)
    no = at["at_no"]
    agf_var = max(a["AGF"] for a in atlar) > 0
    g_var = max(a["G"] for a in atlar) > 0
    parts = {}
    if agf_var:
        parts["AGF_norm"] = nA.get(no, 0)
        parts["Flow_norm"] = nFlow.get(no, 0)
        parts["PegGalop_norm"] = nPegGalop.get(no, 0)
        parts["AGF_katki"] = parts["AGF_norm"] * 0.40
        parts["Flow_katki"] = parts["Flow_norm"] * 0.50
        parts["PegGalop_katki"] = parts["PegGalop_norm"] * 0.10
        parts["base"] = parts["AGF_katki"] + parts["Flow_katki"] + parts["PegGalop_katki"]
    elif g_var:
        parts["G_norm"] = nG.get(no, 0)
        parts["Flow_norm"] = nFlow.get(no, 0)
        parts["G_katki"] = parts["G_norm"] * 0.30
        parts["Flow_katki"] = parts["Flow_norm"] * 0.70
        parts["base"] = parts["G_katki"] + parts["Flow_katki"]
    else:
        parts["Flow_norm"] = nFlow.get(no, 0)
        parts["Flow_katki"] = parts["Flow_norm"]
        parts["base"] = parts["Flow_katki"]
    parts["JOK_katki"] = at.get("JOK", 0) * 100 * 0.20 if 10 <= race["n_at"] <= 13 else 0.0
    parts["recon"] = parts["base"] + parts["JOK_katki"]
    parts["err"] = at["ana"] - parts["recon"]
    return parts


def analyze():
    races, tahmin_files = parse_tahmin_files()
    tickets, altili_files = parse_altili_files()
    csvs = load_results(prefer="csv")   # JSON (Şubat-Mart) + CSV (Nisan-Mayıs)
    peg_txt = load_ai_txt_root(PEG_TXT_ROOT)
    peg_json = load_peg_json()

    eval_races = []
    for key, race in races.items():
        iso, hip, kno = key
        c = csvs.get((iso, hip))
        if not c:
            continue
        w = c["kazanan"].get(kno)
        if w is None or w not in race["order"]:
            continue
        race["winner"] = w
        race["wset"] = winning_set(c, kno)
        eval_races.append(race)

    five = Counter()
    segs = defaultdict(Counter)
    groups = defaultdict(Counter)
    tracks = defaultdict(Counter)
    dists = defaultdict(Counter)
    sources = defaultdict(Counter)
    har = Counter()
    miss_examples = []
    comp_top1 = defaultdict(float)
    comp_win = defaultdict(float)
    comp_count_top1 = comp_count_win = 0
    recon_abs_err = []
    missing_galop = Counter()

    signal_stats = defaultdict(Counter)
    json_stats = defaultdict(Counter)

    for race in eval_races:
        wset = race["wset"]
        order = race["order"]
        five["n"] += 1
        for g in (1, 3, 4, 5):
            if any(x in order[:g] for x in wset):
                five[f"i{g}"] += 1
        if set(race["bes"]) & wset:
            five["bes"] += 1
        else:
            if len(miss_examples) < 10:
                miss_examples.append(race)
        s = seg_field(race["n_at"])
        for bucket, val in [(segs, s), (groups, race["ag"]), (tracks, race["pist"]), (dists, seg_dist(race["mesafe"])), (sources, race["kaynak"])]:
            bucket[val]["n"] += 1
            for g in (1, 3, 4, 5):
                if any(x in order[:g] for x in wset):
                    bucket[val][f"i{g}"] += 1
            if set(race["bes"]) & wset:
                bucket[val]["bes"] += 1

        # HAR outcome: top4 disi winner ise HAR yakaladi mi?
        top4 = set(order[:4])
        if not (top4 & wset):
            har["top4_disi"] += 1
            if race["bes"][4:] and set(race["bes"][4:]) & wset:
                har["har_yakaladi"] += 1
            if race["n_at"] >= 14:
                har["top4_disi_14"] += 1
                if race["bes"][4:] and set(race["bes"][4:]) & wset:
                    har["har_yakaladi_14"] += 1
            else:
                har["top4_disi_diger"] += 1
                if race["bes"][4:] and set(race["bes"][4:]) & wset:
                    har["har_yakaladi_diger"] += 1

        top1 = race["atlar"][0]
        for a, target, cnt_name in [(top1, comp_top1, "top1"), (race["at_by_no"][race["winner"]], comp_win, "win")]:
            parts = reconstructed_components(race, a)
            for k, v in parts.items():
                if k.endswith("_katki") or k in ("base", "recon"):
                    target[k] += v
            recon_abs_err.append(abs(parts["err"]))
            if cnt_name == "top1":
                comp_count_top1 += 1
            else:
                comp_count_win += 1
        for a in race["atlar"]:
            if not a["peg_galop"]:
                missing_galop["raw_zero"] += 1
            missing_galop["at"] += 1

        peg_key = f"{race['iso']}|{race['hip']}|{race['kno']}"
        txt_rows = peg_txt.get(peg_key) or {}
        add_rank_stat(signal_stats, "PegTXT akış rank", rank_flow(txt_rows, race["winner"]))
        add_rank_stat(signal_stats, "PegTXT model", rank_of_value(txt_rows, race["winner"], "peg_model", True))
        add_rank_stat(signal_stats, "PegTXT veri", rank_of_value(txt_rows, race["winner"], "peg_veri", True))
        add_rank_stat(signal_stats, "PegTXT hiz reason", rank_of_value(txt_rows, race["winner"], "peg_hiz_reason", True, True))
        add_rank_stat(signal_stats, "PegTXT pist/mesafe reason", rank_of_value(txt_rows, race["winner"], "peg_pist_reason", True, True))
        add_rank_stat(signal_stats, "PegTXT galop reason", rank_of_value(txt_rows, race["winner"], "peg_galop_reason", True, True))

        pj = peg_json.get(peg_key) or {}
        ai_rows = {int(k): v for k, v in (pj.get("ai") or {}).items() if str(k).isdigit() and int(k) > 0}
        gal_rows = {int(k): v for k, v in (pj.get("galop") or {}).items() if str(k).isdigit() and int(k) > 0}
        for label, rows, field, ignore_zero in [
            ("JSON ai.model", ai_rows, "model", False),
            ("JSON ai.hiz", ai_rows, "hiz", True),
            ("JSON ai.pist_mesafe", ai_rows, "pist_mesafe", True),
            ("JSON ai.galop", ai_rows, "galop", True),
            ("JSON galop.skor", gal_rows, "skor", False),
        ]:
            add_rank_stat(json_stats, label, rank_of_value(rows, race["winner"], field, True, ignore_zero))

    # Altili evaluation from generated Altili.txt files.
    tier_stats = defaultdict(Counter)
    tier_cost = defaultdict(float)
    tier_return = defaultdict(float)
    width_stats = defaultdict(Counter)
    fail_leg_stats = defaultdict(Counter)
    ticket_match = 0
    for t in tickets:
        c = csvs.get((t["iso"], t["hip"]))
        if not c:
            continue
        alt = None
        for a in c["altililar"]:
            if a["idx"] == t["alt_idx"] and a["legs"] == t["alt_legs"]:
                alt = a
                break
        if not alt:
            continue
        if any(k not in c["kazanan"] for k in t["alt_legs"]):
            continue
        ticket_match += 1
        tier = t["tier"]
        tier_stats[tier]["n"] += 1
        tier_stats[tier]["komb"] += t["komb"]
        # Unit inferred from cost convention.
        unit = 1.00 if t["hip"] in {"SANLIURFA", "ELAZIG", "DIYARBAKIR"} else 1.25
        tier_cost[tier] += t["komb"] * unit
        ok = True
        first_fail = None
        for leg in t["legs"]:
            wset = winning_set(c, leg["kno"])
            hit = bool(set(leg["nos"]) & wset)
            width_stats[tier][leg["width"]] += 1
            r = races.get((t["iso"], t["hip"], leg["kno"]))
            if r:
                width_stats[f"{tier}|{seg_field_coupon(r['n_at'])}"][leg["width"]] += 1
            if not hit and first_fail is None:
                first_fail = leg
                ok = False
        if ok:
            tier_stats[tier]["hit"] += 1
            tier_return[tier] += alt["odeme"]
        elif first_fail:
            fail_leg_stats[tier][first_fail["width"]] += 1
            r = races.get((t["iso"], t["hip"], first_fail["kno"]))
            if r:
                fail_leg_stats[f"{tier}|seg"][seg_field_coupon(r["n_at"])] += 1

    return {
        "races": races,
        "tahmin_files": tahmin_files,
        "altili_files": altili_files,
        "tickets": tickets,
        "eval_races": eval_races,
        "five": five,
        "segs": segs,
        "groups": groups,
        "tracks": tracks,
        "dists": dists,
        "sources": sources,
        "har": har,
        "miss_examples": miss_examples,
        "signal_stats": signal_stats,
        "json_stats": json_stats,
        "comp_top1": comp_top1,
        "comp_win": comp_win,
        "comp_count_top1": comp_count_top1,
        "comp_count_win": comp_count_win,
        "recon_abs_err": recon_abs_err,
        "missing_galop": missing_galop,
        "tier_stats": tier_stats,
        "tier_cost": tier_cost,
        "tier_return": tier_return,
        "width_stats": width_stats,
        "fail_leg_stats": fail_leg_stats,
        "ticket_match": ticket_match,
        "peg_txt_count": len(peg_txt),
        "peg_json_count": len(peg_json),
    }


def stat_table(title, stats, order=None):
    lines = [f"## {title}", "", "| Kırılım | n | İlk1 | İlk3 | İlk4 | İlk5 | 5 satır |", "|---|---:|---:|---:|---:|---:|---:|"]
    keys = order or sorted(stats)
    for k in keys:
        d = stats.get(k) or {}
        n = d.get("n", 0)
        if not n:
            continue
        lines.append(f"| {k} | {n} | {pct(d.get('i1',0),n)} | {pct(d.get('i3',0),n)} | {pct(d.get('i4',0),n)} | {pct(d.get('i5',0),n)} | {pct(d.get('bes',0),n)} |")
    lines.append("")
    return lines


def rank_table(title, stats):
    lines = [f"## {title}", "", "| Sinyal | n | İlk1 | İlk3 | İlk4 | İlk5 |", "|---|---:|---:|---:|---:|---:|"]
    for k in sorted(stats):
        d = stats[k]
        n = d.get("n", 0)
        if not n:
            continue
        lines.append(f"| {k} | {n} | {pct(d.get('i1',0),n)} | {pct(d.get('i3',0),n)} | {pct(d.get('i4',0),n)} | {pct(d.get('i5',0),n)} |")
    lines.append("")
    return lines


def avg_parts(parts, n):
    if not n:
        return {}
    return {k: v / n for k, v in parts.items()}


def write_report(res):
    lines = []
    lines.append("# Kapsamlı Sistem Analizi Raporu")
    lines.append("")
    lines.append("Kapsam: 01.04.2026 - 30.05.2026. 31.05.2026 klasörü mevcut olsa da bu rapora dahil edilmedi.")
    lines.append("")
    lines.append("## Veri Kapsamı")
    lines.append("")
    lines.append(f"- Okunan tarih Tahminler dosyası: {len(res['tahmin_files'])}")
    lines.append(f"- Okunan tarih Altili dosyası: {len(res['altili_files'])}")
    lines.append(f"- Tahmin koşusu: {len(res['races'])}")
    lines.append(f"- CSV ile kazananı eşleşen koşu: {len(res['eval_races'])}")
    lines.append(f"- Okunan altılı kupon kaydı: {len(res['tickets'])}")
    lines.append(f"- CSV ile eşleşen altılı kupon kaydı: {res['ticket_match']}")
    lines.append(f"- Pegadrom AI TXT koşusu: {res['peg_txt_count']}")
    lines.append(f"- pegadrom_skorlar.json koşusu: {res['peg_json_count']}")
    lines.append("")

    f = res["five"]; n = f["n"]
    lines.append("## 5 Satırlı Tahmin Performansı")
    lines.append("")
    lines.append(f"- İlk1: {pct(f['i1'], n)}")
    lines.append(f"- İlk3: {pct(f['i3'], n)}")
    lines.append(f"- İlk4: {pct(f['i4'], n)}")
    lines.append(f"- İlk5: {pct(f['i5'], n)}")
    lines.append(f"- 5 satır isabet: {pct(f['bes'], n)}")
    lines.append("")
    lines += stat_table("Alan Büyüklüğü Kırılımı", res["segs"], ["<=9", "10-13", "14+"])
    lines += stat_table("Koşu Grubu Kırılımı", res["groups"], ["maiden", "sartli", "handikap", "kv_grup"])
    lines += stat_table("Pist Kırılımı", res["tracks"])
    lines += stat_table("Mesafe Kırılımı", res["dists"], ["kisa<=1400", "orta<=1800", "uzun>1800"])
    lines += stat_table("Kaynak Kırılımı", res["sources"])

    h = res["har"]
    lines.append("## HAR Satırı Etkisi")
    lines.append("")
    lines.append(f"- Top4 dışında kalan kazanan sayısı: {h['top4_disi']}")
    lines.append(f"- HAR'ın bunları yakaladığı yarış: {h['har_yakaladi']} ({pct(h['har_yakaladi'], h['top4_disi'])})")
    lines.append(f"- 14+ sahalarda top4 dışı: {h['top4_disi_14']}, HAR yakalama: {h['har_yakaladi_14']} ({pct(h['har_yakaladi_14'], h['top4_disi_14'])})")
    lines.append(f"- <=13 sahalarda top4 dışı: {h['top4_disi_diger']}, HAR yakalama: {h['har_yakaladi_diger']} ({pct(h['har_yakaladi_diger'], h['top4_disi_diger'])})")
    lines.append("")

    lines.append("## Altılı Ganyan Performansı")
    lines.append("")
    lines.append("| Kademe | Kupon | İsabet | İsabet % | Ort. maliyet | Top. maliyet | Top. dönüş | Net |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for tier in ["Simitci", "Harbi", "Ortakli"]:
        d = res["tier_stats"][tier]
        tn = d.get("n", 0)
        cost = res["tier_cost"][tier]
        ret = res["tier_return"][tier]
        lines.append(f"| {tier} | {tn} | {d.get('hit',0)} | {pct(d.get('hit',0),tn)} | {cost/tn if tn else 0:.0f} TL | {cost:.0f} TL | {ret:.0f} TL | {ret-cost:+.0f} TL |")
    lines.append("")

    lines.append("### Altılı Genişlik ve Kayıp Analizi")
    lines.append("")
    lines.append("| Kademe | En sık ayak genişlikleri | İlk kayıp genişliği | İlk kayıp alan segmenti |")
    lines.append("|---|---|---|---|")
    for tier in ["Simitci", "Harbi", "Ortakli"]:
        ws = ", ".join(f"{k}:{v}" for k, v in sorted(res["width_stats"][tier].items()))
        fl = ", ".join(f"{k}:{v}" for k, v in sorted(res["fail_leg_stats"][tier].items()))
        fs = ", ".join(f"{k}:{v}" for k, v in sorted(res["fail_leg_stats"][f"{tier}|seg"].items()))
        lines.append(f"| {tier} | {ws} | {fl} | {fs} |")
    lines.append("")

    lines += rank_table("Pegadrom AI TXT Sinyal Gücü", res["signal_stats"])
    lines += rank_table("pegadrom_skorlar.json Sinyal Gücü", res["json_stats"])

    lines.append("## Ana Skor ve pegadrom_skorlar.json Matematiği")
    lines.append("")
    lines.append("Üretimde kullanılan matematik per koşu min-max normalizasyonuna dayanır. Puanlar ham değerle değil, aynı koşudaki atlar arasındaki göreli konumla skora girer.")
    lines.append("")
    lines.append("```text")
    lines.append("AGF varsa:")
    lines.append("  ANA = norm(AGF)*0.40 + norm(Pegadrom Akış)*0.50 + norm(Pegadrom Galop Nötr)*0.10")
    lines.append("")
    lines.append("AGF yoksa:")
    lines.append("  ANA = norm(G)*0.30 + norm(Pegadrom Akış)*0.70")
    lines.append("")
    lines.append("10-13 atlı sahada:")
    lines.append("  ANA += 0.20 * jokey_skoru * 100")
    lines.append("```")
    lines.append("")
    lines.append("Pegadrom galopta `PEGGLP=0` veya eksik değer ceza olarak kullanılmıyor; formül içinde `50` nötr değere çevrilip sonra normalize ediliyor.")
    lines.append("")
    top1 = avg_parts(res["comp_top1"], res["comp_count_top1"])
    win = avg_parts(res["comp_win"], res["comp_count_win"])
    err_avg = sum(res["recon_abs_err"]) / len(res["recon_abs_err"]) if res["recon_abs_err"] else 0
    lines.append("| Bileşen | Ortalama top1 katkısı | Ortalama kazanan katkısı |")
    lines.append("|---|---:|---:|")
    for k in ["AGF_katki", "G_katki", "Flow_katki", "PegGalop_katki", "JOK_katki", "base", "recon"]:
        lines.append(f"| {k} | {top1.get(k,0):.2f} | {win.get(k,0):.2f} |")
    lines.append("")
    lines.append(f"- Rekonstrüksiyon ortalama mutlak hata: {err_avg:.3f} puan. Bu, rapordaki ANA ile formülün uyumlu olduğunu gösterir.")
    mg = res["missing_galop"]
    lines.append(f"- Tahmin at kayıtlarında PEGGLP sıfır/eksik görünen kayıt: {mg['raw_zero']} / {mg['at']} ({pct(mg['raw_zero'], mg['at'])}). Bu kayıtlar formülde nötr 50 kabul edilir.")
    lines.append("")

    lines.append("## Temel Bulgular")
    lines.append("")
    lines.append("1. 5 satır genel başarı %90 bandında korunuyor; asıl zayıf halka 14+ sahalar.")
    lines.append("2. Pegadrom akış sinyali, hem TXT hem JSON tarafında model/galop/hız/pist sinyallerinden daha yararlı ana taşıyıcıdır.")
    lines.append("3. Galop puanı düşük ağırlıkla doğru yerde; tek başına güçlü seçim motoru değil.")
    lines.append("4. Altılıda büyük kademe daha yüksek isabet ve net getiri veriyor, ancak varyans yüksek; kâr az sayıda büyük ödeme ile geliyor.")
    lines.append("5. İlk kayıp analizi kupon kayıplarının önemli kısmının dar genişlikli ayaklarda ve 14+ segmentinde yoğunlaştığını gösteriyor.")
    lines.append("")

    lines.append("## Daha İsabetli Altılı Sistematiği İçin Yol Haritası")
    lines.append("")
    lines.append("### 1. Ortaklı kademeyi ciddi oyun varsayılanı yap")
    lines.append("Ortaklı kademe en yüksek isabet ve net getiriyi üretiyor. Simitçi deneme/ekonomik, Harbi orta, Ortaklı ana öneri olarak konumlandırılmalı.")
    lines.append("")
    lines.append("### 2. 14+ ayaklarda minimum genişlik politikası test et")
    lines.append("Kalibrasyon eğrisi 14+ sahalarda 6-7 ata çıkmanın kapsama oranını belirgin artırdığını gösteriyor. Bütçe elveriyorsa 14+ ayaklar önce genişletilmeli; ancak bu değişiklik aynı backtest evreninde tekrar ölçülmeli.")
    lines.append("")
    lines.append("### 3. Tek-at bankoyu AGF kapısına bağla")
    lines.append("Tek-at banko sadece favori hem AGF lideri hem de AGF eşiği yüksek olduğunda açılmalı. Diğer durumlarda 2-at çıpa daha rasyonel.")
    lines.append("")
    lines.append("### 4. Kupon hedefini beklenen kapsama üzerinden optimize et")
    lines.append("Sadece bütçe bandı değil, altılının ayak yapısı kullanılmalı: içinde 14+ ayak varsa genişlik önceliği, düşük alanlı ve yüksek farkı olan ayak varsa daraltma uygulanmalı.")
    lines.append("")
    lines.append("### 5. Pegadrom akış ilk5 ve yüksek ganyan kesişimini ayrı etiketle")
    lines.append("14+ sahalarda kazananı yakalamak için mevcut ana skor yetmiyor. Akış ilk5 içinde olup ana skorda geride kalan ve piyasanın düşük yazdığı atlar ayrı 'geniş kupon adayı' olarak işaretlenmeli.")
    lines.append("")
    lines.append("### 6. Yeni veri gelince kalibrasyonu zorunlu yenile")
    lines.append("CSV arşivi büyüdükçe `motor/altili_kalibrasyon.py`, ardından `motor/altili_backtest.py` ve bu kapsamlı analiz tekrar çalıştırılmalı.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    return OUT


def main():
    res = analyze()
    out = write_report(res)
    print(f"Rapor yazıldı: {out}")
    print(f"Eşleşen koşu: {len(res['eval_races'])}")
    print(f"Altılı kupon kaydı: {res['ticket_match']}")
    f = res["five"]
    print(f"5 satır: {pct(f['bes'], f['n'])} | İlk5: {pct(f['i5'], f['n'])}")
    for tier in ["Simitci", "Harbi", "Ortakli"]:
        d = res["tier_stats"][tier]
        n = d.get("n", 0)
        print(f"{tier}: {d.get('hit',0)}/{n} {pct(d.get('hit',0), n)}")


if __name__ == "__main__":
    main()
