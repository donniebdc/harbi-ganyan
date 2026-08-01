# -*- coding: utf-8 -*-
"""Google Play Billing doğrulama — subscriptionsv2 API."""
from __future__ import annotations
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..models import Kullanici, Uyelik
from ..config import settings
from ..telegram_notify import notify_purchase_success, notify_purchase_restore, notify_purchase_failure

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/uyelik", tags=["uyelik"])
GECERLI_URUNLER = {"vip_haftalik", "vip_aylik"}
AKTIF_STATES = {"SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"}
MAX_TOKEN_LOG = 20  # Loglarda token'ın kaç karakteri gösterilecek


class DogrulaReq(BaseModel):
    purchase_token: str
    product_id: str


def _build_service():
    """Google Play androidpublisher v3 service nesnesi. SA yoksa None."""
    if not settings.google_play_sa:
        log.warning("HG_GOOGLE_PLAY_SA ayarli degil; Google Play dogrulama atlanıyor.")
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            settings.google_play_sa,
            scopes=["https://www.googleapis.com/auth/androidpublisher"],
        )
        return build("androidpublisher", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        log.error("Google Play service olusturulamadi: %s", exc)
        return None


def _google_play_dogrula(purchase_token: str, product_id: str) -> dict | None:
    """
    subscriptionsv2.get ile token doğrular.
    Pending acknowledgement varsa acknowledge eder.
    Başarısızlıkta None döner.
    """
    service = _build_service()
    if service is None:
        return None
    try:
        result = (
            service.purchases()
            .subscriptionsv2()
            .get(packageName=settings.google_play_package, token=purchase_token)
            .execute()
        )
        # Acknowledge pending purchases (3 gün içinde yapılmazsa Google iptal eder)
        if result.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_PENDING":
            try:
                service.purchases().subscriptions().acknowledge(
                    packageName=settings.google_play_package,
                    subscriptionId=product_id,
                    token=purchase_token,
                    body={},
                ).execute()
                log.info("Acknowledge OK: token=...%s", purchase_token[-MAX_TOKEN_LOG:])
            except Exception as ack_exc:
                log.warning("Acknowledge basarisiz (best-effort): %s", ack_exc)
        return result
    except Exception as exc:
        log.error("Google Play dogrulama hatasi (token=...%s): %s",
                  purchase_token[-MAX_TOKEN_LOG:], exc)
        return None


def _expiry_from_response(abonelik: dict, product_id: str) -> datetime | None:
    """subscriptionsv2 lineItems'tan expiryTime çıkart → naive UTC datetime."""
    line_items = abonelik.get("lineItems", [])
    expiry_str = None
    for item in line_items:
        if item.get("productId") == product_id:
            expiry_str = item.get("expiryTime")
            break
    if not expiry_str and line_items:
        expiry_str = line_items[0].get("expiryTime")
    if not expiry_str:
        return None
    dt = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
    return dt.replace(tzinfo=None)


def _start_time_from_response(abonelik: dict) -> datetime | None:
    st = abonelik.get("startTime")
    if not st:
        return None
    try:
        dt = datetime.fromisoformat(st.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def _plan_type(product_id: str) -> str:
    return "weekly" if product_id == "vip_haftalik" else "monthly"


def _auto_renewing(abonelik: dict) -> bool | None:
    """lineItems'ta autoRenewingPlan varsa auto_renewing flag."""
    for item in abonelik.get("lineItems", []):
        plan = item.get("autoRenewingPlan", {})
        if "autoRenewEnabled" in plan:
            return bool(plan["autoRenewEnabled"])
    return None


def _close_linked_token(purchase_token: str, db: Session) -> None:
    """linkedPurchaseToken varsa eski Uyelik kaydını pasife al."""
    old = db.query(Uyelik).filter_by(purchase_token=purchase_token).first()
    if old and old.aktif:
        old.aktif = False
        old.updated_at = datetime.utcnow()
        log.info("Linked token kapatildi: id=%s", old.id)


def _upsert_uyelik(
    db: Session,
    user: Kullanici,
    purchase_token: str,
    product_id: str,
    abonelik: dict,
    expires_at: datetime | None,
) -> Uyelik:
    """Mevcut Uyelik kaydını güncelle veya yeni oluştur."""
    now = datetime.utcnow()
    mevcut = db.query(Uyelik).filter_by(purchase_token=purchase_token).first()

    fields = dict(
        tier="vip",
        aktif=True,
        google_product_id=product_id,
        expires_at=expires_at,
        plan_type=_plan_type(product_id),
        subscription_state=abonelik.get("subscriptionState"),
        acknowledged=abonelik.get("acknowledgementState") != "ACKNOWLEDGEMENT_STATE_PENDING",
        start_time=_start_time_from_response(abonelik),
        latest_order_id=abonelik.get("latestOrderId"),
        auto_renewing=_auto_renewing(abonelik),
        linked_purchase_token=abonelik.get("linkedPurchaseToken"),
        raw_google_response=abonelik,
        updated_at=now,
        last_verified_at=now,
    )

    if mevcut:
        for k, v in fields.items():
            setattr(mevcut, k, v)
        return mevcut
    else:
        rec = Uyelik(kullanici_id=user.id, kaynak="google_play",
                     purchase_token=purchase_token, **fields)
        db.add(rec)
        return rec


@router.post("/dogrula")
def dogrula(
    req: DogrulaReq,
    user: Kullanici = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Satın alma sonrası çağrılır. İdempotent — aynı token tekrar gönderilebilir."""
    if req.product_id not in GECERLI_URUNLER:
        raise HTTPException(status_code=400, detail="Geçersiz ürün.")

    # Token başka kullanıcıya ait mi?
    sahip = db.query(Uyelik).filter_by(purchase_token=req.purchase_token).first()
    if sahip and sahip.kullanici_id != user.id:
        raise HTTPException(status_code=409, detail="Bu token başka bir hesaba ait.")

    was_active = sahip is not None and sahip.aktif and user.tier == "vip"

    abonelik = _google_play_dogrula(req.purchase_token, req.product_id)
    if abonelik is None:
        notify_purchase_failure(user.id, req.product_id, "google_verify", "Google Play doğrulama None döndü")
        raise HTTPException(status_code=402, detail="Satın alma doğrulanamadı.")

    sub_state = abonelik.get("subscriptionState", "")
    if sub_state not in AKTIF_STATES:
        log.warning("Abonelik aktif degil: user=%s state=%s token=...%s",
                    user.id, sub_state, req.purchase_token[-MAX_TOKEN_LOG:])
        notify_purchase_failure(user.id, req.product_id, "subscription_state", f"Abonelik aktif değil ({sub_state})")
        raise HTTPException(status_code=402, detail=f"Abonelik aktif değil ({sub_state}).")

    expires_at = _expiry_from_response(abonelik, req.product_id)
    if expires_at and expires_at < datetime.utcnow():
        notify_purchase_failure(user.id, req.product_id, "expiry_check", "Abonelik süresi dolmuş")
        raise HTTPException(status_code=402, detail="Abonelik süresi dolmuş.")

    # Eski linkedPurchaseToken'ı kapat
    linked = abonelik.get("linkedPurchaseToken")
    if linked:
        _close_linked_token(linked, db)

    _upsert_uyelik(db, user, req.purchase_token, req.product_id, abonelik, expires_at)

    user.tier = "vip"
    user.vip_until = expires_at
    user.vip_source = "google_play"
    db.commit()

    if not was_active:
        if sahip is None:
            notify_purchase_success(user.id, req.product_id, expires_at, sub_state)
        else:
            notify_purchase_restore(user.id, req.product_id, expires_at, sub_state)

    log.info("VIP aktif: user=%s product=%s expires=%s", user.id, req.product_id, expires_at)
    return {
        "tier": "vip",
        "plan_type": _plan_type(req.product_id),
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.post("/sync")
def sync(
    user: Kullanici = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Uygulama açılışında veya 'geri yükle' akışında çağrılır.
    Kullanıcının aktif Google Play aboneliğini yeniden doğrular.
    """
    aktif_uyelik = (
        db.query(Uyelik)
        .filter_by(kullanici_id=user.id, aktif=True, kaynak="google_play")
        .order_by(Uyelik.id.desc())
        .first()
    )

    if aktif_uyelik is None or not aktif_uyelik.purchase_token:
        return {"tier": user.tier, "synced": False, "detail": "Aktif abonelik bulunamadı."}


    was_vip = user.tier == "vip"
    abonelik = _google_play_dogrula(
        aktif_uyelik.purchase_token, aktif_uyelik.google_product_id or "vip_haftalik"
    )

    now = datetime.utcnow()

    if abonelik is None:
        return {"tier": user.tier, "synced": False, "detail": "Google Play doğrulama başarısız."}

    sub_state = abonelik.get("subscriptionState", "")
    expires_at = _expiry_from_response(
        abonelik, aktif_uyelik.google_product_id or "vip_haftalik"
    )

    if sub_state in AKTIF_STATES and (expires_at is None or expires_at > now):
        _upsert_uyelik(
            db, user, aktif_uyelik.purchase_token,
            aktif_uyelik.google_product_id or "vip_haftalik", abonelik, expires_at,
        )
        user.tier = "vip"
        user.vip_until = expires_at
        user.vip_source = "google_play"
        db.commit()
        if not was_vip:
            notify_purchase_restore(user.id, aktif_uyelik.google_product_id or "vip_haftalik", expires_at, sub_state)
        log.info("Sync VIP: user=%s expires=%s", user.id, expires_at)
        return {
            "tier": "vip",
            "plan_type": aktif_uyelik.plan_type,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "synced": True,
        }
    else:
        # Abonelik sona ermiş veya iptal edilmiş
        aktif_uyelik.aktif = False
        aktif_uyelik.subscription_state = sub_state
        aktif_uyelik.updated_at = now
        aktif_uyelik.last_verified_at = now
        user.tier = "standart"
        user.vip_until = None
        db.commit()
        log.info("Sync -> Standart: user=%s state=%s", user.id, sub_state)
        return {"tier": "standart", "synced": True, "detail": f"Abonelik geçersiz ({sub_state})."}
