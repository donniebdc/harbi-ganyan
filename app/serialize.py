# -*- coding: utf-8 -*-
"""ORM nesnelerini API/export ile AYNI JSON sekline cevirir (tek tutarli sema).

Sprint 1.3 rev3 — Tutarlilik Kurallari:
  1. Surdirek kosusu + surpriz radar atı cakisirsa → o kosu surdirek sayilmaz
     (harbi secim normal cok-at secimini doner).
  2. Surpriz radar atı bulundugu kosunun harbi secim listesinde yoksa eklenir.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from .models import Gun, GunHipodrom, Kosu, Altili, KosuBahis

_TIER_ORDER = {"simitci": 0, "harbi": 1, "ortakli": 2}

_BET_SIRA = ["PLASE", "IKILI", "SIRALI_IKILI", "PLASE_IKILI", "SIRALI_UCLU",
             "TABELA", "SIRALI_BESLI", "CIFTE", "UCLU_GANYAN", "DORTLU_GANYAN",
             "BESLI_GANYAN", "YEDILI_GANYAN", "YEDILI_PLASE"]
_BET_SIRA_INDEX = {c: i for i, c in enumerate(_BET_SIRA)}

_SURDIREK_CACHE = Path("/opt/harbi_ganyan_v3/data/surdirek_cache.json")


def _surdirek_map_for_date(tarih: str) -> dict[tuple[str, int], int]:
    """Belirtilen tarih icin surdirek secimlerini {(hip, kno): horse_no} doner.
    Hem bugun hem gecmis listesini kontrol eder — gecmis ekranda surdirek gosterilir.
    """
    try:
        data = json.loads(_SURDIREK_CACHE.read_text(encoding="utf-8"))
        result: dict[tuple[str, int], int] = {}
        for item in (data.get("bugun", []) + data.get("gecmis", [])):
            if item.get("date") == tarih:
                hip      = item.get("hip", "")
                race_no  = item.get("race_no")
                horse_no = item.get("horse_no")
                if hip and race_no is not None and horse_no is not None:
                    result[(hip, int(race_no))] = int(horse_no)
        return result
    except Exception:
        return {}


def _bugun_surdirek_map(tarih: str) -> dict[tuple[str, int], int]:
    """Geriye donuk uyumluluk — _surdirek_map_for_date kullanilmali."""
    return _surdirek_map_for_date(tarih)


def _surdirek_map_from_daily_panel(daily_panel) -> dict[tuple[str, int], int]:
    """CANONICAL: yayinlanmis daily_panel.surdirekler -> {(hip, kno): at_no}.

    Aktif gun icin tek source-of-truth budur (Asama2). Boylece Detaylar
    (daily_panel.surdirekler), /surdirek ve Harbi Secim is_surdirek AYNI
    tarih+sehir+kosu+at kaydini gosterir; bayat surdirek_cache.json aktif
    gunun Harbi Secim'ini ETKILEMEZ.
    """
    result: dict[tuple[str, int], int] = {}
    if not isinstance(daily_panel, dict):
        return result
    for item in (daily_panel.get("surdirekler") or []):
        if not isinstance(item, dict):
            continue
        hip = item.get("hip", "")
        kno = item.get("kno") if item.get("kno") is not None else item.get("race_no")
        at_no = item.get("at_no") if item.get("at_no") is not None else item.get("horse_no")
        if hip and kno is not None and at_no is not None:
            result[(str(hip), int(kno))] = int(at_no)
    return result


def _build_surpriz_map(surpriz_radar) -> dict[tuple[str, int], list[int]]:
    """surpriz_radar verisini {(hip, kno): [at_no...]} haritasina cevir."""
    if not isinstance(surpriz_radar, dict):
        return {}
    result: dict[tuple[str, int], list[int]] = {}
    for item in surpriz_radar.get("adaylar") or []:
        hip    = item.get("hip", "")
        kno    = item.get("kno")
        at_no  = item.get("at_no")
        if hip and kno is not None and at_no is not None:
            key = (hip, int(kno))
            result.setdefault(key, []).append(int(at_no))
    return result


def _compute_harbi_secim(
    analiz_puanlari: list,
    n_at: Optional[int],
    zorluk: Optional[dict],
    is_surdirek: bool = False,
    surdirek_horse_no: Optional[int] = None,
    force_include_nos: Optional[list] = None,
) -> Optional[dict]:
    try:
        import sys as _sys
        _v3 = "/opt/harbi_ganyan_v3/src"
        if _v3 not in _sys.path:
            _sys.path.insert(0, _v3)
        from harbi_v3.harbi_secim import compute
        zk = (zorluk or {}).get("zorluk_kodu") if zorluk else None
        return compute(
            analiz_puanlari or [],
            n_at=n_at or 0,
            zorluk_kodu=zk,
            is_surdirek=is_surdirek,
            surdirek_horse_no=surdirek_horse_no,
            force_include_nos=force_include_nos,
        )
    except Exception:
        return None


def kosu_payload(
    k: Kosu,
    is_surdirek: bool = False,
    surdirek_horse_no: Optional[int] = None,
    force_include_nos: Optional[list] = None,
) -> dict:
    ap = getattr(k, "analiz_puanlari", None) or []
    zorluk = getattr(k, "zorluk", None)
    # PUBLISH-TIME (Asama3B): saklanmis Kosu.harbi_secim varsa onu oku;
    # request-time compute CALISTIRILMAZ. Sadece eski (legacy) kayitlarda
    # harbi_secim None ise ayni ortak modulle kontrollu fallback.
    _stored = getattr(k, "harbi_secim", None)
    if isinstance(_stored, dict) and _stored:
        # API semasi korunur: publish meta (_publish) response'a girmez.
        harbi_secim = {kk: vv for kk, vv in _stored.items() if kk != "_publish"}
    else:
        harbi_secim = _compute_harbi_secim(
            ap, k.n_at, zorluk, is_surdirek, surdirek_horse_no, force_include_nos
        )
    return {
        "kno": k.kno, "pist": k.pist, "mesafe": k.mesafe, "saat": k.saat,
        "n_at": k.n_at, "race_type": k.race_type, "race_subtype": k.race_subtype,
        "ktip": getattr(k, "ktip", "") or "",
        "guven": getattr(k, "guven", "") or "",
        "harbi_secim": harbi_secim,
        "bes": [{"slot": b.slot, "at_no": b.at_no, "at": b.at, "ana": b.ana,
                 "jokey": getattr(b, "jokey", "") or "",
                 "apranti": bool(getattr(b, "apranti", False)),
                 "eku_partner_nos": getattr(b, "eku_partner_nos", None) or []} for b in k.bes],
        "sonuc": ({"kazanan": k.sonuc.kazanan, "kazanan_ad": k.sonuc.kazanan_ad,
                   "ganyan": k.sonuc.ganyan, "bes_hit": k.sonuc.bes_hit}
                  if k.sonuc else None),
        "analiz_puanlari": ap,
        "zorluk":            zorluk,
        "agf_radar":         getattr(k, "agf_radar", None),
        "aciklama_kartlari": getattr(k, "aciklama_kartlari", None) or [],
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


def _bahis_kazanan(raw) -> tuple:
    if isinstance(raw, dict):
        return (raw.get("kombo") or []), (raw.get("adlar") or {})
    if isinstance(raw, list):
        return raw, {}
    return [], {}


def bahis_payload(b: KosuBahis) -> dict:
    kombo, adlar = _bahis_kazanan(b.kazanan)
    return {
        "tip": b.tip, "ad": b.ad, "aile": b.aile, "bas_kosu": b.bas_kosu,
        "legs": b.legs, "kolonlar": b.kolonlar, "secim_atlar": b.secim_atlar,
        "kombinasyon": b.kombinasyon, "birim": b.birim, "kupon_bedeli": b.kupon_bedeli,
        "misli": b.misli, "max_butce": b.max_butce,
        "sonuc": ({"tuttu": b.tuttu, "ikramiye": b.ganyan, "net": b.net,
                   "kazanan": kombo, "adlar": adlar} if b.tuttu is not None else None),
    }


def gh_payload(
    gh: GunHipodrom,
    surdirek_map: dict,
    surpriz_map: dict,
) -> dict:
    """GunHipodrom → JSON payload.

    surdirek_map:  {(hip, kno): horse_no}   — surdirek atamalari
    surpriz_map:   {(hip, kno): [at_no...]} — surpriz radar atamalari

    Tutarlilik kurali:
      - Bir kos hem surdirek_map hem surpriz_map'te varsa is_surdirek=False yapilir
        (surpriz at gelebilecegi dusunulen bir kosuda tek at onerilmez).
      - surpriz_map'teki at numaralari ilgili kosunun force_include_nos listesine girer.
    """
    bahisler_sirali = sorted(gh.bahisler, key=lambda b: (b.bas_kosu, _BET_SIRA_INDEX.get(b.tip, 99)))
    hip = gh.hipodrom
    return {
        "hipodrom": hip, "birim": gh.birim,
        "kosular": [
            _kosu_with_context(k, hip, surdirek_map, surpriz_map)
            for k in sorted(gh.kosular, key=lambda x: x.kno)
        ],
        "altililar": [altili_payload(a) for a in sorted(gh.altililar, key=lambda x: x.idx)],
        "bahisler": [bahis_payload(b) for b in bahisler_sirali],
    }


def _kosu_with_context(k: Kosu, hip: str, surdirek_map: dict, surpriz_map: dict) -> dict:
    key = (hip, k.kno)
    surpriz_nos = surpriz_map.get(key, [])

    # Surdirek garantisi: cakisma kuralı kaldirildi — surdirek her zaman aktif.
    # harbi_secim.compute'daki step-1 mutlak tek_at dondurur (force_nos bagimsiz).
    is_surdirek  = key in surdirek_map
    surdirek_hno = surdirek_map.get(key) if is_surdirek else None

    # Surpriz atlari force_include ile gonder (surdirek ile birlikte calismaz ama
    # paylodda surpriz_radar alani zaten ayri gosteriliyor)
    force_nos = surpriz_nos if surpriz_nos else None

    return kosu_payload(k, is_surdirek=is_surdirek,
                        surdirek_horse_no=surdirek_hno,
                        force_include_nos=force_nos)


def gh_bahis_payload(gh: GunHipodrom) -> dict:
    bahisler = sorted(gh.bahisler, key=lambda b: (b.bas_kosu, _BET_SIRA_INDEX.get(b.tip, 99)))
    return {"hipodrom": gh.hipodrom, "bahisler": [bahis_payload(b) for b in bahisler]}


def _enrich_one_cikanlar(gun: Gun, dp: dict) -> dict:
    """READ-TIME (Asama3A): canonical daily_panel.surdirekler kosularini
    daily_panel.one_cikanlar'a ekle (yoksa).

    Neden: Detaylar 'Gunun Surdirekleri' ve Harbi Panel, one_cikanlar
    listesinden beslenir; ancak one_cikanlar guven=='surdirekt'/'yuksek_guvenli'
    ile secilir ve v54 fallback surdirekleri (or. gap yuksek ama guven farkli)
    disarida birakir. Bu yuzden /surdirek'te gorunen sehir Detaylar'da bos
    kalabiliyordu. Read-time enjeksiyon ile DB degismeden (kopya uzerinde)
    tum tarihlerde tutarlilik saglanir; Flutter degisikligi gerekmez.
    """
    surdirekler = (dp or {}).get("surdirekler") or []
    if not surdirekler:
        return dp
    one_cikanlar = list((dp or {}).get("one_cikanlar") or [])
    mevcut = {(o.get("hip"), o.get("kno")) for o in one_cikanlar}
    kosu_lookup = {}
    for gh in gun.hipodromlar:
        for k in gh.kosular:
            kosu_lookup[(gh.hipodrom, k.kno)] = k
    eklendi = False
    for sd in surdirekler:
        hip = sd.get("hip")
        kno = sd.get("kno") if sd.get("kno") is not None else sd.get("race_no")
        if hip is None or kno is None:
            continue
        kno = int(kno)
        if (hip, kno) in mevcut:
            continue
        k = kosu_lookup.get((hip, kno))
        zor = getattr(k, "zorluk", None) if k else None
        zk = zor.get("zorluk_kodu") if isinstance(zor, dict) else None
        zp = zor.get("zorluk_puani", 0.0) if isinstance(zor, dict) else 0.0
        one_cikanlar.append({
            "hip": hip,
            "kno": kno,
            "race_type": (getattr(k, "race_type", "") or "") if k else "",
            "n_at": getattr(k, "n_at", None) if k else None,
            "guven": (getattr(k, "guven", "") or "") if k else "",
            "zorluk_kodu": zk,
            "zorluk_puani": zp,
            "norm_score_gap": float(sd.get("gap") or 0.0),
            "agf_model_uyum": None,
        })
        eklendi = True
    if not eklendi:
        return dp
    yeni = dict(dp)
    yeni["one_cikanlar"] = one_cikanlar
    return yeni


def gun_payload(gun: Gun) -> dict:
    dp    = getattr(gun, "daily_panel", None) or {}
    tarih = gun.date.isoformat() if gun.date else ""

    # CANONICAL (Asama2): once yayinlanmis daily_panel.surdirekler; yoksa
    # (eski gunler) geriye donuk uyumluluk icin legacy cache fallback.
    surdirek_map = _surdirek_map_from_daily_panel(dp)
    if not surdirek_map:
        surdirek_map = _surdirek_map_for_date(tarih)
    surpriz_map  = _build_surpriz_map(getattr(gun, "surpriz_radar", None))

    # Asama3A: canonical surdirekleri one_cikanlar'a read-time enjekte et
    dp_out = _enrich_one_cikanlar(gun, dp)

    return {
        "date": tarih,
        "premium_schema_version": "sprint13_v3",
        "daily_panel": dp_out if dp_out else None,
        "son_analiz": gun.son_analiz.isoformat() if gun.son_analiz else None,
        "son_analiz_sebep": gun.son_analiz_sebep,
        "tahmin_asamasi": getattr(gun, "tahmin_asamasi", "on_tahmin") or "on_tahmin",
        "surpriz_radar": getattr(gun, "surpriz_radar", None),
        "hipodromlar": [
            gh_payload(gh, surdirek_map, surpriz_map)
            for gh in sorted(gun.hipodromlar, key=lambda x: x.hipodrom)
        ],
    }


def gun_summary(gun: Gun) -> dict:
    hips = []
    sonuclandi = True
    for gh in sorted(gun.hipodromlar, key=lambda x: x.hipodrom):
        n_alt_sonuc = sum(1 for a in gh.altililar if a.sonuc is not None)
        if n_alt_sonuc < len(gh.altililar):
            sonuclandi = False
        hips.append({"hipodrom": gh.hipodrom, "n_kosu": len(gh.kosular),
                     "n_altili": len(gh.altililar), "n_altili_sonuc": n_alt_sonuc})
    return {"date": gun.date.isoformat(), "hipodromlar": hips, "sonuclandi": sonuclandi}
