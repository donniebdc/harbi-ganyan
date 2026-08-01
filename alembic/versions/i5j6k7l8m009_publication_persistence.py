"""publication persistence + harbi_secim (Sprint14 Asama3B)

Additive/nullable. Kosu.harbi_secim JSONB + GunHipodrom publication metadata.
İki mevcut head'den Kosu/GunHipodrom'u tasiyan h4i5j6k7l008 uzerine baglanir.

Revision ID: i5j6k7l8m009
Revises: h4i5j6k7l008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "i5j6k7l8m009"
down_revision = "h4i5j6k7l008"
branch_labels = None
depends_on = None


def _has_col(insp, tbl, col):
    return col in {c["name"] for c in insp.get_columns(tbl)}


def upgrade():
    # IDEMPOTENT: mevcut sutunu tekrar eklemez (kosu.harbi_secim onceden var
    # olabilir). Yalnizca eksik olanlar eklenir.
    insp = sa.inspect(op.get_bind())
    if not _has_col(insp, "kosu", "harbi_secim"):
        op.add_column("kosu", sa.Column("harbi_secim", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    gh_cols = [
        ("publication_phase", sa.String(length=20)),
        ("publication_status", sa.String(length=20)),
        ("revision", sa.Integer()),
        ("input_hash", sa.String(length=64)),
        ("content_hash", sa.String(length=64)),
        ("preliminary_published_at", sa.DateTime()),
        ("final_published_at", sa.DateTime()),
        ("frozen_at", sa.DateTime()),
        ("source_run_id", sa.String(length=64)),
        ("last_success_at", sa.DateTime()),
        ("last_attempt_at", sa.DateTime()),
        ("last_attempt_status", sa.String(length=20)),
        ("last_error", sa.Text()),
        ("pub_updated_at", sa.DateTime()),
    ]
    for name, typ in gh_cols:
        if not _has_col(insp, "gun_hipodrom", name):
            op.add_column("gun_hipodrom", sa.Column(name, typ, nullable=True))


def downgrade():
    insp = sa.inspect(op.get_bind())
    for name in ["pub_updated_at", "last_error", "last_attempt_status", "last_attempt_at",
                 "last_success_at", "source_run_id", "frozen_at", "final_published_at",
                 "preliminary_published_at", "content_hash", "input_hash", "revision",
                 "publication_status", "publication_phase"]:
        if _has_col(insp, "gun_hipodrom", name):
            op.drop_column("gun_hipodrom", name)
    if _has_col(insp, "kosu", "harbi_secim"):
        op.drop_column("kosu", "harbi_secim")
