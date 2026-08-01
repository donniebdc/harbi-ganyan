# -*- coding: utf-8 -*-
"""add editor roles and prediction tables

Revision ID: j6k7l8m9n010
Revises: e7d79758fd02
Create Date: 2026-08-01

Kapsam (Faz 1A):
  - kullanici.rol (USER|EDITOR|ADMIN) + backfill (is_admin=true -> ADMIN) + CHECK + index
  - 6 yeni tablo: tahmin_kaynak, editor_profil, kosu_tahmin, kosu_tahmin_secim,
    kosu_tahmin_revizyon, kosu_tahmin_sonuc
  - MODEL seed satiri (idempotent: ON CONFLICT (kod) DO NOTHING)

Mevcut model tablolarina (gun, gun_hipodrom, kosu, kosu_bes, kosu_sonuc, surdirek,
altili*, kosu_bahis) DOKUNULMAZ. kosu tablosuna FK YOKTUR: editor tahminleri dogal
anahtar (tarih, hipodrom, kno) ile baglanir (--uret tam yeniden yazimda kosu.id
degisebildigi icin).

UYARI (downgrade): editor verileri (tahmin_kaynak, editor_profil, kosu_tahmin ve
child tablolari) GERI DONUSSUZ silinir; kullanici.rol sutunu kaldirilir. is_admin
alanina ve kullanici satirlarina DOKUNULMAZ. Production'da downgrade calistirmadan
once yedek alinmalidir.
"""
from alembic import op
import sqlalchemy as sa

