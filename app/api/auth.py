# -*- coding: utf-8 -*-
"""Kimlik dogrulama, kullanici profili ve uygulama ici bildirimler."""
from __future__ import annotations
import re
from collections import defaultdict, deque
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Bildirim, DeviceToken, DogrulamaKodu, Kullanici, UserDevice
from ..security import (
    dogrula_sifre, hash_sifre, jwt_olustur, jwt_coz, kod_uret,
    jwt_olustur_v2_access, refresh_token_v2_olustur,
)
from ..mail import kod_gonder
from ..deps import require_user
from ..uyelik_servis import erisim_coz
from ..telegram_notify import notify_new_user
from ..config import settings
from .. import auth_session_service as session_svc

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
    """Cihazi kaydet/guncelle. Aktif cihaz sayisi MAX_AKTIF_CIHAZ'i gecerse en eskiyi revoke et."""
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
        aktif_cihazlar = (
            db.query(UserDevice)
            .filter_by(user_id=user_id, is_active=True)
            .order_by(UserDevice.last_seen_at.asc())
            .all()
        )
        if len(aktif_cihazlar) >= MAX_AKTIF_CIHAZ:
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


def _detect_client_type(request: Request) -> str:
    """User-Agent'tan client tipini tahmin et (metadata amacli, guvenlik karari degil)."""
    ua = (request.headers.get("user-agent") or "").lower()
    if "dart" in ua or "flutter" in ua or "harbi" in ua:
        return "MOBILE"
    if "axios" in ua or "next" in ua or "panel" in ua:
        return "PANEL"
    return "UNKNOWN"


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


class CikisReq(BaseModel):
    refresh_token: str | None = None


class BenResponse(BaseModel):
    # Mevcut alanlar — Android istemci uyumu (kirilmaz)
    id: int
    email: str
    tier: str
    vip_until: str | None
    email_dogrulandi: bool
    is_admin: bool
    # Panel entegrasyonu icin eklenen alanlar (Faz X2A)
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
    """Legacy: Access token + refresh token (ayni JWT, 90 gun). V2 kapali."""
    token = jwt_olustur(user_id, tier)
    return {"token": token, "refresh_token": token, "tier": tier}


def _token_pair_v2(user_id: int, tier: str, db: Session,
                   client_type: str = "UNKNOWN",
                   device_name: str | None = None,
                   user_agent_hash: str | None = None,
                   ip_hash: str | None = None,
                   app_version: str | None = None) -> dict:
    """V2: Kisa omurlu access JWT + ayri opak refresh token + stateful session."""
    from datetime import datetime as _dt, timedelta as _td
    import uuid as _uuid

    access_token, _jti_a, _exp_a = jwt_olustur_v2_access(user_id, tier)
    raw_refresh = refresh_token_v2_olustur()
    refresh_jti = str(_uuid.uuid4())
    token_family = str(_uuid.uuid4())
    expires_at = _dt.utcnow() + _td(days=settings.refresh_token_days)

    session_svc.create_refresh_session(
        db,
        user_id=user_id,
        raw_token=raw_refresh,
        jti=refresh_jti,
        token_family_id=token_family,
        expires_at=expires_at,
        client_type=client_type,
        device_name=device_name,
        user_agent_hash=user_agent_hash,
        ip_hash=ip_hash,
        app_version=app_version,
    )
    db.commit()
    return {
        "token": access_token,
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "tier": tier,
        "token_type": "bearer",
        "expires_in": settings.access_token_minutes * 60,
        "refresh_expires_in": settings.refresh_token_days * 86400,
    }


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
def giris(req: GirisReq, request: Request, db: Session = Depends(get_db)):
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

    if settings.auth_token_v2_enabled:
        import hashlib as _hl
        client_type = _detect_client_type(request)
        raw_ip = request.client.host if request.client else ""
        ip_h = _hl.sha256(raw_ip.encode()).hexdigest() if raw_ip else None
        ua = request.headers.get("user-agent") or ""
        ua_h = _hl.sha256(ua.encode()).hexdigest() if ua else None
        return _token_pair_v2(
            u.id, u.tier, db,
            client_type=client_type,
            device_name=req.device_name,
            user_agent_hash=ua_h,
            ip_hash=ip_h,
            app_version=req.app_version,
        )
    return _token_pair(u.id, u.tier)


@router.post("/yenile")
def yenile(req: YenileReq, db: Session = Depends(get_db)):
    """Refresh token ile yeni token cifti al."""
    if not settings.auth_token_v2_enabled:
        # Legacy: JWT decode + yeni JWT (V2 kapali)
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

    # V2: Stateful rotation
    # 1. Reuse detection: revoked token mu?
    reuse_info = session_svc.detect_and_handle_reuse(db, req.refresh_token)
    if reuse_info and reuse_info.get("reused"):
        db.commit()
        raise HTTPException(status_code=401, detail="Gecersiz token.")

    # 2. Aktif session bul
    session = session_svc.get_session_by_token_hash(db, req.refresh_token)
    if not session:
        raise HTTPException(status_code=401, detail="Gecersiz token.")
    if session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Token iptal edilmis.")

    from datetime import datetime as _dt
    if session.expires_at < _dt.utcnow():
        raise HTTPException(status_code=401, detail="Token suresi dolmus.")

    # 3. Kullanici kontrolu
    user = db.get(Kullanici, session.user_id)
    if not user or not user.aktif:
        session_svc.revoke_session(db, session.id, reason="USER_DISABLED")
        db.commit()
        raise HTTPException(status_code=401, detail="Kullanici bulunamadi veya pasif.")

    # 4. Yeni tokenlar uret
    import uuid as _uuid
    from datetime import timedelta as _td
    new_raw_refresh = refresh_token_v2_olustur()
    new_access_token, new_jti_a, new_exp_a = jwt_olustur_v2_access(user.id, user.tier)
    new_refresh_jti = str(_uuid.uuid4())
    new_expires_at = _dt.utcnow() + _td(days=settings.refresh_token_days)

    # 5. Atomik rotation
    result = session_svc.rotate_refresh_session(
        db,
        old_session_id=session.id,
        new_raw_token=new_raw_refresh,
        new_jti=new_refresh_jti,
        new_expires_at=new_expires_at,
        client_type=session.client_type,
        device_name=session.device_name,
        user_agent_hash=session.user_agent_hash,
        ip_hash=session.ip_hash,
        app_version=session.app_version,
    )
    if result is None:
        raise HTTPException(status_code=409, detail="Rotation basarisiz. Tekrar giris gerekli.")
    db.commit()

    return {
        "token": new_access_token,
        "access_token": new_access_token,
        "refresh_token": new_raw_refresh,
        "tier": user.tier,
        "token_type": "bearer",
        "expires_in": settings.access_token_minutes * 60,
        "refresh_expires_in": settings.refresh_token_days * 86400,
    }


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
def cikis(
    req: CikisReq = None,
    user: Kullanici = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Cikis. V2 aktifse refresh session revoke edilir."""
    if settings.auth_token_v2_enabled and req and req.refresh_token:
        session = session_svc.get_session_by_token_hash(db, req.refresh_token)
        if session and session.user_id == user.id and session.revoked_at is None:
            session_svc.revoke_session(db, session.id, reason="LOGOUT")
            db.commit()
    return {"durum": "cikis"}


@router.post("/mock-yukselt")
def mock_yukselt(req: YukseltReq, user: Kullanici = Depends(require_user),
                 db: Session = Depends(get_db)):
    """Eski test endpointi. Uretimde kullanici kendi uyeligini yukseltemez."""
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
