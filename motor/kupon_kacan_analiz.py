# -*- coding: utf-8 -*-
"""
KUPON KAÇAN ANALİZİ — "5 satırda var ama kupona girmemiş" kazananlar.

Kullanıcı gözlemi: Çoğu altılı 5/6'da kalıyor. Bazı ayaklarda kazananı 5'li satırda
(özellikle Bomba=ANA#4 ve Harbi=ANA#5) BULMUŞUZ ama o ayağın kupon genişliği dar
kaldığı için kupona EKLEYEMEMİŞİZ. Bu script tam da bunu ölçer:
  - Her altılıyı (Harbi_Ganyan_Analiz tahminleri) kupon kurucu ile yeniden kurar.
  - Kaçan ayakları bulur; kazananın ANA-rankını ve 5-satır konumunu (FAV/SUR/YAZ/BOM/HAR)
    ve o ayağa atanan genişliği karşılaştırır.
  - "1 ayak kaçtı (5/6)" kuponlarında: kaç tanesinde kazanan aslında 5-satırımızdaydı
    ama dar genişlik yüzünden dışarıda kaldı → kazanılabilecek kupon sayısı.

Üretim kodunu DEĞİŞTİRMEZ. Çıktı: kupon_kacan_analiz_raporu.md
"""
from __future__ import annotations
import os, sys, glob, re
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from altili_lib import (BASE, norm_hip, load_all_csv, load_results, winning_set, birim_fiyat,
                        ekuri_parse, ekuri_ortaklari)
from altili_kupon_v2 import build_tier, KUPON_TIERS, load_cal

ANALIZ = os.path.join(BASE, "Harbi_Ganyan_Analiz")
OUT = os.path.join(BASE, "Raporlar", "kupon_kacan_analiz_raporu.md")
LINE_LABELS = ["FAV", "SUR", "YAZ", "BOM", "HAR"]


RE_ALT_HIP = re.compile(r"🎰\s*(.+?)\s*[—-]\s*ALTILI GANYAN")
RE_ALT_HEAD = re.compile(r"ALTILI GANYAN\s*\(Koşular\s*(\d+)\s*-\s*(\d+)\)")

def derive_altililar():
    """Harbi_Ganyan_Analiz/*/*_Altili.txt başlıklarından altılı ayak tanımlarını
    türetir (CSV'den bağımsız → tam tarih aralığı). -> {(iso,hip): [{idx,last,legs}]}."""
    out = {}
    for date_dir in sorted(glob.glob(os.path.join(ANALIZ, "*"))):
        if not os.path.isdir(date_dir):
            continue
        m = re.match(r"(\d{2})-(\d{2})-(\d{4})", os.path.basename(date_dir))
        if not m:
            continue
        iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        for path in glob.glob(os.path.join(date_dir, "*_Altili.txt")):
            hip = None
            for raw in open(path, encoding="utf-8", errors="replace").read().split("\n"):
                mh = RE_ALT_HIP.search(raw)
                if mh:
                    hip = norm_hip(mh.group(1)); continue
                ma = RE_ALT_HEAD.search(raw)
                if ma and hip:
                    a, b = int(ma.group(1)), int(ma.group(2))
                    legs = list(range(a, b + 1))
                    key = (iso, hip)
                    lst = out.setdefault(key, [])
                    lst.append({"idx": len(lst) + 1, "last": b, "legs": legs})
    return out


def parse_tahminler_dir():
    """Harbi_Ganyan_Analiz/*/*_Tahminler.txt -> races[(iso,hip,kno)] = {atlar, ekuri, bes_nos}"""
    races = {}
    for date_dir in sorted(glob.glob(os.path.join(ANALIZ, "*"))):
        if not os.path.isdir(date_dir):
            continue
        for path in glob.glob(os.path.join(date_dir, "*_Tahminler.txt")):
            _parse_one(path, races)
    return races


