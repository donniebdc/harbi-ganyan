# -*- coding: utf-8 -*-
"""
ALTILI ÜRETİM + ÇIKTI YAZIMI — ganyan_master.py ve toplu_tahmin.py ortak kullanır.
  - altili_ayaklari(bets_by_kosu, son_kosu): bülten 'bets' alanından altılı ayaklarını çıkarır.
  - hipodrom_altili_bloku(...): bir hipodromun tüm altılıları için akıllı banko kuponlarını
    (3 bütçe kademesi, hipodrom birim fiyatlı) metin olarak üretir.
  - analiz_dosyalari_yaz(...): <date>_Tahminler.txt ve <date>_Altili.txt dosyalarını
    Harbi_Ganyan_Analiz/<date>/ altına yazar.
"""
import os, re
from altili_lib import BASE, birim_fiyat, ekuri_ortaklari
from altili_kupon_v2 import (build_tier, build_nested_tiers, format_coupon,
                             load_cal, KUPON_TIERS, tier_policy)

BANKO_ESIK = 0.50
ANALIZ_KLASOR = os.path.join(BASE, "Harbi_Ganyan_Analiz")

def _fold_bets(text):
    """Bahis metnini regex icin ASCII'ye yakin forma indirir.
    API iki farkli format dondurebiliyor:
    - "1. 6'LI GANYAN bu kosudan baslar"
    - "6'LI GANYAN, 1. CIFTE bu kosudan baslar"
    """
    repl = str.maketrans({
        "ç": "c", "Ç": "C", "ğ": "g", "Ğ": "G", "ı": "i", "I": "I",
        "İ": "I", "ö": "o", "Ö": "O", "ş": "s", "Ş": "S", "ü": "u", "Ü": "U",
    })
    return (text or "").translate(repl).upper()

RE_ALTILI_BETS_NUM = re.compile(r"(\d+)\.\s*6'?LI\s*GANYAN\s+BU\s+KOSUDAN\s+BASLAR")
RE_ALTILI_BETS_UNNUM = re.compile(r"(^|[,;]\s*)6'?LI\s*GANYAN\b.*BU\s+KOSUDAN\s+BASLAR")

def altili_ayaklari(bets_by_kosu, son_kosu):
    """{altili_no: [koşu_no...6 ayak]} — bülten 'bets' metninden."""
    altililar = {}
    for kno, bets in bets_by_kosu.items():
        if not bets:
            continue
        folded = _fold_bets(bets)
        m = RE_ALTILI_BETS_NUM.search(folded)
        if m:
            no = int(m.group(1))
            altililar[no] = [a for a in range(kno, kno + 6) if a <= son_kosu]
            continue
        if RE_ALTILI_BETS_UNNUM.search(folded):
            no = 1
            while no in altililar:
                no += 1
            altililar[no] = [a for a in range(kno, kno + 6) if a <= son_kosu]
    return altililar

def _legs_from_kosu_verileri(ayaklar, kosu_verileri):
    """Kupon kurucu formatına çevir. Eksik ayak varsa (None, eksik_listesi) döner."""
    legs = []; eksik = []
    for kno in ayaklar:
        kv = kosu_verileri.get(kno)
        if not kv or not kv.get("atlar_sirali"):
            eksik.append(kno); continue
        atlar = [{"at_no": a["at_no"], "at": a.get("raw_at", a.get("at", "")),
                  "ana": a["ana_skor"], "agf": a.get("agf", 0),
                  "flow_rank": a.get("peg_flow_rank", 0)}
                 for a in kv["atlar_sirali"]]
        legs.append({"kno": kno, "atlar": atlar,
                     "n_at": kv["n_at"], "fark": kv["fark"],
                     "ekuri": kv.get("ekuri") or []})
    return legs, eksik

def bes_satir_ekuri_notu(secimler, atlar_sirali, gruplar, no_key="at_no", isim_key="raw_at"):
    """5'li satırdaki eküri durumunu çözer.
    secimler: [at_dict, ...] (5 satır sırasıyla, None olabilir)
    -> (notlar: {at_no: 'ortak isim(ler)'}, alternatif: at_dict|None)
       alternatif = seçililerle eküri OLMAYAN, ANA sırasındaki ilk eküri-dışı at.
    """
    notlar = {}
    if not gruplar:
        return notlar, None
    secili = [s for s in secimler if s]
    secili_nos = {s[no_key] for s in secili}
    ekuri_var = False
    for s in secili:
        ortak = ekuri_ortaklari(s[no_key], gruplar) & secili_nos
        if ortak:
            ekuri_var = True
            isimler = [a.get(isim_key, a.get("at", "")) for a in atlar_sirali if a[no_key] in ortak]
            notlar[s[no_key]] = ", ".join(isimler)
    alternatif = None
    if ekuri_var:
        for a in atlar_sirali:
            if a[no_key] in secili_nos: continue
            if ekuri_ortaklari(a[no_key], gruplar) & secili_nos: continue
            alternatif = a; break
    return notlar, alternatif

def hipodrom_altili_bloku(sad, altililar, kosu_verileri, cal=None):
    """Bir hipodromun altılı kupon bölümünü metin satırları olarak döndürür."""
    cal = cal or load_cal()
    birim = birim_fiyat(sad)
    L = []
    L.append("═" * 78)
    L.append(f"🎰 {sad.upper()} — ALTILI GANYAN KUPONLARI")
    L.append("═" * 78)
    for ano in sorted(altililar):
        ayaklar = altililar[ano]
        L.append("")
        L.append(f"🎲 {ano}. ALTILI GANYAN (Koşular {ayaklar[0]}-{ayaklar[-1]}) 🎲")
        L.append("")
        L.append("═" * 78)
        legs, eksik = _legs_from_kosu_verileri(ayaklar, kosu_verileri)
        if eksik or len(legs) < 2:
            L.append(f"  ⚠️ Eksik ayak ({eksik}) — kupon kurulamadı.")
            continue
        for ad, lo, hi, plan, komb in build_nested_tiers(legs, KUPON_TIERS, birim, cal, BANKO_ESIK):
            L.append("")
            L.extend(format_coupon(plan, komb, baslik=ad, birim=birim))
            L.append("")
            L.append("═" * 78)
    return L

def analiz_dosyalari_yaz(tarih_ddmmyyyy, tahmin_satirlari, altili_satirlari):
    """Harbi_Ganyan_Analiz/<tarih>/<tarih>_Tahminler.txt ve _Altili.txt yazar.
    tarih_ddmmyyyy: 'GG-AA-YYYY' (örn. 26-05-2026). -> (tahmin_yol, altili_yol)"""
    klasor = os.path.join(ANALIZ_KLASOR, tarih_ddmmyyyy)
    os.makedirs(klasor, exist_ok=True)
    tahmin_yol = os.path.join(klasor, f"{tarih_ddmmyyyy}_Tahminler.txt")
    altili_yol = os.path.join(klasor, f"{tarih_ddmmyyyy}_Altili.txt")
    with open(tahmin_yol, "w", encoding="utf-8") as f:
        f.write("\n".join(tahmin_satirlari))
    with open(altili_yol, "w", encoding="utf-8") as f:
        f.write("\n".join(altili_satirlari))
    return tahmin_yol, altili_yol
