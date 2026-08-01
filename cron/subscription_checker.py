#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abonelik durum kontrolcüsü.

1) Aktif Google Play aboneliklerini periyodik olarak doğrular; süresi dolan/iptal
   edilenlerde üyelik kaydını pasife alır. Kullanıcı MANUEL VIP'e de sahipse
   Standart'a DÜŞÜRÜLMEZ (Faz 1C — merkezi çözümleyici).
2) Manuel VIP veri temizliği: efektif VIP olmayan tier='vip' kullanıcılarını
   Standart'a düşürür (idempotent). Erişim kararı zaten istek anında
   uyelik_servis.erisim_coz ile verildiği için bu adım gecikse de süresi dolmuş
   kullanıcı VIP içerik GÖREMEZ; bu yalnız veri tutarlılığı içindir.

Çalıştırma:
  cd /opt/harbi_ganyan_backend
  .venv/bin/python cron/subscription_checker.py

Cron (mevcut — her 2 saatte bir):
  0 */2 * * * /opt/harbi_ganyan_backend/.venv/bin/python \
    /opt/harbi_ganyan_backend/cron/subscription_checker.py >> \
    /var/log/harbi_subscription_checker.log 2>&1
"""
from __future__ import annotations
import logging
import sys
from datetime import datetime
from pathlib import Path

# Backend kök dizini sys.path'e ekle
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Kullanici, Uyelik  # noqa: E402
from app import uyelik_servis  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [subscription_checker] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

AKTIF_STATES = {"SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"}
MAX_TOKEN_LOG = 20


def _build_service():
    if not settings.google_play_sa:
        log.warning("HG_GOOGLE_PLAY_SA ayarli degil — dogrulama atlanıyor.")
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
        log.error("Service olusturulamadi: %s", exc)
        return None


def _expiry_from_response(abonelik: dict, product_id: str) -> datetime | None:
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
    try:
        dt = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def _google_play_kontrol(db, service, now: datetime) -> None:
    kontrol_edilen = 0
    vip_kaldi = 0
    dusurulen = 0
    hatali = 0
    aktif_uyelikler = (
        db.query(Uyelik)
        .filter(Uyelik.aktif == True, Uyelik.kaynak == "google_play",  # noqa: E712
                Uyelik.purchase_token.isnot(None))
        .all()
    )
    log.info("%d aktif Google Play aboneligi kontrol edilecek.", len(aktif_uyelikler))

    for uyelik in aktif_uyelikler:
        kontrol_edilen += 1
        product_id = uyelik.google_product_id or "vip_haftalik"
        token = uyelik.purchase_token
        token_log = f"...{token[-MAX_TOKEN_LOG:]}" if token else "?"

        try:
            abonelik = (
                service.purchases()
                .subscriptionsv2()
                .get(packageName=settings.google_play_package, token=token)
                .execute()
            )
        except Exception as exc:
            log.warning("API hatasi user=%s token=%s: %s",
                        uyelik.kullanici_id, token_log, exc)
            hatali += 1
            continue

        sub_state = abonelik.get("subscriptionState", "")
        expires_at = _expiry_from_response(abonelik, product_id)

        uyelik.subscription_state = sub_state
        uyelik.last_verified_at = now
        uyelik.updated_at = now
        uyelik.raw_google_response = abonelik

        user: Kullanici | None = db.get(Kullanici, uyelik.kullanici_id)
        if not user:
            continue

        if sub_state in AKTIF_STATES and (expires_at is None or expires_at > now):
            uyelik.expires_at = expires_at
            if user.tier != "vip":
                user.tier = "vip"
                log.info("VIP yenilendi: user=%s token=%s", user.id, token_log)
            user.vip_until = expires_at
            user.vip_source = "google_play"
            vip_kaldi += 1
        else:
            uyelik.aktif = False
            # Faz 1C: GP bitse de MANUEL VIP aktif olabilir — merkezi karar.
            erisim = uyelik_servis.erisim_coz(db, user, now)
            if erisim.is_vip:
                user.tier = "vip"
                user.vip_source = "manuel"
                user.vip_until = erisim.effective_until
                log.info("GP bitti, manuel VIP korundu: user=%s", user.id)
            elif user.tier == "vip":
                user.tier = "standart"
                log.info("Standart'a dusuruldu: user=%s state=%s token=%s",
                         user.id, sub_state, token_log)
                dusurulen += 1
    log.info("GP tamamlandi: kontrol=%d vip=%d dusurulen=%d hatali=%d",
             kontrol_edilen, vip_kaldi, dusurulen, hatali)


def run() -> None:
    log.info("Subscription checker basliyor...")
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        service = _build_service()
        if service is not None:
            _google_play_kontrol(db, service, now)
        else:
            log.error("Google Play service yok — GP kontrolu atlandi.")
        # Manuel VIP veri temizligi GP servisinden BAGIMSIZ calisir (Faz 1C).
        n = uyelik_servis.suresi_dolan_manuel_temizle(db, now)
        if n:
            log.info("Manuel temizlik: %d kullanici standart'a dusuruldu.", n)
        else:
            log.info("Manuel temizlik: degisiklik yok.")
        db.commit()
    except Exception as exc:
        log.error("Genel hata: %s", exc)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run()
