# -*- coding: utf-8 -*-
"""İçerik uçları: Aktif (Günün/Yarının) Analizler + Geçmiş Analizler.

Zaman mantığı (TR saati, UTC+3):
  - "aktif"  = bugün  VEYA (yarın ve TR saat >= 18:00). Premium+ kilitli; uygulamada
               5 satır / 6'lı sekmelerinde tarih şeridiyle gösterilir.
  - "gizli"  = yarın ama saat < 18:00 (henüz yayınlanmadı) veya daha ileri günler.
  - "gecmis" = bugünden önceki günler. Herkese (anonim dahil) açık.

Yani yarının analizleri DB'de erken üretilse de kullanıcıya ancak 18:00'de görünür;
bugünün analizleri gün dönünce (TR 00:00) otomatik geçmişe kayar.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..config import settings
from ..models import (Gun, GunHipodrom, Kosu, KosuSonuc, Altili, AltiliSonuc,
                      KosuBahis, Kullanici)
from ..serialize import gun_payload, gun_summary, gh_bahis_payload
from ..deps import current_user, has_tier

router = APIRouter(tags=["icerik"])

YAYIN_SAATI = 18  # yarının analizleri TR saat 18:00'de görünür olur


def _now_tr() -> datetime:
    """VPS UTC -> Türkiye saati (UTC+3, DST yok)."""
    return datetime.utcnow() + timedelta(hours=3)


def _siniflandir(d: date, now_tr: datetime) -> str:
    """Bir günü 'aktif' / 'yakinda' / 'gecmis' / 'gizli' olarak sınıflandırır.

    - aktif   : bugün VEYA (yarın ve saat >= 18:00). İçerik açık (VIP kilidiyle).
    - yakinda : yarın ama saat < 18:00. Tarih şeridinde GÖRÜNÜR ama içerik
                18:00'e kadar kilitli ("Analizler 18:00 itibariyle aktif olacaktır").
    - gecmis  : bugünden önce. Herkese açık.
    - gizli   : 2+ gün sonrası. Listelenmez.
    """
    today = now_tr.date()
    if d < today:
        return "gecmis"
    if d == today:
        return "aktif"
    if d == today + timedelta(days=1):
        return "aktif" if now_tr.hour >= YAYIN_SAATI else "yakinda"
    return "gizli"


@router.get("/gunler")
def gunler(
    db: Session = Depends(get_db),
    user: Kullanici | None = Depends(current_user),
    gun_from: date | None = Query(None, alias="from"),
    gun_to: date | None = Query(None, alias="to"),
):
    """Tarih şeridi listesi. Aktif günler (bugün + yayınlanmış yarın) VIP-kilitli,
    geçmiş günler açık. Gizli (henüz yayınlanmamış) günler listelenmez."""
    now_tr = _now_tr()
    today = now_tr.date()
    yarin_yayinda = now_tr.hour >= YAYIN_SAATI
    is_vip = has_tier(user, "vip")

    # Yarın "yakında" olsa bile (henüz 18:00 olmadı) tarih şeridinde görünmeli;
    # bu yüzden üst sınır her zaman yarını kapsar (içerik yine de kilitli kalır).
    upper = today + timedelta(days=1)
    if gun_to is None or gun_to > upper:
        gun_to = upper
    if gun_from is None:
        gun_from = today - timedelta(days=settings.gecmis_gun)

    q = db.query(Gun).filter(Gun.date >= gun_from, Gun.date <= gun_to)
    out = []
    for g in q.order_by(Gun.date.desc()).all():
        sinif = _siniflandir(g.date, now_tr)
        if sinif == "gizli":
            continue
        s = gun_summary(g)
        aktif = sinif == "aktif"
        yakinda = sinif == "yakinda"
        s["aktif"] = aktif
        s["yakinda"] = yakinda
        s["yayin_saati"] = YAYIN_SAATI
        s["gunun_analizi"] = aktif  # geriye uyum (eski istemciler)
        # Aktif günde premium değilse paywall; yakında günde herkese kilit (saat kilidi).
        s["kilit"] = (aktif and not is_vip) or yakinda
        out.append(s)
    return {
        "bugun_date": today.isoformat(),
        "yarin_yayinda": yarin_yayinda,
        "yayin_saati": YAYIN_SAATI,
        "tier": (user.tier if user else "standart"),
        "gunler": out,
    }


@router.get("/gun/{gun_date}")
def gun_detay(gun_date: date, db: Session = Depends(get_db),
              user: Kullanici | None = Depends(current_user)):
    """Bir günün tam analizleri. Aktif günler (bugün/yayınlanmış yarın) VIP ister;
    henüz yayınlanmamış (gizli) günler 404."""
    now_tr = _now_tr()
    sinif = _siniflandir(gun_date, now_tr)
    if sinif == "gizli":
        raise HTTPException(status_code=404, detail="Bu analiz henüz yayınlanmadı.")
    if sinif == "yakinda":
        # Yarının analizi DB'de hazır olsa da 18:00'e kadar içerik verilmez.
        raise HTTPException(status_code=403, detail={
            "mesaj": f"Analizler {YAYIN_SAATI:02d}:00 itibariyle aktif olacaktır.",
            "kilit": True, "yakinda": True, "yayin_saati": YAYIN_SAATI,
        })
    gun = db.query(Gun).filter_by(date=gun_date).one_or_none()
    if gun is None:
        raise HTTPException(status_code=404, detail="Bu güne ait analiz bulunamadı.")
    if sinif == "aktif" and not has_tier(user, "vip"):
        raise HTTPException(status_code=403, detail={
            "mesaj": "Günün/Yarının Analizleri premium üyelere açıktır.",
            "kilit": True, "gereken_tier": "vip",
        })
    _payload = gun_payload(gun)
    # surdirek_gating: bugun + non-VIP icin surdirek'i gizle
    _is_vip_user = has_tier(user, 'vip')
    _today_str = _now_tr().date().isoformat()
    if not _is_vip_user and _today_str == str(gun_date) and isinstance(_payload.get('daily_panel'), dict):
        _payload['daily_panel']['surdirek'] = None
    return _payload


@router.get("/gun/{gun_date}/bahisler")
def gun_bahisler(gun_date: date, db: Session = Depends(get_db),
                 user: Kullanici | None = Depends(current_user)):
    """Koşu Analizleri (alt-bahisler) — VIP üyelere açık. Aktif günlerde içerik
    yayın saatine ve VIP kademesine tabidir; geçmiş günler VIP'e açık."""
    now_tr = _now_tr()
    sinif = _siniflandir(gun_date, now_tr)
    if sinif == "gizli":
        raise HTTPException(status_code=404, detail="Bu analiz henüz yayınlanmadı.")
    if sinif == "yakinda":
        raise HTTPException(status_code=403, detail={
            "mesaj": f"Analizler {YAYIN_SAATI:02d}:00 itibariyle aktif olacaktır.",
            "kilit": True, "yakinda": True, "yayin_saati": YAYIN_SAATI,
        })
    if not has_tier(user, "vip"):
        raise HTTPException(status_code=403, detail={
            "mesaj": "Koşu Analizleri VIP üyelere açıktır.",
            "kilit": True, "gereken_tier": "vip",
        })
    gun = db.query(Gun).filter_by(date=gun_date).one_or_none()
    if gun is None:
        raise HTTPException(status_code=404, detail="Bu güne ait analiz bulunamadı.")
    return {
        "date": gun.date.isoformat(),
        "hipodromlar": [gh_bahis_payload(gh)
                        for gh in sorted(gun.hipodromlar, key=lambda x: x.hipodrom)],
    }


