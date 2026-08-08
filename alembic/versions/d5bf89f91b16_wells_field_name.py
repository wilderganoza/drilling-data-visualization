"""wells field name

Revision ID: d5bf89f91b16
Revises: ca9ec42c1474
Create Date: 2026-07-26 16:22:04.026994

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5bf89f91b16'
down_revision: Union[str, None] = 'ca9ec42c1474'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('wells', sa.Column('field_name', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_wells_field_name'), 'wells', ['field_name'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_wells_field_name'), table_name='wells')
    op.drop_column('wells', 'field_name')
