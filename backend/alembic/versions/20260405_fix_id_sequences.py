"""fix primary key sequences for all tables

After data migration the id columns lost their auto-increment sequences.
This migration ensures every table has a working SERIAL-like sequence so
INSERT statements without an explicit id value work correctly.

Revision ID: rev_20260405_fix_sequences
Revises: rev_20260404_seed_admin
Create Date: 2026-04-05 06:40:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "rev_20260405_fix_sequences"
down_revision: Union[str, None] = "rev_20260404_seed_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ["users", "wells", "processed_datasets", "processed_records"]


def upgrade() -> None:
    for table in TABLES:
        seq = f"{table}_id_seq"
        # Create sequence if missing, attach to column, and sync to max(id).
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq}")
        op.execute(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN id SET DEFAULT nextval('{seq}')"
        )
        op.execute(f"ALTER SEQUENCE {seq} OWNED BY {table}.id")
        op.execute(
            f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
        )


def downgrade() -> None:
    for table in TABLES:
        seq = f"{table}_id_seq"
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id DROP DEFAULT")
        op.execute(f"DROP SEQUENCE IF EXISTS {seq}")
