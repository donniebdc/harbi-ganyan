"""notification: kazanan_ad + gonderilen_bildirim idempotency

Revision ID: b7e1c2f3a004
Revises: d3f2a8b7c901
Create Date: 2026-06-02 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e1c2f3a004"
down_revision: Union[str, None] = "d3f2a8b7c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Kazanan at adı (bildirim metni için) — sonuç tablosunda kalıcı veri.
    with op.batch_alter_table("kosu_sonuc", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kazanan_ad", sa.String(length=60),
                                      nullable=False, server_default=""))
    # Canlı bildirim idempotency: reimport'tan bağımsız doğal-anahtar tablosu.
    op.create_table(
        "gonderilen_bildirim",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("anahtar", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_gonderilen_bildirim_anahtar", "gonderilen_bildirim",
                    ["anahtar"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_gonderilen_bildirim_anahtar", table_name="gonderilen_bildirim")
    op.drop_table("gonderilen_bildirim")
    with op.batch_alter_table("kosu_sonuc", schema=None) as batch_op:
        batch_op.drop_column("kazanan_ad")
