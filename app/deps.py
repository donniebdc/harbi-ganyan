# -*- coding: utf-8 -*-
"""FastAPI bağımlılıkları: oturum kullanıcısı + cihaz + üyelik kademesi."""
from __future__ import annotations
from datetime import datetime

from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from .db import get_db
from .models import Kullanici, UserDevice
from .security import jwt_coz

TIER_RANK = {"standart": 0, "premium": 1, "vip": 2}


def current_user(
    authorization: str | None = Header(None),
    x_device_id: str | None = Header(None, alias="X-Device-ID"),
    db: Session = Depends(get_db),
) -> Kullanici | None:
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

    # EFEKTİF VIP çözümü (Faz 1C): karar merkezi uyelik_servis.erisim_coz'da.
    # Eski hata: vip_until NULL olan manuel VIP'ler süresiz VIP kalıyordu
    # ("user.vip_until and ..." NULL'da kontrolü atlıyordu). Artık tier=='vip'
    # olan her kullanıcı için kaynaklar (Google Play + manuel) istek anında
    # değerlendirilir; efektif VIP değilse tier düşürülür (lazy TEK seferlik
    # yazma — yalnız yanlış durumda commit edilir, her istekte yazılmaz).
    # vip_until audit için NULL'lanmaz.
    if user.tier == "vip":
        from .uyelik_servis import erisim_coz
        erisim = erisim_coz(db, user)
        if not erisim.is_vip:
            user.tier = "standart"
            db.commit()

    # Cihaz revoke kontrolü
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
        raise HTTPException(status_code=401, detail="Giriş gerekli.")
    return user


def require_admin(user: Kullanici = Depends(require_user)) -> Kullanici:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli.")
    return user


def require_editor(user: Kullanici = Depends(require_user)) -> Kullanici:
    """EDITOR veya ADMIN rolu gerekir. Rol her istekte DB'den okunur (token'daki
    claim'e guvenilmez). is_admin=True geriye uyumluluk icin her zaman gecer."""
    if getattr(user, "rol", None) not in ("EDITOR", "ADMIN") and not user.is_admin:
        raise HTTPException(status_code=403, detail="Editör yetkisi gerekli.")
    return user


def tier_of(user: Kullanici | None) -> str:
    return user.tier if user else "standart"


def has_tier(user: Kullanici | None, gereken: str) -> bool:
    return TIER_RANK.get(tier_of(user), 0) >= TIER_RANK.get(gereken, 0)
