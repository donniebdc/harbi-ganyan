"""kosu_bahis: Koşu Analizleri alt-bahis tablosu (13 tür) + grading

Revision ID: c8a2d4e6f105
Revises: b7e1c2f3a004
Create Date: 2026-06-03 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8a2d4e6f105"
down_revision: Union[str, None] = "b7e1c2f3a004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kosu_bahis",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gh_id", sa.Integer(),
                  sa.ForeignKey("gun_hipodrom.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bas_kosu", sa.Integer(), nullable=False),
        sa.Column("tip", sa.String(length=20), nullable=False),
        sa.Column("aile", sa.String(length=6), nullable=False),
        sa.Column("ad", sa.String(length=40), nullable=False),
        sa.Column("legs", sa.JSON(), nullable=False),
        sa.Column("kolonlar", sa.JSON(), nullable=False),
        sa.Column("secim_atlar", sa.JSON(), nullable=False),
        sa.Column("kombinasyon", sa.Integer(), nullable=False),
        sa.Column("birim", sa.Float(), nullable=False),
        sa.Column("kupon_bedeli", sa.Float(), nullable=False),
        sa.Column("misli", sa.Integer(), nullable=False),
        sa.Column("max_butce", sa.Integer(), nullable=False),
        sa.Column("tuttu", sa.Boolean(), nullable=True),
        sa.Column("ganyan", sa.Float(), nullable=True),
        sa.Column("net", sa.Float(), nullable=True),
        sa.Column("kazanan", sa.JSON(), nullable=True),
    )
    op.create_index("ix_kosu_bahis_gh_id", "kosu_bahis", ["gh_id"])
    op.create_index("ix_kosu_bahis_bas_kosu", "kosu_bahis", ["bas_kosu"])


def downgrade() -> None:
    op.drop_index("ix_kosu_bahis_bas_kosu", table_name="kosu_bahis")
    op.drop_index("ix_kosu_bahis_gh_id", table_name="kosu_bahis")
    op.drop_table("kosu_bahis")
