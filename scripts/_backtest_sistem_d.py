# -*- coding: utf-8 -*-
"""
4 Sistem Karşılaştırmalı Backtest
  A) Mevcut harbi_secim rev4          (STOP_GAP eşikleri)
  B) Ortalama-üstü + model birleşimi  (cap yok)
  C) Ortalama-üstü + sert cap         (<=7→3, 8-10→4, >10→sınırsız)
  D) Kalibre Harbi Seçim              (yumuşak cap + kopuş tespiti + ortalama destek)

Sistem D mantığı:
  1. A sistemi çekirdek listeyi üretir.
  2. Koşu puan ortalaması hesaplanır.
  3. Ortalama üstü adaylar: kopuş yoksa ve kap aşılmıyorsa çekirdek listeye eklenir.
  4. Yumuşak kap:
       <=7 at   → hedef 3, maks 4 (4. at ort.üstü + öncekiyle fark<=5 ise)
       8-10 at  → hedef 4, maks 5 (5. at ort.üstü + öncekiyle fark<=5 ise)
       11-13 at → hedef 6, maks 7 (7. at ort.üstü + kopuş yok ise)
       14+ at   → hedef 7, maks 8 (8. at ort.üstü + kopuş yok ise)
  5. Kopuş eşiği: ardışık iki aday arasında puan farkı > 8 → dur.
     Çekirdek adaylar kopuş sonrası da hedef sayıya kadar eklenir.
     Çekirdek dışı adaylar kopuş sonrası kesinlikle eklenmez.
  6. Geniş liste hiçbir durumda sahadaki tüm atları yazmaz.
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
SELECT
    k.kno, k.n_at, k.analiz_puanlari, k.zorluk, k.race_type,
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
""")
rows = cur.fetchall()
cur.close(); conn.close()

print(f"Toplam sonuçlanmış koşu: {len(rows)}\n")

# Sürdirek geçmişini yükle
SURDIREK_CACHE = "/opt/harbi_ganyan_v3/data/surdirek_cache.json"
surdirek_set: set[tuple] = set()   # (date_str, hip, race_no, horse_no)
surdirek_race_set: set[tuple] = set()  # (date_str, hip, race_no)
try:
    with open(SURDIREK_CACHE, encoding="utf-8") as f:
        sc = json.load(f)
    for item in sc.get("gecmis", []):
        d   = item.get("date","")
        hip = item.get("hip","")
        rno = item.get("race_no")
        hno = item.get("horse_no")
        if d and hip and rno is not None and hno is not None:
            surdirek_set.add((d, hip, int(rno), int(hno)))
            surdirek_race_set.add((d, hip, int(rno)))
    for item in sc.get("bugun", []):
        d   = item.get("date","")
        hip = item.get("hip","")
        rno = item.get("race_no")
        hno = item.get("horse_no")
        if d and hip and rno is not None and hno is not None:
            surdirek_set.add((d, hip, int(rno), int(hno)))
            surdirek_race_set.add((d, hip, int(rno)))
    print(f"Sürdirek cache: {len(surdirek_set)} giriş yüklendi.\n")
except Exception as e:
    print(f"Sürdirek cache yüklenemedi: {e}\n")


# ── Yardımcı ─────────────────────────────────────────────────────────────────
def _tip(n):
    return ("tek_at" if n==1 else "iki_aday" if n==2 else
            "uc_aday" if n==3 else "dort_aday" if n==4 else "genis_liste")

def _nb(n_at):
    if n_at <= 7:  return "<=7"
    if n_at <= 10: return "8-10"
    if n_at <= 13: return "11-13"
    return "14+"

def _race_cat(race_type):
    rt = (race_type or "").lower()
    if "maiden" in rt or "debutant" in rt: return "maiden"
    if "handikap" in rt or "handicap" in rt: return "handikap"
    if "sartli" in rt or "sarli" in rt: return "sartli"
    if "grup" in rt or "group" in rt: return "grup"
    return "diger"


