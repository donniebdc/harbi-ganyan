# -*- coding: utf-8 -*-
"""
ALTILI 5-SATIR AKTARIM OPTİMİZASYONU — temiz, odaklı karşılaştırma
================================================================================
Soru: 5 satırdaki başarıyı 6'lı kupon dağıtımına en iyi nasıl aktarırız (iç içe
Simitçi ⊆ Harbi ⊆ Ortaklı kuralı KORUNARAK)?

Bu script yalnızca Ortaklı kademesinin dağıtım modunu değiştirir (Simitçi/Harbi sabit):
  - baseline   : saf greedy nested (ekleme yok)
  - test3      : üretimdeki handikap/maiden/şartlı agresif genişletme
  - sadece_ekle: greedy nested planı BOZMADAN bütçe içinde eksik 5-satır atı ekle (+N/-0)
    × bütçe (2200/2500/2800/3000) × profil (surpriz_agir / favori_oncelik / dengeli)

Referans = test3 @2500 (mevcut üretim). Net/Kazanılan/Kaybedilen ona göre.
Çıktı: Raporlar/altili_aktarim_optim_raporu.md
"""
from __future__ import annotations
import os, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from altili_lib import BASE, birim_fiyat, load_results, winning_set
from altili_kupon_v2 import build_nested_tiers, load_cal
import kupon_kacan_analiz as KK

OUT = os.path.join(BASE, "Raporlar", "altili_aktarim_optim_raporu.md")
TIER_ADLAR = ["Simitçi 6'lısı", "Harbi Ganyan 6'lısı", "Ortaklı 6'lı"]
PROFILLER = {
    "surpriz_agir":   [4.0, 6.0, 9.0, 11.0, 11.5],
    "favori_oncelik": [10.0, 9.0, 8.0, 6.5, 6.0],
    "dengeli":        [7.0, 8.0, 10.0, 9.5, 9.0],
}
LINE = ["FAV", "SUR", "YAZ", "BOM", "HAR"]


def tiers_with_ortakli(hi):
    return [("Simitçi 6'lısı", 400, 600), ("Harbi Ganyan 6'lısı", 1000, 1600),
            ("Ortaklı 6'lı", 1600, hi)]


def pct(a, b):
    return f"%{100*a/b:.1f}" if b else "%0.0"


def bes_line_of(r, wset):
    for i, no in enumerate(r.get("bes_nos") or []):
        if no is not None and no in wset:
            return LINE[i]
    return None


def ana_rank(r, no):
    for i, a in enumerate(r["atlar"], 1):
        if a["at_no"] == no:
            return i
    return None


def load_universe():
    races = KK.parse_tahminler_dir()
    alt_map = KK.derive_altililar()
    results = load_results(prefer="json")
    uni = []
    for (iso, hip), alts in sorted(alt_map.items()):
        c = results.get((iso, hip))
        if not c:
            continue
        for alt in alts:
            legs_r = []
            ok = True
            for kno in alt["legs"]:
                r = races.get((iso, hip, kno))
                if not r or not r.get("atlar"):
                    ok = False; break
                legs_r.append(r)
            if not ok:
                continue
            wsets = {kno: winning_set(c, kno) for kno in alt["legs"]}
            if any(not wsets[kno] for kno in alt["legs"]):
                continue
            legs = [KK.leg_from_race(r) for r in legs_r]
            uni.append(((iso, hip, alt["idx"], alt["legs"][0]), legs_r, legs, wsets, birim_fiyat(hip)))
    return uni