def _parse_one(path, races):
    cur = None
    bes_names = None
    name_to_no = {}
    for raw in open(path, encoding="utf-8", errors="replace").read().split("\n"):
        ln = raw.rstrip("\n")
        if ln.startswith("KO:"):
            if cur is not None:
                _finish(cur, bes_names, name_to_no, races)
            p = ln[3:].split("|")
            if len(p) < 8:
                cur = None; continue
            try:
                kno = int(p[0]); iso = datetime.strptime(p[2], "%d.%m.%Y").strftime("%Y-%m-%d")
            except Exception:
                cur = None; continue
            cur = {"kno": kno, "hip": norm_hip(p[1]), "iso": iso, "atlar": [], "ekuri": [],
                   "race_type": (p[3] if len(p) > 3 else "").strip().lower(),
                   "race_subtype": (p[4] if len(p) > 4 else "").strip().lower()}
            bes_names = None; name_to_no = {}
        elif cur is not None and ln.startswith("EKURI:"):
            cur["ekuri"] = ekuri_parse(ln[6:].strip())
        elif cur is not None and ln.startswith("5SATIR:"):
            vals = {}
            for tok in ln[7:].split("|"):
                if "=" in tok:
                    k, v = tok.split("=", 1); vals[k] = v
            bes_names = [vals.get(k) for k in ("FAV", "SUR", "YAZ", "BOM", "HAR")]
        elif cur is not None and ln.startswith("ATNO:"):
            d = {}
            for tok in ln.split("|"):
                if ":" in tok:
                    k, v = tok.split(":", 1); d[k] = v
            try:
                a = {"at_no": int(d.get("ATNO", 0)), "at": d.get("AT", ""),
                     "ana": float(d.get("ANA", 0) or 0), "agf": float(d.get("AGF", 0) or 0),
                     "flow_rank": int(float(d.get("AKIS", 0) or 0))}
            except Exception:
                continue
            cur["atlar"].append(a)
            name_to_no[a["at"]] = a["at_no"]
    if cur is not None:
        _finish(cur, bes_names, name_to_no, races)


def _finish(cur, bes_names, name_to_no, races):
    cur["atlar"].sort(key=lambda a: a["ana"], reverse=True)
    cur["n_at"] = len(cur["atlar"])
    cur["fark"] = cur["atlar"][0]["ana"] - cur["atlar"][1]["ana"] if len(cur["atlar"]) >= 2 else 100.0
    # yayınlanan 5 satır at_no'ları (ANA rankından bağımsız, gerçek satırlar)
    bes = []
    if bes_names:
        for nm in bes_names:
            bes.append(name_to_no.get(nm))
    cur["bes_nos"] = bes  # [fav,sur,yaz,bom,har] at_no ya da None
    races[(cur["iso"], cur["hip"], cur["kno"])] = cur


def leg_from_race(r):
    return {"kno": r["kno"], "n_at": r["n_at"], "fark": r["fark"],
            "ekuri": r.get("ekuri") or [],
            "race_type": r.get("race_type", ""),
            "race_subtype": r.get("race_subtype", ""),
            "bes_nos": r.get("bes_nos") or [],
            "atlar": [{"at_no": a["at_no"], "at": a["at"], "ana": a["ana"],
                       "agf": a["agf"], "flow_rank": a["flow_rank"]} for a in r["atlar"]]}


def ana_rank(r, no):
    for i, a in enumerate(r["atlar"], 1):
        if a["at_no"] == no:
            return i
    return None


def bes_line_of(r, wset):
    """winning_set'in 5-satırdaki konumu: 'FAV/SUR/YAZ/BOM/HAR' ya da None."""
    for i, no in enumerate(r["bes_nos"]):
        if no is not None and no in wset:
            return LINE_LABELS[i]
    return None