_TIER_KEYS = ["simitci", "harbi", "ortakli"]
_TIER_AD = {"simitci": "Mini 6'lı", "harbi": "Standart 6'lı",
            "ortakli": "Geniş 6'lı"}


def _yuzde(pay: int, payda: int) -> float:
    return round(100.0 * pay / payda, 1) if payda else 0.0


def _donem_istatistik(db: Session, start: date, end: date) -> dict:
    """Verilen tarih aralığında (sonuçlanmış) 5-satır + 3 kademe tutturma ve
    kâr-zarar. Kâr-zarar = kullanıcı o kademenin TÜM kuponlarını oynasaydı:
    maliyet=Σbedel, ikramiye=Σ(6/6 tutan kuponların ikramiyesi), net=ikramiye-maliyet."""
    # 5 satır (yalnız sonucu olan koşular)
    bes_top = 0
    bes_isabet = 0
    # Harbi seçim: sonucu olan tüm koşularda Rev7 compute + kazanan kontrolü
    hs_top = 0
    hs_isabet = 0
    from app.serialize import _compute_harbi_secim
    # Surdirek cache'den tarih+hip+kno → horse_no lookup (is_surdirek=True için)
    _sd_lookup: dict[tuple[str, str, int], int] = {}
    try:
        _sd_raw = json.loads(_SURDIREK_CACHE.read_text(encoding="utf-8"))
        for _it in (_sd_raw.get("bugun", []) + _sd_raw.get("gecmis", [])):
            _sd_lookup[(_it["date"], _it["hip"].upper(), int(_it["race_no"]))] = int(_it["horse_no"])
    except Exception:
        pass
    rows_bes = (db.query(Kosu, KosuSonuc, GunHipodrom, Gun)
                .join(GunHipodrom, Kosu.gh_id == GunHipodrom.id)
                .join(Gun, GunHipodrom.gun_id == Gun.id)
                .join(KosuSonuc, KosuSonuc.kosu_id == Kosu.id)
                .filter(Gun.date >= start, Gun.date <= end).all())
    for k, son, gh, gun in rows_bes:
        bes_top += 1
        if son.bes_hit:
            bes_isabet += 1
        # Harbi seçim isabet — sürdirek koşularında tek_at hesabı kullan
        ap = k.analiz_puanlari or []
        if len(ap) >= 2 and son.kazanan is not None:
            _sd_key = (gun.date.isoformat(), gh.hipodrom.upper(), k.kno)
            _sd_hno = _sd_lookup.get(_sd_key)
            hs = _compute_harbi_secim(ap, k.n_at, k.zorluk,
                                      is_surdirek=(_sd_hno is not None),
                                      surdirek_horse_no=_sd_hno)
            if hs:
                aday_nos = {a["at_no"] for a in hs.get("adaylar", [])}
                if aday_nos:
                    hs_top += 1
                    if son.kazanan in aday_nos:
                        hs_isabet += 1

    tier = {k: {"toplam": 0, "tuttu": 0, "maliyet": 0.0, "ikramiye": 0.0}
            for k in _TIER_KEYS}
    altililar = (db.query(Altili)
                 .join(GunHipodrom, Altili.gh_id == GunHipodrom.id)
                 .join(Gun, GunHipodrom.gun_id == Gun.id)
                 .filter(Gun.date >= start, Gun.date <= end).all())
    for a in altililar:
        if a.sonuc is None:
            continue
        hits = a.sonuc.tier_hits or {}
        ik = a.sonuc.ikramiye or 0.0
        bedel = {kd.key: kd.bedel for kd in a.kademeler}
        for k in _TIER_KEYS:
            if k not in bedel:
                continue
            tier[k]["toplam"] += 1
            tier[k]["maliyet"] += bedel[k]
            if hits.get(k) == 6:
                tier[k]["tuttu"] += 1
                tier[k]["ikramiye"] += ik

    tier_out = {}
    for k in _TIER_KEYS:
        t = tier[k]
        tier_out[k] = {
            "ad": _TIER_AD[k],
            "toplam": t["toplam"],
            "tuttu": t["tuttu"],
            "yuzde": _yuzde(t["tuttu"], t["toplam"]),
            "maliyet": round(t["maliyet"], 2),
            "ikramiye": round(t["ikramiye"], 2),
            "net": round(t["ikramiye"] - t["maliyet"], 2),
        }
    return {
        "bes": {"toplam": bes_top, "isabet": bes_isabet,
                "yuzde": _yuzde(bes_isabet, bes_top)},
        "harbi_secim": {"toplam": hs_top, "isabet": hs_isabet,
                         "yuzde": _yuzde(hs_isabet, hs_top)},
        "tierler": tier_out,
    }


