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
    """Gecerliyse payload dict, suresi dolmussa 'expired', gecersizse None doner."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except jwt.ExpiredSignatureError:
        return "expired"
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Token V2 (Faz X2F-2) — kisa omurlu access JWT + ayri refresh opakligi
# ---------------------------------------------------------------------------

def jwt_olustur_v2_access(kullanici_id: int, tier: str) -> tuple[str, str, datetime]:
    """V2 kisa omurlu access token uretir.

    Returns:
        (token_str, jti, expires_at_utc_naive) — UTC-naive datetime proje standarti.
    Ham token loglanmaz; jti indexleme icin kullanilir.
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.access_token_minutes)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(kullanici_id),
        "type": "access",
        "tier": tier,
        "jti": jti,
        "iat": now,
        "exp": exp,
        "iss": settings.token_issuer,
        "aud": settings.token_audience,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)
    # UTC-naive: DB standarti ile tutarlilik
    return token, jti, exp.replace(tzinfo=None)


def jwt_coz_v2_access(token: str) -> dict | None | str:
    """V2 access token dogrula. type=access claim zorunlu.

    Returns:
        payload dict | 'expired' | None
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_alg],
            audience=settings.token_audience,
        )
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return "expired"
    except JWTError:
        return None


def refresh_token_v2_olustur() -> str:
    """Yuksek entropili opak refresh token (UUID4).

    Ham token yalniz client'a gonderilir; DB'ye ASLA kaydedilmez.
    DB'ye hash_token() sonucu yazilir.
    """
    return str(uuid.uuid4())


def kod_uret() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def refresh_token_olustur() -> str:
    """Opak UUID4. Sadece client'a gonderilir -- DB'ye ASLA kaydedilmez."""
    return str(uuid.uuid4())


def hash_token(token: str) -> str:
    """SHA-256 hex hash -- DB'de saklanan bicim."""
    return hashlib.sha256(token.encode()).hexdigest()
