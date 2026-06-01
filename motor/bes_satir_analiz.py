# -*- coding: utf-8 -*-
"""
5 SATIR PERFORMANS ANALİZİ — taze bulk tahmin (v5_tahmin_*.txt) vs CSV sonuçları.
Eküri-kredili: kazanan kümesi = {kazanan} ∪ eküri ortakları (winning_set).

Ölçülenler:
  - İlk1/İlk3/İlk4/İlk5 = kazanan bizim ANA sıralamamızda ilk-g içinde mi
  - 5-satır isabet = kazanan, FAV/SUR/YAZ/BOM/HAR adlı 5 atımızdan biri mi
  - Segment (≤9 / 10-13 / 14+) ve kaynak (AGF'li / AGF'siz) kırılımı
  - Eküri katkısı (eküri-kredili vs kredisiz fark)
"""
import io, sys, os, glob
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from altili_lib import BASE, norm_hip, load_all_csv, load_results, winning_set, ekuri_parse
from datetime import datetime

def newest_bulk():
    c = sorted(glob.glob(os.path.join(BASE, "v5_tahmin_*.txt")), key=os.path.getmtime)
    return c[-1]

def parse_bulk(path):
    """-> list of race dicts: {ti,hip,kno,kaynak,n_at, sirali:[(at_no,at,ana)], bes:[at_no..], ekuri}"""
    races = []
    cur = None
    isim2no = {}
    bes_isim = None
    for ln in open(path, encoding="utf-8", errors="replace"):
        ln = ln.rstrip("\n")
        if ln.startswith("KO:"):
            if cur is not None: races.append(_finish(cur, bes_isim, isim2no))
            p = ln[3:].split("|")
            ti = datetime.strptime(p[2], "%d.%m.%Y").strftime("%Y-%m-%d")
            cur = {"ti": ti, "hip": norm_hip(p[1]), "kno": int(p[0]),
                   "kaynak": p[8] if len(p) > 8 else "", "atlar": [], "ekuri": []}
            isim2no = {}; bes_isim = None
        elif ln.startswith("EKURI:") and cur is not None:
            cur["ekuri"] = ekuri_parse(ln[6:].strip())
        elif ln.startswith("5SATIR:") and cur is not None:
            d = {}
            for tok in ln[7:].split("|"):
                if "=" in tok:
                    k, v = tok.split("=", 1); d[k] = v
            bes_isim = [d.get("FAV"), d.get("SUR"), d.get("YAZ"), d.get("BOM"), d.get("HAR")]
        elif ln.startswith("ATNO:") and cur is not None:
            f = {}
            for tok in ln.split("|"):
                if ":" in tok:
                    k, v = tok.split(":", 1); f[k] = v
            ano = int(f.get("ATNO", 0)); isim = f.get("AT", ""); ana = float(f.get("ANA", 0))
            cur["atlar"].append((ano, isim, ana)); isim2no[isim] = ano
    if cur is not None: races.append(_finish(cur, bes_isim, isim2no))
    return races

def _finish(cur, bes_isim, isim2no):
    cur["atlar"].sort(key=lambda x: x[2], reverse=True)
    cur["n_at"] = len(cur["atlar"])
    cur["sirali_no"] = [a[0] for a in cur["atlar"]]
    bes = []
    if bes_isim:
        for nm in bes_isim:
            if nm and nm in isim2no: bes.append(isim2no[nm])
    cur["bes"] = bes
    return cur

def seg(n):
    if n <= 9: return "≤9"
    if n <= 13: return "10-13"
    return "14+"