def _surdirek_donem_istatistik(start_date, end_date) -> dict:
    """Surdirek cache'inden verilen tarih araligi icin istatistik."""
    try:
        data = json.loads(_SURDIREK_CACHE.read_text(encoding="utf-8"))
        all_items = data.get("gecmis", []) + data.get("bugun", [])
        toplam = 0
        kazandi = 0
        bucketler: dict = {}
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        for item in all_items:
            d = item.get("date", "")
            if not (start_str <= d <= end_str):
                continue
            if item.get("kazandi") is None:
                continue
            toplam += 1
            if item["kazandi"]:
                kazandi += 1
            bk = item.get("bucket", "")
            if bk not in bucketler:
                bucketler[bk] = {"toplam": 0, "kazandi": 0}
            bucketler[bk]["toplam"] += 1
            if item["kazandi"]:
                bucketler[bk]["kazandi"] += 1
        return {
            "toplam": toplam,
            "kazandi": kazandi,
            "yuzde": _yuzde(kazandi, toplam),
            "bucketler": {
                k: {**v, "yuzde": _yuzde(v["kazandi"], v["toplam"])}
                for k, v in bucketler.items()
            },
        }
    except Exception:
        return {"toplam": 0, "kazandi": 0, "yuzde": 0.0, "bucketler": {}}


