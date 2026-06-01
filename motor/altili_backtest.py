# -*- coding: utf-8 -*-
"""
ALTILI BACKTEST — kurduğumuz kuponları gerçek altılı sonuçlarıyla kıyaslar.
Her altılı için (gün-hipodrom) kuponu üç bütçe kademesinde kurar, her ayağı
gerçek kazanan kümesiyle eşler, tutarsa ödeme dönüşünü yazar.

Çıktı: ekran özeti + altili_backtest_raporu.md
"""
import io, sys, os
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from altili_lib import BASE, parse_tahmin_arsiv, load_all_csv, winning_set, birim_fiyat
from altili_kupon_v2 import build_coupon, build_tier, load_cal, seg_n, KUPON_TIERS, tier_policy
import glob as _glob

def _newest_bulk():
    cands = sorted(_glob.glob(os.path.join(BASE, "v5_tahmin_*.txt")), key=os.path.getmtime)
    return cands[-1] if cands else os.path.join(BASE, "v5_tahmin_01042026-30052026.txt")

TAHMIN = _newest_bulk()
TIERS = KUPON_TIERS   # (ad, lo, hi) — birim fiyat hipodroma göre
BANKO_ESIK = 0.50   # akıllı banko: lider güveni bunun altındaysa tek-at yerine 2-at çıpa
# Politika karşılaştırması bu kademede yapılır (orta band):
KMP_TIER = ("Harbi Ganyan 6'lısı", 1200, 1600)

def build_legs(races, ti, hip, leg_knos):
    legs = []
    for kno in leg_knos:
        r = races.get((ti, hip, kno))
        if not r or not r["atlar"]:
            return None
        legs.append({"kno": kno, "atlar": r["atlar"], "n_at": r["n_at"], "fark": r["fark"]})
    return legs

