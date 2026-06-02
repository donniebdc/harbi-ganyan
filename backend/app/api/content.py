# -*- coding: utf-8 -*-
"""İçerik uçları: Günün Analizleri + Geçmiş Analizler.

Üyelik kilidi: "Günün Analizleri" (DB'deki EN GÜNCEL gün = yaklaşan yarış günü)
yalnız premium+ erişebilir. Geçmiş Analizler her kademeye (anonim dahil) açıktır.
"""
from __future__ import annotations
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..config import settings
from ..models import Gun, Kullanici
from ..serialize import gun_payload, gun_summary
from ..deps import current_user, has_tier

router = APIRouter(tags=["icerik"])


def _gunun_date(db: Session) -> date | None:
    """'Günün Analizleri' = DB'deki en güncel gün."""
    return db.query(Gun.date).order_by(Gun.date.desc()).limit(1).scalar()


@router.get("/gunler")
def gunler(
    db: Session = Depends(get_db),
    user: Kullanici | None = Depends(current_user),
    gun_from: date | None = Query(None, alias="from"),
    gun_to: date | None = Query(None, alias="to"),
):
    """Geçmiş Analizler tarih şeridi (varsayılan son N gün). En güncel gün premium-kilitli."""
    gunun = _gunun_date(db)
    premium = has_tier(user, "premium")
    if gun_to is None:
        gun_to = gunun
    if gun_from is None and gun_to is not None:
        gun_from = gun_to - timedelta(days=settings.gecmis_gun)
    q = db.query(Gun)
    if gun_from is not None:
        q = q.filter(Gun.date >= gun_from)
    if gun_to is not None:
        q = q.filter(Gun.date <= gun_to)
    out = []
    for g in q.order_by(Gun.date.desc()).all():
        s = gun_summary(g)
        s["gunun_analizi"] = (g.date == gunun)
        s["kilit"] = (g.date == gunun) and not premium
        out.append(s)
    return {"from": gun_from, "to": gun_to, "gunun_date": gunun,
            "tier": (user.tier if user else "standart"), "gunler": out}


@router.get("/gun/{gun_date}")
def gun_detay(gun_date: date, db: Session = Depends(get_db),
              user: Kullanici | None = Depends(current_user)):
    """Bir günün tam analizleri. En güncel gün (Günün Analizleri) premium+ ister."""
    gun = db.query(Gun).filter_by(date=gun_date).one_or_none()
    if gun is None:
        raise HTTPException(status_code=404, detail="Bu güne ait analiz bulunamadı.")
    if gun_date == _gunun_date(db) and not has_tier(user, "premium"):
        raise HTTPException(status_code=403, detail={
            "mesaj": "Günün Analizleri premium üyelere açıktır.",
            "kilit": True, "gereken_tier": "premium",
        })
    return gun_payload(gun)
