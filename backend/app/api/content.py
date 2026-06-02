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
from ..models import Gun, Kullanici
from ..serialize import gun_payload, gun_summary
from ..deps import current_user, has_tier

router = APIRouter(tags=["icerik"])

YAYIN_SAATI = 18  # yarının analizleri TR saat 18:00'de görünür olur


def _now_tr() -> datetime:
    """VPS UTC -> Türkiye saati (UTC+3, DST yok)."""
    return datetime.utcnow() + timedelta(hours=3)


def _siniflandir(d: date, now_tr: datetime) -> str:
    """Bir günü 'aktif' / 'gecmis' / 'gizli' olarak sınıflandırır."""
    today = now_tr.date()
    if d < today:
        return "gecmis"
    if d == today:
        return "aktif"
    if d == today + timedelta(days=1) and now_tr.hour >= YAYIN_SAATI:
        return "aktif"
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

    upper = today + timedelta(days=1) if yarin_yayinda else today
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
        s["aktif"] = aktif
        s["gunun_analizi"] = aktif  # geriye uyum (eski istemciler)
        s["kilit"] = aktif and not premium
        out.append(s)
    return {
        "bugun_date": today.isoformat(),
        "yarin_yayinda": yarin_yayinda,
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
    gun = db.query(Gun).filter_by(date=gun_date).one_or_none()
    if gun is None:
        raise HTTPException(status_code=404, detail="Bu güne ait analiz bulunamadı.")
    if sinif == "aktif" and not has_tier(user, "premium"):
        raise HTTPException(status_code=403, detail={
            "mesaj": "Günün/Yarının Analizleri premium üyelere açıktır.",
            "kilit": True, "gereken_tier": "premium",
        })
    return gun_payload(gun)
