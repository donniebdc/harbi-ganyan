"""merge alembic heads before editor system

Revision ID: e7d79758fd02
Revises: a346f4eb7d12, i5j6k7l8m009
Create Date: 2026-08-01 17:23:43.492819
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7d79758fd02'
down_revision: Union[str, None] = ('a346f4eb7d12', 'i5j6k7l8m009')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
