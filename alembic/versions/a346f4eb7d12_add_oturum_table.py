"""add_oturum_table

Revision ID: a346f4eb7d12
Revises: f2e4c6d8a012
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'a346f4eb7d12'
down_revision = 'f2e4c6d8a012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'oturum',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kullanici_id', sa.Integer(),
                  sa.ForeignKey('kullanici.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('cihaz_id', sa.String(64), nullable=True),
        sa.Column('ip', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.String(256), nullable=True),
        sa.Column('olusturma', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('son_kullanim', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('gecerli', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    op.drop_table('oturum')
