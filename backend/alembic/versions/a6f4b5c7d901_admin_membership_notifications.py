"""admin membership notifications

Revision ID: a6f4b5c7d901
Revises: 4605ae948edf
Create Date: 2026-06-02 11:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6f4b5c7d901"
down_revision: Union[str, None] = "4605ae948edf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("kullanici", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("aktif", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.create_table(
        "bildirim",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kullanici_id", sa.Integer(), nullable=True),
        sa.Column("baslik", sa.String(length=120), nullable=False),
        sa.Column("mesaj", sa.Text(), nullable=False),
        sa.Column("hedef_tier", sa.String(length=10), nullable=True),
        sa.Column("okundu", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["kullanici_id"], ["kullanici.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("bildirim", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_bildirim_kullanici_id"), ["kullanici_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("bildirim", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bildirim_kullanici_id"))
    op.drop_table("bildirim")
    with op.batch_alter_table("kullanici", schema=None) as batch_op:
        batch_op.drop_column("aktif")
        batch_op.drop_column("is_admin")
