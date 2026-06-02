# -*- coding: utf-8 -*-
"""ORM nesnelerini API/export ile AYNI JSON şekline çevirir (tek tutarlı şema)."""
from __future__ import annotations
from .models import Gun, GunHipodrom, Kosu, Altili, KosuBahis

_TIER_ORDER = {"simitci": 0, "harbi": 1, "ortakli": 2}

# Koşu Analizleri bahis görünüm sırası (bahis_uretim.BET_SIRA ile aynı)
_BET_SIRA = ["PLASE", "IKILI", "SIRALI_IKILI", "PLASE_IKILI", "SIRALI_UCLU",
             "TABELA", "SIRALI_BESLI", "CIFTE", "UCLU_GANYAN", "DORTLU_GANYAN",
             "BESLI_GANYAN", "YEDILI_GANYAN", "YEDILI_PLASE"]
_BET_SIRA_INDEX = {c: i for i, c in enumerate(_BET_SIRA)}


def kosu_payload(k: Kosu) -> dict:
    return {
        "kno": k.kno, "pist": k.pist, "mesafe": k.mesafe, "saat": k.saat,
        "n_at": k.n_at, "race_type": k.race_type, "race_subtype": k.race_subtype,
        "bes": [{"slot": b.slot, "at_no": b.at_no, "at": b.at, "ana": b.ana} for b in k.bes],
        "sonuc": ({"kazanan": k.sonuc.kazanan, "kazanan_ad": k.sonuc.kazanan_ad,
                   "ganyan": k.sonuc.ganyan, "bes_hit": k.sonuc.bes_hit}
                  if k.sonuc else None),
    }


def altili_payload(a: Altili) -> dict:
    kademeler = sorted(a.kademeler, key=lambda kd: _TIER_ORDER.get(kd.key, 9))
    return {
        "idx": a.idx, "legs": a.legs,
        "kademeler": [{
            "ad": kd.ad, "key": kd.key, "bedel": kd.bedel, "komb": kd.komb,
            "ayaklar": [{"kno": ay.kno, "width": ay.width, "banko_lider": ay.banko_lider,
                         "secilen": ay.secilen,
                         "secilen_atlar": ay.secilen_atlar or []}
                        for ay in sorted(kd.ayaklar, key=lambda x: x.kno)],
        } for kd in kademeler],
        "sonuc": ({"winners": a.sonuc.winners, "ikramiye": a.sonuc.ikramiye,
                   "tier_hits": a.sonuc.tier_hits} if a.sonuc else None),
    }


def bahis_payload(b: KosuBahis) -> dict:
    return {
        "tip": b.tip, "ad": b.ad, "aile": b.aile, "bas_kosu": b.bas_kosu,
        "legs": b.legs, "kolonlar": b.kolonlar, "secim_atlar": b.secim_atlar,
        "kombinasyon": b.kombinasyon, "birim": b.birim, "kupon_bedeli": b.kupon_bedeli,
        "misli": b.misli, "max_butce": b.max_butce,
        "sonuc": ({"tuttu": b.tuttu, "ganyan": b.ganyan, "net": b.net,
                   "kazanan": b.kazanan} if b.tuttu is not None else None),
    }


def gh_bahis_payload(gh: GunHipodrom) -> dict:
    """Koşu Analizleri (VIP): hipodromun alt-bahisleri, başlangıç koşusuna göre sıralı."""
    bahisler = sorted(gh.bahisler,
                      key=lambda b: (b.bas_kosu, _BET_SIRA_INDEX.get(b.tip, 99)))
    return {"hipodrom": gh.hipodrom, "bahisler": [bahis_payload(b) for b in bahisler]}


def gh_payload(gh: GunHipodrom) -> dict:
    return {
        "hipodrom": gh.hipodrom, "birim": gh.birim,
        "kosular": [kosu_payload(k) for k in sorted(gh.kosular, key=lambda x: x.kno)],
        "altililar": [altili_payload(a) for a in sorted(gh.altililar, key=lambda x: x.idx)],
    }


def gun_payload(gun: Gun) -> dict:
    return {
        "date": gun.date.isoformat(),
        "hipodromlar": [gh_payload(gh) for gh in sorted(gun.hipodromlar, key=lambda x: x.hipodrom)],
    }


def gun_summary(gun: Gun) -> dict:
    """Geçmiş Analizler tarih şeridi için hafif özet."""
    hips = []
    sonuclandi = True
    for gh in sorted(gun.hipodromlar, key=lambda x: x.hipodrom):
        n_alt_sonuc = sum(1 for a in gh.altililar if a.sonuc is not None)
        if n_alt_sonuc < len(gh.altililar):
            sonuclandi = False
        hips.append({"hipodrom": gh.hipodrom, "n_kosu": len(gh.kosular),
                     "n_altili": len(gh.altililar), "n_altili_sonuc": n_alt_sonuc})
    return {"date": gun.date.isoformat(), "hipodromlar": hips, "sonuclandi": sonuclandi}
