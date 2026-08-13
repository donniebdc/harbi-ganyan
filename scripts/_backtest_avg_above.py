# -*- coding: utf-8 -*-
"""
Karşılaştırmalı backtest:
  A) Mevcut sistem  (harbi_secim.compute — STOP_GAP eşikleri)
  B) Yeni sistem    (ortalama üstü zorunlu + model ek seçim yapabilir)

Yeni sistem mantığı:
  avg = sum(puan) / n_at
  force_list = [at | at.puan >= avg]       ← her zaman yazılır
  model_list = harbi_secim.compute(...)    ← mevcut mantık
  final      = union(force_list, model_list)
"""
from __future__ import annotations
import sys, json, os, re
from collections import defaultdict

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/opt/harbi_ganyan_v3/src")
sys.path.insert(0, "/opt/harbi_ganyan_backend")

from harbi_v3.harbi_secim import compute as hs_compute
from app.config import settings

# ── DB bağlantısı ────────────────────────────────────────────────────────────
m = re.match(r"postgresql\+psycopg2://([^:]+):([^@]+)@([^/]+)/(.+)", settings.database_url)
db_user, db_pass, db_host, db_name = m.groups() if m else ("postgres","","localhost","harbi_ganyan")
conn = psycopg2.connect(host=db_host, user=db_user, password=db_pass, dbname=db_name)
cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

SQL = """
SELECT
    k.kno, k.n_at, k.analiz_puanlari, k.zorluk,
    ks.kazanan,
    gh.hipodrom,
    g.date
FROM kosu k
JOIN gun_hipodrom gh ON gh.id = k.gh_id
JOIN gun g           ON g.id  = gh.gun_id
JOIN kosu_sonuc ks   ON ks.kosu_id = k.id
WHERE ks.kazanan IS NOT NULL
  AND k.analiz_puanlari IS NOT NULL
ORDER BY g.date, gh.hipodrom, k.kno
"""
cur.execute(SQL)
rows = cur.fetchall()
cur.close()
conn.close()

print(f"Toplam sonuçlanmış koşu: {len(rows)}")


# ── Yeni sistem: ortalama üstü zorunlu + model birleşimi ─────────────────────
def compute_avg_above(ap: list, n_at: int, zk: str | None) -> dict | None:
    if not ap:
        return None

    scores  = [p.get("ana", 0) for p in ap]
    avg     = sum(scores) / len(scores) if scores else 0
    sirali  = sorted(ap, key=lambda x: x.get("ana", 0), reverse=True)

    # Zorunlu: ortalama üstü
    above_avg_nos = {p["at_no"] for p in sirali if p.get("ana", 0) >= avg}

    # Model seçimi
    try:
        model_result = hs_compute(ap, n_at=n_at, zorluk_kodu=zk,
                                  is_surdirek=False, surdirek_horse_no=None)
        model_nos = {a["at_no"] for a in (model_result or {}).get("adaylar", [])}
    except Exception:
        model_nos = set()

    # Birleştir
    final_nos     = above_avg_nos | model_nos
    final_adaylar = [p for p in sirali if p["at_no"] in final_nos]
    adet          = len(final_adaylar)

    tip = ("tek_at"     if adet == 1 else
           "iki_aday"   if adet == 2 else
           "uc_aday"    if adet == 3 else
           "dort_aday"  if adet == 4 else
           "genis_liste")

    return {"tip": tip, "adaylar": final_adaylar, "adet": adet,
            "avg": avg, "above_count": len(above_avg_nos)}


# ── Backtest ─────────────────────────────────────────────────────────────────
def make_stats():
    return defaultdict(lambda: {"toplam": 0, "isabetli": 0, "toplam_adet": 0})

stats_a = {"tip": make_stats(), "n_at": make_stats(), "hip": make_stats(), "gun": make_stats()}
stats_b = {"tip": make_stats(), "n_at": make_stats(), "hip": make_stats(), "gun": make_stats()}
genel_a = {"toplam": 0, "isabetli": 0, "hata": 0}
genel_b = {"toplam": 0, "isabetli": 0, "hata": 0}

# Sürdirek koşuları (gun.surdirek json — günden hangi koşunun surdirek olduğuna bakarız)
# gun.surdirek kolonu mevcut değilse atla; sürdirek için is_surdirek=False tutuyoruz
# (backtest amacıyla eşit muamele — sadece ortalama filtresini test ediyoruz)

TIP_ORDER = ["tek_at", "iki_aday", "uc_aday", "dort_aday", "genis_liste"]