# ── Sistem B: ortalama-üstü + model, cap yok ─────────────────────────────────
def compute_b(ap, n_at, zk):
    if not ap: return None
    sirali = sorted(ap, key=lambda x: x.get("ana", 0), reverse=True)
    avg = sum(p.get("ana",0) for p in sirali) / len(sirali)
    above_nos = {p["at_no"] for p in sirali if p.get("ana",0) >= avg}
    try:
        m = hs_compute(ap, n_at=n_at, zorluk_kodu=zk, is_surdirek=False)
        model_nos = {a["at_no"] for a in (m or {}).get("adaylar",[])}
    except:
        model_nos = set()
    final_nos  = above_nos | model_nos
    final_list = [p for p in sirali if p["at_no"] in final_nos]
    adet = len(final_list)
    return {"tip": _tip(adet), "adaylar": final_list, "adet": adet}


# ── Sistem C: ortalama-üstü + sert cap ───────────────────────────────────────
def compute_c(ap, n_at, zk):
    if not ap: return None
    sirali = sorted(ap, key=lambda x: x.get("ana", 0), reverse=True)
    avg = sum(p.get("ana",0) for p in sirali) / len(sirali)
    above_nos = {p["at_no"] for p in sirali if p.get("ana",0) >= avg}
    try:
        m = hs_compute(ap, n_at=n_at, zorluk_kodu=zk, is_surdirek=False)
        model_nos = {a["at_no"] for a in (m or {}).get("adaylar",[])}
    except:
        model_nos = set()
    final_nos  = above_nos | model_nos
    cap = (3 if n_at <= 7 else 4 if n_at <= 10 else len(sirali))
    final_list = [p for p in sirali if p["at_no"] in final_nos][:cap]
    adet = len(final_list)
    return {"tip": _tip(adet), "adaylar": final_list, "adet": adet}


# ── Sistem D: Kalibre Harbi Seçim ────────────────────────────────────────────
def compute_d(ap, n_at, zk):
    """
    Yumuşak cap + kopuş tespiti + ortalama üstü destek sinyali.

    Çekirdek liste: A sistemi (hs_compute).
    Ortalama üstü adaylar: kopuş yoksa ve kap dolmamışsa eklenir.
    Kopuş (gap>8): çekirdek dışı adaylar durur, çekirdek adaylar hedef dolana
    kadar devam eder.
    Yumuşak uzantı: hedefin 1 üstüne kadar, koşul sağlanırsa çıkılabilir.
    """
    if not ap:
        return None

    sirali = sorted(ap, key=lambda x: x.get("ana", 0), reverse=True)
    avg    = sum(p.get("ana", 0) for p in sirali) / len(sirali)

    # A sistemi çekirdeği
    try:
        model     = hs_compute(ap, n_at=n_at, zorluk_kodu=zk, is_surdirek=False)
        core_nos  = {a["at_no"] for a in (model or {}).get("adaylar", [])}
    except Exception:
        core_nos = set()

    # Yumuşak cap parametreleri
    if n_at <= 7:    target, soft_max, soft_gap = 3, 4, 5
    elif n_at <= 10: target, soft_max, soft_gap = 4, 5, 5
    elif n_at <= 13: target, soft_max, soft_gap = 6, 7, 8
    else:            target, soft_max, soft_gap = 7, 8, 8

    KOPUS_ESIK = 8   # ardışık iki seçim arasındaki max izin verilen fark

    final: list = []
    kopus_hit  = False  # kopuş gerçekleşti mi (çekirdek dışı atlar için dur)

    for p in sirali:
        n     = len(final)
        score = p.get("ana", 0)
        in_core    = p["at_no"] in core_nos
        above_avg  = score >= avg

        # Öncekiyle fark
        prev_score = final[-1].get("ana", 0) if final else score
        gap        = prev_score - score
        kopus      = gap > KOPUS_ESIK

        if kopus and not kopus_hit:
            kopus_hit = True

        # Hard ceiling
        if n >= soft_max:
            break

        if in_core:
            # Çekirdek: hedef dolana kadar kopuşa bakma, hedefe kadar her zaman ekle
            if n < target:
                final.append(p)
            else:
                # Yumuşak uzantı bölgesi (target → soft_max)
                # Kopuş yoksa ve yumuşak fark eşiği geçilmemişse ekle
                if not kopus_hit and gap <= soft_gap:
                    final.append(p)
        else:
            # Çekirdek dışı
            if kopus_hit:
                break  # kopuş sonrası çekirdek dışı ekleme yok
            if not above_avg:
                # Ortalama altı + çekirdek dışı → atla (break değil, ileride core olabilir)
                continue
            # Ortalama üstü + çekirdek dışı
            if n < target:
                final.append(p)
            elif gap <= soft_gap:
                # Yumuşak uzantı: sadece küçük fark varsa
                final.append(p)

    adet = len(final)
    return {"tip": _tip(adet), "adaylar": final, "adet": adet}


