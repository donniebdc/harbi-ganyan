# -*- coding: utf-8 -*-
"""Stateful refresh session servisi (Faz X2F-1).

Bu modul yalniz altyapi ve test amaclıdır. Mevcut auth endpointlerinden
CAGRILMAZ; X2F-2'de /auth/giris ve /auth/yenile entegrasyonuyla devreye girer.

Guvenlik prensipleri:
- Ham refresh token bu modulun disina asla cikmaz.
- DB'ye yalniz SHA-256 hex hash yazilir (hash_token kullanilir).
- Rotation atomik tasarlanmistir: eski session revoke + yeni session olusturma
  ayni transaction icinde gerceklesir.
- Reuse detection: gecersiz (revoked) token kullanildiginda ayni token ailesinin
  tum aktif sessionlari revoke edilir.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, select, update
from sqlalchemy.orm import Session

from .models import AuthSession
from .security import hash_token, REFRESH_TOKEN_EXPIRE_DAYS

_DEFAULT_EXPIRE_DAYS = REFRESH_TOKEN_EXPIRE_DAYS


def _now() -> datetime:
    """UTC-naive simdi (proje standardi)."""
    return datetime.utcnow()


def _expires_default() -> datetime:
    return _now() + timedelta(days=_DEFAULT_EXPIRE_DAYS)


# --- OLUSTURMA ----------------------------------------------------------------

def create_refresh_session(
    db: Session,
    *,
    user_id: int,
    raw_token: str,
    jti: str,
    token_family_id: str,
    expires_at: datetime | None = None,
    client_type: str = "UNKNOWN",
    device_name: str | None = None,
    user_agent_hash: str | None = None,
    ip_hash: str | None = None,
    app_version: str | None = None,
) -> AuthSession:
    """Yeni refresh session olusturur. Ham token DB'ye yazilmaz."""
    if expires_at is None:
        expires_at = _expires_default()
    session = AuthSession(
        user_id=user_id,
        token_hash=hash_token(raw_token),
        jti=jti,
        token_family_id=token_family_id,
        expires_at=expires_at,
        client_type=client_type,
        device_name=device_name,
        user_agent_hash=user_agent_hash,
        ip_hash=ip_hash,
        app_version=app_version,
    )
    db.add(session)
    db.flush()
    return session


# --- ARAMA -------------------------------------------------------------------

def get_session_by_token_hash(db: Session, raw_token: str) -> AuthSession | None:
    """Ham tokeni hashleyerek DB'de arar."""
    return db.execute(
        select(AuthSession).where(AuthSession.token_hash == hash_token(raw_token))
    ).scalar_one_or_none()


def get_session_by_jti(db: Session, jti: str) -> AuthSession | None:
    return db.execute(
        select(AuthSession).where(AuthSession.jti == jti)
    ).scalar_one_or_none()


# --- GUNCELLEME --------------------------------------------------------------

def mark_session_used(db: Session, session_id: int) -> None:
    """Son kullanim zamanini gunceller."""
    db.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id)
        .values(last_used_at=_now())
    )
    db.flush()


# --- REVOKE ------------------------------------------------------------------

def revoke_session(
    db: Session, session_id: int, reason: str = "LOGOUT"
) -> bool:
    """Tek sessioni revoke eder. Zaten revoke ise False doner."""
    session = db.get(AuthSession, session_id)
    if session is None or session.revoked_at is not None:
        return False
    now = _now()
    session.revoked_at = now
    session.revoke_reason = reason
    db.flush()
    return True


