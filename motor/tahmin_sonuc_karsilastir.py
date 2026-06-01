# -*- coding: utf-8 -*-
"""
TAHMİN ↔ SONUÇ KARŞILAŞTIRMA — `TahminSonuçları` klasörü
================================================================================
Üretilen tahminleri (Harbi_Ganyan_Analiz/<gün>/_Tahminler.txt = 5 satır) JSON
sonuçlarıyla karşılaştırır ve her gün için okunabilir bir karşılaştırma dosyası
yazar (kullanıcı ŞABLON ÖRNEKLEM):
  - Her koşu: 5 satır tahmin + KAZANAN (ganyan/ikili/sıralı ikili) + ✓ (kazanan 5-satırda mı).
  - Her altılı: ALTILI sonucu + 3 iç-içe kupon (Simitçi/Harbi/Ortaklı) ayak-ayak ✓/✗
    ve "TAHMİNİMİZ N'TE KALDI / TUTTU" özeti.

Kuponlar build_nested_tiers ile YENİDEN kurulur (güncel iç-içe mantık); _Altili.txt
parse edilmez. Sonuç kaynağı `load_results` (JSON taban). Üretim kodunu değiştirmez.

Kullanım:
    python tahmin_sonuc_karsilastir.py                 # tüm örtüşen günler
    python tahmin_sonuc_karsilastir.py 2026-02-08
    python tahmin_sonuc_karsilastir.py 2026-02-01 2026-02-28
"""
from __future__ import annotations
import os, sys, glob, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from altili_lib import BASE, birim_fiyat, winning_set, load_results
from altili_kupon_v2 import build_nested_tiers, load_cal, KUPON_TIERS
from kupon_kacan_analiz import parse_tahminler_dir, derive_altililar, leg_from_race
from sonuc_txt_uret import fmt_kalem, fmt_tutar, is_big

JSON_DIR = os.path.join(BASE, "Sonuclar JSON")
OUT_DIR = os.path.join(BASE, "TahminSonuçları")
CIZGI = "═" * 78
SLOTLAR = ["🎯 Harbi Ganyan Favorisi  ", "🔒 Kazanırsa Sürpriz Olmaz",
           "✍️  Kupona Yazılabilir    ", "💣 Bomba!                 ",
           "❓ Harbi mi?              "]