# ── Backtest döngüsü ──────────────────────────────────────────────────────────
def mk():
    return defaultdict(lambda: {"toplam": 0, "isabetli": 0, "toplam_adet": 0})

def eg():
    return {"toplam": 0, "isabetli": 0, "hata": 0, "toplam_adet": 0}

GA, GB, GC, GD = eg(), eg(), eg(), eg()
SA = {k: mk() for k in ("tip","nb","hip","gun","rcat")}
SB = {k: mk() for k in ("tip","nb","hip","gun","rcat")}
SC = {k: mk() for k in ("tip","nb","hip","gun","rcat")}
SD = {k: mk() for k in ("tip","nb","hip","gun","rcat")}

# Sürdirek tutarlılık istatistikleri (sadece D için)
sd_uyum = {"toplam_sd": 0, "d_tek_at": 0, "d_tutarli": 0,
            "isabetli_sd": 0, "isabetli_d_teklek": 0}

TIP_ORDER = ["tek_at","iki_aday","uc_aday","dort_aday","genis_liste"]

def kaydet(G, S, result, kazanan_no, nb, hip, tarih, rcat):
    if result is None:
        G["hata"] += 1
        return
    nos  = {a["at_no"] for a in result.get("adaylar",[])}
    tip  = result.get("tip","bilinmiyor")
    adet = result.get("adet", len(nos))
    hit  = kazanan_no in nos
    G["toplam"]      += 1
    G["isabetli"]    += int(hit)
    G["toplam_adet"] += adet
    for d, k in ((S["tip"],tip),(S["nb"],nb),(S["hip"],hip),
                 (S["gun"],tarih),(S["rcat"],rcat)):
        d[k]["toplam"]      += 1
        d[k]["isabetli"]    += int(hit)
        d[k]["toplam_adet"] += adet

for row in rows:
    ap         = row["analiz_puanlari"] or []
    kazanan_no = row["kazanan"]
    if kazanan_no is None or not ap:
        continue

    n_at   = row["n_at"] or 0
    zk     = (row["zorluk"] or {}).get("zorluk_kodu")
    tarih  = str(row["date"])
    hip    = row["hipodrom"] or "?"
    kno    = int(row["kno"])
    rcat   = _race_cat(row.get("race_type"))
    nb     = _nb(n_at)

    # A
    try:
        ra = hs_compute(ap, n_at=n_at, zorluk_kodu=zk,
                        is_surdirek=False, surdirek_horse_no=None)
        kaydet(GA, SA, ra, kazanan_no, nb, hip, tarih, rcat)
    except:
        GA["hata"] += 1

    # B
    try:
        kaydet(GB, SB, compute_b(ap,n_at,zk), kazanan_no, nb, hip, tarih, rcat)
    except:
        GB["hata"] += 1

    # C
    try:
        kaydet(GC, SC, compute_c(ap,n_at,zk), kazanan_no, nb, hip, tarih, rcat)
    except:
        GC["hata"] += 1

    # D
    try:
        rd = compute_d(ap, n_at, zk)
        kaydet(GD, SD, rd, kazanan_no, nb, hip, tarih, rcat)

        # Sürdirek tutarlılık analizi
        sd_key  = (tarih, hip, kno)
        is_sd_race = sd_key in surdirek_race_set
        if is_sd_race and rd:
            sd_uyum["toplam_sd"] += 1
            sd_nos = {a["at_no"] for a in rd.get("adaylar",[])}
            hit_sd = kazanan_no in sd_nos
            sd_uyum["isabetli_sd"] += int(hit_sd)

            # D sistemi bu koşuya tek_at dedi mi?
            is_tek = rd.get("tip") == "tek_at"
            sd_uyum["d_tek_at"] += int(is_tek)

            # Gerçek sürdirek atı D sisteminin listesinde mi?
            sd_horse = next((h for d,h2,r,h in surdirek_set
                            if (d,h2,r)==(tarih,hip,kno)), None)
            if sd_horse and sd_horse in sd_nos:
                sd_uyum["d_tutarli"] += 1
            if is_tek and hit_sd:
                sd_uyum["isabetli_d_teklek"] += 1
    except:
        GD["hata"] += 1


