# -*- coding: utf-8 -*-
"""Ilk admin kullanicisini olusturur veya mevcut kullaniciyi admin yapar.

Kullanim:
  python backend/scripts/create_admin.py admin@example.com 'CokGucluSifre123'
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db import SessionLocal  # noqa: E402
from app.models import Kullanici  # noqa: E402
from app.security import hash_sifre  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("sifre")
    args = parser.parse_args()
    if len(args.sifre) < 10:
        raise SystemExit("Sifre en az 10 karakter olmali.")
    email = args.email.strip().lower()
    with SessionLocal() as db:
        user = db.query(Kullanici).filter_by(email=email).one_or_none()
        if user is None:
            user = Kullanici(
                email=email,
                sifre_hash=hash_sifre(args.sifre),
                email_dogrulandi=True,
                tier="vip",
                is_admin=True,
                aktif=True,
            )
            db.add(user)
            action = "olusturuldu"
        else:
            user.sifre_hash = hash_sifre(args.sifre)
            user.email_dogrulandi = True
            user.is_admin = True
            user.aktif = True
            action = "guncellendi"
        db.commit()
        print(f"Admin kullanici {action}: {email}")


if __name__ == "__main__":
    main()
