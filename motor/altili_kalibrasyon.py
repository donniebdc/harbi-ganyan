# -*- coding: utf-8 -*-
"""
ALTILI KALİBRASYON — gerçek sonuçlarla ölçülen kapsama eğrileri.
  (A) Favori (ANA #1) gerçek kazanma oranı -> BANKO gücü tablosu
      fark x alan-büyüklüğü segmentine göre.
  (B) Kazananın bizim ilk-g ANA sıralamamızda olma oranı (cov[g]) -> ayak
      genişliği başına isabet, alan segmentine göre.
Bu tablolar kupon kurucunun veri-temelli çekirdeğidir.
"""
import io, sys, os
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from altili_lib import BASE, MOTOR, parse_tahmin_arsiv, load_all_csv, winning_set
import glob

def _newest_bulk():
    cands = sorted(glob.glob(os.path.join(BASE, "Toplu Tahminler", "v5_tahmin_*.txt")), key=os.path.getmtime)
    return cands[-1] if cands else os.path.join(BASE, "Toplu Tahminler", "v5_tahmin_01042026-30052026.txt")

TAHMIN = _newest_bulk()

def seg_n(n):
    if n <= 7:   return "≤7"
    if n <= 9:   return "8-9"
    if n <= 11:  return "10-11"
    if n <= 13:  return "12-13"
    return "14+"

def seg_fark(f):
    if f >= 40: return "≥40"
    if f >= 25: return "25-40"
    if f >= 15: return "15-25"
    if f >= 8:  return "8-15"
    return "<8"

def main():
    races = parse_tahmin_arsiv(TAHMIN)
    csvs  = load_all_csv()
    print(f"Tahmin koşusu: {len(races)} | CSV gün-hipodrom: {len(csvs)}")

    # eşleşen koşular: winner bilinen
    matched = []
    for (ti, hip, kno), r in races.items():
        c = csvs.get((ti, hip))
        if not c: continue
        w = c["kazanan"].get(kno)
        if w is None: continue
        # bizim sıralamada kazananın rank'ı
        order = [a["at_no"] for a in r["atlar"]]
        if w not in order: continue
        wrank = order.index(w) + 1   # 1 = favorimiz kazandı
        matched.append((r, w, wrank))
    print(f"Kazananı eşleşen koşu: {len(matched)}\n")

    # ── (A) FAVORİ KAZANMA ORANI: fark x alan ──
    print("="*72)
    print("(A) FAVORİ (ANA #1) GERÇEK KAZANMA ORANI  — banko gücü")
    print("="*72)
    tbl = defaultdict(lambda: [0, 0])  # (seg_n, seg_fark) -> [win, total]
    glob_n = defaultdict(lambda: [0, 0])
    for r, w, wrank in matched:
        sn = seg_n(r["n_at"]); sf = seg_fark(r["fark"])
        tbl[(sn, sf)][1] += 1
        glob_n[sn][1] += 1
        if wrank == 1:
            tbl[(sn, sf)][0] += 1
            glob_n[sn][0] += 1
    segs_n = ["≤7","8-9","10-11","12-13","14+"]
    segs_f = ["≥40","25-40","15-25","8-15","<8"]
    print(f"{'alan/fark':<10}" + "".join(f"{s:>12}" for s in segs_f) + f"{'GENEL':>12}")
    for sn in segs_n:
        row = f"{sn:<10}"
        for sf in segs_f:
            w, t = tbl[(sn, sf)]
            row += f"{(f'{100*w/t:.0f}% ({t})' if t else '-'):>12}"
        gw, gt = glob_n[sn]
        row += f"{(f'{100*gw/gt:.0f}% ({gt})' if gt else '-'):>12}"
        print(row)

    # ── (B) KAPSAMA cov[g]: kazanan ilk-g içinde mi? alan segmentine göre ──
    print("\n" + "="*72)
    print("(B) KAPSAMA cov[g] = P(kazanan bizim ilk-g ANA sıralamasında) — alan segmenti")
    print("="*72)
    cov = defaultdict(lambda: defaultdict(int))  # seg -> g -> count(wrank<=g)
    tot = defaultdict(int)
    for r, w, wrank in matched:
        sn = seg_n(r["n_at"]); tot[sn] += 1
        for g in range(1, 11):
            if wrank <= g:
                cov[sn][g] += 1
    print(f"{'alan':<8}{'n':>6}" + "".join(f"{('g='+str(g)):>8}" for g in range(1, 9)))
    for sn in segs_n:
        t = tot[sn]
        if not t: continue
        row = f"{sn:<8}{t:>6}"
        for g in range(1, 9):
            row += f"{100*cov[sn][g]/t:>7.0f}%"
        print(row)
    # genel
    gtot = sum(tot.values())
    gcov = defaultdict(int)
    for r, w, wrank in matched:
        for g in range(1, 11):
            if wrank <= g: gcov[g] += 1
    row = f"{'GENEL':<8}{gtot:>6}"
    for g in range(1, 9):
        row += f"{100*gcov[g]/gtot:>7.0f}%"
    print(row)

    # cov tablolarını dosyaya yaz (kupon kurucu okuyacak)
    import json
    out = {"cov": {sn: {g: cov[sn][g]/tot[sn] for g in range(1, 11)} for sn in segs_n if tot[sn]},
           "tot": {sn: tot[sn] for sn in segs_n},
           "fav": {f"{sn}|{sf}": (tbl[(sn,sf)][0], tbl[(sn,sf)][1]) for sn in segs_n for sf in segs_f}}
    with open(os.path.join(MOTOR, "altili_kalibrasyon.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nKalibrasyon kaydedildi: altili_kalibrasyon.json")

if __name__ == "__main__":
    main()