@router.get("/istatistik")
def istatistik(db: Session = Depends(get_db)):
    """Haftalık ve aylık tutturma + kâr-zarar istatistikleri (herkese açık)."""
    today = _now_tr().date()
    from datetime import timedelta as _td
    hafta = _donem_istatistik(db, today - timedelta(days=7), today)
    ay = _donem_istatistik(db, today - timedelta(days=30), today)
    hafta["surdirek"] = _surdirek_donem_istatistik(today - _td(days=7), today)
    ay["surdirek"] = _surdirek_donem_istatistik(today - _td(days=30), today)
    return {"bugun": today.isoformat(), "hafta": hafta, "ay": ay}


# Bahis türü görünüm sırası + adları (serialize._BET_SIRA ile aynı)
_BAHIS_SIRA = ["PLASE", "IKILI", "SIRALI_IKILI", "PLASE_IKILI", "SIRALI_UCLU",
               "TABELA", "SIRALI_BESLI", "CIFTE", "UCLU_GANYAN", "DORTLU_GANYAN",
               "BESLI_GANYAN", "YEDILI_GANYAN", "YEDILI_PLASE"]


def _bahis_istatistik(db: Session, start: date, end: date) -> list[dict]:
    """Bahis türü bazında: kaç analiz, kaç tuttu, toplam kupon parası (misli dahil),
    toplam kazanç ve net. Yalnız sonuçlanmış (tuttu != None) bahisler sayılır."""
    agg = {c: {"toplam": 0, "tuttu": 0, "maliyet": 0.0, "kazanc": 0.0} for c in _BAHIS_SIRA}
    adlar = {}
    rows = (db.query(KosuBahis)
            .join(GunHipodrom, KosuBahis.gh_id == GunHipodrom.id)
            .join(Gun, GunHipodrom.gun_id == Gun.id)
            .filter(Gun.date >= start, Gun.date <= end,
                    KosuBahis.tuttu.isnot(None)).all())
    for b in rows:
        a = agg.get(b.tip)
        if a is None:
            continue
        adlar[b.tip] = b.ad
        a["toplam"] += 1
        a["maliyet"] += (b.kupon_bedeli or 0.0) * (b.misli or 1)
        if b.tuttu:
            a["tuttu"] += 1
            a["kazanc"] += (b.net or 0.0)
    out = []
    for c in _BAHIS_SIRA:
        a = agg[c]
        if a["toplam"] == 0:
            continue
        out.append({
            "tip": c, "ad": adlar.get(c, c),
            "toplam": a["toplam"], "tuttu": a["tuttu"],
            "yuzde": _yuzde(a["tuttu"], a["toplam"]),
            "maliyet": round(a["maliyet"], 2),
            "kazanc": round(a["kazanc"], 2),
            "net": round(a["kazanc"] - a["maliyet"], 2),
        })
    return out


@router.get("/istatistik/bahis")
def istatistik_bahis(db: Session = Depends(get_db),
                     user: Kullanici | None = Depends(current_user)):
    """Koşu Analizleri bahis türü istatistikleri (VIP). Haftalık + aylık."""
    if not has_tier(user, "vip"):
        raise HTTPException(status_code=403, detail={
            "mesaj": "Bahis istatistikleri VIP üyelere açıktır.", "gereken_tier": "vip"})
    today = _now_tr().date()
    return {
        "bugun": today.isoformat(),
        "hafta": _bahis_istatistik(db, today - timedelta(days=7), today),
        "ay": _bahis_istatistik(db, today - timedelta(days=30), today),
    }



