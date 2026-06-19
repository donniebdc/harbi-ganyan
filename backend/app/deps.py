# -*- coding: utf-8 -*-
"""FastAPI bağımlılıkları: oturum kullanıcısı + üyelik kademesi."""
from __future__ import annotations
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from .db import get_db
from .models import Kullanici
from .security import jwt_coz

TIER_RANK = {"standart": 0, "premium": 1, "vip": 2}


def current_user(authorization: str | None = Header(None),
                 db: Session = Depends(get_db)) -> Kullanici | None:
    """Token varsa kullanıcı, yoksa None (anonim = standart)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    payload = jwt_coz(authorization.split(" ", 1)[1])
    if not payload:
        return None
    try:
        user = db.get(Kullanici, int(payload["sub"]))
    except (TypeError, ValueError):
        return None
    if user is None or not user.aktif:
        return None
    return user


def require_user(user: Kullanici | None = Depends(current_user)) -> Kullanici:
    if user is None:
        raise HTTPException(status_code=401, detail="Giriş gerekli.")
    return user


def require_admin(user: Kullanici = Depends(require_user)) -> Kullanici:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli.")
    return user


def tier_of(user: Kullanici | None) -> str:
    return user.tier if user else "standart"


def has_tier(user: Kullanici | None, gereken: str) -> bool:
    return TIER_RANK.get(tier_of(user), 0) >= TIER_RANK.get(gereken, 0)
