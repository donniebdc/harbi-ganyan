
# -*- coding: utf-8 -*-
import sys, json, os
from collections import defaultdict

sys.path.insert(0, "/opt/harbi_ganyan_v3/src")
sys.path.insert(0, "/opt/harbi_ganyan_backend")

from harbi_v3.harbi_secim import compute
from app.db import SessionLocal
from app.models import Kosu, Gun, GunHipodrom

db = SessionLocal()
try:
    # Kosu.gh_id -> GunHipodrom.id -> GunHipodrom.gun_id -> Gun.id
    rows = (
        db.query(Kosu, GunHipodrom, Gun)
        .join(GunHipodrom, GunHipodrom.id == Kosu.gh_id)
        .join(Gun, Gun.id == GunHipodrom.gun_id)
        .filter(Kosu.sonuc.isnot(None))
        .filter(Kosu.analiz_puanlari.isnot(None))
        .order_by(Gun.date)
        .all()
    )
    print(f"Toplam sonuclanmis kosu: {len(rows)}")
finally:
    db.close()

tip_stats   = defaultdict(lambda: {"toplam": 0, "isabetli": 0})
gun_stats   = defaultdict(lambda: {"toplam": 0, "isabetli": 0})
hip_stats   = defaultdict(lambda: {"toplam": 0, "isabetli": 0})
n_at_stats  = defaultdict(lambda: {"toplam": 0, "isabetli": 0})
genel       = {"toplam": 0, "isabetli": 0, "ap_yok": 0, "hs_hata": 0}
TIP_ORDER   = ["tek_at", "iki_aday", "uc_aday", "dort_aday", "genis_liste"]

for k, gh, gun in rows:
    ap = k.analiz_puanlari or []
    if not ap:
        genel["ap_yok"] += 1
        continue

    sonuc = k.sonuc or {}
    kazanan_no = sonuc.get("kazanan")
    if kazanan_no is None:
        continue

    n_at   = k.n_at or 0
    zorluk = k.zorluk or {}
    zk     = zorluk.get("zorluk_kodu") if zorluk else None
    tarih  = gun.date.isoformat() if gun.date else "?"
    hip    = gh.hipodrom or "?"

    try:
        hs = compute(ap, n_at=n_at, zorluk_kodu=zk,
                     is_surdirek=False, surdirek_horse_no=None)
    except Exception:
        genel["hs_hata"] += 1
        continue

    if not hs:
        genel["hs_hata"] += 1
        continue

    tip         = hs.get("tip", "bilinmiyor")
    adaylar     = hs.get("adaylar", [])
    aday_nolari = {a["at_no"] for a in adaylar}
    isabetli    = kazanan_no in aday_nolari

    tip_stats[tip]["toplam"]   += 1
    tip_stats[tip]["isabetli"] += int(isabetli)
    gun_stats[tarih]["toplam"]   += 1
    gun_stats[tarih]["isabetli"] += int(isabetli)
    hip_stats[hip]["toplam"]   += 1
    hip_stats[hip]["isabetli"] += int(isabetli)

    n_at_bucket = ("<=7" if n_at<=7 else "8-10" if n_at<=10 else "11-13" if n_at<=13 else "14+")
    n_at_stats[n_at_bucket]["toplam"]   += 1
    n_at_stats[n_at_bucket]["isabetli"] += int(isabetli)

    genel["toplam"]   += 1
    genel["isabetli"] += int(isabetli)

# --- Rapor ---
print("\n" + "="*65)
print("HARBI SECIM BACKTEST SONUCLARI")
print("="*65)

G = genel
if G["toplam"] > 0:
    oran = G["isabetli"] / G["toplam"] * 100
    print(f"\nGENEL:")
    print(f"  Analiz edilen kosu  : {G['toplam']}")
    print(f"  Isabetli (kazanan listede) : {G['isabetli']}")
    print(f"  Genel isabet orani  : %{oran:.1f}")
    print(f"  AP bos atlanan      : {G['ap_yok']}")
    print(f"  HS hesap hatasi     : {G['hs_hata']}")
else:
    print("\nHic veri bulunamadi!")

print(f"\nTIP BAZLI:")
print(f"  {'Tip':<16} {'Toplam':>7} {'Isabetli':>9} {'%Isabet':>9} {'Ort.Aday':>9}")
print(f"  {'-'*55}")
aday_map = {"tek_at":"1","iki_aday":"2","uc_aday":"3","dort_aday":"4","genis_liste":"5+"}
for tip in TIP_ORDER:
    if tip not in tip_stats:
        continue
    s = tip_stats[tip]
    t, i = s["toplam"], s["isabetli"]
    oran = i/t*100 if t>0 else 0
    print(f"  {tip:<16} {t:>7} {i:>9} {oran:>8.1f}% {aday_map.get(tip,'?'):>9}")

print(f"\nN_AT KATEGORI:")
for bucket in ["<=7","8-10","11-13","14+"]:
    if bucket not in n_at_stats:
        continue
    s = n_at_stats[bucket]
    t, i = s["toplam"], s["isabetli"]
    print(f"  {bucket:<8} {t:>7} kosu  %{i/t*100:.1f}" if t>0 else f"  {bucket:<8} 0 kosu")

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