for row in rows:
    ap         = row["analiz_puanlari"] or []
    kazanan_no = row["kazanan"]
    if kazanan_no is None or not ap:
        continue

    n_at   = row["n_at"] or 0
    zorluk = row["zorluk"] or {}
    zk     = zorluk.get("zorluk_kodu") if zorluk else None
    tarih  = str(row["date"])
    hip    = row["hipodrom"] or "?"
    nb     = ("<=7" if n_at<=7 else "8-10" if n_at<=10 else "11-13" if n_at<=13 else "14+")

    # A) Mevcut sistem
    try:
        hs = hs_compute(ap, n_at=n_at, zorluk_kodu=zk,
                        is_surdirek=False, surdirek_horse_no=None) or {}
        nos_a   = {a["at_no"] for a in hs.get("adaylar", [])}
        tip_a   = hs.get("tip", "bilinmiyor")
        adet_a  = hs.get("adet", len(nos_a))
        hit_a   = kazanan_no in nos_a
        genel_a["toplam"]   += 1
        genel_a["isabetli"] += int(hit_a)
        for d, k in ((stats_a["tip"], tip_a), (stats_a["n_at"], nb),
                     (stats_a["hip"], hip), (stats_a["gun"], tarih)):
            d[k]["toplam"]      += 1
            d[k]["isabetli"]    += int(hit_a)
            d[k]["toplam_adet"] += adet_a
    except Exception:
        genel_a["hata"] += 1

    # B) Yeni sistem
    try:
        res_b = compute_avg_above(ap, n_at, zk)
        if not res_b:
            genel_b["hata"] += 1
            continue
        nos_b  = {a["at_no"] for a in res_b.get("adaylar", [])}
        tip_b  = res_b["tip"]
        adet_b = res_b["adet"]
        hit_b  = kazanan_no in nos_b
        genel_b["toplam"]   += 1
        genel_b["isabetli"] += int(hit_b)
        for d, k in ((stats_b["tip"], tip_b), (stats_b["n_at"], nb),
                     (stats_b["hip"], hip), (stats_b["gun"], tarih)):
            d[k]["toplam"]      += 1
            d[k]["isabetli"]    += int(hit_b)
            d[k]["toplam_adet"] += adet_b
    except Exception:
        genel_b["hata"] += 1


# ── Rapor ─────────────────────────────────────────────────────────────────────
SEP = "=" * 70

def pct(i, t):
    return f"%{i/t*100:.1f}" if t > 0 else "-%"

def avg_adet(d, k):
    s = d[k]
    return f"{s['toplam_adet']/s['toplam']:.2f}" if s["toplam"] > 0 else "-"

print(f"\n{SEP}")
print("KARŞILAŞTIRMALI BACKTEST:  A=Mevcut  B=Ortalama-Üstü+Model")
print(SEP)

# Genel
Ga, Gb = genel_a, genel_b
print(f"\n{'':30} {'A (Mevcut)':>14} {'B (Ort.Üstü)':>14}")
print(f"  {'Toplam koşu':<28} {Ga['toplam']:>14} {Gb['toplam']:>14}")
print(f"  {'İsabetli':<28} {Ga['isabetli']:>14} {Gb['isabetli']:>14}")
print(f"  {'İsabet oranı':<28} {pct(Ga['isabetli'],Ga['toplam']):>14} {pct(Gb['isabetli'],Gb['toplam']):>14}")
print(f"  {'Hata':<28} {Ga['hata']:>14} {Gb['hata']:>14}")

# Fark
delta = (Gb["isabetli"]/Gb["toplam"] - Ga["isabetli"]/Ga["toplam"]) * 100 if Gb["toplam"] > 0 else 0
print(f"\n  >> Fark (B - A): {'+' if delta >= 0 else ''}{delta:.2f} puan")

# Tip bazlı
print(f"\n{'-'*70}")
print("TİP BAZLI:")
print(f"  {'Tip':<14} {'A:Top':>6} {'A:Hit%':>7} {'A:AvgAt':>7}  {'B:Top':>6} {'B:Hit%':>7} {'B:AvgAt':>7}")
print(f"  {'-'*62}")
all_tips = list(dict.fromkeys(TIP_ORDER + [t for t in stats_b["tip"] if t not in TIP_ORDER]))
for tip in all_tips:
    sa = stats_a["tip"][tip]
    sb = stats_b["tip"][tip]
    if sa["toplam"] == 0 and sb["toplam"] == 0:
        continue
    aa = f"{sa['toplam_adet']/sa['toplam']:.2f}" if sa['toplam']>0 else "-"
    ba = f"{sb['toplam_adet']/sb['toplam']:.2f}" if sb['toplam']>0 else "-"
    print(f"  {tip:<14} {sa['toplam']:>6} {pct(sa['isabetli'],sa['toplam']):>7} {aa:>7}  "
          f"{sb['toplam']:>6} {pct(sb['isabetli'],sb['toplam']):>7} {ba:>7}")