def revoke_user_sessions(
    db: Session,
    user_id: int,
    reason: str = "ALL_DEVICES_LOGOUT",
    exclude_session_id: int | None = None,
) -> int:
    """Kullanicinin tum aktif sessionlarini revoke eder. Etkilenen satir sayisi doner."""
    now = _now()
    q = (
        select(AuthSession)
        .where(
            and_(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
        )
    )
    if exclude_session_id is not None:
        q = q.where(AuthSession.id != exclude_session_id)
    sessions = db.execute(q).scalars().all()
    count = 0
    for s in sessions:
        s.revoked_at = now
        s.revoke_reason = reason
        count += 1
    db.flush()
    return count


def revoke_token_family(
    db: Session, token_family_id: str, reason: str = "TOKEN_REUSE"
) -> int:
    """Token ailesinin tum aktif sessionlarini revoke eder."""
    now = _now()
    sessions = db.execute(
        select(AuthSession).where(
            and_(
                AuthSession.token_family_id == token_family_id,
                AuthSession.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    count = 0
    for s in sessions:
        s.revoked_at = now
        s.revoke_reason = reason
        count += 1
    db.flush()
    return count


# --- ROTATION ----------------------------------------------------------------

def rotate_refresh_session(
    db: Session,
    *,
    old_session_id: int,
    new_raw_token: str,
    new_jti: str,
    new_expires_at: datetime | None = None,
    client_type: str = "UNKNOWN",
    device_name: str | None = None,
    user_agent_hash: str | None = None,
    ip_hash: str | None = None,
    app_version: str | None = None,
) -> tuple | None:
    """Mevcut sessioni revoke edip yerine yeni session olusturur.

    Atomik: eski session REPLACED olarak isaretlenir, yeni session ayni
    transaction icinde olusturulur.

    Donus: (yeni_session, eski_session) veya None (gecersiz eski session).
    """
    old = db.get(AuthSession, old_session_id, with_for_update=True)
    if old is None:
        return None
    if old.revoked_at is not None:
        return None
    now = _now()
    if old.expires_at < now:
        return None

    new = create_refresh_session(
        db,
        user_id=old.user_id,
        raw_token=new_raw_token,
        jti=new_jti,
        token_family_id=old.token_family_id,
        expires_at=new_expires_at or _expires_default(),
        client_type=client_type,
        device_name=device_name,
        user_agent_hash=user_agent_hash,
        ip_hash=ip_hash,
        app_version=app_version,
    )

    old.revoked_at = now
    old.revoke_reason = "REPLACED"
    old.replaced_by_id = new.id
    db.flush()

    return new, old


# --- REUSE DETECTION ---------------------------------------------------------

def detect_and_handle_reuse(
    db: Session, raw_token: str
) -> dict | None:
    """Eski (revoke edilmis) refresh token kullanimini tespit eder.

    Ham tokena ait session revoke edilmisse token family tumüyle revoke
    edilir ve guvenlik uyarisi icin metadata doner. Aktif session ise None doner.
    """
    token_h = hash_token(raw_token)
    session = db.execute(
        select(AuthSession).where(AuthSession.token_hash == token_h)
    ).scalar_one_or_none()

    if session is None:
        return None
    if session.revoked_at is None:
        return None

    family_id = session.token_family_id
    count = revoke_token_family(db, family_id, reason="TOKEN_REUSE")
    db.flush()
    return {
        "family_id": family_id,
        "revoked_count": count,
        "reason": "TOKEN_REUSE",
        "original_session_id": session.id,
    }


# --- TEMIZLIK ----------------------------------------------------------------

def delete_expired_sessions(
    db: Session,
    before: datetime | None = None,
    retention_days: int = 7,
) -> int:
    """Suresi dolmus + revoke edilmis sessionlari siler.

    Yalniz hem suresi dolmus hem de revoke edilmis satirlari siler.
    Aktif session silinmez.
    retention_days: revoke anindan bu kadar gun gecmis satirlari sil.
    """
    cutoff = before or _now()
    retain_cutoff = cutoff - timedelta(days=retention_days)

    candidates = db.execute(
        select(AuthSession).where(
            and_(
                AuthSession.expires_at < cutoff,
                AuthSession.revoked_at.isnot(None),
                AuthSession.revoked_at < retain_cutoff,
            )
        )
    ).scalars().all()

    count = len(candidates)
    for s in candidates:
        db.delete(s)
    db.flush()
    return count
