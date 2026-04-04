"""add artifacts columns to processed_records

Revision ID: 20240403_add_processed_record_artifacts
Revises: rev_20240402_proc_ds
Create Date: 2026-04-03 06:06:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "rev_20240403_record_artifacts"
down_revision: Union[str, None] = "rev_20240402_proc_ds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE IF EXISTS processed_records
            ADD COLUMN IF NOT EXISTS scaled_data JSONB
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE IF EXISTS processed_records
            ADD COLUMN IF NOT EXISTS component_scores JSONB
            """
        )
    )


def downgrade() -> None:
    op.drop_column("processed_records", "component_scores")
    op.drop_column("processed_records", "scaled_data")