def main():
    print("Tahminler parse ediliyor...")
    races = parse_tahminler_dir()
    results = load_results(prefer="csv")          # JSON (Şubat-Mart) + CSV (Nisan-Mayıs)
    alt_map = derive_altililar()                   # altılı tanımları _Altili.txt'ten (tam aralık)
    cal = load_cal()
    print(f"  koşu: {len(races)}, sonuç gün/hip: {len(results)}, "
          f"altılı gün/hip: {len(alt_map)}")

    # tier bazli sayaclar
    stats = {ad: {
        "altili": 0, "hit": 0,
        "leg_dagilim": Counter(),     # dogru ayak sayisi -> kupon sayisi
        "miss1": 0,                   # tam 1 ayak kacti (5/6)
        "miss1_bes_ici": 0,           # o 1 ayagin kazanani 5-satirdaydi
        "miss1_line": Counter(),      # 5-satir konumu (FAV..HAR / DISI)
        "miss1_width_lt_rank": 0,     # genislik < kazanan ANA-rank (genisletilince girer)
        "miss1_banko_leg": 0,         # kacan ayak banko/cipa ayagiydi
        "miss1_rank": Counter(),      # kazanan ANA-rank dagilimi
        "miss1_examples": [],
    } for ad, _, _ in KUPON_TIERS}

    for (iso, hip), alts in alt_map.items():
        c = results.get((iso, hip))
        if not c:
            continue
        for alt in alts:
            legs_r = []
            ok = True
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
            legs = [leg_from_race(r) for r in legs_r]
            birim = birim_fiyat(hip)
            for tier in KUPON_TIERS:
                ad = tier[0]
                _, _, _, plan, komb = build_tier(legs, tier, birim, cal, 0.50)
                st = stats[ad]
                st["altili"] += 1
                # ayak isabetleri
                miss = []
                dogru = 0
                for p, r in zip(plan, legs_r):
                    sec = {a["at_no"] for a in p["secilen"]}
                    if sec & wsets[r["kno"]]:
                        dogru += 1
                    else:
                        miss.append((p, r))
                st["leg_dagilim"][dogru] += 1
                if dogru == 6:
                    st["hit"] += 1
                if len(miss) == 1:
                    st["miss1"] += 1
                    p, r = miss[0]
                    wset = wsets[r["kno"]]
                    line = bes_line_of(r, wset)
                    wno = next(iter(wset))  # kazanan (tekil) — rank icin
                    # winning_set icinden 5-satirda olani sec (rank icin en iyi)
                    rnk = None
                    for no in wset:
                        rr = ana_rank(r, no)
                        if rr and (rnk is None or rr < rnk):
                            rnk = rr
                    st["miss1_rank"][rnk if rnk and rnk <= 6 else (7 if rnk else 0)] += 1
                    if line:
                        st["miss1_bes_ici"] += 1
                        st["miss1_line"][line] += 1
                        if rnk is not None and p["width"] < rnk:
                            st["miss1_width_lt_rank"] += 1
                    else:
                        st["miss1_line"]["5-satır DIŞI"] += 1
                    if p.get("banko_lider"):
                        st["miss1_banko_leg"] += 1
                    if line in ("BOM", "HAR") and len(st["miss1_examples"]) < 12:
                        st["miss1_examples"].append(
                            f"{iso} {hip} K{r['kno']} alt#{alt['idx']}: kazanan No:{wno} "
                            f"= {line} (ANA#{rnk}), ayak genişliği {p['width']} at "
                            f"[{'BANKO' if p.get('banko_lider') else p['etiket']}], "
                            f"n_at={r['n_at']} fark={r['fark']:.0f}")

    # rapor
    L = ["# Kupon Kaçan Analizi — '5 satırda var, kupona girmemiş' kazananlar", ""]
    L.append(f"- Aralık tahmin koşusu: {len(races)} | sonuç gün/hip: {len(results)} | altılı gün/hip: {len(alt_map)}")
    L.append("- Soru: Kaç 5/6 kuponda kazanan aslında 5-satırımızdaydı ama dar ayak yüzünden dışarıda kaldı?")
    L.append("- Üretim kodu DEĞİŞTİRİLMEDİ.")
    L.append("")
    for ad, _, _ in KUPON_TIERS:
        st = stats[ad]
        n = st["altili"]
        L.append(f"## {ad}")
        L.append(f"- Altılı: {n} | Tam isabet (6/6): {st['hit']} (%{100*st['hit']/n:.1f})" if n else f"## {ad}\n- veri yok")
        if not n:
            L.append(""); continue
        dag = st["leg_dagilim"]
        L.append("- Doğru ayak dağılımı: " +
                 ", ".join(f"{k}/6={dag.get(k,0)}" for k in range(6, 1, -1)))
        m1 = st["miss1"]
        L.append(f"- Tam 1 ayak kaçan (5/6): {m1}")
        if m1:
            bi = st["miss1_bes_ici"]
            L.append(f"  - Bunların **{bi}**'inde kazanan 5-satırımızdaydı (%{100*bi/m1:.1f})")
            L.append(f"  - Bunların **{st['miss1_width_lt_rank']}**'inde ayak genişliği < kazanan ANA-rank "
                     f"→ ayağı genişletsek kupon **6/6 olurdu** (%{100*st['miss1_width_lt_rank']/m1:.1f} of 5/6)")
            L.append("  - 5-satır konumu: " +
                     ", ".join(f"{k}={st['miss1_line'][k]}" for k in
                               ["FAV","SUR","YAZ","BOM","HAR","5-satır DIŞI"] if st['miss1_line'].get(k)))
            L.append("  - Kazanan ANA-rank dağılımı: " +
                     ", ".join(f"#{k}={st['miss1_rank'][k]}" for k in sorted(st['miss1_rank']) if k) +
                     (f", 7+={st['miss1_rank'].get(7,0)}" if st['miss1_rank'].get(7) else "") +
                     (f", eşleşmedi={st['miss1_rank'].get(0,0)}" if st['miss1_rank'].get(0) else ""))
            L.append(f"  - Kaçan ayak banko/çıpa ayağıydı: {st['miss1_banko_leg']}")
        L.append("")

    # örnekler (Harbi tier)
    L.append("## Örnekler — BOM/HAR'da kazananı bulduğumuz ama kupona almadığımız ayaklar (Harbi 6'lısı)")
    for ex in stats["Harbi Ganyan 6'lısı"]["miss1_examples"]:
        L.append(f"- {ex}")
    L.append("")

    open(OUT, "w", encoding="utf-8").write("\n".join(L))
    print(f"Rapor yazıldı: {OUT}")
    print("\n".join(L))


if __name__ == "__main__":
    main()