def main():
    path = newest_bulk()
    print(f"Bulk: {os.path.basename(path)}")
    races = parse_bulk(path)
    csvs = load_results(prefer="csv")   # JSON (Şubat-Mart) + CSV (Nisan-Mayıs)

    # toplam + segment + kaynak sayaçları
    M = {"i1": 0, "i3": 0, "i4": 0, "i5": 0, "bes": 0, "n": 0,
         "i1_ne": 0, "bes_ne": 0}  # _ne = eküri kredisi YOK
    seg_stat = defaultdict(lambda: dict(i1=0, i3=0, i4=0, i5=0, bes=0, n=0))
    src_stat = defaultdict(lambda: dict(i1=0, i3=0, i4=0, i5=0, bes=0, n=0))
    ekuri_etkili = 0   # eküri kredisinin 5-satır sonucunu değiştirdiği koşu

    for r in races:
        c = csvs.get((r["ti"], r["hip"]))
        if not c: continue
        w = c["kazanan"].get(r["kno"])
        if w is None: continue
        order = r["sirali_no"]
        if w not in order: continue
        wset = winning_set(c, r["kno"])  # eküri-kredili
        M["n"] += 1
        s = seg(r["n_at"]); src = "AGF'li" if "AGF" in r["kaynak"] else "AGF'siz"
        seg_stat[s]["n"] += 1; src_stat[src]["n"] += 1

        # İlk-g (eküri-kredili): wset'ten herhangi biri ilk-g'de mi
        def in_topg(g):
            return any(x in order[:g] for x in wset)
        # eküri kredisiz (sadece kazanan)
        wrank = order.index(w) + 1
        for g, key in [(1, "i1"), (3, "i3"), (4, "i4"), (5, "i5")]:
            if in_topg(g):
                M[key] += 1; seg_stat[s][key] += 1; src_stat[src][key] += 1
        if wrank == 1: M["i1_ne"] += 1
        # 5-satır (eküri-kredili): wset ∩ bes
        bes_set = set(r["bes"])
        hit = bool(wset & bes_set)
        hit_ne = w in bes_set
        if hit: M["bes"] += 1; seg_stat[s]["bes"] += 1; src_stat[src]["bes"] += 1
        if hit_ne: M["bes_ne"] += 1
        if hit and not hit_ne: ekuri_etkili += 1

    n = M["n"]
    def pct(x): return f"{100*x/n:.1f}%" if n else "-"
    print(f"\nEşleşen koşu: {n}\n")
    print("="*60)
    print("GENEL (eküri-kredili)")
    print("="*60)
    print(f"  İlk1: {pct(M['i1'])}  İlk3: {pct(M['i3'])}  İlk4: {pct(M['i4'])}  İlk5: {pct(M['i5'])}")
    print(f"  5-SATIR isabet: {pct(M['bes'])}")
    print(f"\n  Eküri katkısı: İlk1 {100*(M['i1']-M['i1_ne'])/n:+.1f}p, "
          f"5-satır {100*(M['bes']-M['bes_ne'])/n:+.1f}p ({ekuri_etkili} koşuda 5-satır eküri ile tuttu)")

    print("\n" + "="*60)
    print("SEGMENT (alan büyüklüğü)")
    print("="*60)
    print(f"{'segment':<8}{'n':>5}{'İlk1':>8}{'İlk3':>8}{'İlk4':>8}{'İlk5':>8}{'5-satır':>9}")
    for sg in ["≤9", "10-13", "14+"]:
        d = seg_stat[sg]; m = d["n"] or 1
        print(f"{sg:<8}{d['n']:>5}{100*d['i1']/m:>7.0f}%{100*d['i3']/m:>7.0f}%"
              f"{100*d['i4']/m:>7.0f}%{100*d['i5']/m:>7.0f}%{100*d['bes']/m:>8.0f}%")

    print("\n" + "="*60)
    print("KAYNAK")
    print("="*60)
    print(f"{'kaynak':<8}{'n':>5}{'İlk1':>8}{'İlk3':>8}{'İlk4':>8}{'İlk5':>8}{'5-satır':>9}")
    for src in ["AGF'li", "AGF'siz"]:
        d = src_stat[src]; m = d["n"] or 1
        print(f"{src:<8}{d['n']:>5}{100*d['i1']/m:>7.0f}%{100*d['i3']/m:>7.0f}%"
              f"{100*d['i4']/m:>7.0f}%{100*d['i5']/m:>7.0f}%{100*d['bes']/m:>8.0f}%")

    # rapor için döndür
    return M, seg_stat, src_stat, ekuri_etkili

if __name__ == "__main__":
    main()