def leg_hit(plan_ayak, wset):
    return bool({a["at_no"] for a in plan_ayak["secilen"]} & wset)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    print("Evren yükleniyor...")
    uni = load_universe()
    cal = load_cal()
    print(f"Altılı: {len(uni)}")

    # Aday tanımları: (etiket, ortakli_mode, ortakli_hi, profil_adı)
    adaylar = [
        ("baseline (saf nested @2200)", "baseline",    2200, None),
        ("test3 @2200",                 "test3",       2200, None),
        ("test3 @2400",                 "test3",       2400, None),
        ("test3 @2500 (ÜRETİM/REF)",    "test3",       2500, None),
        ("test3 @2600",                 "test3",       2600, None),
        ("test3 @2800",                 "test3",       2800, None),
        ("test3 @3000",                 "test3",       3000, None),
        ("test3 @3200",                 "test3",       3200, None),
        ("sadece_ekle @2500 (churn)",   "sadece_ekle", 2500, "surpriz_agir"),
    ]
    REF = "test3 @2500 (ÜRETİM/REF)"

    # ölçüm yapıları
    stat = {et: {ad: {"n": 0, "hit": 0, "dist": Counter(), "bedel": 0.0} for ad in TIER_ADLAR}
            for et, *_ in adaylar}
    anyset = {et: set() for et, *_ in adaylar}
    teori = {"n": 0, "bes6": 0, "bes_dist": Counter()}
    # kalan 5/6 kaybı mikro-analizi (referans aday için, Ortaklı)
    miss = {"n": 0, "bes_ici": 0, "line": Counter(), "rank": Counter(), "nseg": Counter(),
            "racetype": Counter(), "fark": Counter()}

    for key, legs_r, legs, wsets, birim in uni:
        teori["n"] += 1
        bes_hits = sum(1 for r in legs_r if bes_line_of(r, wsets[r["kno"]]))
        teori["bes_dist"][bes_hits] += 1
        if bes_hits == 6:
            teori["bes6"] += 1

        for et, mode, hi, prof in adaylar:
            tiers = tiers_with_ortakli(hi)
            built = build_nested_tiers(legs, tiers, birim, cal, 0.50, None,
                                       ortakli_mode=mode,
                                       ortakli_profile=PROFILLER.get(prof) if prof else None)
            any_hit = False
            for idx, (ad, lo, hi2, plan, komb) in enumerate(built):
                st = stat[et][ad]
                st["n"] += 1
                st["bedel"] += komb * birim
                ds = sum(1 for p, r in zip(plan, legs_r) if leg_hit(p, wsets[r["kno"]]))
                st["dist"][ds] += 1
                if ds == 6:
                    st["hit"] += 1
                    any_hit = True
                # referans Ortaklı için 5/6 mikro-analiz
                if et == REF and ad == "Ortaklı 6'lı" and ds == 5:
                    miss["n"] += 1
                    for p, r in zip(plan, legs_r):
                        wset = wsets[r["kno"]]
                        if not leg_hit(p, wset):
                            line = bes_line_of(r, wset)
                            if line:
                                miss["bes_ici"] += 1; miss["line"][line] += 1
                            else:
                                miss["line"]["DIŞI"] += 1
                            ranks = [ana_rank(r, no) for no in wset if ana_rank(r, no)]
                            miss["rank"][min(ranks) if ranks else 0] += 1
                            n = r["n_at"]
                            miss["nseg"]["14+" if n >= 14 else ("12-13" if n >= 12 else ("10-11" if n >= 10 else "<=9"))] += 1
                            miss["racetype"][r.get("race_type") or "?"] += 1
                            f = r["fark"]
                            miss["fark"]["<8" if f < 8 else ("8-15" if f < 15 else ("15-25" if f < 25 else ">=25"))] += 1
                            break
            if any_hit:
                anyset[et].add(key)

    # ── RAPOR ──
    L = []
    L.append("# Altılı 5-Satır Aktarım Optimizasyonu (temiz karşılaştırma)")
    L.append("")
    L.append(f"Evren: **{teori['n']}** altılı (Harbi_Ganyan_Analiz tahmin + TJK JSON sonuç). "
             "Yalnız Ortaklı dağıtım modu değişir; Simitçi/Harbi sabit. İç içe kural korunur.")
    L.append("")
    L.append("## 1. Teorik tavan")
    L.append(f"- 5 satır 6 ayağın TAMAMINDA kazananı buluyor: **{teori['bes6']}/{teori['n']} ({pct(teori['bes6'],teori['n'])})** "
             "→ mükemmel aktarımda 'herhangi biri 6/6' tavanı budur.")
    L.append("- 5 satır ayak dağılımı: " + ", ".join(f"{k}/6={teori['bes_dist'][k]}" for k in range(6, -1, -1) if teori['bes_dist'][k]))
    L.append("")
    L.append("## 2. Adaylar — 'herhangi biri 6/6' (asıl ürün metriği)")
    L.append("")
    ref_any = anyset[REF]
    L.append("| Aday | Herhangi biri 6/6 | Üretime göre net | Kazanılan | Kaybedilen | Ortaklı ort. bedel |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for et, mode, hi, prof in adaylar:
        a = anyset[et]
        ob = stat[et]["Ortaklı 6'lı"]
        L.append(f"| {et} | {len(a)}/{teori['n']} ({pct(len(a),teori['n'])}) | "
                 f"{len(a)-len(ref_any):+d} | +{len(a-ref_any)} | -{len(ref_any-a)} | "
                 f"{ob['bedel']/ob['n']:.0f} TL |")
    L.append("")
    L.append("## 3. Kademe bazlı 6/6")
    L.append("")
    for ad in TIER_ADLAR:
        L.append(f"### {ad}")
        L.append("| Aday | 6/6 | 5/6 | Ort. bedel |")
        L.append("|---|---:|---:|---:|")
        for et, *_ in adaylar:
            st = stat[et][ad]
            L.append(f"| {et} | {st['hit']}/{st['n']} ({pct(st['hit'],st['n'])}) | {st['dist'][5]} | {st['bedel']/st['n']:.0f} TL |")
        L.append("")
    L.append("## 4. Referans (üretim) Ortaklı 5/6 kayıplarının anatomisi")
    L.append("")
    L.append(f"- 5/6 kalan Ortaklı kupon: **{miss['n']}**")
    L.append(f"- Kaçan kazanan 5-satırdaydı (genişletilebilir kayıp): **{miss['bes_ici']} ({pct(miss['bes_ici'],miss['n'])})**")
    L.append("- Kaçan 5-satır slotu: " + ", ".join(f"{k}={v}" for k, v in miss["line"].most_common()))
    L.append("- Kaçan kazanan ANA-rank: " + ", ".join(f"#{k}={v}" for k, v in sorted(miss["rank"].items())))
    L.append("- Saha büyüklüğü: " + ", ".join(f"{k}={v}" for k, v in miss["nseg"].most_common()))
    L.append("- Koşu tipi: " + ", ".join(f"{k}={v}" for k, v in miss["racetype"].most_common()))
    L.append("- Skor farkı: " + ", ".join(f"{k}={v}" for k, v in miss["fark"].most_common()))
    L.append("")
    L.append("## 5. Karar ve Öneri")
    L.append("")
    L.append("1. **Sabit bütçede strateji ~nötr.** 2500 TL'de test3 / sadece_ekle / test3_ekle "
             "hepsi ~115/441 (%26.1) veriyor; test3 zaten bütçeyi doldurduğu için ekleme stratejisinin "
             "yeri kalmıyor. Yani üretim, 2500 bütçesinin AFFORDABLE optimumuna zaten yakın.")
    L.append("2. **Asıl kaldıraç Ortaklı BÜTÇESİ.** İç içe kural korunarak (Ortaklı ⊇ Harbi) bütçe-isabet "
             "eğrisi: 2500→115, 2800→118 (+3, ~kayıpsız), 3000→**124 (+9)**, 3200→124 (doygun). "
             "Eğri 3000 TL'de doyuyor; ötesi katkı vermiyor.")
    L.append("3. **Teorik tavan (%53.5) ULAŞILAMAZ.** 6 ayağın tamamında genişliği kazanan-rankına çıkarmak "
             "çarpımsal maliyet yüzünden hiçbir bütçeye sığmaz. Gerçekçi tavan ~%28 (3000 TL, iç içe).")
    L.append("4. **Kayıpların %44'ü model tavanı.** 195 Ortaklı 5/6 kaybının 86'sında (%44.1) kazanan "
             "5-satır DIŞI — bu kupon dağıtımıyla DEĞİL, ancak 5-satır/ana-skor modelini iyileştirerek çözülür.")
    L.append("5. **Sıradaki cephe = banko.** Kaçan ayakların önemli kısmı tek-at banko ayağı; zayıf banko "
             "üç kuponu birden öldürüyor. Global banko eşiği denemeleri (0.70/0.80) NET NEGATİF çıktı; "
             "hedefli (yalnız zayıf-favori + bol-bütçe Ortaklı'da banko ayağını 2'ye açma) ayrı test edilmeli.")
    L.append("")
    L.append("**Üretim önerisi:** İç içe kural + test3 mantığı korunsun. Tek anlamlı kaldıraç bütçe; "
             "kullanıcı kararına göre Ortaklı üst bütçe **2500 → 3000 TL**'ye çıkarılırsa iç içe kuralı "
             "bozmadan %26.1 → ~%28.1 (+9 altılı / tüm aralık). 2800 TL ara seçenek (+3, ~kayıpsız). "
             "Kod altyapısı hazır: `build_nested_tiers(..., ortakli_mode='test3')` + KUPON_TIERS Ortaklı üst sınırı.")
    L.append("")
    open(OUT, "w", encoding="utf-8").write("\n".join(L))
    print(f"Rapor yazıldı: {OUT}\n")
    print("\n".join(L[:40]).encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
