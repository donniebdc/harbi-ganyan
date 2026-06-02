# -*- coding: utf-8 -*-
"""Admin API: kullanici, uyelik, gelir ozeti ve bildirim yonetimi."""
from __future__ import annotations
from datetime import datetime, timedelta
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin
from ..models import Bildirim, Kullanici, Uyelik
from ..security import hash_sifre

router = APIRouter(prefix="/admin/api", tags=["admin"])

TIER_PRICE_WEEKLY = {"standart": 0, "premium": 150, "vip": 250}
VALID_TIERS = set(TIER_PRICE_WEEKLY)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AdminUserCreate(BaseModel):
    email: str
    sifre: str
    tier: str = "standart"
    email_dogrulandi: bool = True
    is_admin: bool = False
    uyelik_bitis: datetime | None = None

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

    @field_validator("tier")
    @classmethod
    def _tier(cls, v: str) -> str:
        if v not in VALID_TIERS:
            raise ValueError("tier standart/premium/vip olmali.")
        return v


class AdminUserUpdate(BaseModel):
    tier: str | None = None
    aktif: bool | None = None
    email_dogrulandi: bool | None = None
    is_admin: bool | None = None
    uyelik_bitis: datetime | None = None
    uzat_gun: int | None = None

    @field_validator("tier")
    @classmethod
    def _tier(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TIERS:
            raise ValueError("tier standart/premium/vip olmali.")
        return v

    @field_validator("uzat_gun")
    @classmethod
    def _uzat(cls, v: int | None) -> int | None:
        if v is not None and (v < 0 or v > 3650):
            raise ValueError("uzat_gun 0-3650 arasinda olmali.")
        return v


class BildirimReq(BaseModel):
    baslik: str
    mesaj: str
    kullanici_id: int | None = None
    hedef_tier: str | None = None

    @field_validator("baslik")
    @classmethod
    def _baslik(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("Baslik 1-120 karakter olmali.")
        return v

    @field_validator("mesaj")
    @classmethod
    def _mesaj(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 2000:
            raise ValueError("Mesaj 1-2000 karakter olmali.")
        return v

    @field_validator("hedef_tier")
    @classmethod
    def _hedef_tier(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TIERS:
            raise ValueError("hedef_tier standart/premium/vip olmali.")
        return v


def _aktif_uyelik(user: Kullanici) -> Uyelik | None:
    now = datetime.utcnow()
    aktifler = [
        u for u in user.uyelikler
        if u.aktif and (u.bitis is None or u.bitis >= now)
    ]
    return max(aktifler, key=lambda u: u.baslangic, default=None)


def _sync_membership(db: Session, user: Kullanici, bitis: datetime | None = None) -> None:
    now = datetime.utcnow()
    for uyelik in user.uyelikler:
        if uyelik.aktif and uyelik.tier != user.tier:
            uyelik.aktif = False
    if user.tier == "standart":
        for uyelik in user.uyelikler:
            uyelik.aktif = False
        return
    current = _aktif_uyelik(user)
    if current is None or current.tier != user.tier:
        current = Uyelik(kullanici_id=user.id, tier=user.tier, kaynak="admin", aktif=True)
        db.add(current)
    if bitis is not None:
        current.bitis = bitis


def _user_payload(user: Kullanici) -> dict:
    uyelik = _aktif_uyelik(user)
    return {
        "id": user.id,
        "email": user.email,
        "tier": user.tier,
        "aktif": user.aktif,
        "is_admin": user.is_admin,
        "email_dogrulandi": user.email_dogrulandi,
        "created_at": user.created_at,
        "uyelik_bitis": uyelik.bitis if uyelik else None,
        "uyelik_kaynak": uyelik.kaynak if uyelik else None,
        "haftalik_tutar": TIER_PRICE_WEEKLY.get(user.tier, 0) if user.aktif else 0,
    }


@router.get("/ozet")
def ozet(_: Kullanici = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(Kullanici).all()
    aktif = [u for u in users if u.aktif]
    premium = [u for u in aktif if u.tier == "premium"]
    vip = [u for u in aktif if u.tier == "vip"]
    haftalik = sum(TIER_PRICE_WEEKLY.get(u.tier, 0) for u in aktif)
    return {
        "toplam_kullanici": len(users),
        "aktif_kullanici": len(aktif),
        "standart": len([u for u in aktif if u.tier == "standart"]),
        "premium": len(premium),
        "vip": len(vip),
        "haftalik_gelir_tl": haftalik,
    }


@router.get("/kullanicilar")
def kullanicilar(
    _: Kullanici = Depends(require_admin),
    db: Session = Depends(get_db),
    q: str | None = Query(None),
    tier: str | None = Query(None),
):
    query = db.query(Kullanici)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(or_(Kullanici.email.ilike(like)))
    if tier:
        if tier not in VALID_TIERS:
            raise HTTPException(status_code=400, detail="Gecersiz tier.")
        query = query.filter(Kullanici.tier == tier)
    return {"kullanicilar": [_user_payload(u) for u in query.order_by(Kullanici.id.desc()).all()]}


@router.post("/kullanicilar", status_code=201)
def kullanici_ekle(req: AdminUserCreate, _: Kullanici = Depends(require_admin),
                   db: Session = Depends(get_db)):
    if db.query(Kullanici).filter_by(email=req.email).first():
        raise HTTPException(status_code=409, detail="Bu email zaten kayitli.")
    user = Kullanici(
        email=req.email,
        sifre_hash=hash_sifre(req.sifre),
        email_dogrulandi=req.email_dogrulandi,
        tier=req.tier,
        is_admin=req.is_admin,
        aktif=True,
    )
    db.add(user)
    db.flush()
    _sync_membership(db, user, req.uyelik_bitis)
    db.commit()
    db.refresh(user)
    return _user_payload(user)


@router.patch("/kullanicilar/{user_id}")
def kullanici_guncelle(user_id: int, req: AdminUserUpdate,
                       admin: Kullanici = Depends(require_admin),
                       db: Session = Depends(get_db)):
    user = db.get(Kullanici, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    if user.id == admin.id and req.aktif is False:
        raise HTTPException(status_code=400, detail="Kendi admin hesabinizi pasife alamazsiniz.")
    if req.tier is not None:
        user.tier = req.tier
    if req.aktif is not None:
        user.aktif = req.aktif
    if req.email_dogrulandi is not None:
        user.email_dogrulandi = req.email_dogrulandi
    if req.is_admin is not None:
        user.is_admin = req.is_admin
    bitis = req.uyelik_bitis
    if req.uzat_gun is not None:
        uyelik = _aktif_uyelik(user)
        base = max(uyelik.bitis, datetime.utcnow()) if uyelik and uyelik.bitis else datetime.utcnow()
        bitis = base + timedelta(days=req.uzat_gun)
    _sync_membership(db, user, bitis)
    db.commit()
    db.refresh(user)
    return _user_payload(user)


@router.delete("/kullanicilar/{user_id}", status_code=204)
def kullanici_sil(user_id: int, admin: Kullanici = Depends(require_admin),
                  db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Kendi admin hesabinizi silemezsiniz.")
    user = db.get(Kullanici, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    db.delete(user)
    db.commit()


@router.post("/bildirimler", status_code=201)
def bildirim_gonder(req: BildirimReq, _: Kullanici = Depends(require_admin),
                    db: Session = Depends(get_db)):
    if req.kullanici_id is not None and db.get(Kullanici, req.kullanici_id) is None:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    if req.kullanici_id is None and req.hedef_tier is None:
        targets = db.query(Kullanici).filter_by(aktif=True).all()
        for user in targets:
            db.add(Bildirim(kullanici_id=user.id, baslik=req.baslik, mesaj=req.mesaj))
        adet = len(targets)
    elif req.kullanici_id is not None:
        db.add(Bildirim(kullanici_id=req.kullanici_id, baslik=req.baslik, mesaj=req.mesaj))
        adet = 1
    else:
        targets = db.query(Kullanici).filter_by(aktif=True, tier=req.hedef_tier).all()
        for user in targets:
            db.add(Bildirim(kullanici_id=user.id, baslik=req.baslik, mesaj=req.mesaj,
                            hedef_tier=req.hedef_tier))
        adet = len(targets)
    db.commit()
    return {"durum": "gonderildi", "adet": adet}
