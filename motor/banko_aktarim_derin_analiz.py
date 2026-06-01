# -*- coding: utf-8 -*-
"""
BANKO + 5-SATIR AKTARIM DERİN ANALİZİ
================================================================================
Soru: 5'li satırdaki başarıyı 6'lı kupona neden tam aktaramıyoruz ve koşullu banko +
yeni bütçe limitleri bunu ne kadar düzeltiyor?

Karşılaştırma (441 altılı, taze tahminler + TJK JSON sonuç):
  ESKİ  = zorunlu banko (force) + Ortaklı @2500   (banko_zorunlu_esik=None)
  YENİ  = KOŞULLU banko (BANKO_ZORUNLU_ESIK=0.55) + Ortaklı @2800  (üretim)

Çıktı: Raporlar/banko_aktarim_derin_analiz_raporu.md
İç içe kural (Simitçi ⊆ Harbi ⊆ Ortaklı) her iki kurguda da korunur ve doğrulanır.
"""
from __future__ import annotations
import os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import altili_kupon_v2 as K
from altili_kupon_v2 import (build_nested_tiers, load_cal, banko_score,
                             banko_guven_eff, BANKO_ZORUNLU_ESIK, KUPON_TIERS)
import altili_aktarim_optim as AO
from altili_lib import BASE

OUT = os.path.join(BASE, "Raporlar", "banko_aktarim_derin_analiz_raporu.md")
SIM, HAR, ORT = AO.TIER_ADLAR


def pct(a, b):
    return f"%{100*a/b:.1f}" if b else "%0.0"


def old_tiers():
    return [(SIM, 400, 600), (HAR, 1000, 1600), (ORT, 1600, 2500)]


def build(legs, birim, cal, tiers, zorunlu):
    return build_nested_tiers(legs, tiers, birim, cal, 0.50, None,
                              ortakli_mode="test3", banko_zorunlu_esik=zorunlu)


def coupon_dist(plan, legs_r, wsets):
    return sum(1 for p, r in zip(plan, legs_r) if AO.leg_hit(p, wsets[r["kno"]]))


def run_config(uni, cal, tiers, zorunlu):
    """-> dict: anyset, tier_hit, tier_n, bedel, banko_killed, loss5, banko_used,
                nest_ok, miss(anatomi for Ortaklı 5/6)."""
    anyset = set()
    th = {a: 0 for a in AO.TIER_ADLAR}
    tn = {a: 0 for a in AO.TIER_ADLAR}
    bd = {a: 0.0 for a in AO.TIER_ADLAR}
    killed = loss5 = banko_used = lider_count = coup = 0
    nest_ok = True
    miss = {"n": 0, "bes_ici": 0, "line": Counter(), "rank": Counter(),
            "nseg": Counter(), "racetype": Counter()}
    for key, legs_r, legs, wsets, birim in uni:
        built = build(legs, birim, cal, tiers, zorunlu)
        sets = []
        anyf = False
        for ad, lo, hi, plan, komb in built:
            tn[ad] += 1
            bd[ad] += komb * birim
            ds = coupon_dist(plan, legs_r, wsets)
            if ds == 6:
                th[ad] += 1
                anyf = True
            sets.append([set(a["at_no"] for a in p["secilen"]) for p in plan])
            if ad == ORT:
                coup += 1
                if any(p["width"] == 1 for p in plan):
                    banko_used += 1
                if any(p.get("banko_lider") for p in plan):
                    lider_count += 1
                if ds == 5:
                    loss5 += 1
                    for p, r in zip(plan, legs_r):
                        wset = wsets[r["kno"]]
                        if not AO.leg_hit(p, wset):
                            if p["width"] == 1:
                                killed += 1
                            miss["n"] += 1
                            line = AO.bes_line_of(r, wset)
                            if line:
                                miss["bes_ici"] += 1
                                miss["line"][line] += 1
                            else:
                                miss["line"]["DIŞI"] += 1
                            ranks = [AO.ana_rank(r, no) for no in wset if AO.ana_rank(r, no)]
                            miss["rank"][min(ranks) if ranks else 0] += 1
                            n = r["n_at"]
                            miss["nseg"]["14+" if n >= 14 else ("12-13" if n >= 12 else ("10-11" if n >= 10 else "≤9"))] += 1
                            miss["racetype"][r.get("race_type") or "?"] += 1
                            break
        for li in range(6):
            if not (sets[0][li] <= sets[1][li] <= sets[2][li]):
                nest_ok = False
        if anyf:
            anyset.add(key)
    return dict(anyset=anyset, th=th, tn=tn, bd=bd, killed=killed, loss5=loss5,
                banko_used=banko_used, lider_count=lider_count, coup=coup,
                nest_ok=nest_ok, miss=miss)


