# -*- coding: utf-8 -*-
"""
KOŞU ANALİZLERİ — Bahis türü üretimi + grading (Güncelleme v3 / Bahis Türleri.txt).

İki aile:
  • Tek-koşu bahisleri (aynı koşunun ANA sıralamasından): PLASE, İKİLİ, SIRALI İKİLİ,
    PLASE İKİLİ, SIRALI ÜÇLÜ, TABELA, SIRALI BEŞLİ.
  • Çok-ayak bahisleri (bülten 'bu koşudan başlar' işaretiyle, ardışık koşular):
    ÇİFTE(2), ÜÇLÜ GANYAN(3), DÖRTLÜ GANYAN(4), 5'Lİ GANYAN(5), 7'Lİ GANYAN(7),
    7'Lİ PLASE(7).  (6'LI GANYAN bu modülün DIŞINDA — ayrı altılı bloğu zaten var.)

Seçim ANA skoru sıralı atlardan türetilir (tek öneri). Misli = max bütçeye sığacak
şekilde: misli = floor(max_butce / kupon_bedeli), kupon_bedeli = kombinasyon * birim.

GRADING: TJK resmi `emiParasalNeticeler_tr` -> kalemler [{tip, kombinasyon, tutar}].
Kalemdeki `kombinasyon` GERÇEKLEŞEN kazanan kombinasyondur; `tutar` resmi ödemedir.
Bizim seçimimiz o kombinasyonu kapsıyorsa bahis TUTTU; net = tutar * misli.
"""
from __future__ import annotations
import re
from math import floor

# ──────────────────────────────────────────────────────────────────────────
# Bahis türü kayıt defteri
# ──────────────────────────────────────────────────────────────────────────
# family: "tek" (tek koşu, positions) | "ayak" (çok koşu, legs)
# positions/legs: kolon sayısı
# ordered: sıra önemli mi (permütasyon) yoksa kombinasyon mu
# place: True ise ilk-2 (plase) mantığı (kazanan değil, dereceye giren)
# widths: kolon başına varsayılan at genişliği (ANA top-N), bütçeye göre kırpılır

BET = {
    # ---- Tek koşu ----
    "PLASE":        dict(ad="Plase",          birim=1.00, max_butce=200, family="tek",
                         positions=1, ordered=False, place=True,  width=1),
    "IKILI":        dict(ad="İkili",          birim=1.00, max_butce=200, family="tek",
                         positions=2, ordered=False, place=False, width=3),
    "SIRALI_IKILI": dict(ad="Sıralı İkili",   birim=1.00, max_butce=200, family="tek",
                         positions=2, ordered=True,  place=False, width=3),
    "PLASE_IKILI":  dict(ad="Plase İkili",    birim=2.00, max_butce=200, family="tek",
                         positions=2, ordered=False, place=True,  width=4, place_pool=3),
    "SIRALI_UCLU":  dict(ad="Sıralı Üçlü",    birim=2.00, max_butce=300, family="tek",
                         positions=3, ordered=True,  place=False, width=4),
    "TABELA":       dict(ad="Tabela",         birim=1.50, max_butce=300, family="tek",
                         positions=4, ordered=False, place=False, width=6),
    "SIRALI_BESLI": dict(ad="Sıralı Beşli",   birim=1.25, max_butce=300, family="tek",
                         positions=5, ordered=True,  place=False, width=5),
    # ---- Çok ayak ----
    "CIFTE":         dict(ad="Çifte",          birim=1.00, max_butce=200, family="ayak",
                          legs=2, place=False, width=2),
    "UCLU_GANYAN":   dict(ad="Üçlü Ganyan",    birim=2.00, max_butce=200, family="ayak",
                          legs=3, place=False, width=2),
    "DORTLU_GANYAN": dict(ad="Dörtlü Ganyan",  birim=1.75, max_butce=200, family="ayak",
                          legs=4, place=False, width=2),
    "BESLI_GANYAN":  dict(ad="5'li Ganyan",    birim=1.50, max_butce=300, family="ayak",
                          legs=5, place=False, width=2),
    "YEDILI_GANYAN": dict(ad="7'li Ganyan",    birim=2.00, max_butce=500, family="ayak",
                          legs=7, place=False, width=2),
    "YEDILI_PLASE":  dict(ad="7'li Plase",     birim=2.00, max_butce=300, family="ayak",
                          legs=7, place=True,  width=2),
}