# ── Rapor ─────────────────────────────────────────────────────────────────────
SEP = "=" * 74

def pct(i, t):
    return f"%{i/t*100:.1f}" if t else "  -"

def aat(G):
    return f"{G['toplam_adet']/G['toplam']:.2f}" if G["toplam"] else "-"

def pat(s):
    return f"{s['toplam_adet']/s['toplam']:.1f}" if s["toplam"] else "-"

print(f"\n{SEP}")
print("  DÖRT SİSTEM KARŞILAŞTIRMALI BACKTEST")
print(f"  A=Mevcut  B=OrtÜstü(cap yok)  C=OrtÜstü(sert cap)  D=Kalibre")
print(SEP)

print(f"\n{'':32} {'A':>10} {'B':>10} {'C':>10} {'D':>10}")
print(f"  {'Toplam koşu':<30} {GA['toplam']:>10} {GB['toplam']:>10} {GC['toplam']:>10} {GD['toplam']:>10}")
print(f"  {'İsabetli':<30} {GA['isabetli']:>10} {GB['isabetli']:>10} {GC['isabetli']:>10} {GD['isabetli']:>10}")
print(f"  {'İsabet oranı':<30} {pct(GA['isabetli'],GA['toplam']):>10} "
      f"{pct(GB['isabetli'],GB['toplam']):>10} {pct(GC['isabetli'],GC['toplam']):>10} "
      f"{pct(GD['isabetli'],GD['toplam']):>10}")
print(f"  {'Ort. at/koşu':<30} {aat(GA):>10} {aat(GB):>10} {aat(GC):>10} {aat(GD):>10}")

dDA = (GD['isabetli']/GD['toplam'] - GA['isabetli']/GA['toplam'])*100 if GA['toplam'] and GD['toplam'] else 0
dDB = (GD['isabetli']/GD['toplam'] - GB['isabetli']/GB['toplam'])*100 if GB['toplam'] and GD['toplam'] else 0
dDC = (GD['isabetli']/GD['toplam'] - GC['isabetli']/GC['toplam'])*100 if GC['toplam'] and GD['toplam'] else 0
print(f"\n  D vs A: {'+' if dDA>=0 else ''}{dDA:.2f} puan")
print(f"  D vs B: {'+' if dDB>=0 else ''}{dDB:.2f} puan")
print(f"  D vs C: {'+' if dDC>=0 else ''}{dDC:.2f} puan")

# Tip bazlı
print(f"\n{'-'*74}")
print("TİP DAĞILIMI:")
print(f"  {'Tip':<14} {'A:N':>5} {'A:%':>7}  {'B:N':>5} {'B:%':>7}  "
      f"{'C:N':>5} {'C:%':>7}  {'D:N':>5} {'D:%':>7}")
print(f"  {'-'*70}")
for tip in TIP_ORDER:
    sa,sb,sc,sdx = SA["tip"][tip],SB["tip"][tip],SC["tip"][tip],SD["tip"][tip]
    if all(s["toplam"]==0 for s in (sa,sb,sc,sdx)): continue
    print(f"  {tip:<14} {sa['toplam']:>5} {pct(sa['isabetli'],sa['toplam']):>7}  "
          f"{sb['toplam']:>5} {pct(sb['isabetli'],sb['toplam']):>7}  "
          f"{sc['toplam']:>5} {pct(sc['isabetli'],sc['toplam']):>7}  "
          f"{sdx['toplam']:>5} {pct(sdx['isabetli'],sdx['toplam']):>7}")

# At sayısı
print(f"\n{'-'*74}")
print("AT SAYISI KATEGORİSİ:")
header = f"  {'Kat.':<8} {'A:%':>7} {'A:Ort':>6}  {'B:%':>7} {'B:Ort':>6}  " \
         f"{'C:%':>7} {'C:Ort':>6}  {'D:%':>7} {'D:Ort':>6}  Cap(D)"
