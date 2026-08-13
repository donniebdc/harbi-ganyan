
# -*- coding: utf-8 -*-
import sys, json, os
from collections import defaultdict
import psycopg2
import psycopg2.extras

sys.path.insert(0, "/opt/harbi_ganyan_v3/src")
from harbi_v3.harbi_secim import compute

# DB baglantisi — config.py'den url al
sys.path.insert(0, "/opt/harbi_ganyan_backend")
from app.config import settings

db_url = settings.database_url
# postgresql+psycopg2://user:pw@host/db -> host/db ayristir
import re
m = re.match(r"postgresql\+psycopg2://([^:]+):([^@]+)@([^/]+)/(.+)", db_url)
if m:
    db_user, db_pass, db_host, db_name = m.groups()
else:
    db_user, db_pass, db_host, db_name = "postgres", "", "localhost", "harbi_ganyan"

conn = psycopg2.connect(host=db_host, user=db_user, password=db_pass, dbname=db_name)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Sonucu ve analiz_puanlari olan tum kosuları cek
SQL = """
SELECT
    k.kno,
    k.n_at,
    k.analiz_puanlari,
    k.zorluk,
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

print(f"Toplam sonuclanmis kosu: {len(rows)}")

tip_stats  = defaultdict(lambda: {"toplam": 0, "isabetli": 0})
gun_stats  = defaultdict(lambda: {"toplam": 0, "isabetli": 0})
hip_stats  = defaultdict(lambda: {"toplam": 0, "isabetli": 0})
n_at_stats = defaultdict(lambda: {"toplam": 0, "isabetli": 0})
genel      = {"toplam": 0, "isabetli": 0, "hs_hata": 0}
TIP_ORDER  = ["tek_at", "iki_aday", "uc_aday", "dort_aday", "genis_liste"]

for row in rows:
    ap        = row["analiz_puanlari"] or []
    kazanan_no = row["kazanan"]
    if kazanan_no is None:
        continue

    n_at   = row["n_at"] or 0
    zorluk = row["zorluk"] or {}
    zk     = zorluk.get("zorluk_kodu") if zorluk else None
    tarih  = str(row["date"]) if row["date"] else "?"
    hip    = row["hipodrom"] or "?"

    try:
        hs = compute(ap, n_at=n_at, zorluk_kodu=zk,
                     is_surdirek=False, surdirek_horse_no=None)
    except Exception as e:
        genel["hs_hata"] += 1
        continue

    if not hs:
        genel["hs_hata"] += 1
        continue

    tip         = hs.get("tip", "bilinmiyor")
    adaylar     = hs.get("adaylar", [])
    aday_nolari = {a["at_no"] for a in adaylar}
    isabetli    = kazanan_no in aday_nolari

    tip_stats[tip]["toplam"]      += 1
    tip_stats[tip]["isabetli"]    += int(isabetli)
    gun_stats[tarih]["toplam"]    += 1
    gun_stats[tarih]["isabetli"]  += int(isabetli)
    hip_stats[hip]["toplam"]      += 1
    hip_stats[hip]["isabetli"]    += int(isabetli)

    nb = ("<=7" if n_at<=7 else "8-10" if n_at<=10 else "11-13" if n_at<=13 else "14+")
    n_at_stats[nb]["toplam"]   += 1
    n_at_stats[nb]["isabetli"] += int(isabetli)

    genel["toplam"]   += 1
    genel["isabetli"] += int(isabetli)

# --- Rapor ---
SEP = "="*65
print(f"\n{SEP}")
print("HARBI SECIM BACKTEST SONUCLARI")
print(SEP)

G = genel
if G["toplam"] > 0:
    oran = G["isabetli"] / G["toplam"] * 100
    print(f"\nGENEL:")
    print(f"  Analiz edilen kosu          : {G['toplam']}")
    print(f"  Isabetli (kazanan listede)  : {G['isabetli']}")
    print(f"  Genel isabet orani          : %{oran:.1f}")
    print(f"  HS hesap hatasi             : {G['hs_hata']}")
else:
    print("\nHic veri bulunamadi!")

print(f"\nTIP BAZLI:")
print(f"  {'Tip':<16} {'Toplam':>7} {'Isabetli':>9} {'%Isabet':>9} {'Aday':>6}")
print(f"  {'-'*53}")
aday_map = {"tek_at":"1","iki_aday":"2","uc_aday":"3","dort_aday":"4","genis_liste":"5+"}
for tip in TIP_ORDER:
    if tip not in tip_stats:
        continue
    s = tip_stats[tip]
    t, i = s["toplam"], s["isabetli"]
    oran = i/t*100 if t>0 else 0
    print(f"  {tip:<16} {t:>7} {i:>9} {oran:>8.1f}% {aday_map.get(tip,'?'):>6}")

print(f"\nN_AT KATEGORI:")
for bucket in ["<=7","8-10","11-13","14+"]:
    if bucket not in n_at_stats:
        continue
    s = n_at_stats[bucket]
    t, i = s["toplam"], s["isabetli"]
    if t > 0:
        print(f"  {bucket:<8} : {t:>6} kosu  %{i/t*100:.1f} isabet")

print(f"\nHIPODROM BAZLI (>=10 kosu):")
print(f"  {'Hipodrom':<14} {'Toplam':>7} {'Isabetli':>9} {'%':>8}")
print(f"  {'-'*42}")
for hip, s in sorted(hip_stats.items(), key=lambda x: -x[1]["toplam"]):
    if s["toplam"] < 10:
        continue
    t, i = s["toplam"], s["isabetli"]
    print(f"  {hip:<14} {t:>7} {i:>9} {i/t*100:>7.1f}%")

print(f"\nGUN BAZLI (son 14 gun):")
print(f"  {'Tarih':<12} {'Kosu':>6} {'Isabet':>8} {'%':>8}")
print(f"  {'-'*38}")
for tarih, gs in sorted(gun_stats.items())[-14:]:
    t, i = gs["toplam"], gs["isabetli"]
    print(f"  {tarih:<12} {t:>6} {i:>8} {i/t*100:>7.1f}%")

tarihler = sorted(gun_stats.keys())
if tarihler:
    print(f"\nTARIH ARALIGI: {tarihler[0]} – {tarihler[-1]}")
    print(f"Toplam gun    : {len(tarihler)}")

result = {
    "genel": genel,
    "tip_stats": {k:dict(v) for k,v in tip_stats.items()},
    "gun_stats": {k:dict(v) for k,v in gun_stats.items()},
    "hip_stats": {k:dict(v) for k,v in hip_stats.items()},
    "n_at_stats": {k:dict(v) for k,v in n_at_stats.items()},
}
out_path = "/opt/harbi_ganyan_v3/reports/harbi_secim_backtest_v2.json"
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nJSON: {out_path}")
