"""add tahmin_asamasi to gun

Revision ID: f2e4c6d8a012
Revises: e1f3a9b2c406
Create Date: 2026-06-09 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2e4c6d8a012"
down_revision: Union[str, None] = "e1f3a9b2c406"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("gun", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("tahmin_asamasi", sa.String(15), nullable=False,
                      server_default="on_tahmin")
        )


def downgrade() -> None:
    with op.batch_alter_table("gun", schema=None) as batch_op:
        batch_op.drop_column("tahmin_asamasi")
