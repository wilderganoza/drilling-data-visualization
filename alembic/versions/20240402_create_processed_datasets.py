"""create processed datasets tables

Revision ID: 20240402_create_processed_datasets
Revises: 
Create Date: 2026-04-02 22:23:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "rev_20240402_proc_ds"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_processed_records_dataset_id")
    op.execute("DROP INDEX IF EXISTS ix_processed_datasets_created_by")
    op.execute("DROP INDEX IF EXISTS ix_processed_datasets_well_id")
    op.execute("DROP TABLE IF EXISTS processed_records CASCADE")
    op.execute("DROP TABLE IF EXISTS processed_datasets CASCADE")

    op.create_table(
        "processed_datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("pipeline_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="completed"),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_processed_datasets_well_id",
        "processed_datasets",
        ["well_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_processed_datasets_created_by",
        "processed_datasets",
        ["created_by"],
        unique=False,
        if_not_exists=True,
    )

    op.create_table(
        "processed_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("source_record_id", sa.Integer(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_outlier", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["processed_datasets.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_processed_records_dataset_id",
        "processed_records",
        ["dataset_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_processed_records_dataset_id", table_name="processed_records")
    op.drop_table("processed_records")

    op.drop_index("ix_processed_datasets_created_by", table_name="processed_datasets")
    op.drop_index("ix_processed_datasets_well_id", table_name="processed_datasets")
    op.drop_table("processed_datasets")
