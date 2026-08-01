# -*- coding: utf-8 -*-
"""Harbi Ganyan için tek yönlü, best-effort Telegram production bildirimleri."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from zoneinfo import ZoneInfo

import requests

from .config import settings


log = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="hg-telegram",
)

_RECENT_EVENTS: dict[str, float] = {}
_RECENT_LOCK = Lock()

_TELEGRAM_API_BASE = "https://api.telegram.org"
_ISTANBUL = ZoneInfo("Europe/Istanbul")


def _enabled() -> bool:
    return bool(
        settings.telegram_alerts_enabled
        and settings.telegram_bot_token
        and settings.telegram_chat_id
    )


def _now_text() -> str:
    return datetime.now(_ISTANBUL).strftime("%d.%m.%Y %H:%M:%S")


def _datetime_text(value: datetime | None) -> str:
    if value is None:
        return "Bilinmiyor"

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(_ISTANBUL).strftime("%d.%m.%Y %H:%M")


def _plan_text(product_id: str) -> str:
    return {
        "vip_haftalik": "Haftalık VIP",
        "vip_aylik": "Aylık VIP",
    }.get(product_id, product_id)


def _safe_text(value: object, max_length: int = 180) -> str:
    text = " ".join(str(value).split())
    return text[:max_length]


def _claim_event(key: str, ttl_seconds: int) -> bool:
    now = time.monotonic()

    with _RECENT_LOCK:
        expired = [
            event_key
            for event_key, created_at in _RECENT_EVENTS.items()
            if now - created_at >= ttl_seconds
        ]

        for event_key in expired:
            _RECENT_EVENTS.pop(event_key, None)

        created_at = _RECENT_EVENTS.get(key)
        if created_at is not None and now - created_at < ttl_seconds:
            return False

        _RECENT_EVENTS[key] = now
        return True


def _release_event(key: str) -> None:
    with _RECENT_LOCK:
        _RECENT_EVENTS.pop(key, None)


def send_telegram_notification(text: str) -> bool:
    """
    Telegram mesajını senkron gönderir.

    Hata hiçbir zaman çağıran kayıt, billing veya auth işlemini bozmaz.
    Bot token'ı loglanmaz.
    """
    if not _enabled():
        return False

    url = (
        f"{_TELEGRAM_API_BASE}/bot"
        f"{settings.telegram_bot_token}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            data={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            },
            timeout=(3.05, 5),
        )
        response.raise_for_status()

        payload = response.json()
        if payload.get("ok") is not True:
            raise RuntimeError("Telegram API ok=false döndürdü.")

        return True

    except Exception as exc:
        # Exception metni URL/token içerebilir. Bu yüzden yalnız tip loglanır.
        log.warning(
            "Telegram bildirimi gönderilemedi: %s",
            type(exc).__name__,
        )
        return False


def _send_claimed(text: str, event_key: str) -> None:
    sent = send_telegram_notification(text)

    if not sent:
        # Başarısız gönderim daha sonraki denemeyi bloke etmesin.
        _release_event(event_key)


def queue_telegram_notification(
    text: str,
    *,
    event_key: str,
    ttl_seconds: int,
) -> bool:
    """
    Mesajı ana HTTP isteğini bekletmeden arka planda gönderir.

    Aynı olay için kısa süreli process-içi tekrar koruması uygular.
    """
    if not _enabled():
        return False

    if not _claim_event(event_key, ttl_seconds):
        return False

    try:
        _EXECUTOR.submit(_send_claimed, text, event_key)
        return True
    except Exception as exc:
        _release_event(event_key)
        log.warning(
            "Telegram bildirim kuyruğu oluşturulamadı: %s",
            type(exc).__name__,
        )
        return False


def notify_new_user(user_id: int) -> None:
    text = (
        "🆕 Yeni kullanıcı doğrulandı\n"
        f"Kullanıcı ID: {user_id}\n"
        f"Ortam: {settings.telegram_env_label}\n"
        f"Saat: {_now_text()}"
    )

    queue_telegram_notification(
        text,
        event_key=f"new-user:{user_id}",
        ttl_seconds=86400,
    )


def notify_purchase_success(
    user_id: int,
    product_id: str,
    expires_at: datetime | None,
    subscription_state: str,
) -> None:
    text = (
        "💳 Yeni Google Play aboneliği\n"
        f"Kullanıcı ID: {user_id}\n"
        f"Plan: {_plan_text(product_id)}\n"
        f"Durum: {_safe_text(subscription_state)}\n"
        f"VIP bitiş: {_datetime_text(expires_at)}\n"
        f"Ortam: {settings.telegram_env_label}\n"
        f"Saat: {_now_text()}"
    )

    queue_telegram_notification(
        text,
        event_key=(
            f"purchase-success:{user_id}:"
            f"{product_id}:{expires_at}"
        ),
        ttl_seconds=86400,
    )


def notify_purchase_restore(
    user_id: int,
    product_id: str,
    expires_at: datetime | None,
    subscription_state: str,
) -> None:
    text = (
        "♻️ Google Play aboneliği geri yüklendi\n"
        f"Kullanıcı ID: {user_id}\n"
        f"Plan: {_plan_text(product_id)}\n"
        f"Durum: {_safe_text(subscription_state)}\n"
        f"VIP bitiş: {_datetime_text(expires_at)}\n"
        f"Ortam: {settings.telegram_env_label}\n"
        f"Saat: {_now_text()}"
    )

    queue_telegram_notification(
        text,
        event_key=(
            f"purchase-restore:{user_id}:"
            f"{product_id}:{expires_at}"
        ),
        ttl_seconds=86400,
    )


def notify_purchase_failure(
    user_id: int,
    product_id: str,
    stage: str,
    reason: str,
) -> None:
    safe_stage = _safe_text(stage, 80)
    safe_reason = _safe_text(reason, 180)

    text = (
        "❌ Satın alma doğrulama hatası\n"
        f"Kullanıcı ID: {user_id}\n"
        f"Plan: {_plan_text(product_id)}\n"
        f"Aşama: {safe_stage}\n"
        f"Hata: {safe_reason}\n"
        f"Ortam: {settings.telegram_env_label}\n"
        f"Saat: {_now_text()}"
    )

    queue_telegram_notification(
        text,
        event_key=(
            f"purchase-failure:{user_id}:"
            f"{product_id}:{safe_stage}:{safe_reason}"
        ),
        ttl_seconds=900,
    )
