# -*- coding: utf-8 -*-
"""
Karşılaştırmalı backtest — 3 sistem:
  A) Mevcut sistem  (harbi_secim rev4 — STOP_GAP eşikleri)
  B) Ortalama-üstü + model birleşimi (önceki test, cap yok)
  C) Ortalama-üstü + model birleşimi + AT KAPI:
       n_at <= 7  → maks 3 at
       n_at 8-10  → maks 4 at
       n_at > 10  → sınırsız (ortalama üstü + model ne verirse)

Her sistemde sürdirek atlar kendi koşusunda tek_at (backtest'te
is_surdirek=False kullanılıyor — eşit karşılaştırma için).
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

# ── DB ───────────────────────────────────────────────────────────────────────
m = re.match(r"postgresql\+psycopg2://([^:]+):([^@]+)@([^/]+)/(.+)", settings.database_url)
db_user, db_pass, db_host, db_name = m.groups() if m else ("postgres","","localhost","harbi_ganyan")
conn = psycopg2.connect(host=db_host, user=db_user, password=db_pass, dbname=db_name)
cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("""
SELECT k.kno, k.n_at, k.analiz_puanlari, k.zorluk,
       ks.kazanan, gh.hipodrom, g.date
FROM kosu k
JOIN gun_hipodrom gh ON gh.id = k.gh_id
JOIN gun g           ON g.id  = gh.gun_id
JOIN kosu_sonuc ks   ON ks.kosu_id = k.id
WHERE ks.kazanan IS NOT NULL
  AND k.analiz_puanlari IS NOT NULL
