# -*- coding: utf-8 -*-
"""
ALTILI KUPON KURUCU v2 — GARANTİLİ BANKO + VERİ-TEMELLİ DAĞITIM
================================================================================
Kullanıcı direktifi:
  1) Her altılı kuponunda EN AZ 1 banko (tek at) zorunlu.
  2) Sürprize açık koşularda 5-satır ötesindeki atlar da kupona eklenebilmeli.
  3) Banko = 5'li satırda favori gördüğümüz, rakiplerini geçeceğine inandığımız at.

Çekirdek: altili_kalibrasyon.json (gerçek sonuçlarla ölçülen kapsama eğrileri)
  - fav[seg_n|seg_fark]  = favorinin gerçek kazanma oranı  -> BANKO seçimi
  - cov[seg_n][g]        = kazananın ilk-g sıralamamızda olma oranı -> ayak genişliği

Mantık:
  A) Her ayağın banko güveni hesaplanır; EN GÜÇLÜ ayak tek-at banko'ya kilitlenir.
  B) Kalan bütçe, kapsama çarpımını maksimize edecek şekilde açgözlü dağıtılır
     (Δlog(kapsama)/Δlog(genişlik) oranına göre). Sürprize açık/kalabalık ayaklar
     doğal olarak genişler, ezici favorili ayaklar dar kalır.
  C) Genişleme tavanı min(n_at, CAP); CAP=8 -> 5 satır ötesine taşabilir.
"""
import os, json, math
from altili_lib import BASE, MOTOR, birim_fiyat, ekuri_ortaklari

CAL_PATH = os.path.join(MOTOR, "altili_kalibrasyon.json")

BIRIM_TL = 1.25   # varsayılan birim (hipodrom verilmezse)
CAP = 8

# Bütçe kademeleri: (ad, alt_sınır_TL, üst_sınır_TL). Kupon değeri bu banda hedeflenir;
# açgözlü dağıtım üst sınıra (kombinasyon = üst/birim) kadar genişler.
KUPON_TIERS = [
    ("Simitçi 6'lısı",       400,  600),
    ("Harbi Ganyan 6'lısı", 1000, 1600),
    ("Ortaklı 6'lı",        1600, 2200),
]

# 5-SATIR TABANI tier politikası (220 altılı testi, kupon_fix_test_raporu.md):
#   - Simitçi (dar bütçe):  floor_only           -> +3 kupon (%13.2->%14.5)
#   - Harbi  (orta bütçe):  floor + banko disipl. -> +4 kupon (%20.5->%22.3)
#   - Ortaklı (bol bütçe):  KAPALI — greedy zaten optimuma yakın, düzeltme zarar veriyor.
TIER_POLICY = {
    "Simitçi 6'lısı":      {"bes_floor": True, "floor_flow": 3, "floor_bonus": 6.0, "banko_kac": False},
    "Harbi Ganyan 6'lısı": {"bes_floor": True, "floor_flow": 3, "floor_bonus": 6.0, "banko_kac": True},
    "Ortaklı 6'lı":        {},   # baseline (düzeltme kapalı)
}
def tier_policy(ad):
    """Tier adına göre build_coupon kwargs'ı (kopya)."""
    return dict(TIER_POLICY.get(ad, {}))

def seg_n(n):
    if n <= 7:  return "≤7"
    if n <= 9:  return "8-9"
    if n <= 11: return "10-11"
    if n <= 13: return "12-13"
    return "14+"

def seg_fark(f):
    if f >= 40: return "≥40"
    if f >= 25: return "25-40"
    if f >= 15: return "15-25"
    if f >= 8:  return "8-15"
    return "<8"

_CAL = None
def load_cal():
    global _CAL
    if _CAL is None:
        with open(CAL_PATH, encoding="utf-8") as f:
            _CAL = json.load(f)
    return _CAL

