"""add analiz_puanlari to kosu

Revision ID: e1f3a9b2c406
Revises: c8a2d4e6f105
Create Date: 2026-06-09 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f3a9b2c406"
down_revision: Union[str, None] = "c8a2d4e6f105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("kosu", schema=None) as batch_op:
        batch_op.add_column(sa.Column("analiz_puanlari", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("kosu", schema=None) as batch_op:
        batch_op.drop_column("analiz_puanlari")