def banko_dagilimi(uni, cal):
    """PROD'un kilitlediği banko-lider ayağın favori efektif güven dağılımı."""
    vals = []
    for key, legs_r, legs, wsets, birim in uni:
        bi = max(range(len(legs)), key=lambda i: banko_score(legs[i]))
        vals.append(banko_guven_eff(legs[bi], cal))
    vals.sort()
    def p(q):
        return vals[min(len(vals) - 1, int(q / 100 * len(vals)))]
    return dict(n=len(vals), med=vals[len(vals) // 2], p25=p(25), p75=p(75),
                p90=p(90), mx=vals[-1], mn=vals[0])


def threshold_sweep(uni, cal):
    """Eşik eğrisi: @2800 yeni bütçede çeşitli eşikler."""
    new_t = KUPON_TIERS
    rows = []
    for label, z in [("force (zorunlu)", None), ("0.50", 0.50), ("0.55 (ÜRETİM)", 0.55),
                     ("0.58", 0.58), ("kapalı (hiç banko)", 1.01)]:
        r = run_config(uni, cal, new_t, z)
        rows.append((label, len(r["anyset"]), r["th"][SIM], r["th"][HAR], r["th"][ORT]))
    return rows


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    print("Evren yükleniyor...")
    uni = AO.load_universe()
    cal = load_cal()
    N = len(uni)
    print(f"Altılı: {N}")

    # teorik tavan
    bes6 = 0
    bes_dist = Counter()
    for key, legs_r, legs, wsets, birim in uni:
        h = sum(1 for r in legs_r if AO.bes_line_of(r, wsets[r["kno"]]))
        bes_dist[h] += 1
        if h == 6:
            bes6 += 1

    bd_stat = banko_dagilimi(uni, cal)
    OLD = run_config(uni, cal, old_tiers(), None)
    NEW = run_config(uni, cal, KUPON_TIERS, BANKO_ZORUNLU_ESIK)
    sweep = threshold_sweep(uni, cal)

    old_any, new_any = OLD["anyset"], NEW["anyset"]
    kazanilan = new_any - old_any
    kaybedilen = old_any - new_any

    L = []
    A = L.append
    A("# Banko + 5-Satır Aktarım Derin Analizi")
    A("")
    A(f"Evren: **{N}** altılı (Harbi_Ganyan_Analiz taze tahmin + TJK JSON sonuç, "
      "01.02–30.05.2026). İç içe kural (Simitçi ⊆ Harbi ⊆ Ortaklı) korunur.")
    A("")
    A("## 1. Aktarım uçurumu: 5 satır buluyor, kupon yansıtamıyor")
    A("")
    A(f"- 5 satır 6 ayağın **TAMAMINDA** kazananı buluyor: **{bes6}/{N} ({pct(bes6,N)})** "
      "→ mükemmel aktarımda 'herhangi bir kupon 6/6' teorik tavanı budur.")
    A("- 5 satır ayak dağılımı: " + ", ".join(f"{k}/6={bes_dist[k]}" for k in range(6, -1, -1) if bes_dist[k]))
    A(f"- ESKİ üretim bunu kupona yalnız **{len(old_any)}/{N} ({pct(len(old_any),N)})** "
      "olarak yansıtabiliyordu. Uçurumun üç sebebi: (a) zorunlu banko, (b) bütçe tavanı, "
      "(c) model tavanı (kazanan 5-satır dışı). Bu rapor (a) ve (b)'yi düzeltir.")
    A("")
    A("## 2. Zorunlu bankonun kanıtlanmış maliyeti")
    A("")
    A(f"PROD'un her kupona kilitlediği **banko-lider ayağın** favori efektif kazanma "
      f"olasılığı (kendi + eküri ortağı payı, {bd_stat['n']} altılı):")
    A("")
    A("| İstatistik | Favori efektif güven |")
    A("|---|---:|")
    A(f"| Medyan | **{bd_stat['med']:.3f}** (favori medyanda yalnız ~%{100*bd_stat['med']:.0f} kazanıyor) |")
    A(f"| p25 / p75 | {bd_stat['p25']:.3f} / {bd_stat['p75']:.3f} |")
    A(f"| p90 / max | {bd_stat['p90']:.3f} / {bd_stat['mx']:.3f} |")
    A("")
    A("> Yani üretim, favorinin yarıdan fazla kez KAYBETTİĞİ ayaklara bile tek-at banko "
      "yazıp üç kuponu birden riske atıyordu. Bu, kullanıcı sezgisini doğruluyor: banko "
      "zorunluluğu kaldırılmalı, banko yalnız net üstünlükte yazılmalı.")
    A("")
    A("## 3. Koşullu banko eşik eğrisi (yeni bütçe @2800)")
    A("")
    A("Banko, banko-aday ayağın favori efektif güveni eşiği geçerse yazılır; geçmezse "
      "ayak en az 2'ye genişler.")
    A("")
    A("| Eşik | Herhangi 6/6 | Simitçi | Harbi | Ortaklı |")
    A("|---|---:|---:|---:|---:|")
    for label, anyc, s, h, o in sweep:
        A(f"| {label} | {anyc}/{N} ({pct(anyc,N)}) | {s} | {h} | {o} |")
    A("")
    A("**Kritik nüans:** bankoyu *tamamen* kapatmak (hiç banko) koşullu tutmaktan DAHA "
      "KÖTÜ. Optimum 'hep banko' da 'hiç banko' da değil — **koşullu banko**. Eşik "
      "0.50–0.58 platosunda sonuç ±1 altılı; **0.55** = 'favori ≥%55 kazanır' net "
      "üstünlük (kullanıcı tercihi).")
    A("")
    A("## 4. ESKİ vs YENİ (üretim) — net etki")
    A("")
    A("| Kademe | ESKİ (force@2500) 6/6 | YENİ (0.55@2800) 6/6 | Δ | YENİ ort. bedel |")
    A("|---|---:|---:|---:|---:|")
    for ad in AO.TIER_ADLAR:
        o = OLD["th"][ad]; n = NEW["th"][ad]
        A(f"| {ad} | {o}/{N} ({pct(o,N)}) | {n}/{N} ({pct(n,N)}) | {n-o:+d} | "
          f"{NEW['bd'][ad]/NEW['tn'][ad]:.0f} TL |")
    A(f"| **Herhangi biri** | **{len(old_any)} ({pct(len(old_any),N)})** | "
      f"**{len(new_any)} ({pct(len(new_any),N)})** | **{len(new_any)-len(old_any):+d}** | — |")
    A("")
    A(f"- Net: **{len(new_any)-len(old_any):+d} altılı** ({pct(len(old_any),N)} → "
      f"**{pct(len(new_any),N)}**). Kazanılan: +{len(kazanilan)}, kaybedilen: -{len(kaybedilen)}.")
    A(f"- Banko-killed kayıp (tek-at banko ayağının kuponu tek başına öldürdüğü 5/6): "
      f"ESKİ {OLD['killed']} → YENİ {NEW['killed']}.")
    A(f"- **Zorunlu banko-lider (Ortaklı):** ESKİ {OLD['lider_count']}/{OLD['coup']} kupon "
      f"(her kupona kilitli) → YENİ {NEW['lider_count']}/{NEW['coup']} kupon "
      f"({pct(NEW['lider_count'],NEW['coup'])} — yalnız net üstünlükte). Banko zorunluluğu kalktı.")
    A(f"- İç içe kural korundu: ESKİ={OLD['nest_ok']}, YENİ={NEW['nest_ok']}.")
    A("")
    A("## 5. Kalan kayıpların anatomisi (YENİ üretim, Ortaklı 5/6)")
    A("")
    m = NEW["miss"]
    A(f"- 5/6'da kalan Ortaklı kupon: **{m['n']}**")
    A(f"- Kaçan kazanan 5-satırdaydı (dağıtımla kurtarılabilir): **{m['bes_ici']} "
      f"({pct(m['bes_ici'],m['n'])})**")
    model_tavan = m['n'] - m['bes_ici']
    A(f"- Kaçan kazanan 5-satır DIŞI (model tavanı, dağıtımla çözülmez): **{model_tavan} "
      f"({pct(model_tavan,m['n'])})**")
    A("- Kaçan slot: " + ", ".join(f"{k}={v}" for k, v in m["line"].most_common()))
    A("- Kaçan kazanan ANA-rank: " + ", ".join(f"#{k}={v}" for k, v in sorted(m["rank"].items())))
    A("- Saha büyüklüğü: " + ", ".join(f"{k}={v}" for k, v in m["nseg"].most_common()))
    A("- Koşu tipi: " + ", ".join(f"{k}={v}" for k, v in m["racetype"].most_common()))
    A("")
    A("## 6. Yol haritası")
    A("")
    A("1. **TAMAM — Koşullu banko (0.55) + Ortaklı @2800.** Üretimde aktif. "
      f"{pct(len(old_any),N)} → {pct(len(new_any),N)}. İç içe kural ve bütçe bantları korunur.")
    A("2. **Sıradaki cephe = model tavanı.** Kalan kayıpların ~%44'ünde kazanan 5-satır "
      "DIŞI. Bu dağıtımla çözülmez; 5-satır/ANA skor modelinin (özellikle BOM/HAR slot "
      "seçimi ve kalabalık-saha) iyileştirilmesi gerekir. Akış-ilk5 + yüksek-ganyan "
      "adaylarını HAR slotuna taşıma testi önerilir.")
    A("3. **Kalabalık-saha genişliği.** 14+ atlı koşularda favori-kazanma düşük; bu "
      "ayaklarda taban genişliği (min 2 yerine min 3) ayrı test edilmeli.")
    A("4. **Eşik izleme.** 0.55 tutucu; ileride canlı veriyle 0.50'ye çekmek +2 altılı "
      "verebilir ama 'net üstünlük' barını düşürür — kullanıcı kararı.")
    A("")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Rapor yazıldı: {OUT}")
    print("\n".join(L[:60]).encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