print(header)
print(f"  {'-'*70}")
for bkt, cap_str in [("<=7","3→4"),("8-10","4→5"),("11-13","6→7"),("14+","7→8")]:
    sa,sb,sc,sdx = SA["nb"][bkt],SB["nb"][bkt],SC["nb"][bkt],SD["nb"][bkt]
    if all(s["toplam"]==0 for s in (sa,sb,sc,sdx)): continue
    print(f"  {bkt:<8} {pct(sa['isabetli'],sa['toplam']):>7} {pat(sa):>6}  "
          f"{pct(sb['isabetli'],sb['toplam']):>7} {pat(sb):>6}  "
          f"{pct(sc['isabetli'],sc['toplam']):>7} {pat(sc):>6}  "
          f"{pct(sdx['isabetli'],sdx['toplam']):>7} {pat(sdx):>6}  {cap_str}")

# Koşu tipi
print(f"\n{'-'*74}")
print("KOŞU TİPİ:")
for rcat in ["maiden","sartli","grup","handikap","diger"]:
    sa,sd_ = SA["rcat"][rcat],SD["rcat"][rcat]
    if sa["toplam"] < 5: continue
    sb,sc = SB["rcat"][rcat],SC["rcat"][rcat]
    print(f"  {rcat:<12} A:{pct(sa['isabetli'],sa['toplam']):>7}  "
          f"B:{pct(sb['isabetli'],sb['toplam']):>7}  "
          f"C:{pct(sc['isabetli'],sc['toplam']):>7}  "
          f"D:{pct(sd_['isabetli'],sd_['toplam']):>7}  "
          f"(n={sa['toplam']})")

# Hipodrom
print(f"\n{'-'*74}")
print("HİPODROM (>=20 koşu):")
print(f"  {'Hip':<14} {'A:%':>7} {'A:Ort':>6}  {'B:%':>7} {'B:Ort':>6}  "
      f"{'C:%':>7} {'C:Ort':>6}  {'D:%':>7} {'D:Ort':>6}  D-A")
print(f"  {'-'*72}")
for hip in sorted(SA["hip"], key=lambda h: -SA["hip"][h]["toplam"]):
    sa,sdx = SA["hip"][hip],SD["hip"][hip]
    if sa["toplam"] < 20: continue
    sb,sc = SB["hip"][hip],SC["hip"][hip]
    d = (sdx['isabetli']/sdx['toplam']-sa['isabetli']/sa['toplam'])*100 if sa['toplam'] and sdx['toplam'] else 0
    flag = "↑" if d>2 else ("↓" if d<-2 else " ")
    print(f"  {hip:<14} {pct(sa['isabetli'],sa['toplam']):>7} {pat(sa):>6}  "
          f"{pct(sb['isabetli'],sb['toplam']):>7} {pat(sb):>6}  "
          f"{pct(sc['isabetli'],sc['toplam']):>7} {pat(sc):>6}  "
          f"{pct(sdx['isabetli'],sdx['toplam']):>7} {pat(sdx):>6}  {flag}{abs(d):.1f}")

# Son 14 gün
print(f"\n{'-'*74}")
print("SON 14 GÜN:")
print(f"  {'Tarih':<12} {'A:%':>6} {'B:%':>6} {'C:%':>6} {'D:%':>6}  "
      f"{'A:Ort':>5} {'D:Ort':>5}  D-A")
print(f"  {'-'*62}")
all_dates = sorted(set(list(SA["gun"].keys())+list(SD["gun"].keys())))[-14:]
for t in all_dates:
    sa,sd_ = SA["gun"][t],SD["gun"][t]
    sb,sc  = SB["gun"][t],SC["gun"][t]
    if sa["toplam"]==0 and sd_["toplam"]==0: continue
    pa = sa['isabetli']/sa['toplam']*100 if sa['toplam'] else 0
    pd = sd_['isabetli']/sd_['toplam']*100 if sd_['toplam'] else 0
    d  = pd-pa
    aa = f"{sa['toplam_adet']/sa['toplam']:.1f}" if sa['toplam'] else "-"
    da = f"{sd_['toplam_adet']/sd_['toplam']:.1f}" if sd_['toplam'] else "-"
    print(f"  {t:<12} {pa:>5.1f}% {pct(sb['isabetli'],sb['toplam']):>6} "
          f"{pct(sc['isabetli'],sc['toplam']):>6} {pd:>5.1f}%  {aa:>5} {da:>5}  "
          f"{('+' if d>=0 else '')}{d:.1f}")

