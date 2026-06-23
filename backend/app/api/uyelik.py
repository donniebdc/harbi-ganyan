# -*- coding: utf-8 -*-
"""Google Play Billing doğrulama."""
from __future__ import annotations
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..models import Kullanici, Uyelik
from ..config import settings

router = APIRouter(prefix="/api/uyelik", tags=["uyelik"])
GECERLI_URUNLER = {"vip_haftalik", "vip_aylik"}


class DogrulaReq(BaseModel):
    purchase_token: str
    product_id: str


def _google_play_dogrula(purchase_token: str, product_id: str) -> dict | None:
    if not settings.google_play_sa:
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            settings.google_play_sa,
            scopes=["https://www.googleapis.com/auth/androidpublisher"],
        )
        service = build("androidpublisher", "v3", credentials=creds, cache_discovery=False)
        return (
            service.purchases().subscriptions().get(
                packageName=settings.google_play_package,
                subscriptionId=product_id,
                token=purchase_token,
            ).execute()
        )
    except Exception:
        return None


@router.post("/dogrula")
def dogrula(
    req: DogrulaReq,
    user: Kullanici = Depends(require_user),
    db: Session = Depends(get_db),
):
    if req.product_id not in GECERLI_URUNLER:
        raise HTTPException(status_code=400, detail="Geçersiz ürün.")

    mevcut = db.query(Uyelik).filter(Uyelik.purchase_token == req.purchase_token).first()
    if mevcut and mevcut.kullanici_id != user.id:
        raise HTTPException(status_code=409, detail="Bu token zaten kullanılmış.")

    abonelik = _google_play_dogrula(req.purchase_token, req.product_id)
    if abonelik is None:
        raise HTTPException(status_code=402, detail="Satın alma doğrulanamadı.")

    if abonelik.get("paymentState", 0) not in (1, 2):
        raise HTTPException(status_code=402, detail="Ödeme tamamlanmamış.")

    expiry_ms = int(abonelik.get("expiryTimeMillis", 0))
    expires_at = datetime.utcfromtimestamp(expiry_ms / 1000) if expiry_ms else None

    if expires_at and expires_at < datetime.utcnow():
        raise HTTPException(status_code=402, detail="Abonelik süresi dolmuş.")

    if mevcut:
        mevcut.expires_at = expires_at
        mevcut.aktif = True
    else:
        db.add(Uyelik(
            kullanici_id=user.id,
            tier="vip",
            kaynak="google_play",
            purchase_token=req.purchase_token,
            google_product_id=req.product_id,
            expires_at=expires_at,
            aktif=True,
        ))

    user.tier = "vip"
    db.commit()
    return {"tier": "vip", "expires_at": expires_at.isoformat() if expires_at else None}
