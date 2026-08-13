# -*- coding: utf-8 -*-
import sys, json, os
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, "/opt/harbi_ganyan_v3/src")
from harbi_v3.harbi_secim import compute

EXPORT_DIR = Path("/opt/harbi_ganyan_v3/data/export_out")

# --- istatistik yapilari ---
# tip -> {toplam, isabetli}
tip_stats = defaultdict(lambda: {"toplam": 0, "isabetli": 0})
gun_stats = {}  # date -> {toplam, isabetli}

# Genel
genel = {"toplam": 0, "isabetli": 0, "sonucsuz": 0, "harbi_secim_yok": 0}

# Tip bazli detay
TIP_ORDER = ["tek_at", "iki_aday", "uc_aday", "dort_aday", "genis_liste"]

json_files = sorted(EXPORT_DIR.glob("20??-??-??.json"))
print(f"Toplam dosya: {len(json_files)}")

for jf in json_files:
    tarih = jf.stem
    try:
        data = json.loads(jf.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  SKIP {tarih}: {e}")
        continue

    gun_toplam = 0
    gun_isabetli = 0

    for hip in data.get("hipodromlar", []):
        for kosu in hip.get("kosular", []):
            sonuc = kosu.get("sonuc")
            if not sonuc or sonuc.get("kazanan") is None:
                genel["sonucsuz"] += 1
                continue

            kazanan_no = sonuc["kazanan"]
            ap = kosu.get("analiz_puanlari") or []
            if not ap:
                genel["harbi_secim_yok"] += 1
                continue

            n_at = kosu.get("n_at") or 0
            zorluk = kosu.get("zorluk") or {}
            zk = zorluk.get("zorluk_kodu") if zorluk else None

            # Surdirek bilgisi: daily_panel'den degil export'tan anlayamayiz
            # Bu backtest is_surdirek=False ile calisir (tutarli olmasi icin)
            try:
                hs = compute(ap, n_at=n_at, zorluk_kodu=zk,
                             is_surdirek=False, surdirek_horse_no=None)
            except Exception as e:
                genel["harbi_secim_yok"] += 1
                continue

            if not hs:
                genel["harbi_secim_yok"] += 1
                continue

            tip = hs.get("tip", "bilinmiyor")
            adaylar = hs.get("adaylar", [])
            aday_nolari = {a["at_no"] for a in adaylar}

            isabetli = kazanan_no in aday_nolari

            tip_stats[tip]["toplam"] += 1
            tip_stats[tip]["isabetli"] += isabetli
            genel["toplam"] += 1
            genel["isabetli"] += int(isabetli)
            gun_toplam += 1
            gun_isabetli += int(isabetli)

    if gun_toplam > 0:
        gun_stats[tarih] = {
            "toplam": gun_toplam,
            "isabetli": gun_isabetli,
            "yuzde": round(gun_isabetli / gun_toplam * 100, 1)
        }

# --- Rapor ---
print("\n" + "="*60)
print("HARBI SECIM BACKTEST SONUCLARI")
print("="*60)

G = genel
if G["toplam"] > 0:
    genel_yuzde = G["isabetli"] / G["toplam"] * 100
    print(f"\nGENEL:")
    print(f"  Analiz edilen kosu : {G['toplam']}")
    print(f"  Isabetli           : {G['isabetli']}")
    print(f"  Genel isabet orani : %{genel_yuzde:.1f}")
    print(f"  Sonucsuz atlanan   : {G['sonucsuz']}")
    print(f"  HS hesaplanamayan  : {G['harbi_secim_yok']}")

print(f"\nTIP BAZLI:")
print(f"  {'Tip':<16} {'Toplam':>7} {'Isabetli':>9} {'Oran':>8} {'Ort. Aday':>10}")
print(f"  {'-'*55}")
for tip in TIP_ORDER:
    if tip not in tip_stats:
        continue
    s = tip_stats[tip]
    t, i = s["toplam"], s["isabetli"]
    oran = i/t*100 if t > 0 else 0

    # Ortalama aday sayisi tipten cikar
    aday_map = {
        "tek_at": 1, "iki_aday": 2, "uc_aday": 3,
        "dort_aday": 4, "genis_liste": "5+"
    }
    print(f"  {tip:<16} {t:>7} {i:>9} {oran:>7.1f}% {str(aday_map.get(tip,'?')):>10}")

# Diger tipler (eger varsa)
for tip, s in sorted(tip_stats.items()):
    if tip not in TIP_ORDER:
        t, i = s["toplam"], s["isabetli"]
        print(f"  {tip:<16} {t:>7} {i:>9} {i/t*100 if t>0 else 0:>7.1f}%")

print(f"\nGUN BAZLI (son 10 gun):")
print(f"  {'Tarih':<12} {'Kosu':>6} {'Isabet':>8} {'Oran':>8}")
print(f"  {'-'*38}")
for tarih, gs in sorted(gun_stats.items())[-10:]:
    print(f"  {tarih:<12} {gs['toplam']:>6} {gs['isabetli']:>8} {gs['yuzde']:>7.1f}%")

print(f"\nTARIH ARALIGI: {sorted(gun_stats.keys())[0] if gun_stats else '?'} – {sorted(gun_stats.keys())[-1] if gun_stats else '?'}")
print(f"Toplam gun    : {len(gun_stats)}")

# JSON ciktisi
result = {
    "genel": genel,
    "tip_stats": dict(tip_stats),
    "gun_stats": gun_stats,
}
out_path = "/opt/harbi_ganyan_v3/reports/harbi_secim_backtest.json"
import os; os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nJSON kaydedildi: {out_path}")
