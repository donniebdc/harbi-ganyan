"""add stateful refresh sessions

Revision ID: 5d272977ff1d
Revises: j6k7l8m9n010
Create Date: 2026-08-03 18:22:20.811007

Kapsam (Faz X2F-1):
  - auth_session tablosu: stateful refresh token persistence altyapisi
  - Mevcut auth endpoint davranisi DEGISTIRILMEZ; X2F-2'de devreye girer.
  - UserDevice (fiziksel cihaz) ile karistirilmamali: bu tablo token lifecycle'ini izler.

  Alanlar:
    token_hash    : SHA-256 hex (ham token asla saklanmaz)
    token_family_id: rotation zincirini temsil eden UUID4
    jti           : JWT token'in benzersiz ID'si
    revoke_reason : LOGOUT | ALL_DEVICES_LOGOUT | PASSWORD_CHANGED |
                    USER_DISABLED | ROLE_CHANGED | TOKEN_REUSE | ADMIN_REVOKE |
                    EXPIRED | SECURITY_EVENT | REPLACED
    client_type   : PANEL | MOBILE | API | UNKNOWN
    replaced_by_id: rotation zinciri icin self-reference FK
    ip_hash / user_agent_hash: PII minimizasyonu — ham deger degil SHA-256 hash

  NOT: Tablo production DB'de daha once olusturulmustu (IF NOT EXISTS ile guvenli).

UYARI (downgrade): auth_session tablosu GERI DONUSSUZ silinir; oncesinde yedek alinmalidir.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '5d272977ff1d'
down_revision: Union[str, None] = 'j6k7l8m9n010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'auth_session',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('token_family_id', sa.String(length=36), nullable=False),
        sa.Column('jti', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revoke_reason', sa.String(length=20), nullable=True),
        sa.Column('replaced_by_id', sa.Integer(), nullable=True),
        sa.Column('client_type', sa.String(length=10), nullable=False),
        sa.Column('device_name', sa.String(length=100), nullable=True),
        sa.Column('user_agent_hash', sa.String(length=64), nullable=True),
        sa.Column('ip_hash', sa.String(length=64), nullable=True),
        sa.Column('app_version', sa.String(length=20), nullable=True),
        sa.CheckConstraint(
            "client_type IN ('PANEL','MOBILE','API','UNKNOWN')",
            name='ck_auth_session_client_type',
        ),
        sa.CheckConstraint(
            "revoke_reason IN ("
            "'LOGOUT','ALL_DEVICES_LOGOUT','PASSWORD_CHANGED','USER_DISABLED',"
            "'ROLE_CHANGED','TOKEN_REUSE','ADMIN_REVOKE','EXPIRED',"
            "'SECURITY_EVENT','REPLACED') OR revoke_reason IS NULL",
            name='ck_auth_session_revoke_reason',
        ),
        sa.ForeignKeyConstraint(
            ['replaced_by_id'], ['auth_session.id'],
            name='auth_session_replaced_by_id_fkey',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['kullanici.id'],
            name='auth_session_user_id_fkey',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name='auth_session_pkey'),
        sa.UniqueConstraint('jti', name='uq_auth_session_jti'),
        sa.UniqueConstraint('token_hash', name='uq_auth_session_token_hash'),
        if_not_exists=True,
    )
    op.create_index(
        'ix_auth_session_user_id', 'auth_session', ['user_id'],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        'ix_auth_session_token_family_id', 'auth_session', ['token_family_id'],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        'ix_auth_session_expires', 'auth_session', ['expires_at'],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        'ix_auth_session_user_revoked', 'auth_session', ['user_id', 'revoked_at'],
        unique=False, if_not_exists=True,
    )
    op.create_index(
        'ix_auth_session_family_revoked', 'auth_session', ['token_family_id', 'revoked_at'],
        unique=False, if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index('ix_auth_session_family_revoked', table_name='auth_session', if_exists=True)
    op.drop_index('ix_auth_session_user_revoked', table_name='auth_session', if_exists=True)
    op.drop_index('ix_auth_session_expires', table_name='auth_session', if_exists=True)
    op.drop_index('ix_auth_session_token_family_id', table_name='auth_session', if_exists=True)
    op.drop_index('ix_auth_session_user_id', table_name='auth_session', if_exists=True)
    op.drop_table('auth_session', if_exists=True)