# ── Sürdirek endpoint ──────────────────────────────────────────────────────────

_SURDIREK_CACHE = Path("/opt/harbi_ganyan_v3/data/surdirek_cache.json")


def _bos_istatistik() -> dict:
    return {"toplam": 0, "kazandi": 0, "yuzde": 0.0, "bucketler": {}}


def _canonical_bugun_surdirek(today_gun) -> list:
    """CANONICAL (Asama2): bugun surdirek listesi yayinlanmis
    daily_panel.surdirekler'den uretilir (surdirek_cache.json DEGIL).
    Flutter SurdirekItem semasini eksiksiz karsilar; degerler v3_export
    (SurdirekResult) gercek kaynagindan gelir.

    SONUC (Asama0): kazandi/ganyan READ-TIME KosuSonuc'tan hesaplanir
    (surdirek at == yarisin kazanani -> kazandi=True). Sonuc katmani
    tahmin icerigine YAZILMAZ (daily_panel'e dokunulmaz) -> tahmin
    content_hash/frozen degismez. Kriter: mevcut _kazandi_ganyan
    (surdirek_build_cache) ile ayni (kazanan == surdirek horse_no).
    """
    out: list = []
    dp = (getattr(today_gun, "daily_panel", None) if today_gun else None) or {}
    today_str = today_gun.date.isoformat() if today_gun and today_gun.date else ""
    # Read-time kazanan lookup: (hip, kno) -> (kazanan_at_no, ganyan)
    kazanan_map: dict = {}
    for gh in (getattr(today_gun, "hipodromlar", None) or []):
        for k in gh.kosular:
            son = getattr(k, "sonuc", None)
            if son is not None and son.kazanan is not None:
                kazanan_map[(gh.hipodrom, k.kno)] = (son.kazanan, son.ganyan)
    for it in (dp.get("surdirekler") or []):
        if not isinstance(it, dict):
            continue
        race_no = it.get("kno") if it.get("kno") is not None else it.get("race_no")
        horse_no = it.get("at_no") if it.get("at_no") is not None else it.get("horse_no")
        if race_no is None or horse_no is None:
            continue
        race_no = int(race_no)
        horse_no = int(horse_no)
        kazanan = kazanan_map.get((it.get("hip", ""), race_no))
        if kazanan is None:
            kazandi = None
            ganyan = None
        else:
            kazandi = (horse_no == kazanan[0])
            ganyan = kazanan[1] if kazandi else None
        out.append({
            "date":       today_str,
            "hip":        it.get("hip", ""),
            "race_no":    race_no,
            "horse_no":   horse_no,
            "horse_name": it.get("at") or it.get("horse_name") or "",
            "gap":        float(it.get("gap") or 0.0),
            "norm_score": float(it.get("norm_score") or 0.0),
            "win_rate":   float(it.get("win_rate") or 0.0),
            "bucket":     it.get("bucket", ""),
            "bucket_ad":  it.get("bucket_ad") or it.get("bucket", ""),
            "source":     it.get("source", "production"),
            "is_fallback": bool(it.get("is_fallback", False)),
            "kazandi":    kazandi,
            "ganyan":     ganyan,
        })
    return out