def _raw_gun(iso):
    p = os.path.join(JSON_DIR, f"{iso}.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def _kazanan_satiri(kv):
    """KAZANAN bloğu: '<no> - <ad> | GANYAN.. | İKİLİ.. | S.İKİLİ..' (büyük kombineler hariç)."""
    wno = kv.get("kazanan")
    wname = next((s.get("at", "") for s in kv.get("siralama", []) if s.get("sira") == 1), "")
    kalemler = [fmt_kalem(b) for b in (kv.get("bahisler") or {}).get("kalemler") or []
                if not is_big(b.get("tip", "")) and b.get("tip") in
                ("GANYAN", "İKİLİ", "SIRALI İKİLİ")]
    return f"\t{wno} - {wname}   |   " + "   |   ".join(kalemler)


def _kosu_blok(iso, hip, kno, races, kv):
    r = races.get((iso, hip, kno))
    L = []
    pist = kv.get("pist", ""); mesafe = kv.get("mesafe", "")
    bilgi = f"{pist} {mesafe}m".strip()
    L.append(f"┌─ \t{kno}. KOŞU | {bilgi} | {kv.get('n_at','?')} at")
    L.append("│")
    wset = set()  # kazanan kümesi (berabere/eküri dahil) bu koşu için
    if r and r.get("bes_nos"):
        no2ad = {a["at_no"]: a["at"] for a in r["atlar"]}
        kazanan_no = kv.get("kazanan")
        for i, no in enumerate(r["bes_nos"]):
            ad = no2ad.get(no, "")
            isabet = (no == kazanan_no)
            mark = "  ✅" if isabet else ""
            L.append(f"│  {SLOTLAR[i]} : No:{no if no else '-':<3} {ad}{mark}")
    else:
        L.append("│  (5-satır tahmini bulunamadı)")
    L.append("")
    L.append(CIZGI)
    L.append("\tKAZANAN")
    L.append("")
    L.append(_kazanan_satiri(kv))
    L.append("")
    L.append(CIZGI)
    return L


def _altili_blok(iso, hip, alt, races, res, kosular, birim, cal):
    legs_kno = alt["legs"]
    L = []
    # ayak verileri (tahminden)
    legs = []
    ok = True
    for kno in legs_kno:
        r = races.get((iso, hip, kno))
        if not r or not r["atlar"]:
            ok = False; break
        legs.append(leg_from_race(r))
    winners = [str(kosular.get(str(k), {}).get("kazanan", "?")) for k in legs_kno]
    L.append(CIZGI)
    L.append(f"{alt['idx']}. ALTILI GANYAN (Sonuçlar) : {'/'.join(winners)}"
             f"\tİKRAMİYE BEDELİ : {fmt_tutar(alt.get('odeme'))} TL")
    L.append(CIZGI)
    L.append("")
    L.append("🎲  TAHMİNLERİMİZ 🎲")
    L.append("")
    if not ok:
        L.append("  (altılı ayaklarının tahmini eksik — kupon kurulamadı)")
        L.append(""); L.append(CIZGI)
        return L
    for ad, lo, hi, plan, komb in build_nested_tiers(legs, KUPON_TIERS, birim, cal, 0.50):
        hits = 0
        leg_lines = []
        for p in plan:
            wset = winning_set(res, p["kno"])
            sec_nos = {a["at_no"] for a in p["secilen"]}
            hit = bool(wset & sec_nos)
            if hit:
                hits += 1
            nos = []; names = []
            for a in p["secilen"]:
                if a["at_no"] in wset:
                    nos.append(f"[{a['at_no']}]"); names.append(f"[{a['at']}]")
                else:
                    nos.append(str(a["at_no"])); names.append(a["at"])
            isaret = "✓" if hit else "✗"
            leg_lines.append(f"    {isaret} {'-'.join(nos):<18} {', '.join(names)}")
        bedel = komb * birim
        ozet = "TUTTU ✅ (6/6)" if hits == 6 else f"{hits}'TE KALDI ({hits}/6)"
        L.append(f"  🎲 {ad} {bedel:.0f} TL 🎲 (6'LI GANYAN TAHMİNİMİZ {ozet})")
        L.append("  " + "─" * 58)
        L += leg_lines
        L.append("")
    L.append(CIZGI)
    return L


def uret_gun(iso, races, results, cal):
    gun = _raw_gun(iso)
    if not gun:
        return None
    try:
        tarih_disp = datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        tarih_disp = iso
    alt_map = derive_altililar()
    L = []
    for hip_key, hd in (gun.get("hipodromlar") or {}).items():
        from altili_lib import norm_hip
        hipn = norm_hip(hip_key)
        kosular = hd.get("kosular") or {}
        res = results.get((iso, hipn))
        if res is None:
            continue
        L.append(CIZGI)
        L.append(f"🎰 {tarih_disp} {hip_key} KARŞILAŞTIRMALI SONUÇ")
        L.append(CIZGI)
        L.append("")
        for kno_s in sorted(kosular, key=lambda x: int(x)):
            L += _kosu_blok(iso, hipn, int(kno_s), races, kosular[kno_s])
            L.append("")
        # altılılar — sonuç JSON'undan (ödeme dahil); yoksa analiz dosyalarından
        birim = birim_fiyat(hipn)
        alts = _altili_from_json(kosular) or alt_map.get((iso, hipn))
        for alt in alts:
            L += _altili_blok(iso, hipn, alt, races, res, kosular, birim, cal)
            L.append("")
    if not L:
        return None
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{iso}.txt")
    open(out_path, "w", encoding="utf-8").write("\n".join(L).rstrip() + "\n")
    return out_path


def _altili_from_json(kosular):
    import re
    out = []
    for kno_s, kv in kosular.items():
        for b in (kv.get("bahisler") or {}).get("kalemler") or []:
            if "6'LI GANYAN" in b.get("tip", ""):
                kno = int(kno_s)
                mi = re.match(r"\s*(\d+)\s*\.", b["tip"])
                out.append({"idx": int(mi.group(1)) if mi else len(out) + 1,
                            "last": kno, "legs": list(range(kno - 5, kno + 1)),
                            "odeme": b.get("tutar")})
    out.sort(key=lambda a: a["last"])
    return out


def main():
    args = sys.argv[1:]
    print("Tahminler ve sonuçlar yükleniyor...")
    races = parse_tahminler_dir()
    results = load_results(prefer="json")
    cal = load_cal()
    files = sorted(glob.glob(os.path.join(JSON_DIR, "*.json")))
    if args:
        bas = args[0]; bit = args[1] if len(args) > 1 else bas
        files = [f for f in files if bas <= os.path.basename(f)[:-5] <= bit]
    yazilan = 0
    for f in files:
        iso = os.path.basename(f)[:-5]
        p = uret_gun(iso, races, results, cal)
        if p:
            yazilan += 1
            print(f"yazıldı: {os.path.basename(p)}")
    print(f"\nTamamlandı. {yazilan} gün -> {OUT_DIR}")


if __name__ == "__main__":
    main()