# Sürdirek tutarlılık
print(f"\n{'-'*74}")
print("SÜRDİREK TUTARLILIK ANALİZİ (D sistemi, cache'den):")
sd = sd_uyum
if sd["toplam_sd"] > 0:
    print(f"  Cache'de sürdirek olan koşu sayısı   : {sd['toplam_sd']}")
    print(f"  D sistemi tek_at dedi                 : {sd['d_tek_at']} "
          f"({sd['d_tek_at']/sd['toplam_sd']*100:.1f}%)")
    print(f"  Gerçek sürdirek atı D listesinde      : {sd['d_tutarli']} "
          f"({sd['d_tutarli']/sd['toplam_sd']*100:.1f}%)")
    print(f"  Sürdirek koşularında D isabeti        : "
          f"{pct(sd['isabetli_sd'],sd['toplam_sd'])}")
    print(f"  D tek_at + kazanan olan               : {sd['isabetli_d_teklek']}")
    tutarsiz = sd["toplam_sd"] - sd["d_tek_at"]
    print(f"  D tutarsız (teklek değil) sayısı      : {tutarsiz} "
          f"({tutarsiz/sd['toplam_sd']*100:.1f}%)")
    print()
    print(f"  NOT: 'D tutarsız' = sürdirek seçilen ama D sistemi")
    print(f"       tek_at değil yazan koşular. Bu koşular için sürdirek")
    print(f"       seçim sırası farklı koşuya yönelmeliydi.")
else:
    print("  Sürdirek cache verisi yeterli değil.")

# Özet
print(f"\n{SEP}")
print("ÖZET")
print(SEP)
print(f"  A Mevcut          : {pct(GA['isabetli'],GA['toplam'])} isabet / {aat(GA)} at/koşu")
print(f"  B Ort.Üstü-CAPsız : {pct(GB['isabetli'],GB['toplam'])} isabet / {aat(GB)} at/koşu")
print(f"  C Ort.Üstü-SertCAP: {pct(GC['isabetli'],GC['toplam'])} isabet / {aat(GC)} at/koşu")
print(f"  D Kalibre         : {pct(GD['isabetli'],GD['toplam'])} isabet / {aat(GD)} at/koşu")
print(f"\n  D vs A : {'+' if dDA>=0 else ''}{dDA:.2f} puan")
print(f"  D vs B : {'+' if dDB>=0 else ''}{dDB:.2f} puan")
print(f"  D vs C : {'+' if dDC>=0 else ''}{dDC:.2f} puan")
print(f"\n  Toplam koşu : {GA['toplam']}")

# JSON
result = {
    "A": {"pct": GA['isabetli']/GA['toplam']*100 if GA['toplam'] else 0,
          "avg_at": GA['toplam_adet']/GA['toplam'] if GA['toplam'] else 0, **GA},
    "B": {"pct": GB['isabetli']/GB['toplam']*100 if GB['toplam'] else 0,
          "avg_at": GB['toplam_adet']/GB['toplam'] if GB['toplam'] else 0, **GB},
    "C": {"pct": GC['isabetli']/GC['toplam']*100 if GC['toplam'] else 0,
          "avg_at": GC['toplam_adet']/GC['toplam'] if GC['toplam'] else 0, **GC},
    "D": {"pct": GD['isabetli']/GD['toplam']*100 if GD['toplam'] else 0,
          "avg_at": GD['toplam_adet']/GD['toplam'] if GD['toplam'] else 0, **GD},
    "D_vs_A": dDA, "D_vs_B": dDB, "D_vs_C": dDC,
    "surdirek_uyum": sd_uyum,
}
out = "/opt/harbi_ganyan_v3/reports/backtest_sistem_d_2026-07-09.json"
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nJSON: {out}")