revision = "j6k7l8m9n010"
down_revision = "e7d79758fd02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1) kullanici.rol ──────────────────────────────────────────────────────
    # server_default ile NOT NULL guvenli eklenir (mevcut satirlar USER olur).
    op.add_column("kullanici", sa.Column(
        "rol", sa.String(length=20), nullable=False, server_default="USER"))
    # Backfill: mevcut adminler ADMIN rolu alir (is_admin degismez).
    op.execute("UPDATE kullanici SET rol = 'ADMIN' WHERE is_admin = true")
    op.create_check_constraint(
        "ck_kullanici_rol", "kullanici", "rol IN ('USER','EDITOR','ADMIN')")
    op.create_index("ix_kullanici_rol", "kullanici", ["rol"])

    # ── 2) tahmin_kaynak ──────────────────────────────────────────────────────
    op.create_table(
        "tahmin_kaynak",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kaynak_tipi", sa.String(length=10), nullable=False),
        sa.Column("kod", sa.String(length=30), nullable=False),
        sa.Column("gorunen_ad", sa.String(length=60), nullable=False),
        sa.Column("aktif", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sira", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avatar_url", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("kaynak_tipi IN ('MODEL','EDITOR')",
                           name="ck_tahmin_kaynak_tipi"),
        sa.UniqueConstraint("kod", name="uq_tahmin_kaynak_kod"),
    )
    op.create_index("ix_tahmin_kaynak_kod", "tahmin_kaynak", ["kod"])

    # ── 3) editor_profil ──────────────────────────────────────────────────────
    op.create_table(
        "editor_profil",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kullanici_id", sa.Integer(),
                  sa.ForeignKey("kullanici.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kaynak_id", sa.Integer(),
                  sa.ForeignKey("tahmin_kaynak.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("public_ad", sa.String(length=60), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.String(length=255), nullable=True),
        sa.Column("aktif", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("kullanici_id", name="uq_editor_profil_kullanici"),
        sa.UniqueConstraint("kaynak_id", name="uq_editor_profil_kaynak"),
    )

    # ── 4) kosu_tahmin ────────────────────────────────────────────────────────
    op.create_table(
        "kosu_tahmin",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tarih", sa.Date(), nullable=False),
        sa.Column("hipodrom", sa.String(length=40), nullable=False),
        sa.Column("kno", sa.Integer(), nullable=False),
        sa.Column("kaynak_id", sa.Integer(),
                  sa.ForeignKey("tahmin_kaynak.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="DRAFT"),
        sa.Column("ana_at_no", sa.Integer(), nullable=True),
        sa.Column("yorum", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(),
                  sa.ForeignKey("kullanici.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','PUBLISHED','LOCKED','CANCELLED')",
            name="ck_kosu_tahmin_status"),
    )
    op.create_index("ix_kosu_tahmin_kaynak_status", "kosu_tahmin",
                    ["kaynak_id", "status"])
    op.create_index("ix_kosu_tahmin_dogal", "kosu_tahmin",
                    ["tarih", "hipodrom", "kno"])
    op.create_index("ix_kosu_tahmin_created_by", "kosu_tahmin", ["created_by"])
    op.create_index("ix_kosu_tahmin_published_at", "kosu_tahmin", ["published_at"])
    # Ayni kaynak+kosu icin tek aktif tahmin (CANCELLED haric) — partial unique.
    op.create_index("uq_kosu_tahmin_aktif", "kosu_tahmin",
                    ["tarih", "hipodrom", "kno", "kaynak_id"], unique=True,
                    postgresql_where=sa.text("status <> 'CANCELLED'"),
                    sqlite_where=sa.text("status <> 'CANCELLED'"))

    # ── 5) kosu_tahmin_secim ──────────────────────────────────────────────────
    op.create_table(
        "kosu_tahmin_secim",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tahmin_id", sa.Integer(),
                  sa.ForeignKey("kosu_tahmin.id", ondelete="CASCADE"), nullable=False),
        sa.Column("at_no", sa.Integer(), nullable=False),
        sa.Column("at_ad", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("sira", sa.Integer(), nullable=False),
        sa.Column("ana_tercih", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("etiket", sa.String(length=20), nullable=True),
        sa.UniqueConstraint("tahmin_id", "at_no", name="uq_kosu_tahmin_secim_at"),
        sa.UniqueConstraint("tahmin_id", "sira", name="uq_kosu_tahmin_secim_sira"),
        sa.CheckConstraint("sira > 0", name="ck_kosu_tahmin_secim_sira"),
        sa.CheckConstraint("at_no > 0", name="ck_kosu_tahmin_secim_at_no"),
    )
    op.create_index("ix_kosu_tahmin_secim_tahmin_id", "kosu_tahmin_secim", ["tahmin_id"])

    # ── 6) kosu_tahmin_revizyon ───────────────────────────────────────────────
    op.create_table(
        "kosu_tahmin_revizyon",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tahmin_id", sa.Integer(),
                  sa.ForeignKey("kosu_tahmin.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("degistiren", sa.Integer(),
                  sa.ForeignKey("kullanici.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("degisme_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("sebep", sa.String(length=200), nullable=True),
        sa.UniqueConstraint("tahmin_id", "version", name="uq_kosu_tahmin_revizyon"),
        sa.CheckConstraint("version > 0", name="ck_kosu_tahmin_revizyon_version"),
    )
    op.create_index("ix_kosu_tahmin_revizyon_tahmin_id", "kosu_tahmin_revizyon", ["tahmin_id"])

    # ── 7) kosu_tahmin_sonuc ──────────────────────────────────────────────────
    op.create_table(
        "kosu_tahmin_sonuc",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tahmin_id", sa.Integer(),
                  sa.ForeignKey("kosu_tahmin.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kazanan_at_no", sa.Integer(), nullable=False),
        sa.Column("kazanan_secimde", sa.Boolean(), nullable=False),
        sa.Column("ana_tercih_kazandi", sa.Boolean(), nullable=False),
        sa.Column("secim_adedi", sa.Integer(), nullable=False),
        sa.Column("kazanan_sira", sa.Integer(), nullable=True),
        sa.Column("ganyan", sa.Float(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tahmin_id", name="uq_kosu_tahmin_sonuc_tahmin"),
        sa.CheckConstraint("kazanan_at_no > 0", name="ck_kosu_tahmin_sonuc_at_no"),
        sa.CheckConstraint("secim_adedi >= 0", name="ck_kosu_tahmin_sonuc_secim_adedi"),
        sa.CheckConstraint("kazanan_sira IS NULL OR kazanan_sira > 0",
                           name="ck_kosu_tahmin_sonuc_kazanan_sira"),
    )

    # ── 8) MODEL seed (idempotent) ────────────────────────────────────────────
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "INSERT INTO tahmin_kaynak (kaynak_tipi, kod, gorunen_ad, aktif, sira) "
            "VALUES ('MODEL', 'MODEL', 'Harbi Model', true, 0) "
            "ON CONFLICT (kod) DO NOTHING")
    else:  # SQLite test uyumu
        op.execute(
            "INSERT OR IGNORE INTO tahmin_kaynak (kaynak_tipi, kod, gorunen_ad, aktif, sira) "
            "VALUES ('MODEL', 'MODEL', 'Harbi Model', 1, 0)")


def downgrade() -> None:
    # UYARI: editor verileri geri donussuz silinir (docstring'e bakin).
    op.drop_table("kosu_tahmin_sonuc")
    op.drop_index("ix_kosu_tahmin_revizyon_tahmin_id", table_name="kosu_tahmin_revizyon")
    op.drop_table("kosu_tahmin_revizyon")
    op.drop_index("ix_kosu_tahmin_secim_tahmin_id", table_name="kosu_tahmin_secim")
    op.drop_table("kosu_tahmin_secim")
    op.drop_index("uq_kosu_tahmin_aktif", table_name="kosu_tahmin")
    op.drop_index("ix_kosu_tahmin_published_at", table_name="kosu_tahmin")
    op.drop_index("ix_kosu_tahmin_created_by", table_name="kosu_tahmin")
    op.drop_index("ix_kosu_tahmin_dogal", table_name="kosu_tahmin")
    op.drop_index("ix_kosu_tahmin_kaynak_status", table_name="kosu_tahmin")
    op.drop_table("kosu_tahmin")
    op.drop_table("editor_profil")
    op.drop_index("ix_tahmin_kaynak_kod", table_name="tahmin_kaynak")
    op.drop_table("tahmin_kaynak")
    op.drop_index("ix_kullanici_rol", table_name="kullanici")
    op.drop_constraint("ck_kullanici_rol", "kullanici", type_="check")
    op.drop_column("kullanici", "rol")