# N_at kategorisi
print(f"\n{'-'*70}")
print("AT SAYISI KATEGORİSİ:")
print(f"  {'Kat.':<8} {'A:Top':>6} {'A:Hit%':>7} {'A:AvgAt':>7}  {'B:Top':>6} {'B:Hit%':>7} {'B:AvgAt':>7}")
print(f"  {'-'*58}")
for bucket in ["<=7", "8-10", "11-13", "14+"]:
    sa = stats_a["n_at"][bucket]
    sb = stats_b["n_at"][bucket]
    if sa["toplam"] == 0 and sb["toplam"] == 0:
        continue
    aa = f"{sa['toplam_adet']/sa['toplam']:.2f}" if sa['toplam']>0 else "-"
    ba = f"{sb['toplam_adet']/sb['toplam']:.2f}" if sb['toplam']>0 else "-"
    print(f"  {bucket:<8} {sa['toplam']:>6} {pct(sa['isabetli'],sa['toplam']):>7} {aa:>7}  "
          f"{sb['toplam']:>6} {pct(sb['isabetli'],sb['toplam']):>7} {ba:>7}")

# Hipodrom
print(f"\n{'-'*70}")
print("HİPODROM (>=20 koşu):")
print(f"  {'Hip':<14} {'A:Top':>6} {'A:Hit%':>7} {'A:AvgAt':>7}  {'B:Top':>6} {'B:Hit%':>7} {'B:AvgAt':>7}")
print(f"  {'-'*62}")
for hip in sorted(stats_a["hip"], key=lambda h: -stats_a["hip"][h]["toplam"]):
    sa = stats_a["hip"][hip]
    sb = stats_b["hip"][hip]
    if sa["toplam"] < 20:
        continue
    aa = f"{sa['toplam_adet']/sa['toplam']:.2f}" if sa['toplam']>0 else "-"
    ba = f"{sb['toplam_adet']/sb['toplam']:.2f}" if sb['toplam']>0 else "-"
    delta_h = (sb["isabetli"]/sb["toplam"] - sa["isabetli"]/sa["toplam"]) * 100 if sb["toplam"] > 0 else 0
    flag = "↑" if delta_h > 2 else ("↓" if delta_h < -2 else " ")
    print(f"  {hip:<14} {sa['toplam']:>6} {pct(sa['isabetli'],sa['toplam']):>7} {aa:>7}  "
          f"{sb['toplam']:>6} {pct(sb['isabetli'],sb['toplam']):>7} {ba:>7}  {flag}{abs(delta_h):.1f}")

# Son 14 gün
print(f"\n{'-'*70}")
print("SON 14 GÜN:")
print(f"  {'Tarih':<12} {'A:Koşu':>6} {'A:%':>6}  {'B:Koşu':>6} {'B:%':>6}  {'Fark':>6}")
print(f"  {'-'*52}")
all_dates = sorted(set(list(stats_a["gun"].keys()) + list(stats_b["gun"].keys())))[-14:]
for tarih in all_dates:
    sa = stats_a["gun"][tarih]
    sb = stats_b["gun"][tarih]
    if sa["toplam"] == 0 and sb["toplam"] == 0:
        continue
    pa = sa["isabetli"]/sa["toplam"]*100 if sa["toplam"]>0 else 0
    pb = sb["isabetli"]/sb["toplam"]*100 if sb["toplam"]>0 else 0
    d  = pb - pa
    print(f"  {tarih:<12} {sa['toplam']:>6} {pa:>5.1f}%  {sb['toplam']:>6} {pb:>5.1f}%  "
          f"{('+' if d>=0 else '')}{d:.1f}")

# Ortalama at sayısı özeti
total_a = sum(s["toplam_adet"] for s in stats_a["tip"].values())
total_b = sum(s["toplam_adet"] for s in stats_b["tip"].values())
n_total = genel_a["toplam"]
print(f"\n{'-'*70}")
print(f"ORTALAMA AT SAYISI PER KOŞU:")
print(f"  A (Mevcut)     : {total_a/n_total:.2f}")
print(f"  B (Ort.Üstü)   : {total_b/n_total:.2f}" if n_total > 0 else "  B: -")

print(f"\n{SEP}")
print("ÖZET")
print(SEP)
print(f"  Mevcut sistem (A)         : {pct(Ga['isabetli'],Ga['toplam'])} isabet / {n_total} koşu")
print(f"  Yeni sistem (B)           : {pct(Gb['isabetli'],Gb['toplam'])} isabet / {Gb['toplam']} koşu")
print(f"  Fark                      : {'+' if delta>=0 else ''}{delta:.2f} puan")
print(f"  Ortalama at/koşu (A)      : {total_a/n_total:.2f}")
print(f"  Ortalama at/koşu (B)      : {total_b/n_total:.2f}" if n_total > 0 else "  -")

# JSON kaydet
result = {
    "genel_a": genel_a, "genel_b": genel_b,
    "delta_pct": delta,
    "avg_horses_a": total_a / n_total if n_total else 0,
    "avg_horses_b": total_b / n_total if n_total else 0,
}
out = "/opt/harbi_ganyan_v3/reports/backtest_avg_above_2026-07-09.json"
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nJSON: {out}")
