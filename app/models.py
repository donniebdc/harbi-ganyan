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
                        CheckConstraint, Index, Text, JSON, Date, DateTime, func, text)
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class Gun(Base):
    __tablename__ = "gun"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date_t] = mapped_column(Date, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Canlı takip: en son ne zaman / hangi sebeple analiz (yeniden) üretildi.
    # reimport'ta Gun satırı silinmediği için (import_to_db._get_or_create_gun) korunur.
    son_analiz: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    son_analiz_sebep: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tahmin_asamasi: Mapped[str] = mapped_column(String(15), default='on_tahmin')
    # Premium içerik (Sprint 1) — JSONB sütunlar DB'de mevcut; ORM mapping korunmalı.
    daily_panel: Mapped[dict | None] = mapped_column(PG_JSONB, nullable=True)
    surpriz_radar: Mapped[dict | None] = mapped_column(PG_JSONB, nullable=True)
    hipodromlar: Mapped[list["GunHipodrom"]] = relationship(
        back_populates="gun", cascade="all, delete-orphan")


class GunHipodrom(Base):
    __tablename__ = "gun_hipodrom"
    __table_args__ = (UniqueConstraint("gun_id", "hipodrom"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    gun_id: Mapped[int] = mapped_column(ForeignKey("gun.id", ondelete="CASCADE"), index=True)
    hipodrom: Mapped[str] = mapped_column(String(40), index=True)
    birim: Mapped[float] = mapped_column(Float)
    # Publication metadata (Sprint14 Asama3B) — additive/nullable.
    # publication_phase: LEGACY | PRELIMINARY | FINAL
    # publication_status: PUBLISHED | NO_CHANGE | FAILED_CANDIDATE
    publication_phase: Mapped[str | None] = mapped_column(String(20), nullable=True)
    publication_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preliminary_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    final_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    pub_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    gun: Mapped[Gun] = relationship(back_populates="hipodromlar")
    kosular: Mapped[list["Kosu"]] = relationship(
        back_populates="gh", cascade="all, delete-orphan")
    altililar: Mapped[list["Altili"]] = relationship(
        back_populates="gh", cascade="all, delete-orphan")
    bahisler: Mapped[list["KosuBahis"]] = relationship(
        back_populates="gh", cascade="all, delete-orphan")
    surdirek: Mapped["Surdirek | None"] = relationship(
        back_populates="gh", cascade="all, delete-orphan", uselist=False)


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
    ktip: Mapped[str] = mapped_column(String(40), default="")  # koşu tipi (görünüm)
    guven: Mapped[str] = mapped_column(String(30), default="")  # tahmin güven etiketi (Sprint 1)
    analiz_puanlari: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{at_no, at, ana}...]
    # Premium içerik (Sprint 1) — JSONB sütunlar DB'de mevcut; ORM mapping korunmalı.
    zorluk: Mapped[dict | None] = mapped_column(PG_JSONB, nullable=True)
    agf_radar: Mapped[dict | None] = mapped_column(PG_JSONB, nullable=True)
    aciklama_kartlari: Mapped[list | None] = mapped_column(PG_JSONB, nullable=True)
    # Harbi Secim publish-time persistence (Sprint14 Asama3B) — additive/nullable.
    # Payload: {tip, ui_baslik, adet, adaylar, gerekce, is_surdirek,
    #           surdirek_horse_no, generated_at, source_revision, content_hash}
    harbi_secim: Mapped[dict | None] = mapped_column(PG_JSONB, nullable=True)
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
    jokey: Mapped[str] = mapped_column(String(40), default="")    # kısa jokey adı (görünüm)
    apranti: Mapped[bool] = mapped_column(Boolean, default=False)  # apranti jokey mi
    eku_partner_nos: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [at_no...] (Sprint 1)
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


class Surdirek(Base):
    """Bir günün hipodromunda seçilen sürdirek (banko) atı."""
    __tablename__ = "surdirek"
    id: Mapped[int] = mapped_column(primary_key=True)
    gh_id: Mapped[int] = mapped_column(ForeignKey("gun_hipodrom.id", ondelete="CASCADE"), unique=True)
    race_no: Mapped[int] = mapped_column(Integer)
    horse_no: Mapped[int] = mapped_column(Integer)
    horse_name: Mapped[str] = mapped_column(String(60), default="")
    gap: Mapped[float] = mapped_column(Float, default=0.0)
    norm_score: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    bucket: Mapped[str] = mapped_column(String(30), default="")  # kosu tipi kategorisi
    gh: Mapped["GunHipodrom"] = relationship(back_populates="surdirek")


# ---------------- Kullanıcı / Üyelik ----------------

class Kullanici(Base):
    __tablename__ = "kullanici"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    sifre_hash: Mapped[str] = mapped_column(String(255))
    email_dogrulandi: Mapped[bool] = mapped_column(Boolean, default=False)
    tier: Mapped[str] = mapped_column(String(10), default="standart")  # standart/premium/vip
    vip_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    vip_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "google_play"
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Rol: USER | EDITOR | ADMIN — yetkilendirme her istekte DB'den okunur.
    # is_admin geriye uyumluluk icin korunur; senkron migration backfill'de yapilir
    # (ORM event/otomatik senkron YOK).
    rol: Mapped[str] = mapped_column(String(20), nullable=False, default="USER",
                                     server_default="USER", index=True)
    aktif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    uyelikler: Mapped[list["Uyelik"]] = relationship(
        back_populates="kullanici", cascade="all, delete-orphan")
    bildirimler: Mapped[list["Bildirim"]] = relationship(
        back_populates="kullanici", cascade="all, delete-orphan")
    cihaz_tokenlari: Mapped[list["DeviceToken"]] = relationship(
        back_populates="kullanici", cascade="all, delete-orphan")
    cihazlar: Mapped[list["UserDevice"]] = relationship(
        back_populates="kullanici", cascade="all, delete-orphan")
    editor_profil: Mapped["EditorProfil | None"] = relationship(
        back_populates="kullanici", cascade="all, delete-orphan", uselist=False)


class Uyelik(Base):
    """Google Play abonelik kaydı."""
    __tablename__ = "uyelik"
    id: Mapped[int] = mapped_column(primary_key=True)
    kullanici_id: Mapped[int] = mapped_column(ForeignKey("kullanici.id", ondelete="CASCADE"), index=True)
    tier: Mapped[str] = mapped_column(String(10))  # premium/vip
    baslangic: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    bitis: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kaynak: Mapped[str] = mapped_column(String(20), default="google_play")
    aktif: Mapped[bool] = mapped_column(Boolean, default=True)
    # Google Play alanları
    purchase_token: Mapped[str | None] = mapped_column(String(500), nullable=True, unique=True)
    google_product_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # = vip_until
    plan_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "weekly" / "monthly"
    subscription_state: Mapped[str | None] = mapped_column(String(60), nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    latest_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    auto_renewing: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    linked_purchase_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_google_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class UserDevice(Base):
    """Oturum güvenliği — kullanıcı başına maksimum 2 aktif cihaz."""
    __tablename__ = "user_device"
    __table_args__ = (UniqueConstraint("user_id", "device_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("kullanici.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str] = mapped_column(String(100), index=True)
    platform: Mapped[str] = mapped_column(String(10), default="android")
    app_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    push_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kullanici: Mapped[Kullanici] = relationship(back_populates="cihazlar")


# ---------------- Editör Tahmin Sistemi (Faz 1) ----------------
# Model tahminleri bu tablolara YAZILMAZ; MODEL kaynagi mevcut kosu tablolarindan
# adapter ile okunur. Editor tahminleri kosu.id'ye FK ile BAGLANMAZ: --uret tam
# yeniden yazimda kosu.id degistigi icin dogal anahtar (tarih, hipodrom, kno)
# kullanilir — model pipeline'in delete/rewrite davranisi editor verisini etkileyemez.

class TahminKaynak(Base):
    """Tahmin kaynagi: MODEL (adapter, tek seed satiri) veya EDITOR (1:1 profil)."""
    __tablename__ = "tahmin_kaynak"
    __table_args__ = (
        CheckConstraint("kaynak_tipi IN ('MODEL','EDITOR')",
                        name="ck_tahmin_kaynak_tipi"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    kaynak_tipi: Mapped[str] = mapped_column(String(10))  # MODEL | EDITOR
    kod: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    gorunen_ad: Mapped[str] = mapped_column(String(60))
    aktif: Mapped[bool] = mapped_column(Boolean, default=True)
    sira: Mapped[int] = mapped_column(Integer, default=0)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    editor_profil: Mapped["EditorProfil | None"] = relationship(
        back_populates="kaynak", uselist=False)
    tahminler: Mapped[list["KosuTahmin"]] = relationship(back_populates="kaynak")


class EditorProfil(Base):
    """Editor kimligi — kullanici 1:1, kaynak 1:1."""
    __tablename__ = "editor_profil"
    id: Mapped[int] = mapped_column(primary_key=True)
    kullanici_id: Mapped[int] = mapped_column(
        ForeignKey("kullanici.id", ondelete="CASCADE"), unique=True)
    kaynak_id: Mapped[int] = mapped_column(
        ForeignKey("tahmin_kaynak.id", ondelete="RESTRICT"), unique=True)
    public_ad: Mapped[str] = mapped_column(String(60))
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aktif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kullanici: Mapped[Kullanici] = relationship(back_populates="editor_profil")
    kaynak: Mapped[TahminKaynak] = relationship(back_populates="editor_profil")


class KosuTahmin(Base):
    """Editor tahmini (koşu basina). Kosu'ya FK YOK — dogal anahtar kullanilir.

    Ayni (tarih, hipodrom, kno, kaynak) icin status != CANCELLED tek satir
    (partial unique index). ana_at_no'nun secim listesinde olmasi API katmaninda
    dogrulanir. version: optimistic locking."""
    __tablename__ = "kosu_tahmin"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','PUBLISHED','LOCKED','CANCELLED')",
            name="ck_kosu_tahmin_status"),
        Index("ix_kosu_tahmin_kaynak_status", "kaynak_id", "status"),
        Index("ix_kosu_tahmin_dogal", "tarih", "hipodrom", "kno"),
        Index("uq_kosu_tahmin_aktif", "tarih", "hipodrom", "kno", "kaynak_id",
              unique=True,
              postgresql_where=text("status <> 'CANCELLED'"),
              sqlite_where=text("status <> 'CANCELLED'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tarih: Mapped[date_t] = mapped_column(Date)
    hipodrom: Mapped[str] = mapped_column(String(40))
    kno: Mapped[int] = mapped_column(Integer)
    kaynak_id: Mapped[int] = mapped_column(
        ForeignKey("tahmin_kaynak.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")
    ana_at_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yorum: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("kullanici.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kaynak: Mapped[TahminKaynak] = relationship(back_populates="tahminler")
    olusturan: Mapped[Kullanici] = relationship()
    secimler: Mapped[list["KosuTahminSecim"]] = relationship(
        back_populates="tahmin", cascade="all, delete-orphan",
        order_by="KosuTahminSecim.sira")
    revizyonlar: Mapped[list["KosuTahminRevizyon"]] = relationship(
        back_populates="tahmin", cascade="all, delete-orphan")
    sonuc: Mapped["KosuTahminSonuc | None"] = relationship(
        back_populates="tahmin", cascade="all, delete-orphan", uselist=False)


class KosuTahminSecim(Base):
    """Tahmindeki at secimi (normalize satir)."""
    __tablename__ = "kosu_tahmin_secim"
    __table_args__ = (
        UniqueConstraint("tahmin_id", "at_no"),
        UniqueConstraint("tahmin_id", "sira"),
        CheckConstraint("sira > 0", name="ck_kosu_tahmin_secim_sira"),
        CheckConstraint("at_no > 0", name="ck_kosu_tahmin_secim_at_no"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tahmin_id: Mapped[int] = mapped_column(
        ForeignKey("kosu_tahmin.id", ondelete="CASCADE"), index=True)
    at_no: Mapped[int] = mapped_column(Integer)
    at_ad: Mapped[str] = mapped_column(String(60), default="")  # ad snapshot
    sira: Mapped[int] = mapped_column(Integer)  # 1..n
    ana_tercih: Mapped[bool] = mapped_column(Boolean, default=False)
    etiket: Mapped[str | None] = mapped_column(String(20), nullable=True)  # TEK_TERCIH vb.
    tahmin: Mapped[KosuTahmin] = relationship(back_populates="secimler")


class KosuTahminRevizyon(Base):
    """Yayin/degisiklik denetim izi (audit)."""
    __tablename__ = "kosu_tahmin_revizyon"
    __table_args__ = (
        UniqueConstraint("tahmin_id", "version"),
        CheckConstraint("version > 0", name="ck_kosu_tahmin_revizyon_version"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tahmin_id: Mapped[int] = mapped_column(
        ForeignKey("kosu_tahmin.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)  # {status, ana_at_no, yorum, secimler}
    degistiren: Mapped[int] = mapped_column(
        ForeignKey("kullanici.id", ondelete="RESTRICT"))
    degisme_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sebep: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tahmin: Mapped[KosuTahmin] = relationship(back_populates="revizyonlar")


class KosuTahminSonuc(Base):
    """Sonuc degerlendirmesi — kosu_sonuc'tan snapshot (reimport'tan bagimsiz)."""
    __tablename__ = "kosu_tahmin_sonuc"
    __table_args__ = (
        CheckConstraint("kazanan_at_no > 0", name="ck_kosu_tahmin_sonuc_at_no"),
        CheckConstraint("secim_adedi >= 0", name="ck_kosu_tahmin_sonuc_secim_adedi"),
        CheckConstraint("kazanan_sira IS NULL OR kazanan_sira > 0",
                        name="ck_kosu_tahmin_sonuc_kazanan_sira"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tahmin_id: Mapped[int] = mapped_column(
        ForeignKey("kosu_tahmin.id", ondelete="CASCADE"), unique=True)
    kazanan_at_no: Mapped[int] = mapped_column(Integer)
    kazanan_secimde: Mapped[bool] = mapped_column(Boolean)
    ana_tercih_kazandi: Mapped[bool] = mapped_column(Boolean)
    secim_adedi: Mapped[int] = mapped_column(Integer)
    kazanan_sira: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ganyan: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tahmin: Mapped[KosuTahmin] = relationship(back_populates="sonuc")
