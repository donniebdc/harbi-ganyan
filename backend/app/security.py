# -*- coding: utf-8 -*-
"""Şifre hashleme, JWT, doğrulama kodu."""
from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

from .config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


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


def jwt_coz(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except JWTError:
        return None


def kod_uret() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