# Görünüm sırası (mobil ekranda)
BET_SIRA = ["PLASE", "IKILI", "SIRALI_IKILI", "PLASE_IKILI", "SIRALI_UCLU",
            "TABELA", "SIRALI_BESLI", "CIFTE", "UCLU_GANYAN", "DORTLU_GANYAN",
            "BESLI_GANYAN", "YEDILI_GANYAN", "YEDILI_PLASE"]


# ──────────────────────────────────────────────────────────────────────────
# Bülten 'bets' alanı -> hangi bahisler açık
# ──────────────────────────────────────────────────────────────────────────

def _fold(s: str) -> str:
    repl = str.maketrans({"ç": "C", "Ç": "C", "ğ": "G", "Ğ": "G", "ı": "I", "İ": "I",
                          "ö": "O", "Ö": "O", "ş": "S", "Ş": "S", "ü": "U", "Ü": "U",
                          "I": "I"})
    return (s or "").translate(repl).upper()

# Çok-ayak bahis kaç ayak sürer
AYAK_UZUNLUK = {"CIFTE": 2, "UCLU_GANYAN": 3, "DORTLU_GANYAN": 4,
                "BESLI_GANYAN": 5, "YEDILI_GANYAN": 7, "YEDILI_PLASE": 7}


def _token_kodu_tek(tok_f: str) -> str | None:
    """Tek-koşu bahis token'ını (folded) koda çevirir. Yoksa None."""
    t = tok_f.strip()
    if "PLASE IKILI" in t:
        return "PLASE_IKILI"
    if "SIRALI IKILI" in t:
        return "SIRALI_IKILI"
    if "UCLU BAHIS" in t or "SIRALI UCLU" in t:
        return "SIRALI_UCLU"
    if "SIRALI 5" in t or "SIRALI BESLI" in t:
        return "SIRALI_BESLI"
    if "TABELA" in t:                 # "TABELA BAHIS" / "TABELA BAHIS SIRASIZ" -> tek kart
        return "TABELA"
    if t == "IKILI":
        return "IKILI"
    if t == "PLASE":
        return "PLASE"
    return None                        # GANYAN (düz) ve çok-ayak token'ları burada None


def _token_kodu_ayak(tok_f: str) -> str | None:
    """Çok-ayak bahis token'ını (folded) koda çevirir. 6'lı ve düz ganyan -> None."""
    t = tok_f.strip()
    if re.search(r"\bCIFTE\b", t):
        return "CIFTE"
    if re.search(r"7'?L[IU]\s*PLASE", t):
        return "YEDILI_PLASE"
    m = re.search(r"(\d)'?L[IU]\s*GANYAN", t)
    if m:
        return {"3": "UCLU_GANYAN", "4": "DORTLU_GANYAN", "5": "BESLI_GANYAN",
                "7": "YEDILI_GANYAN"}.get(m.group(1))   # 6 -> None (altılı hariç)
    return None


def _tokens(bets_str: str) -> list[str]:
    return [_fold(t) for t in (bets_str or "").split(",") if t.strip()]


def tek_kosu_bahisleri(bets_str: str) -> list[str]:
    """Bir koşunun bülten 'bets' metninden açık olan TEK-koşu bahis kodları."""
    found = set()
    for t in _tokens(bets_str):
        c = _token_kodu_tek(t)
        if c:
            found.add(c)
    return [c for c in BET_SIRA if c in found]