ORDER BY g.date, gh.hipodrom, k.kno
""")
rows = cur.fetchall()
cur.close(); conn.close()
print(f"Toplam sonuçlanmış koşu: {len(rows)}\n")


# ── Yardımcı ─────────────────────────────────────────────────────────────────
def _n_bucket(n_at):
    if n_at <= 7:  return "<=7"
    if n_at <= 10: return "8-10"
    if n_at <= 13: return "11-13"
    return "14+"

def _tip(adet):
    return ("tek_at" if adet==1 else "iki_aday" if adet==2 else
            "uc_aday" if adet==3 else "dort_aday" if adet==4 else "genis_liste")


# ── Sistem B & C: ortalama-üstü + model ──────────────────────────────────────
def compute_b(ap, n_at, zk, apply_cap=False):
    """
    apply_cap=False → Sistem B (cap yok)
    apply_cap=True  → Sistem C (≤7→max3, 8-10→max4, >10→sınırsız)
    """
    if not ap:
        return None

    scores = [p.get("ana", 0) for p in ap]
    avg    = sum(scores) / len(scores)
    sirali = sorted(ap, key=lambda x: x.get("ana", 0), reverse=True)

    # Zorunlu: ortalama üstü
    above_nos = {p["at_no"] for p in sirali if p.get("ana", 0) >= avg}

    # Model seçimi
    try:
        model = hs_compute(ap, n_at=n_at, zorluk_kodu=zk,
                           is_surdirek=False, surdirek_horse_no=None)
        model_nos = {a["at_no"] for a in (model or {}).get("adaylar", [])}
    except Exception:
        model_nos = set()

    # Birleştir
    final_nos  = above_nos | model_nos
    final_list = [p for p in sirali if p["at_no"] in final_nos]

    # Cap uygula
    if apply_cap:
        cap = (3 if n_at <= 7 else 4 if n_at <= 10 else len(final_list))
        final_list = final_list[:cap]

    adet = len(final_list)
    return {"tip": _tip(adet), "adaylar": final_list, "adet": adet}


# ── Backtest döngüsü ──────────────────────────────────────────────────────────
def make_stats():
    return defaultdict(lambda: {"toplam": 0, "isabetli": 0, "toplam_adet": 0})

def empty_genel():
    return {"toplam": 0, "isabetli": 0, "hata": 0, "toplam_adet": 0}

GA, GB, GC = empty_genel(), empty_genel(), empty_genel()
SA = {k: make_stats() for k in ("tip","nb","hip","gun")}
SB = {k: make_stats() for k in ("tip","nb","hip","gun")}
SC = {k: make_stats() for k in ("tip","nb","hip","gun")}

TIP_ORDER = ["tek_at","iki_aday","uc_aday","dort_aday","genis_liste"]

for row in rows:
    ap         = row["analiz_puanlari"] or []
    kazanan_no = row["kazanan"]
    if kazanan_no is None or not ap:
        continue

    n_at  = row["n_at"] or 0
    zk    = (row["zorluk"] or {}).get("zorluk_kodu")
    tarih = str(row["date"])
    hip   = row["hipodrom"] or "?"
    nb    = _n_bucket(n_at)

    def _kaydet(G, S, result):
        if result is None:
            G["hata"] += 1
            return False
        nos   = {a["at_no"] for a in result.get("adaylar", [])}
        tip   = result.get("tip", "bilinmiyor")
        adet  = result.get("adet", len(nos))
        hit   = kazanan_no in nos
        G["toplam"]      += 1
        G["isabetli"]    += int(hit)
        G["toplam_adet"] += adet
        for d, k in ((S["tip"],tip),(S["nb"],nb),(S["hip"],hip),(S["gun"],tarih)):
            d[k]["toplam"]      += 1
            d[k]["isabetli"]    += int(hit)
            d[k]["toplam_adet"] += adet
        return True

    # A
    try:
        ra = hs_compute(ap, n_at=n_at, zorluk_kodu=zk,
                        is_surdirek=False, surdirek_horse_no=None)
        _kaydet(GA, SA, ra)
    except Exception:
        GA["hata"] += 1

    # B (cap yok)
    try:
        rb = compute_b(ap, n_at, zk, apply_cap=False)
        _kaydet(GB, SB, rb)
    except Exception:
        GB["hata"] += 1

    # C (cap var: ≤7→3, 8-10→4, >10→sınırsız)
    try:
        rc = compute_b(ap, n_at, zk, apply_cap=True)
        _kaydet(GC, SC, rc)
    except Exception:
        GC["hata"] += 1


# ── Rapor ─────────────────────────────────────────────────────────────────────
SEP = "=" * 72

def pct(i, t):
    return f"%{i/t*100:.1f}" if t > 0 else "  -"

def avg_at(G):
    return f"{G['toplam_adet']/G['toplam']:.2f}" if G["toplam"] else "-"

print(f"\n{SEP}")
print("KARŞILAŞTIRMALI BACKTEST  A=Mevcut  B=OrtalamaÜstü  C=OrtüstüCaplı")
print(f"  Cap kuralı:  ≤7at→max3   8-10at→max4   >10at→sınırsız")
print(SEP)

print(f"\n{'':30} {'A (Mevcut)':>12} {'B (OrtÜstü)':>13} {'C (Caplı)':>12}")
for label, fa, fb, fc in [
    ("Toplam koşu",  GA["toplam"],   GB["toplam"],   GC["toplam"]),
    ("İsabetli",     GA["isabetli"], GB["isabetli"], GC["isabetli"]),
]:
    print(f"  {label:<28} {fa:>12} {fb:>13} {fc:>12}")
print(f"  {'İsabet oranı':<28} {pct(GA['isabetli'],GA['toplam']):>12} "
      f"{pct(GB['isabetli'],GB['toplam']):>13} {pct(GC['isabetli'],GC['toplam']):>12}")
print(f"  {'Ort. at/koşu':<28} {avg_at(GA):>12} {avg_at(GB):>13} {avg_at(GC):>12}")
da = (GC["isabetli"]/GC["toplam"] - GA["isabetli"]/GA["toplam"])*100 if GA["toplam"] and GC["toplam"] else 0
db = (GC["isabetli"]/GC["toplam"] - GB["isabetli"]/GB["toplam"])*100 if GB["toplam"] and GC["toplam"] else 0
print(f"\n  C vs A: {'+' if da>=0 else ''}{da:.2f} puan")
print(f"  C vs B: {'+' if db>=0 else ''}{db:.2f} puan")

# Tip
print(f"\n{'-'*72}")
print("TİP BAZLI:")
print(f"  {'Tip':<14} {'A:N':>5} {'A:%':>7} {'A:Ort':>6}  "
      f"{'B:N':>5} {'B:%':>7} {'B:Ort':>6}  {'C:N':>5} {'C:%':>7} {'C:Ort':>6}")
print(f"  {'-'*66}")
all_tips = list(dict.fromkeys(TIP_ORDER))
for tip in all_tips:
    sa = SA["tip"][tip]; sb = SB["tip"][tip]; sc = SC["tip"][tip]
    if sa["toplam"]==0 and sb["toplam"]==0 and sc["toplam"]==0: continue
    def at(s): return f"{s['toplam_adet']/s['toplam']:.1f}" if s["toplam"] else "-"
    print(f"  {tip:<14} {sa['toplam']:>5} {pct(sa['isabetli'],sa['toplam']):>7} {at(sa):>6}  "
          f"{sb['toplam']:>5} {pct(sb['isabetli'],sb['toplam']):>7} {at(sb):>6}  "
          f"{sc['toplam']:>5} {pct(sc['isabetli'],sc['toplam']):>7} {at(sc):>6}")

# At sayısı kategori
print(f"\n{'-'*72}")
print("AT SAYISI KATEGORİSİ (Cap kuralı burada devreye giriyor):")
print(f"  {'Kat.':<8} {'A:N':>5} {'A:%':>7} {'A:Ort':>6}  "
      f"{'B:N':>5} {'B:%':>7} {'B:Ort':>6}  {'C:N':>5} {'C:%':>7} {'C:Ort':>6}  Cap")
print(f"  {'-'*70}")
for bucket, cap_str in [("<=7","max3"),("8-10","max4"),("11-13","sınırsız"),("14+","sınırsız")]:
    sa = SA["nb"][bucket]; sb = SB["nb"][bucket]; sc = SC["nb"][bucket]
    if sa["toplam"]==0 and sb["toplam"]==0 and sc["toplam"]==0: continue
    def at(s): return f"{s['toplam_adet']/s['toplam']:.1f}" if s["toplam"] else "-"
    print(f"  {bucket:<8} {sa['toplam']:>5} {pct(sa['isabetli'],sa['toplam']):>7} {at(sa):>6}  "
          f"{sb['toplam']:>5} {pct(sb['isabetli'],sb['toplam']):>7} {at(sb):>6}  "
          f"{sc['toplam']:>5} {pct(sc['isabetli'],sc['toplam']):>7} {at(sc):>6}  {cap_str}")

# Hipodrom
print(f"\n{'-'*72}")
print("HİPODROM (>=20 koşu):")
print(f"  {'Hip':<14} {'A:%':>7} {'A:Ort':>6}  {'B:%':>7} {'B:Ort':>6}  "
      f"{'C:%':>7} {'C:Ort':>6}  CvsA")
print(f"  {'-'*66}")
for hip in sorted(SA["hip"], key=lambda h: -SA["hip"][h]["toplam"]):
    sa = SA["hip"][hip]; sb = SB["hip"][hip]; sc = SC["hip"][hip]
    if sa["toplam"] < 20: continue
    def at(s): return f"{s['toplam_adet']/s['toplam']:.1f}" if s["toplam"] else "-"
    d = (sc["isabetli"]/sc["toplam"]-sa["isabetli"]/sa["toplam"])*100 if sa["toplam"] and sc["toplam"] else 0
    flag = ("↑" if d>2 else "↓" if d<-2 else " ")
    print(f"  {hip:<14} {pct(sa['isabetli'],sa['toplam']):>7} {at(sa):>6}  "
          f"{pct(sb['isabetli'],sb['toplam']):>7} {at(sb):>6}  "
          f"{pct(sc['isabetli'],sc['toplam']):>7} {at(sc):>6}  {flag}{abs(d):.1f}")

# Son 14 gün
print(f"\n{'-'*72}")
print("SON 14 GÜN:")
print(f"  {'Tarih':<12} {'A:%':>6} {'A:Ort':>6}  {'B:%':>6} {'B:Ort':>6}  "
      f"{'C:%':>6} {'C:Ort':>6}  CvsA")
print(f"  {'-'*65}")
all_dates = sorted(set(list(SA["gun"].keys())+list(SC["gun"].keys())))[-14:]
for tarih in all_dates:
    sa = SA["gun"][tarih]; sc = SC["gun"][tarih]; sb = SB["gun"][tarih]
    if sa["toplam"]==0 and sc["toplam"]==0: continue
    pa = sa["isabetli"]/sa["toplam"]*100 if sa["toplam"] else 0
    pb = sb["isabetli"]/sb["toplam"]*100 if sb["toplam"] else 0
    pc = sc["isabetli"]/sc["toplam"]*100 if sc["toplam"] else 0
    aa = f"{sa['toplam_adet']/sa['toplam']:.1f}" if sa["toplam"] else "-"
    ab = f"{sb['toplam_adet']/sb['toplam']:.1f}" if sb["toplam"] else "-"
    ac = f"{sc['toplam_adet']/sc['toplam']:.1f}" if sc["toplam"] else "-"
    d = pc-pa
    print(f"  {tarih:<12} {pa:>5.1f}% {aa:>6}  {pb:>5.1f}% {ab:>6}  "
          f"{pc:>5.1f}% {ac:>6}  {('+' if d>=0 else '')}{d:.1f}")

print(f"\n{SEP}")
print("ÖZET")
print(SEP)
print(f"  A Mevcut (rev4)        : {pct(GA['isabetli'],GA['toplam'])} isabet, {avg_at(GA)} at/koşu")
print(f"  B Ort.Üstü (cap yok)   : {pct(GB['isabetli'],GB['toplam'])} isabet, {avg_at(GB)} at/koşu")
print(f"  C Ort.Üstü (caplı)     : {pct(GC['isabetli'],GC['toplam'])} isabet, {avg_at(GC)} at/koşu")
print(f"\n  C vs A fark            : {'+' if da>=0 else ''}{da:.2f} puan")
print(f"  C vs B fark            : {'+' if db>=0 else ''}{db:.2f} puan")
print(f"  Toplam koşu            : {GA['toplam']}")

result = {
    "A": {"isabet_pct": GA["isabetli"]/GA["toplam"]*100 if GA["toplam"] else 0,
          "avg_at": GA["toplam_adet"]/GA["toplam"] if GA["toplam"] else 0, **GA},
    "B": {"isabet_pct": GB["isabetli"]/GB["toplam"]*100 if GB["toplam"] else 0,
          "avg_at": GB["toplam_adet"]/GB["toplam"] if GB["toplam"] else 0, **GB},
    "C": {"isabet_pct": GC["isabetli"]/GC["toplam"]*100 if GC["toplam"] else 0,
          "avg_at": GC["toplam_adet"]/GC["toplam"] if GC["toplam"] else 0, **GC},
    "delta_C_vs_A": da, "delta_C_vs_B": db,
}
out = "/opt/harbi_ganyan_v3/reports/backtest_avg_caps_2026-07-09.json"
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nJSON: {out}")