def banko_guven(n_at, fark, cal):
    """Favorinin kazanma olasılığı tahmini (shrinkage ile) — GÖSTERİM için."""
    sn = seg_n(n_at); sf = seg_fark(fark)
    w, t = cal["fav"].get(f"{sn}|{sf}", [0, 0])
    genel = 0.37  # tüm-veri favori kazanma payı (prior)
    k = 12.0
    return (w + k * genel) / (t + k)

def _fav_ekuri_partner_agf(lg):
    """Favorinin (ANA#1) eküri ortaklarının toplam AGF'si (kazanma şansı proxy'si).
    Ekürili favori, ortağı da kapsadığı için 'tek slot, iki at' avantajı taşır."""
    gruplar = lg.get("ekuri") or []
    if not gruplar: return 0.0
    fav = lg["atlar"][0]
    ortaklar = ekuri_ortaklari(fav["at_no"], gruplar)
    if not ortaklar: return 0.0
    return sum(a.get("agf", 0) for a in lg["atlar"] if a["at_no"] in ortaklar)

def banko_score(lg):
    """Banko AYAĞI SEÇİMİ için sıralama skoru.
    - fark + AGF-uyumu + akış-uyumu (212 altılı taramasında en iyi banko-isabeti)
    - Eküri bonusu: ekürili favori ortağını da kapsadığı için daha güçlü banko
    - 14+/12-13 alan cezası: kalabalık sahada favori-kazanma düşük (banko %50/%62);
      bu ayakları banko lider yapmaktan kaçın (212 altılı testi: isabet %19.3->%19.8)."""
    fav = lg["atlar"][0]
    agf1 = (fav["agf"] == max(a["agf"] for a in lg["atlar"]) and fav["agf"] > 0)
    akis1 = (fav.get("flow_rank", 0) == 1)
    ekuri_bonus = min(_fav_ekuri_partner_agf(lg) * 0.6, 20)  # ortak AGF'sine göre, sınırlı
    n = lg["n_at"]
    alan_cezasi = 25 if n >= 14 else (10 if n >= 12 else 0)
    return (min(lg["fark"], 70) + (15 if agf1 else 0) + (15 if akis1 else 0)
            + ekuri_bonus - alan_cezasi)

def banko_guven_eff(lg, cal):
    """Favorinin EFEKTİF banko güveni = kendi kazanma payı + eküri ortağının payı.
    Ortak AGF'si win-prob proxy'si olarak eklenir (kuplaj birini kapsar)."""
    base = banko_guven(lg["n_at"], lg["fark"], cal)
    p_partner = _fav_ekuri_partner_agf(lg) / 100.0
    return min(0.99, base + p_partner)

def select_with_ekuri(atlar, g, gruplar):
    """İlk-g seçim, AMA eküri ortağı zaten seçiliyse onu atla (kuplaj birini kapsar);
    böylece aynı kombinasyon maliyetiyle daha çok DİSTİNCT sonuç kapsanır."""
    if not gruplar:
        return atlar[:g]
    sel = []; sel_nos = set()
    for a in atlar:
        if len(sel) >= g: break
        if ekuri_ortaklari(a["at_no"], gruplar) & sel_nos:
            continue  # ortağı zaten yazıldı -> gereksiz
        sel.append(a); sel_nos.add(a["at_no"])
    # g'ye ulaşılamadıysa (kalanların hepsi gereksiz) kalanlarla doldur
    if len(sel) < g:
        for a in atlar:
            if len(sel) >= g: break
            if a["at_no"] not in sel_nos:
                sel.append(a); sel_nos.add(a["at_no"])
    return sel

def cov_curve(n_at, cal):
    """seg için cov[g] eğrisi (1..CAP), n_at ile sınırlı, monoton."""
    sn = seg_n(n_at)
    raw = cal["cov"].get(sn) or cal["cov"].get("8-9")
    out = []
    prev = 0.0
    for g in range(1, CAP + 1):
        if g > n_at:
            out.append(out[-1] if out else 1.0)
            continue
        v = raw.get(str(g), raw.get(g, prev))
        v = max(v, prev)          # monoton
        out.append(min(v, 0.999))
        prev = v
    return out