def ayak_baslangic(bets_str: str) -> set[str]:
    """Bu koşuda BAŞLAYAN çok-ayak bahis kodları (bülten bunları yalnız
    başlangıç koşusunda listeler). 6'LI GANYAN hariç tutulur."""
    found = set()
    for t in _tokens(bets_str):
        c = _token_kodu_ayak(t)
        if c:
            found.add(c)
    return found


# ──────────────────────────────────────────────────────────────────────────
# Kombinasyon / misli
# ──────────────────────────────────────────────────────────────────────────

def _perm(n: int, k: int) -> int:
    r = 1
    for i in range(k):
        r *= (n - i)
    return max(r, 0)

def _comb(n: int, k: int) -> int:
    if k > n or k < 0:
        return 0
    num = _perm(n, k)
    den = 1
    for i in range(1, k + 1):
        den *= i
    return num // den


def _tek_kombinasyon(spec: dict, n_sec: int) -> int:
    """Tek-koşu bahsinde seçilen at sayısına göre kombinasyon."""
    p = spec["positions"]
    if spec.get("place") and p == 1:        # PLASE: tek kolon, at sayısı kadar
        return n_sec
    if spec.get("place") and p == 2:        # PLASE İKİLİ: sırasız ikili
        return _comb(n_sec, 2)
    if spec["ordered"]:
        return _perm(n_sec, p)
    return _comb(n_sec, p)


def _ayak_kombinasyon(widths: list[int]) -> int:
    r = 1
    for w in widths:
        r *= w
    return r


def _misli(kombinasyon: int, birim: float, max_butce: float) -> int:
    bedel = kombinasyon * birim
    if bedel <= 0:
        return 0
    return max(1, floor(max_butce / bedel))


# ──────────────────────────────────────────────────────────────────────────
# Seçim üretimi
# ──────────────────────────────────────────────────────────────────────────

def _atlar_ozet(atlar_sirali: list[dict], nos: list[int]) -> list[dict]:
    no2 = {a["at_no"]: a for a in atlar_sirali}
    return [{"at_no": no, "at": no2.get(no, {}).get("at", "")} for no in nos]


def uret_tek(code: str, atlar_sirali: list[dict]) -> dict | None:
    """Tek-koşu bahsi için ANA sıralı atlardan seçim üretir.
    atlar_sirali: [{at_no, at, ana}, ...] ANA'ya göre azalan.
    Döner: {tip, ad, kolonlar:[[no...]], secim_atlar, kombinasyon, birim, kupon_bedeli, misli}
    """
    spec = BET[code]
    nos = [a["at_no"] for a in atlar_sirali]
    if len(nos) < spec["positions"]:
        return None
    w = min(spec["width"], len(nos))
    # bütçeye sığacak şekilde gerekiyorsa genişliği kıs
    while w >= spec["positions"]:
        komb = _tek_kombinasyon(spec, w)
        if komb > 0 and komb * spec["birim"] <= spec["max_butce"]:
            break
        w -= 1
    if w < spec["positions"]:
        w = spec["positions"]
    sec_nos = nos[:w]
    komb = _tek_kombinasyon(spec, w)
    misli = _misli(komb, spec["birim"], spec["max_butce"])
    return {
        "tip": code, "ad": spec["ad"],
        "kolonlar": [sec_nos],            # tek koşu: tek havuz (görünüm)
        "secim_atlar": _atlar_ozet(atlar_sirali, sec_nos),
        "kombinasyon": komb, "birim": spec["birim"],
        "kupon_bedeli": round(komb * spec["birim"], 2),
        "misli": misli, "max_butce": spec["max_butce"],
    }


