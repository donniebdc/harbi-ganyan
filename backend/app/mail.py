# -*- coding: utf-8 -*-
"""Doğrulama kodu gönderimi. SMTP yapılandırılmamışsa kod konsola yazılır (dev)."""
from __future__ import annotations
import smtplib
from email.message import EmailMessage

from .config import settings


def kod_gonder(email: str, kod: str) -> None:
    govde = f"Harbi Ganyan doğrulama kodunuz: {kod}\nKod 15 dakika geçerlidir."
    if not settings.smtp_host:
        print(f"[mail:dev] {email} -> doğrulama kodu: {kod}")
        return
    msg = EmailMessage()
    msg["Subject"] = "Harbi Ganyan Doğrulama Kodu"
    msg["From"] = settings.smtp_from
    msg["To"] = email
    msg.set_content(govde)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
        s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_pass)
        s.send_message(msg)