@router.get("/surdirek")
def surdirek(
    db: Session = Depends(get_db),
    user: Kullanici | None = Depends(current_user),
):
    """Son 30 gunun surdirek tahminleri. Bugun VIP, gecmis herkese acik.

    KAYNAK (Asama2):
      - bugun: CANONICAL yayinlanmis daily_panel.surdirekler (DB).
               surdirek_cache.json 'bugun' alani ARTIK KULLANILMAZ; bayat
               cache aktif gune sizamaz.
      - gecmis + istatistik: gecici enrichment olarak cache'ten alinir,
               yalnizca gecmis (bugun tarihi haric). win_rate model feature
               (horse_win_rate_past) DB'de tutulmadigindan gecmis istatistik
               su asamada cache uzerinden verilir (Asama-sonraki is).

    Tutarlilik kurali korunur: bugun surpriz radarinda cakisan kosu
    'surdirek_cakisan' alanina alinir.
    """
    today = _now_tr().date()
    today_str = today.isoformat()
    try:
        today_gun = db.query(Gun).filter(Gun.date == today).first()
    except Exception:
        today_gun = None

    # gecmis + istatistik: cache enrichment (aktif gun HARIC)
    gecmis: list = []
    istatistik: dict = _bos_istatistik()
    if _SURDIREK_CACHE.exists():
        try:
            _cache = json.loads(_SURDIREK_CACHE.read_text(encoding="utf-8"))
            gecmis = [g for g in (_cache.get("gecmis") or [])
                      if g.get("date") != today_str]
            istatistik = _cache.get("istatistik") or _bos_istatistik()
        except Exception:
            pass

    # GUN-GECISI GUVENCESI: cache builder o gunu ertesi sabah (07:30 cron)
    # kadar 'bugun' tutar; gece/erken sabah penceresinde DUN gecmis'te
    # gorunmez. Cache.gecmis'te olmayan (bugun HARIC) DB canonical gunleri
    # read-time ekle. Boylece cache gecikmesi kullaniciyi etkilemez.
    try:
        _cache_gecmis_tarih = {g.get("date") for g in gecmis}
        _eksik_gunler = (
            db.query(Gun)
            .filter(Gun.date < today, Gun.daily_panel.isnot(None))
            .order_by(Gun.date.desc())
            .limit(3)
            .all()
        )
        _ek = []
        for _g in _eksik_gunler:
            _ds = _g.date.isoformat()
            if _ds in _cache_gecmis_tarih:
                continue
            _sd = _canonical_bugun_surdirek(_g)  # tarih-agnostik: kazandi read-time
            if _sd:
                _ek.extend(_sd)
        if _ek:
            gecmis = _ek + gecmis
    except Exception:
        pass

    # bugun: CANONICAL daily_panel
    bugun_canonical = _canonical_bugun_surdirek(today_gun)

    # SONUC (Asama0): bugun TAM sonuclandiysa (kazandi != None) istatistige
    # read-time dahil et. Cache builder bugunu 'aktif' saydigi icin gecmis
    # istatistige almiyor; yaris bitince gercek kazandi ile guncelle.
    # Sadece sonuclanmis (null degil) sayilir; bugun gecmis'te olmadigindan
    # duplicate olusmaz.
    _bugun_sonuclu = [it for it in bugun_canonical if it.get("kazandi") is not None]
    if _bugun_sonuclu:
        _ist = dict(istatistik)
        _ist["toplam"] = int(_ist.get("toplam", 0)) + len(_bugun_sonuclu)
        _ist["kazandi"] = int(_ist.get("kazandi", 0)) + sum(1 for it in _bugun_sonuclu if it.get("kazandi"))
        _ist["yuzde"] = round(100.0 * _ist["kazandi"] / _ist["toplam"], 1) if _ist["toplam"] else 0.0
        istatistik = _ist

    # VIP gating: bugun sadece VIP'e acik (gecmis herkese)
    if not has_tier(user, "vip"):
        return {"bugun": [], "gecmis": gecmis, "surdirek_cakisan": [],
                "istatistik": istatistik}

    # Surpriz radar cakisma ayrimi
    surpriz_races: dict[tuple[str, int], set] = {}
    try:
        if today_gun and today_gun.surpriz_radar:
            for item in (today_gun.surpriz_radar.get("adaylar") or []):
                hip = item.get("hip", "")
                kno = item.get("kno")
                at_no = item.get("at_no")
                if hip and kno is not None and at_no is not None:
                    surpriz_races.setdefault((hip, int(kno)), set()).add(int(at_no))
    except Exception:
        pass

    aktif: list = []
    cakisan: list = []
    for item in bugun_canonical:
        key = (item.get("hip", ""), item.get("race_no"))
        if key in surpriz_races:
            item["surpriz_cakismasi"] = True
            cakisan.append(item)
        else:
            item["surpriz_cakismasi"] = False
            aktif.append(item)

    return {"bugun": aktif, "gecmis": gecmis, "surdirek_cakisan": cakisan,
            "istatistik": istatistik}