def uret_ayak(code: str, legs_atlar: list[list[dict]]) -> dict | None:
    """Çok-ayak bahsi. legs_atlar: her ayağın ANA sıralı at listesi (sırayla).
    Yüksek güvenli ayaklara (ilk sıradaki at) banko (genişlik 1), kalanlara width.
    Bütçeye göre genişlikler kısılır.
    """
    spec = BET[code]
    nlegs = spec["legs"]
    if len(legs_atlar) < nlegs:
        return None
    legs_atlar = legs_atlar[:nlegs]
    # başlangıç genişlikleri
    widths = []
    for la in legs_atlar:
        widths.append(min(spec["width"], len(la)))
    # bütçeye sığana kadar en geniş ayağı daralt
    def komb_of(ws): return _ayak_kombinasyon(ws)
    while komb_of(widths) * spec["birim"] > spec["max_butce"]:
        i = max(range(nlegs), key=lambda x: widths[x])
        if widths[i] <= 1:
            break
        widths[i] -= 1
    kolonlar = []
    kolon_atlar = []
    for la, w in zip(legs_atlar, widths):
        nos = [a["at_no"] for a in la[:w]]
        kolonlar.append(nos)
        kolon_atlar.append(_atlar_ozet(la, nos))
    komb = komb_of(widths)
    misli = _misli(komb, spec["birim"], spec["max_butce"])
    return {
        "tip": code, "ad": spec["ad"],
        "kolonlar": kolonlar,             # her ayağın seçilen at_no'ları
        "secim_atlar": kolon_atlar,       # her ayak için [{at_no,at}]
        "kombinasyon": komb, "birim": spec["birim"],
        "kupon_bedeli": round(komb * spec["birim"], 2),
        "misli": misli, "max_butce": spec["max_butce"],
    }


# ──────────────────────────────────────────────────────────────────────────
# GRADING — TJK resmi kalemler ile
# ──────────────────────────────────────────────────────────────────────────

# Kalem tip metni -> bahis kodu eşleştirme (folded ASCII upper üzerinde).
def _kalem_kodu(tip_f: str) -> str | None:
    """emiParasalNeticeler tip metnini bizim koda çevirir (folded)."""
    t = tip_f
    if re.search(r"\d'?L[IU]\s*PLASE", t):           # 7'Lİ PLASE
        return "YEDILI_PLASE"
    m = re.search(r"(\d)'?L[IU]\s*GANYAN", t)          # 3/4/5/6/7 'Lİ GANYAN
    if m:
        return {"3": "UCLU_GANYAN", "4": "DORTLU_GANYAN", "5": "BESLI_GANYAN",
                "7": "YEDILI_GANYAN"}.get(m.group(1))   # 6 -> None (altılı hariç)
    if "CIFTE" in t:
        return "CIFTE"
    if "TABELA" in t:
        # Bizim Tabela bahsimiz SIRASIZ; sıralı tabela kalemini eşleştirme
        # (aksi halde yanlış/yüksek ödeme raporlanır).
        return "TABELA" if "SIRASIZ" in t else None
    if re.search(r"SIRALI\s*5\s*L[IU]|SIRALI\s*BESLI", t):
        return "SIRALI_BESLI"
    if "PLASE IKILI" in t:
        return "PLASE_IKILI"
    if "SIRALI IKILI" in t:
        return "SIRALI_IKILI"
    if "UCLU BAHIS" in t or "SIRALI UCLU" in t:
        return "SIRALI_UCLU"
    if re.search(r"(?<!SIRALI )(?<!PLASE )IKILI", t) or t.strip() == "IKILI":
        if "IKILI" in t:
            return "IKILI"
    if t.strip() == "PLASE" or re.search(r"^PLASE\b", t):
        return "PLASE"
    if t.strip() == "GANYAN":
        return "GANYAN"
    return None


def _parse_kombo(kombo: str) -> list[list[int]]:
    """'9/2,4,5/12' -> [[9],[2,4,5],[12]] (kolon başına at_no listesi)."""
    out = []
    for col in kombo.split("/"):
        nos = []
        for x in re.split(r"[,\s]+", col.strip()):
            x = x.strip()
            if x.isdigit():
                nos.append(int(x))
        if nos:
            out.append(nos)
    return out