def _flow_kredili_surpriz(lg, floor_flow):
    """Ayağın ANA rank-4 (BOM) / rank-5 (HAR) atları içinde akış-güvenilir
    (flow_rank 1..floor_flow) olanın EN DERİN ANA-rankını döndürür, yoksa 0.
    'Akış sever ama ANA gömmüş' = bizim gerçek sürpriz sinyalimiz."""
    atl = lg["atlar"]
    derin = 0
    for r in (4, 5):           # 1-based ANA rank
        if len(atl) >= r:
            fr = atl[r - 1].get("flow_rank", 0)
            if 0 < fr <= floor_flow:
                derin = r
    return derin

def build_coupon(legs, max_komb, cal=None, force_banko=True, banko_esik=0.0,
                 bes_floor=False, floor_flow=3, floor_bonus=4.0, banko_kac=True,
                 min_width=None, fixed_banko=None):
    """legs: [ {'kno':int,'atlar':[{at_no,at,ana,agf}...] (ANA azalan),
               'n_at':int,'fark':float} ... ]  (6 ayak)
    force_banko=True -> en güçlü ayak tek-at banko'ya kilitlenir (kullanıcı direktifi).
    force_banko=False -> banko zorunlu değil (karşılaştırma için).
    bes_floor=True -> "5-satır tabanı" düzeltmesi (212 altılı analizinde 5/6'da kalan
      kuponların %57'sinde kazanan 5-satırdaydı ama dar ayak yüzünden dışarıda kalmıştı):
        (1) banko_kac: akış-güvenilir BOM/HAR'ı olan ayağı banko yapmaktan kaçın.
        (2) floor_bonus: greedy'de o ayağı, akış-güvenilir sürprizi kapsayacak şekilde
            genişletmeye öncelik ver (bütçe-nötr; max_komb tavanı korunur).
    -> (plan, toplam_komb)
    """
    cal = cal or load_cal()
    L = len(legs)
    info = []
    for lg in legs:
        n = lg["n_at"]; fark = lg["fark"]
        bsc = banko_score(lg)
        surpriz_rank = _flow_kredili_surpriz(lg, floor_flow) if bes_floor else 0
        if bes_floor and banko_kac and surpriz_rank:
            bsc -= 30   # canlı sürprizi olan ayağı banko yapma → daha temiz ayağa kaydır
        info.append({
            "lg": lg,
            "guven": banko_guven_eff(lg, cal),   # eküri ortağını kredliyor
            "bscore": bsc,
            "cov": cov_curve(n, cal),
            "maxw": min(n, CAP),
            "surpriz_rank": surpriz_rank,        # akış-güvenilir BOM/HAR'ın ANA-rankı (0=yok)
        })
    # A) en güçlü ayak = banko lider (banko_score ile seçilir).
    #    banko_esik: liderin güveni eşiğin altındaysa tek-at yerine yarı-banko (2 at)
    #    çıpası kurulur — zayıf banko'nun kuponu öldürmesini engeller (akıllı banko).
    banko_idx = (fixed_banko if fixed_banko is not None
                 else max(range(L), key=lambda i: info[i]["bscore"]))
    # min_width: bir ALT kademenin ayak genişlikleri (iç-içe/superset zorunluluğu).
    if min_width:
        width = [max(1, min(min_width[i], info[i]["maxw"])) for i in range(L)]
    else:
        width = [1] * L
    locked = set()
    lider_yari = False
    if force_banko:
        locked = {banko_idx}
        if width[banko_idx] < 2 and info[banko_idx]["guven"] < banko_esik and info[banko_idx]["maxw"] >= 2:
            width[banko_idx] = 2
        lider_yari = width[banko_idx] >= 2

    # B) açgözlü genişletme: Δlog(cov)/Δlog(width) en yüksek olana ekle
    def komb(ws):
        p = 1
        for w in ws: p *= w
        return p

    # önce banko-dışı ayakları min 2'ye çıkar (bütçe elveriyorsa) — tek-at çöküşünü engelle
    for i in range(L):
        if i in locked or width[i] >= 2: continue
        if info[i]["maxw"] >= 2 and komb([width[j] if j != i else 2 for j in range(L)]) <= max_komb:
            width[i] = 2

    # greedy
    while True:
        best = None  # (skor, i)
        for i in range(L):
            if i in locked: continue
            g = width[i]
            if g >= info[i]["maxw"]: continue
            yeni = komb([width[j] if j != i else g + 1 for j in range(L)])
            if yeni > max_komb: continue
            cov = info[i]["cov"]
            c0 = cov[g - 1]; c1 = cov[g]   # cov index 0=g1
            if c1 <= c0:
                gain = 1e-6
            else:
                gain = (math.log(c1) - math.log(c0)) / (math.log(g + 1) - math.log(g))
            # 5-satır tabanı: bu genişleme (g -> g+1) akış-güvenilir BOM/HAR'ı henüz
            # kapsamamış ayağı, o atı kapsayacak ranka taşıyorsa önceliklendir.
            if bes_floor and info[i]["surpriz_rank"] and (g + 1) <= info[i]["surpriz_rank"]:
                gain *= floor_bonus
            if best is None or gain > best[0]:
                best = (gain, i)
        if best is None:
            break
        width[best[1]] += 1

    # plan üret
    plan = []
    for i, lg in enumerate(legs):
        w = width[i]
        secilen = select_with_ekuri(lg["atlar"], w, lg.get("ekuri") or [])
        is_banko = (w == 1)
        guven = info[i]["guven"]
        is_lider = (i == banko_idx and force_banko)
        if is_lider and lider_yari:
            etiket = "🔑 ÇIPA (yarı-banko)"
        elif is_lider:
            etiket = "🔒 BANKO LİDER"
        elif is_banko:
            etiket = "🔒 banko"
        elif w >= 6:
            etiket = "🌪️ SÜRPRİZE AÇIK"
        elif w >= 4:
            etiket = "⚖️ açık"
        elif w == 3:
            etiket = "✍️ standart"
        else:
            etiket = "🎯 yarı banko"
        lg_ekuri = lg.get("ekuri") or []
        plan.append({"kno": lg["kno"], "width": w, "banko": is_banko,
                     "banko_lider": is_lider, "secilen": secilen,
                     "guven": guven, "etiket": etiket,
                     "ekuri": lg_ekuri,
                     "ekuri_isim": {a["at_no"]: a["at"] for a in lg["atlar"]
                                    if any(a["at_no"] in g for g in lg_ekuri)}})
    return plan, komb(width)

