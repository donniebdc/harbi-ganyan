"""billing v2 + device management

Revision ID: h4i5j6k7l008
Revises: g3h4i5j6k007
Branch_labels: None
Depends_on: None
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "h4i5j6k7l008"
down_revision: Union[str, None] = "g3h4i5j6k007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # kullanici: vip_until + vip_source
    with op.batch_alter_table("kullanici", schema=None) as batch_op:
        batch_op.add_column(sa.Column("vip_until", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("vip_source", sa.String(20), nullable=True))

    # uyelik: yeni alanlar
    with op.batch_alter_table("uyelik", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plan_type", sa.String(10), nullable=True))
        batch_op.add_column(sa.Column("subscription_state", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("acknowledged", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column("start_time", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("latest_order_id", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("auto_renewing", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("linked_purchase_token", sa.String(500), nullable=True))
        batch_op.add_column(sa.Column("raw_google_response", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("last_verified_at", sa.DateTime(), nullable=True))

    # user_device tablosu (yeni)
    op.create_table(
        "user_device",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(100), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False, server_default="android"),
        sa.Column("app_version", sa.String(20), nullable=True),
        sa.Column("push_token", sa.String(255), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoke_reason", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["kullanici.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "device_id"),
    )
    with op.batch_alter_table("user_device", schema=None) as batch_op:
        batch_op.create_index("ix_user_device_user_id", ["user_id"], unique=False)
        batch_op.create_index("ix_user_device_device_id", ["device_id"], unique=False)


def downgrade() -> None:
    op.drop_table("user_device")

    with op.batch_alter_table("uyelik", schema=None) as batch_op:
        for col in ["plan_type", "subscription_state", "acknowledged", "start_time",
                    "latest_order_id", "auto_renewing", "linked_purchase_token",
                    "raw_google_response", "updated_at", "last_verified_at"]:
            batch_op.drop_column(col)

    with op.batch_alter_table("kullanici", schema=None) as batch_op:
        batch_op.drop_column("vip_source")
        batch_op.drop_column("vip_until")
