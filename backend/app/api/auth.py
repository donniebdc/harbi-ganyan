# -*- coding: utf-8 -*-
"""Kimlik dogrulama, kullanici profili ve uygulama ici bildirimler."""
from __future__ import annotations
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Bildirim, DeviceToken, DogrulamaKodu, Kullanici
from ..security import dogrula_sifre, hash_sifre, jwt_olustur, kod_uret
from ..mail import kod_gonder
from ..deps import require_user

router = APIRouter(prefix="/auth", tags=["auth"])
KOD_GECERLILIK_DK = 15
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class KayitReq(BaseModel):
    email: str
    sifre: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Gecersiz email.")
        return v

    @field_validator("sifre")
    @classmethod
    def _sifre(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Sifre en az 10 karakter olmali.")
        return v


class DogrulaReq(BaseModel):
    email: str
    kod: str


class GirisReq(BaseModel):
    email: str
    sifre: str


class YukseltReq(BaseModel):
    tier: str


def _kod_olustur_gonder(db: Session, email: str) -> None:
    kod = kod_uret()
    db.add(DogrulamaKodu(
        email=email,
        kod=kod,
        son_gecerlilik=datetime.utcnow() + timedelta(minutes=KOD_GECERLILIK_DK),
    ))
    db.commit()
    kod_gonder(email, kod)


@router.post("/kayit")
def kayit(req: KayitReq, db: Session = Depends(get_db)):
    u = db.query(Kullanici).filter_by(email=req.email).one_or_none()
    if u and u.email_dogrulandi:
        raise HTTPException(status_code=409, detail="Bu email zaten kayitli.")
    if u is None:
        u = Kullanici(email=req.email, sifre_hash=hash_sifre(req.sifre), email_dogrulandi=False)
        db.add(u)
        db.commit()
    else:
        u.sifre_hash = hash_sifre(req.sifre)
        db.commit()
    _kod_olustur_gonder(db, req.email)
    return {"durum": "kod_gonderildi", "email": req.email}


@router.post("/dogrula")
def dogrula(req: DogrulaReq, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    rec = (db.query(DogrulamaKodu)
           .filter_by(email=email, kod=req.kod, kullanildi=False)
           .order_by(DogrulamaKodu.id.desc()).first())
    if not rec or rec.son_gecerlilik < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Kod gecersiz veya suresi dolmus.")
    u = db.query(Kullanici).filter_by(email=email).one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    rec.kullanildi = True
    u.email_dogrulandi = True
    db.commit()
    return {"token": jwt_olustur(u.id, u.tier), "tier": u.tier}


@router.post("/giris")
def giris(req: GirisReq, db: Session = Depends(get_db)):
    u = db.query(Kullanici).filter_by(email=req.email.strip().lower()).one_or_none()
    if not u or not dogrula_sifre(req.sifre, u.sifre_hash):
        raise HTTPException(status_code=401, detail="Email veya sifre hatali.")
    if not u.email_dogrulandi:
        raise HTTPException(status_code=403, detail="Email dogrulanmamis.")
    if not u.aktif:
        raise HTTPException(status_code=403, detail="Hesap pasif.")
    return {"token": jwt_olustur(u.id, u.tier), "tier": u.tier}


@router.get("/ben")
def ben(user: Kullanici = Depends(require_user)):
    return {
        "id": user.id,
        "email": user.email,
        "tier": user.tier,
        "email_dogrulandi": user.email_dogrulandi,
        "is_admin": user.is_admin,
    }


@router.post("/mock-yukselt")
def mock_yukselt(req: YukseltReq, user: Kullanici = Depends(require_user),
                 db: Session = Depends(get_db)):
    """Eski test endpoint'i. Uretimde kullanici kendi uyeligini yukseltemez."""
    raise HTTPException(status_code=410, detail="Uyelik islemleri admin panelinden yonetilir.")


@router.get("/bildirimler")
def bildirimler(user: Kullanici = Depends(require_user), db: Session = Depends(get_db)):
    rows = (db.query(Bildirim)
            .filter_by(kullanici_id=user.id)
            .order_by(Bildirim.id.desc())
            .limit(50)
            .all())
    return {"bildirimler": [{
        "id": b.id,
        "baslik": b.baslik,
        "mesaj": b.mesaj,
        "okundu": b.okundu,
        "created_at": b.created_at,
    } for b in rows]}


@router.post("/bildirimler/{bildirim_id}/okundu")
def bildirim_okundu(bildirim_id: int, user: Kullanici = Depends(require_user),
                    db: Session = Depends(get_db)):
    row = db.get(Bildirim, bildirim_id)
    if row is None or row.kullanici_id != user.id:
        raise HTTPException(status_code=404, detail="Bildirim bulunamadi.")
    row.okundu = True
    db.commit()
    return {"durum": "okundu"}


class FcmTokenReq(BaseModel):
    token: str
    platform: str = "android"

    @field_validator("token")
    @classmethod
    def _token(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 255:
            raise ValueError("Gecersiz token.")
        return v


@router.post("/fcm-token")
def fcm_token_kaydet(req: FcmTokenReq, user: Kullanici = Depends(require_user),
                     db: Session = Depends(get_db)):
    """Cihazın FCM push token'ını kaydeder/günceller (push bildirimleri için)."""
    existing = db.query(DeviceToken).filter_by(token=req.token).one_or_none()
    if existing is not None:
        existing.kullanici_id = user.id
        existing.platform = req.platform
    else:
        db.add(DeviceToken(kullanici_id=user.id, token=req.token, platform=req.platform))
    db.commit()
    return {"durum": "kaydedildi"}
