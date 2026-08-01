# -*- coding: utf-8 -*-
"""Sifre hashleme, JWT, dogrulama kodu."""
from __future__ import annotations
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

from .config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

REFRESH_TOKEN_EXPIRE_DAYS = 30

TIER_SESSION_LIMIT: dict[str, int] = {
    "standart": 2,
    "vip": 3,
    "premium": 3,
}


def hash_sifre(p: str) -> str:
    return _pwd.hash(p)


def dogrula_sifre(p: str, h: str) -> bool:
    try:
        return _pwd.verify(p, h)
    except Exception:
        return False


def jwt_olustur(kullanici_id: int, tier: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_min)
    return jwt.encode({"sub": str(kullanici_id), "tier": tier, "exp": exp},
                      settings.jwt_secret, algorithm=settings.jwt_alg)


def jwt_coz(token: str) -> dict | None | str:
    """Geçerliyse payload dict, süresi dolmuşsa 'expired', geçersizse None döner."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except jwt.ExpiredSignatureError:
        return "expired"
    except JWTError:
        return None


def kod_uret() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def refresh_token_olustur() -> str:
    """Opak UUID4. Sadece client'a gonderilir -- DB'ye ASLA kaydedilmez."""
    return str(uuid.uuid4())


def hash_token(token: str) -> str:
    """SHA-256 hex hash -- DB'de saklanan bicim."""
    return hashlib.sha256(token.encode()).hexdigest()