def build_tier(legs, tier, birim, cal=None, banko_esik=0.50, **kw):
    """Bir bütçe kademesi (ad, lo, hi) için kupon kurar. max_komb = hi/birim.
    Ek kwargs (bes_floor, floor_flow, floor_bonus, banko_kac) build_coupon'a geçer."""
    ad, lo, hi = tier
    max_komb = int(hi / birim)
    plan, komb = build_coupon(legs, max_komb, cal, force_banko=True,
                              banko_esik=banko_esik, **kw)
    return ad, lo, hi, plan, komb

def build_nested_tiers(legs, tiers=None, birim=BIRIM_TL, cal=None, banko_esik=0.50,
                       policies=None):
    """İÇ İÇE (SUPERSET) KADEMELER — kullanıcı direktifi (ŞABLON ÖRNEKLEM):
      Harbi ⊇ Simitçi, Ortaklı ⊇ Harbi  (her ayakta, at bazında).
    Her üst kademe alt kademenin ayak genişliklerini TABAN alır ve yalnızca genişler;
    seçim ANA-sıralı prefix olduğundan genişlik ≥ ise seçim otomatik superset olur.
    Banko ayağı ilk (en dar) kademede seçilir ve tüm kademelerde SABİT kalır.

    tiers: artan bütçeli [(ad,lo,hi)...] (varsayılan KUPON_TIERS).
    policies: {ad: build_coupon-kwargs} (varsayılan TIER_POLICY).
    -> [(ad, lo, hi, plan, komb), ...]  (format_coupon ile aynı plan yapısı)
    """
    cal = cal or load_cal()
    tiers = tiers or KUPON_TIERS
    if policies is None:
        policies = TIER_POLICY
    out = []
    prev_w = None
    banko_idx = None
    for tier in tiers:
        ad, lo, hi = tier
        max_komb = int(hi / birim)
        kw = dict(policies.get(ad, {}))
        plan, komb = build_coupon(legs, max_komb, cal, force_banko=True,
                                  banko_esik=banko_esik, min_width=prev_w,
                                  fixed_banko=banko_idx, **kw)
        if banko_idx is None:
            banko_idx = next((i for i, p in enumerate(plan) if p["banko_lider"]), None)
        prev_w = [p["width"] for p in plan]
        out.append((ad, lo, hi, plan, komb))
    return out