def main():
    races = parse_tahmin_arsiv(TAHMIN)
    csvs  = load_all_csv()
    cal   = load_cal()

    # tüm altılıları topla
    altililar = []
    for (ti, hip), c in csvs.items():
        for alt in c["altililar"]:
            altililar.append((ti, hip, c, alt))
    print(f"CSV'de toplam altılı: {len(altililar)}")

    rapor = []
    def R(s=""): rapor.append(s)
    R(f"# ALTILI GANYAN BACKTEST RAPORU")
    R(f"\nKaynak tahmin: `{os.path.basename(TAHMIN)}`  |  Birim: hipodroma göre 1.00 / 1.25 TL")
    R(f"\nKademeler: " + ", ".join(f"{ad} ({lo}-{hi}₺)" for ad, lo, hi in TIERS))
    R(f"\nToplam CSV altılısı: {len(altililar)}\n")

    # tier istatistikleri
    stat = {ad: {"degerlendirilen": 0, "isabet": 0, "maliyet": 0.0, "donus": 0.0,
                 "komb": 0, "banko_dogru": 0, "banko_say": 0,
                 "banko_seg": defaultdict(lambda: [0, 0])} for ad, _, _ in TIERS}

    detaylar = []  # örnek kuponlar
    eval_say = 0
    for ti, hip, c, alt in altililar:
        legs = build_legs(races, ti, hip, alt["legs"])
        if legs is None:
            continue
        # tüm ayakların kazananı bilinmeli
        wsets = {kno: winning_set(c, kno) for kno in alt["legs"]}
        if any(not wsets[kno] for kno in alt["legs"]):
            continue
        eval_say += 1
        birim = birim_fiyat(hip)
        for tier in TIERS:
            ad, lo, hi = tier
            _, _, _, plan, komb = build_tier(legs, tier, birim, cal, BANKO_ESIK,
                                             **tier_policy(ad))
            s = stat[ad]
            s["degerlendirilen"] += 1
            s["komb"] += komb
            s["maliyet"] += komb * birim
            # isabet: her ayak seçimi kazanan kümesini kesiyor mu
            hit = True
            for p in plan:
                sec = {a["at_no"] for a in p["secilen"]}
                if not (sec & wsets[p["kno"]]):
                    hit = False
                    break
            if hit:
                s["isabet"] += 1
                s["donus"] += alt["odeme"]
            # banko lider doğruluğu
            bl = next((p for p in plan if p["banko_lider"]), None)
            if bl:
                s["banko_say"] += 1
                sg = seg_n(legs[[p["kno"] for p in plan].index(bl["kno"])]["n_at"])
                s["banko_seg"][sg][1] += 1
                if {a["at_no"] for a in bl["secilen"]} & wsets[bl["kno"]]:
                    s["banko_dogru"] += 1
                    s["banko_seg"][sg][0] += 1
            # örnek kupon (Harbi Ganyan 6'lısı kademesi)
            if ad == KMP_TIER[0] and len(detaylar) < 6:
                detaylar.append((ti, hip, alt, plan, komb, hit, wsets, birim))

    # ── KARŞILAŞTIRMA: 3 banko politikası (Harbi Ganyan 6'lısı kademesi) ──
    POL = [("Banko ZORUNLU (her zaman tek-at)", True, 0.0),
           ("Akıllı banko (eşik 0.50)",          True, BANKO_ESIK),
           ("Bankosuz (serbest)",                False, 0.0)]
    cmp_stat = {ad: {"isabet": 0, "maliyet": 0.0, "donus": 0.0, "n": 0,
                     "tekbanko": 0, "tekbanko_dogru": 0} for ad, _, _ in POL}
    for ti, hip, c, alt in altililar:
        legs = build_legs(races, ti, hip, alt["legs"])
        if legs is None: continue
        wsets = {kno: winning_set(c, kno) for kno in alt["legs"]}
        if any(not wsets[kno] for kno in alt["legs"]): continue
        birim = birim_fiyat(hip)
        for ad, fb, esik in POL:
            plan, komb = build_coupon(legs, int(KMP_TIER[2] / birim), cal,
                                      force_banko=fb, banko_esik=esik)
            cs = cmp_stat[ad]; cs["n"] += 1; cs["maliyet"] += komb * birim
            if all(({a["at_no"] for a in p["secilen"]} & wsets[p["kno"]]) for p in plan):
                cs["isabet"] += 1; cs["donus"] += alt["odeme"]
            bl = next((p for p in plan if p["banko_lider"] and p["width"] == 1), None)
            if bl:
                cs["tekbanko"] += 1
                if {a["at_no"] for a in bl["secilen"]} & wsets[bl["kno"]]:
                    cs["tekbanko_dogru"] += 1

    print(f"Değerlendirilen altılı (tahmin+sonuç tam): {eval_say}\n")
    R(f"Değerlendirilen altılı (tahmin+sonuç eşleşen): **{eval_say}**\n")

    # ── ÖZET TABLO ──
    print("="*78)
    print(f"{'Bütçe':<10}{'Altılı':>8}{'İsabet':>9}{'İsabet%':>9}{'OrtMaliyet':>12}{'TopMaliyet':>12}{'TopDönüş':>12}{'Net':>12}")
    print("="*78)
    R("## Bütçe kademesi sonuçları\n")
    R(f"| Bütçe | Altılı | İsabet | İsabet % | Ort. Maliyet | Top. Maliyet | Top. Dönüş | Net |")
    R(f"|---|---:|---:|---:|---:|---:|---:|---:|")
    for ad, _, _ in TIERS:
        s = stat[ad]
        d = s["degerlendirilen"] or 1
        isb = 100 * s["isabet"] / d
        ortm = s["maliyet"] / d
        net = s["donus"] - s["maliyet"]
        print(f"{ad:<10}{s['degerlendirilen']:>8}{s['isabet']:>9}{isb:>8.1f}%"
              f"{ortm:>11.0f}₺{s['maliyet']:>11.0f}₺{s['donus']:>11.0f}₺{net:>11.0f}₺")
        R(f"| {ad} | {s['degerlendirilen']} | {s['isabet']} | %{isb:.1f} | "
          f"{ortm:.0f}₺ | {s['maliyet']:.0f}₺ | {s['donus']:.0f}₺ | {net:+.0f}₺ |")

    # ── BANKO DOĞRULUĞU ──
    print("\n" + "="*78)
    print("ÇIPA AYAĞI DOĞRULUĞU (tek-at banko veya 2-at çıpa, kazananı içerdi mi)")
    print("="*78)
    R("\n## Çıpa ayağı doğruluğu\n")
    R("Her altılıda lider çıpa ayağının (tek-at banko ya da 2-at çıpa) kazananı içerme oranı:\n")
    R("| Bütçe | Banko doğru / toplam | Oran |")
    R("|---|---:|---:|")
    for ad, _, _ in TIERS:
        s = stat[ad]
        bs = s["banko_say"] or 1
        oran = 100 * s["banko_dogru"] / bs
        print(f"  {ad:<10}: {s['banko_dogru']}/{s['banko_say']}  (%{oran:.1f})")
        R(f"| {ad} | {s['banko_dogru']}/{s['banko_say']} | %{oran:.1f} |")
    # banko segment dağılımı (1000 TL)
    print("\n  Banko ayağı alan-segmenti (Harbi 6'lısı):")
    R("\nBanko ayağının seçildiği alan segmenti (Harbi Ganyan 6'lısı kademesi):\n")
    R("| Alan | Banko doğru / toplam | Oran |")
    R("|---|---:|---:|")
    sb = stat[KMP_TIER[0]]["banko_seg"]
    for sg in ["≤7","8-9","10-11","12-13","14+"]:
        w, t = sb[sg]
        if t:
            print(f"    {sg:<6}: {w}/{t} (%{100*w/t:.0f})")
            R(f"| {sg} | {w}/{t} | %{100*w/t:.0f} |")

    # ── 3 BANKO POLİTİKASI KARŞILAŞTIRMASI ──
    print("\n" + "="*78)
    print("BANKO POLİTİKASI KARŞILAŞTIRMASI (Harbi Ganyan 6'lısı)")
    print("="*78)
    R("\n## Banko politikası karşılaştırması (Harbi Ganyan 6'lısı kademesi)\n")
    R("Her altılıda ≥1 banko/çıpa direktifinin maliyeti ve akıllı banko çözümü:\n")
    R("| Politika | İsabet | İsabet % | Top. Maliyet | Top. Dönüş | Net | Tek-at banko doğruluğu |")
    R("|---|---:|---:|---:|---:|---:|---:|")
    for ad, _, _ in POL:
        cs = cmp_stat[ad]; n = cs["n"] or 1
        isb = 100 * cs["isabet"] / n; net = cs["donus"] - cs["maliyet"]
        tb = (f"{cs['tekbanko_dogru']}/{cs['tekbanko']} (%{100*cs['tekbanko_dogru']/cs['tekbanko']:.0f})"
              if cs["tekbanko"] else "—")
        print(f"  {ad:<34}: isabet {cs['isabet']}/{cs['n']} (%{isb:.1f}) | "
              f"net {net:+.0f}₺ | tekbanko {tb}")
        R(f"| {ad} | {cs['isabet']}/{cs['n']} | %{isb:.1f} | {cs['maliyet']:.0f}₺ | "
          f"{cs['donus']:.0f}₺ | {net:+.0f}₺ | {tb} |")

    # ── ÖRNEK KUPONLAR ──
    R("\n## Örnek kuponlar (Harbi Ganyan 6'lısı kademesi)\n")
    for ti, hip, alt, plan, komb, hit, wsets, birim in detaylar:
        R(f"### {ti} · {hip} · {alt['idx']}. Altılı (Koşu {alt['legs'][0]}-{alt['legs'][-1]})")
        R(f"Sonuç: {'✅ TUTTU' if hit else '❌ tutmadı'} · {komb} komb × {birim:.2f}₺ = {komb*birim:.0f}₺ · ödeme {alt['odeme']:.0f}₺\n")
        R("| Ayak | Genişlik | Etiket | Seçilen | Kazanan |")
        R("|---|---|---|---|---|")
        for p in plan:
            nos = "-".join(str(a["at_no"]) for a in p["secilen"])
            kaz = ",".join(str(x) for x in sorted(wsets[p["kno"]]))
            mark = "✓" if ({a["at_no"] for a in p["secilen"]} & wsets[p["kno"]]) else "✗"
            R(f"| {p['kno']} | {p['width']} | {p['etiket']} | {nos} | {kaz} {mark} |")
        R("")

    out = os.path.join(BASE, "altili_backtest_raporu.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(rapor))
    print(f"\n📝 Rapor: {out}")

if __name__ == "__main__":
    main()
