# -*- coding: utf-8 -*-
"""Kimlik dogrulama, kullanici profili ve uygulama ici bildirimler."""
from __future__ import annotations
import re
from collections import defaultdict, deque
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Bildirim, DeviceToken, DogrulamaKodu, Kullanici, UserDevice
from ..security import dogrula_sifre, hash_sifre, jwt_olustur, jwt_coz, kod_uret
from ..mail import kod_gonder
from ..deps import require_user
from ..uyelik_servis import erisim_coz
from ..telegram_notify import notify_new_user

router = APIRouter(prefix="/auth", tags=["auth"])
KOD_GECERLILIK_DK = 15
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RATE_WINDOW_SEC = 15 * 60
_RATE_LIMITS = {
    "kayit": 5,
    "dogrula": 8,
    "giris": 10,
}
_attempts: dict[tuple[str, str], deque[datetime]] = defaultdict(deque)
MAX_AKTIF_CIHAZ = 2


def _rate_limit(action: str, email: str, now: datetime | None = None) -> None:
    now = now or datetime.utcnow()
    key = (action, email.strip().lower())
    attempts = _attempts[key]
    cutoff = now - timedelta(seconds=_RATE_WINDOW_SEC)
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    if len(attempts) >= _RATE_LIMITS[action]:
        raise HTTPException(status_code=429, detail="Cok fazla deneme. Lutfen sonra tekrar deneyin.")
    attempts.append(now)


def _cihaz_kaydet(db: Session, user_id: int, cihaz_id: str | None,
                  platform: str = "android", app_version: str | None = None) -> None:
    """Cihazı kaydet/güncelle. Aktif cihaz sayısı MAX_AKTIF_CIHAZ'ı geçerse en eskiyi revoke et."""
    if not cihaz_id:
        return
    now = datetime.utcnow()
    mevcut = (
        db.query(UserDevice)
        .filter_by(user_id=user_id, device_id=cihaz_id)
        .first()
    )
    if mevcut:
        mevcut.is_active = True
        mevcut.revoked_at = None
        mevcut.revoke_reason = None
        mevcut.last_seen_at = now
        mevcut.app_version = app_version or mevcut.app_version
        mevcut.platform = platform
    else:
        # Yeni cihaz: limit kontrolü
        aktif_cihazlar = (
            db.query(UserDevice)
            .filter_by(user_id=user_id, is_active=True)
            .order_by(UserDevice.last_seen_at.asc())
            .all()
        )
        if len(aktif_cihazlar) >= MAX_AKTIF_CIHAZ:
            # En eski cihazı revoke et
            eski = aktif_cihazlar[0]
            eski.is_active = False
            eski.revoked_at = now
            eski.revoke_reason = "max_device_limit"
        db.add(UserDevice(
            user_id=user_id,
            device_id=cihaz_id,
            platform=platform,
            app_version=app_version,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
        ))


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
    cihaz_id: str | None = None
    app_version: str | None = None


class GirisReq(BaseModel):
    email: str
    sifre: str
    cihaz_id: str | None = None
    device_name: str | None = None
    app_version: str | None = None


class YukseltReq(BaseModel):
    tier: str


class YenileReq(BaseModel):
    refresh_token: str


class BenResponse(BaseModel):
    # Mevcut alanlar — Android istemci uyumu (kırılmaz)
    id: int
    email: str
    tier: str
    vip_until: str | None
    email_dogrulandi: bool
    is_admin: bool
    # Panel entegrasyonu için eklenen alanlar (Faz X2A)
    rol: str
    is_editor: bool
    is_vip: bool
    aktif: bool


def _kod_olustur_gonder(db: Session, email: str) -> None:
    kod = kod_uret()
    db.add(DogrulamaKodu(
        email=email,
        kod=kod,
        son_gecerlilik=datetime.utcnow() + timedelta(minutes=KOD_GECERLILIK_DK),
    ))
    db.commit()
    kod_gonder(email, kod)


def _token_pair(user_id: int, tier: str) -> dict:
    """Access token + refresh token (aynı JWT, 90 gün) döndür."""
    token = jwt_olustur(user_id, tier)
    return {"token": token, "refresh_token": token, "tier": tier}


@router.post("/kayit")
def kayit(req: KayitReq, db: Session = Depends(get_db)):
    _rate_limit("kayit", req.email)
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
    _rate_limit("dogrula", email)
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
    _cihaz_kaydet(db, u.id, req.cihaz_id, app_version=req.app_version)
    db.commit()
    notify_new_user(u.id)
    return _token_pair(u.id, u.tier)


@router.post("/giris")
def giris(req: GirisReq, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    _rate_limit("giris", email)
    u = db.query(Kullanici).filter_by(email=email).one_or_none()
    if not u or not dogrula_sifre(req.sifre, u.sifre_hash):
        raise HTTPException(status_code=401, detail="Email veya sifre hatali.")
    if not u.email_dogrulandi:
        raise HTTPException(status_code=403, detail="Email dogrulanmamis.")
    if not u.aktif:
        raise HTTPException(status_code=403, detail="Hesap pasif.")
    _cihaz_kaydet(db, u.id, req.cihaz_id, app_version=req.app_version)
    db.commit()
    return _token_pair(u.id, u.tier)


@router.post("/yenile")
def yenile(req: YenileReq, db: Session = Depends(get_db)):
    """Refresh token ile yeni access token al. Tier DB'den güncellenir."""
    payload = jwt_coz(req.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Gecersiz refresh token.")
    try:
        user = db.get(Kullanici, int(payload["sub"]))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Gecersiz token.")
    if not user or not user.aktif:
        raise HTTPException(status_code=401, detail="Kullanici bulunamadi.")
    return _token_pair(user.id, user.tier)


@router.get("/ben", response_model=BenResponse)
def ben(user: Kullanici = Depends(require_user), db: Session = Depends(get_db)):
    erisim = erisim_coz(db, user)
    return BenResponse(
        id=user.id,
        email=user.email,
        tier=user.tier,
        vip_until=user.vip_until.isoformat() if user.vip_until else None,
        email_dogrulandi=user.email_dogrulandi,
        is_admin=user.is_admin,
        rol=user.rol,
        is_editor=user.rol in ("EDITOR", "ADMIN") or user.is_admin,
        is_vip=erisim.is_vip,
        aktif=user.aktif,
    )


@router.post("/cikis")
def cikis(user: Kullanici = Depends(require_user)):
    """Çıkış — server tarafında ek işlem yok (stateless JWT). Loglama amaçlı."""
    return {"durum": "cikis"}


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
            .limit(30)
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


@router.post("/bildirimler/okundu-hepsi")
def bildirimler_okundu_hepsi(user: Kullanici = Depends(require_user),
                             db: Session = Depends(get_db)):
    n = (db.query(Bildirim)
         .filter_by(kullanici_id=user.id, okundu=False)
         .update({Bildirim.okundu: True}, synchronize_session=False))
    db.commit()
    return {"durum": "okundu", "adet": n}


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
    existing = db.query(DeviceToken).filter_by(token=req.token).one_or_none()
    if existing is not None:
        existing.kullanici_id = user.id
        existing.platform = req.platform
    else:
        db.add(DeviceToken(kullanici_id=user.id, token=req.token, platform=req.platform))
    db.commit()
    return {"durum": "kaydedildi"}