def _leg_ekuri_notu(p):
    """Bir ayağın eküri notu: seçili atlardan eküri olanları + otomatik kapsananı yazar.
    Döndürür: not satırı (str) ya da None."""
    gruplar = p.get("ekuri") or []
    if not gruplar:
        return None
    isim = p.get("ekuri_isim", {})
    sec_nos = {a["at_no"] for a in p["secilen"]}
    parcalar = []
    for g in gruplar:
        if not (g & sec_nos):
            continue  # bu eküri grubundan ayakta seçili at yok
        uyeler = " ⇄ ".join(f"No:{n} {isim.get(n,'')}".strip() for n in sorted(g))
        kapsanan = g - sec_nos  # yazılmayan ama otomatik kapsanan ortaklar
        if kapsanan:
            ek = ", ".join(f"No:{n} {isim.get(n,'')}".strip() for n in sorted(kapsanan))
            parcalar.append(f"{uyeler} (kuplaj — {ek} otomatik kapsanır)")
        else:
            parcalar.append(f"{uyeler} (kuplaj — biri yeter)")
    if not parcalar:
        return None
    return "      ↳ eküri: " + " | ".join(parcalar)

def _format_bedel_tl(value):
    return f"{value:.0f} TL"

def _format_leg_numbers_and_note(p):
    """Şablon satırı için seçili at numaraları ve eküri notunu tek satıra indirir."""
    selected = p["secilen"]
    gruplar = p.get("ekuri") or []
    isim = p.get("ekuri_isim", {})
    sec_nos = {a["at_no"] for a in selected}
    nos_parts = []
    notes = []
    noted_groups = set()
    for a in selected:
        no = a["at_no"]
        partners = ekuri_ortaklari(no, gruplar)
        hidden = sorted(partners - sec_nos)
        if hidden:
            nos_parts.append(f"{no}/(" + ",".join(str(x) for x in hidden) + ")")
        else:
            nos_parts.append(str(no))
        grp = next((g for g in gruplar if no in g), None)
        if grp:
            key = tuple(sorted(grp))
            if key not in noted_groups:
                noted_groups.add(key)
                members = " ⇄ ".join(f"No:{n} {isim.get(n, '')}".strip() for n in sorted(grp))
                notes.append(f"{members} eküridir")
    return "-".join(nos_parts), (" (" + " | ".join(notes) + ")" if notes else "")

def format_coupon(plan, toplam_komb, baslik="", birim=BIRIM_TL):
    out = []
    bedel = toplam_komb * birim
    out.append(f"  🎲 {baslik} {_format_bedel_tl(bedel)} 🎲")
    out.append("")
    out.append("  " + "─" * 58)
    out.append("")
    for p in plan:
        nos, ekuri_note = _format_leg_numbers_and_note(p)
        isim = ", ".join(a["at"] for a in p["secilen"])
        out.append(f"    Koşu {p['kno']:>2} {p['etiket']:<22} [{p['width']} at] {nos:<16} {isim}{ekuri_note}")
    return out
