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

    - aktif   : bugün VEYA (yarın ve saat >= 18:00). İçerik açık (premium kilidiyle).
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
    """Tarih şeridi listesi. Aktif günler (bugün + yayınlanmış yarın) premium-kilitli,
    geçmiş günler açık. Gizli (henüz yayınlanmamış) günler listelenmez."""
    now_tr = _now_tr()
    today = now_tr.date()
    yarin_yayinda = now_tr.hour >= YAYIN_SAATI
    premium = has_tier(user, "premium")

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
        s["kilit"] = (aktif and not premium) or yakinda
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
    """Bir günün tam analizleri. Aktif günler (bugün/yayınlanmış yarın) premium+ ister;
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
    if sinif == "aktif" and not has_tier(user, "premium"):
        raise HTTPException(status_code=403, detail={
            "mesaj": "Günün/Yarının Analizleri premium üyelere açıktır.",
            "kilit": True, "gereken_tier": "premium",
        })
    return gun_payload(gun)


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
_TIER_AD = {"simitci": "Simitçi 6'lısı", "harbi": "Harbi Ganyan 6'lısı",
            "ortakli": "Ortak Bonkör 6'lı"}


def _yuzde(pay: int, payda: int) -> float:
    return round(100.0 * pay / payda, 1) if payda else 0.0


def _donem_istatistik(db: Session, start: date, end: date) -> dict:
    """Verilen tarih aralığında (sonuçlanmış) 5-satır + 3 kademe tutturma ve
    kâr-zarar. Kâr-zarar = kullanıcı o kademenin TÜM kuponlarını oynasaydı:
    maliyet=Σbedel, ikramiye=Σ(6/6 tutan kuponların ikramiyesi), net=ikramiye-maliyet."""
    # 5 satır (yalnız sonucu olan koşular)
    bes_top = 0
    bes_isabet = 0
    for _, son in (db.query(Kosu, KosuSonuc)
                   .join(GunHipodrom, Kosu.gh_id == GunHipodrom.id)
                   .join(Gun, GunHipodrom.gun_id == Gun.id)
                   .join(KosuSonuc, KosuSonuc.kosu_id == Kosu.id)
                   .filter(Gun.date >= start, Gun.date <= end)):
        bes_top += 1
        if son.bes_hit:
            bes_isabet += 1

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
        "tierler": tier_out,
    }


@router.get("/istatistik")
def istatistik(db: Session = Depends(get_db)):
    """Haftalık ve aylık tutturma + kâr-zarar istatistikleri (herkese açık)."""
    today = _now_tr().date()
    hafta = _donem_istatistik(db, today - timedelta(days=7), today)
    ay = _donem_istatistik(db, today - timedelta(days=30), today)
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
