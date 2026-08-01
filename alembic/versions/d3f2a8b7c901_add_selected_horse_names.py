"""add selected horse names

Revision ID: d3f2a8b7c901
Revises: a6f4b5c7d901
Create Date: 2026-06-02 14:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3f2a8b7c901"
down_revision: Union[str, None] = "a6f4b5c7d901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("altili_ayak", schema=None) as batch_op:
        batch_op.add_column(sa.Column("secilen_atlar", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("altili_ayak", schema=None) as batch_op:
        batch_op.drop_column("secilen_atlar")
