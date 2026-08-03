# -*- coding: utf-8 -*-
"""FastAPI bagimliliklar: oturum kullanicisi + cihaz + uyelik kademesi."""
from __future__ import annotations
from datetime import datetime

from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from .db import get_db
from .models import Kullanici, UserDevice
from .security import jwt_coz, jwt_coz_v2_access

TIER_RANK = {"standart": 0, "premium": 1, "vip": 2}


def current_user(
    authorization: str | None = Header(None),
    x_device_id: str | None = Header(None, alias="X-Device-ID"),
    db: Session = Depends(get_db),
) -> Kullanici | None:
    """Token varsa kullanici, yoksa None (anonim = standart).

    Decode sirasi:
    1. V2 access token dene (aud claim ile) — basariliysa kabul et
    2. Basarisizsa legacy JWT dene (aud claim olmadan)
    Opak refresh tokenlar (UUID4) JWT olmadigi icin her iki adimda da None doner.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    raw_token = authorization.split(" ", 1)[1]

    # V2 access token: type=access + aud zorunlu
    v2_payload = jwt_coz_v2_access(raw_token)
    if isinstance(v2_payload, dict):
        payload = v2_payload
    else:
        # Legacy token (aud claim yok) veya V2 decode basarisiz
        payload = jwt_coz(raw_token)

    if not payload or payload == "expired":
        return None

    # Refresh-type JWT'yi bearer API erisiminde reddet
    if isinstance(payload, dict) and payload.get("type") == "refresh":
        return None

    try:
        user = db.get(Kullanici, int(payload["sub"]))
    except (TypeError, ValueError):
        return None
    if user is None or not user.aktif:
        return None

    # EFEKTiF VIP cozumu (Faz 1C): karar merkezi uyelik_servis.erisim_coz'da.
    if user.tier == "vip":
        from .uyelik_servis import erisim_coz
        erisim = erisim_coz(db, user)
        if not erisim.is_vip:
            user.tier = "standart"
            db.commit()

    # Cihaz revoke kontrolu
    if x_device_id:
        device = (
            db.query(UserDevice)
            .filter_by(user_id=user.id, device_id=x_device_id)
            .first()
        )
        if device:
            if not device.is_active:
                raise HTTPException(
                    status_code=401,
                    detail="DEVICE_REVOKED",
                    headers={"X-Error-Code": "DEVICE_REVOKED"},
                )
            device.last_seen_at = datetime.utcnow()
            db.commit()

    return user


def require_user(user: Kullanici | None = Depends(current_user)) -> Kullanici:
    if user is None:
        raise HTTPException(status_code=401, detail="Giris gerekli.")
    return user


def require_admin(user: Kullanici = Depends(require_user)) -> Kullanici:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli.")
    return user


def require_editor(user: Kullanici = Depends(require_user)) -> Kullanici:
    """EDITOR veya ADMIN rolu gerekir. Rol her istekte DB'den okunur (token'daki
    claim'e guvenilmez). is_admin=True geriye uyumluluk icin her zaman gecer."""
    if getattr(user, "rol", None) not in ("EDITOR", "ADMIN") and not user.is_admin:
        raise HTTPException(status_code=403, detail="Editor yetkisi gerekli.")
    return user


def tier_of(user: Kullanici | None) -> str:
    return user.tier if user else "standart"


def has_tier(user: Kullanici | None, gereken: str) -> bool:
    return TIER_RANK.get(tier_of(user), 0) >= TIER_RANK.get(gereken, 0)