def kalemler_index(kalemler: list[dict]) -> dict:
    """kalemler -> {kod: [{'kombo':[[..]], 'tutar':float}, ...]}.
    PLASE/PLASE İKİLİ gibi birden çok kalemli tipler liste olarak tutulur."""
    idx: dict[str, list] = {}
    for b in (kalemler or []):
        kod = _kalem_kodu(_fold(b.get("tip", "")))
        if not kod:
            continue
        idx.setdefault(kod, []).append({
            "kombo": _parse_kombo(b.get("kombinasyon", "")),
            "tutar": b.get("tutar"),
        })
    return idx


def _kapsiyor_sirali(secim_kolon: list[int], gercek_kolonlar: list[list[int]],
                     positions: int) -> bool:
    """Sıralı tek-koşu: her pozisyon i'deki gerçek at, seçimimizde olmalı.
    (Box seçim: tüm kolonlar aynı havuz secim_kolon.)"""
    if len(gercek_kolonlar) < positions:
        return False
    for i in range(positions):
        if not any(no in secim_kolon for no in gercek_kolonlar[i]):
            return False
    return True


def _kapsiyor_sirasiz(secim_kolon: list[int], gercek_kolonlar: list[list[int]],
                      positions: int) -> bool:
    """Sırasız tek-koşu: gerçek kombinasyondaki tüm atlar seçimimizde olmalı."""
    gercek = [g[0] for g in gercek_kolonlar[:positions]] if gercek_kolonlar else []
    if len(gercek) < positions:
        # bazı sırasız kalemler tek kolonda verilebilir
        flat = [no for g in gercek_kolonlar for no in g]
        gercek = flat[:positions]
    return len(gercek) >= positions and all(no in secim_kolon for no in gercek)


def grade(bahis: dict, idx: dict) -> dict | None:
    """Bir üretilmiş bahsi resmi kalemlerle değerlendirir.
    Döner: {tuttu, ganyan, net, kazanan_kombo} | None (sonuç yok)."""
    code = bahis["tip"]
    kalem_list = idx.get(code)
    if not kalem_list:
        return None
    spec = BET[code]
    misli = bahis.get("misli", 1)
    if spec["family"] == "tek":
        secim = bahis["kolonlar"][0]
        if spec.get("place") and code == "PLASE":
            # her placing at ayrı kalem; seçtiğimiz atlardan dereceye girenler kazanır
            kazanan = 0.0
            kombos = []
            for kl in kalem_list:
                gno = kl["kombo"][0][0] if kl["kombo"] and kl["kombo"][0] else None
                if gno in secim and kl["tutar"]:
                    kazanan += kl["tutar"]
                    kombos.append(gno)
            tuttu = kazanan > 0
            return {"tuttu": tuttu, "ganyan": round(kazanan, 2) if tuttu else None,
                    "net": round(kazanan * misli, 2) if tuttu else 0.0,
                    "kazanan_kombo": kombos}
        # tek kalem (en yüksek tutarlı) — normalde tek olur
        kl = max(kalem_list, key=lambda x: x["tutar"] or 0)
        if spec["ordered"]:
            ok = _kapsiyor_sirali(secim, kl["kombo"], spec["positions"])
        else:
            ok = _kapsiyor_sirasiz(secim, kl["kombo"], spec["positions"])
        return {"tuttu": ok, "ganyan": kl["tutar"] if ok else None,
                "net": round((kl["tutar"] or 0) * misli, 2) if ok else 0.0,
                "kazanan_kombo": kl["kombo"]}
    else:
        # çok ayak: her ayakta gerçek kazanan(lar)dan biri bizim kolonda olmalı
        kl = max(kalem_list, key=lambda x: x["tutar"] or 0)
        gercek = kl["kombo"]
        kolonlar = bahis["kolonlar"]
        if len(gercek) < len(kolonlar):
            return {"tuttu": False, "ganyan": None, "net": 0.0, "kazanan_kombo": gercek}
        ok = all(any(no in kolonlar[i] for no in gercek[i]) for i in range(len(kolonlar)))
        return {"tuttu": ok, "ganyan": kl["tutar"] if ok else None,
                "net": round((kl["tutar"] or 0) * misli, 2) if ok else 0.0,
                "kazanan_kombo": gercek}
