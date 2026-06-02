# -*- coding: utf-8 -*-
"""Veri modeli — tahmin içeriği + kullanıcı/üyelik.

İçerik hiyerarşisi:
    gun (tarih)
      └─ gun_hipodrom (tarih+hipodrom, birim)
           ├─ kosu  ──┬─ kosu_bes (5 satır slotları)
           │          └─ kosu_sonuc (kazanan/ganyan/bes_hit)
           └─ altili ─┬─ altili_kademe (simitci/harbi/ortakli) ─ altili_ayak
                      └─ altili_sonuc (winners/ikramiye/tier_hits)
"""
from __future__ import annotations
from datetime import datetime, date as date_t
from sqlalchemy import (String, Integer, Float, Boolean, ForeignKey, UniqueConstraint,
                        Text, JSON, Date, DateTime, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class Gun(Base):
    __tablename__ = "gun"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date_t] = mapped_column(Date, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    hipodromlar: Mapped[list["GunHipodrom"]] = relationship(
        back_populates="gun", cascade="all, delete-orphan")


class GunHipodrom(Base):
    __tablename__ = "gun_hipodrom"
    __table_args__ = (UniqueConstraint("gun_id", "hipodrom"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    gun_id: Mapped[int] = mapped_column(ForeignKey("gun.id", ondelete="CASCADE"), index=True)
    hipodrom: Mapped[str] = mapped_column(String(40), index=True)
    birim: Mapped[float] = mapped_column(Float)
    gun: Mapped[Gun] = relationship(back_populates="hipodromlar")
    kosular: Mapped[list["Kosu"]] = relationship(
        back_populates="gh", cascade="all, delete-orphan")
    altililar: Mapped[list["Altili"]] = relationship(
        back_populates="gh", cascade="all, delete-orphan")
    bahisler: Mapped[list["KosuBahis"]] = relationship(
        back_populates="gh", cascade="all, delete-orphan")


class Kosu(Base):
    __tablename__ = "kosu"
    __table_args__ = (UniqueConstraint("gh_id", "kno"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    gh_id: Mapped[int] = mapped_column(ForeignKey("gun_hipodrom.id", ondelete="CASCADE"), index=True)
    kno: Mapped[int] = mapped_column(Integer)
    pist: Mapped[str] = mapped_column(String(20), default="")
    mesafe: Mapped[str] = mapped_column(String(20), default="")
    saat: Mapped[str] = mapped_column(String(10), default="")
    n_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    race_type: Mapped[str] = mapped_column(String(30), default="")
    race_subtype: Mapped[str] = mapped_column(String(30), default="")
    gh: Mapped[GunHipodrom] = relationship(back_populates="kosular")
    bes: Mapped[list["KosuBes"]] = relationship(
        back_populates="kosu", cascade="all, delete-orphan", order_by="KosuBes.sira")
    sonuc: Mapped["KosuSonuc | None"] = relationship(
        back_populates="kosu", cascade="all, delete-orphan", uselist=False)


class KosuBes(Base):
    """5 satır slotu (FAV/SUR/YAZ/BOM/HAR)."""
    __tablename__ = "kosu_bes"
    id: Mapped[int] = mapped_column(primary_key=True)
    kosu_id: Mapped[int] = mapped_column(ForeignKey("kosu.id", ondelete="CASCADE"), index=True)
    sira: Mapped[int] = mapped_column(Integer)  # 0..4
    slot: Mapped[str] = mapped_column(String(4))  # FAV/SUR/YAZ/BOM/HAR
    at_no: Mapped[int] = mapped_column(Integer)
    at: Mapped[str] = mapped_column(String(60), default="")
    ana: Mapped[float] = mapped_column(Float, default=0.0)
    kosu: Mapped[Kosu] = relationship(back_populates="bes")


class KosuSonuc(Base):
    __tablename__ = "kosu_sonuc"
    id: Mapped[int] = mapped_column(primary_key=True)
    kosu_id: Mapped[int] = mapped_column(ForeignKey("kosu.id", ondelete="CASCADE"), unique=True)
    kazanan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kazanan_ad: Mapped[str] = mapped_column(String(60), default="")  # kazanan at adı (bildirim metni)
    ganyan: Mapped[float | None] = mapped_column(Float, nullable=True)
    bes_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    kosu: Mapped[Kosu] = relationship(back_populates="sonuc")


class Altili(Base):
    __tablename__ = "altili"
    __table_args__ = (UniqueConstraint("gh_id", "idx"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    gh_id: Mapped[int] = mapped_column(ForeignKey("gun_hipodrom.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    legs: Mapped[list] = mapped_column(JSON)  # [kno...]
    gh: Mapped[GunHipodrom] = relationship(back_populates="altililar")
    kademeler: Mapped[list["AltiliKademe"]] = relationship(
        back_populates="altili", cascade="all, delete-orphan")
    sonuc: Mapped["AltiliSonuc | None"] = relationship(
        back_populates="altili", cascade="all, delete-orphan", uselist=False)


class AltiliKademe(Base):
    __tablename__ = "altili_kademe"
    id: Mapped[int] = mapped_column(primary_key=True)
    altili_id: Mapped[int] = mapped_column(ForeignKey("altili.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(10))  # simitci/harbi/ortakli
    ad: Mapped[str] = mapped_column(String(40))
    bedel: Mapped[float] = mapped_column(Float)
    komb: Mapped[int] = mapped_column(Integer)
    altili: Mapped[Altili] = relationship(back_populates="kademeler")
    ayaklar: Mapped[list["AltiliAyak"]] = relationship(
        back_populates="kademe", cascade="all, delete-orphan")


class AltiliAyak(Base):
    __tablename__ = "altili_ayak"
    id: Mapped[int] = mapped_column(primary_key=True)
    kademe_id: Mapped[int] = mapped_column(ForeignKey("altili_kademe.id", ondelete="CASCADE"), index=True)
    kno: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    banko_lider: Mapped[bool] = mapped_column(Boolean, default=False)
    secilen: Mapped[list] = mapped_column(JSON)  # [at_no...]
    secilen_atlar: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{at_no, at}...]
    kademe: Mapped[AltiliKademe] = relationship(back_populates="ayaklar")


class AltiliSonuc(Base):
    __tablename__ = "altili_sonuc"
    id: Mapped[int] = mapped_column(primary_key=True)
    altili_id: Mapped[int] = mapped_column(ForeignKey("altili.id", ondelete="CASCADE"), unique=True)
    winners: Mapped[list] = mapped_column(JSON)         # [at_no...]
    ikramiye: Mapped[float | None] = mapped_column(Float, nullable=True)
    tier_hits: Mapped[dict] = mapped_column(JSON)       # {simitci:6, harbi:6, ortakli:6}
    altili: Mapped[Altili] = relationship(back_populates="sonuc")


class KosuBahis(Base):
    """Koşu Analizleri — bir hipodrom gününün alt-bahis analizleri (13 tür).
    Tek-koşu bahisleri (legs=[kno]) ve çok-ayak bahisleri (legs=[k..k+L-1]) ortak tablo.
    Grading alanları (tuttu/ganyan/net/kazanan) sonuç gelince doldurulur."""
    __tablename__ = "kosu_bahis"
    id: Mapped[int] = mapped_column(primary_key=True)
    gh_id: Mapped[int] = mapped_column(ForeignKey("gun_hipodrom.id", ondelete="CASCADE"), index=True)
    bas_kosu: Mapped[int] = mapped_column(Integer, index=True)  # başlangıç koşu no
    tip: Mapped[str] = mapped_column(String(20))               # PLASE, IKILI, CIFTE...
    aile: Mapped[str] = mapped_column(String(6))               # tek / ayak
    ad: Mapped[str] = mapped_column(String(40))                # görünen ad
    legs: Mapped[list] = mapped_column(JSON)                   # [kno...]
    kolonlar: Mapped[list] = mapped_column(JSON)               # [[at_no...]...]
    secim_atlar: Mapped[list] = mapped_column(JSON)            # tek:[{at_no,at}] ayak:[[...]]
    kombinasyon: Mapped[int] = mapped_column(Integer)
    birim: Mapped[float] = mapped_column(Float)
    kupon_bedeli: Mapped[float] = mapped_column(Float)
    misli: Mapped[int] = mapped_column(Integer)
    max_butce: Mapped[int] = mapped_column(Integer)
    # --- grading (sonuç) ---
    tuttu: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ganyan: Mapped[float | None] = mapped_column(Float, nullable=True)
    net: Mapped[float | None] = mapped_column(Float, nullable=True)
    kazanan: Mapped[list | None] = mapped_column(JSON, nullable=True)  # gerçek kazanan kombo
    gh: Mapped[GunHipodrom] = relationship(back_populates="bahisler")


# ---------------- Kullanıcı / Üyelik ----------------

class Kullanici(Base):
    __tablename__ = "kullanici"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    sifre_hash: Mapped[str] = mapped_column(String(255))
    email_dogrulandi: Mapped[bool] = mapped_column(Boolean, default=False)
    tier: Mapped[str] = mapped_column(String(10), default="standart")  # standart/premium/vip
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    aktif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    uyelikler: Mapped[list["Uyelik"]] = relationship(
        back_populates="kullanici", cascade="all, delete-orphan")
    bildirimler: Mapped[list["Bildirim"]] = relationship(
        back_populates="kullanici", cascade="all, delete-orphan")
    cihaz_tokenlari: Mapped[list["DeviceToken"]] = relationship(
        back_populates="kullanici", cascade="all, delete-orphan")


class Uyelik(Base):
    """Abonelik kaydı (MVP'de mock; sonra Google Play Billing doğrulaması bağlanır)."""
    __tablename__ = "uyelik"
    id: Mapped[int] = mapped_column(primary_key=True)
    kullanici_id: Mapped[int] = mapped_column(ForeignKey("kullanici.id", ondelete="CASCADE"), index=True)
    tier: Mapped[str] = mapped_column(String(10))  # premium/vip
    baslangic: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    bitis: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kaynak: Mapped[str] = mapped_column(String(20), default="mock")  # mock/google_play
    aktif: Mapped[bool] = mapped_column(Boolean, default=True)
    kullanici: Mapped[Kullanici] = relationship(back_populates="uyelikler")


class DogrulamaKodu(Base):
    """Email doğrulama / giriş kodu."""
    __tablename__ = "dogrulama_kodu"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    kod: Mapped[str] = mapped_column(String(10))
    son_gecerlilik: Mapped[datetime] = mapped_column(DateTime)
    kullanildi: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Bildirim(Base):
    """Admin tarafindan gonderilen uygulama ici bildirim."""
    __tablename__ = "bildirim"
    id: Mapped[int] = mapped_column(primary_key=True)
    kullanici_id: Mapped[int | None] = mapped_column(
        ForeignKey("kullanici.id", ondelete="CASCADE"), index=True, nullable=True)
    baslik: Mapped[str] = mapped_column(String(120))
    mesaj: Mapped[str] = mapped_column(Text)
    hedef_tier: Mapped[str | None] = mapped_column(String(10), nullable=True)
    okundu: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    kullanici: Mapped[Kullanici | None] = relationship(back_populates="bildirimler")


class GonderilenBildirim(Base):
    """Canlı bildirim idempotency kaydı (reimport'tan BAĞIMSIZ).

    Sonuç tabloları (kosu_sonuc/altili_sonuc) her reimport'ta cascade silinip
    yeniden yazıldığından, "bu bildirimi gönderdim mi?" durumu orada tutulamaz.
    Bu tablo doğal anahtarla (tarih+hipodrom+tip+no+aşama) gönderimi izler.

    anahtar örnekleri:
      "2026-06-02|ANKARA|kosu|1|gayriresmi"
      "2026-06-02|ANKARA|kosu|1|resmi"
      "2026-06-02|ANKARA|altili|0|ayak"
      "2026-06-02|ANKARA|altili|0|tam"
      "2026-06-03|yayin"
    """
    __tablename__ = "gonderilen_bildirim"
    id: Mapped[int] = mapped_column(primary_key=True)
    anahtar: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DeviceToken(Base):
    """FCM push için cihaz kayıt token'ı (kullanıcı başına 0..n cihaz)."""
    __tablename__ = "device_token"
    id: Mapped[int] = mapped_column(primary_key=True)
    kullanici_id: Mapped[int] = mapped_column(
        ForeignKey("kullanici.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(10), default="android")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    kullanici: Mapped[Kullanici] = relationship(back_populates="cihaz_tokenlari")
