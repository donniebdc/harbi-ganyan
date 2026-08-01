"""billing fields

Revision ID: g3h4i5j6k007
Revises: f2e4c6d8a012
Branch_labels: None
Depends_on: None
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "g3h4i5j6k007"
down_revision: Union[str, None] = "f2e4c6d8a012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("uyelik", schema=None) as batch_op:
        batch_op.add_column(sa.Column("purchase_token", sa.String(500), nullable=True))
        batch_op.add_column(sa.Column("google_product_id", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_uyelik_purchase_token", ["purchase_token"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("uyelik", schema=None) as batch_op:
        batch_op.drop_index("ix_uyelik_purchase_token")
        batch_op.drop_column("expires_at")
        batch_op.drop_column("google_product_id")
        batch_op.drop_column("purchase_token")
