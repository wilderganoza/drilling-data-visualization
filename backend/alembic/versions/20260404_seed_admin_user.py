"""seed admin base user

Revision ID: rev_20260404_seed_admin
Revises: rev_20240403_record_artifacts
Create Date: 2026-04-04 23:40:00.000000
"""

import logging
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "rev_20260404_seed_admin"
down_revision: Union[str, None] = "rev_20240403_record_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

ADMIN_USERNAME = os.environ.get("ADMIN_SEED_USERNAME", "admin")
ADMIN_FULL_NAME = "Administrator"


def upgrade() -> None:
    # La contraseña inicial debe venir del entorno: nunca material de
    # credenciales (ni siquiera hasheado) versionado en el repositorio.
    admin_password = os.environ.get("ADMIN_SEED_PASSWORD")
    if not admin_password:
        logger.warning(
            "ADMIN_SEED_PASSWORD not set; skipping admin user seed. "
            "Create the initial admin manually or re-run with the variable set."
        )
        return

    from passlib.context import CryptContext

    password_hash = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(admin_password)

    op.execute(
        sa.text(
            """
            INSERT INTO users (username, full_name, hashed_password, is_active, is_admin, created_at, updated_at)
            SELECT :username, :full_name, :password_hash, true, true, NOW(), NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM users
            )
            """
        ).bindparams(
            username=ADMIN_USERNAME,
            full_name=ADMIN_FULL_NAME,
            password_hash=password_hash,
        )
    )


def downgrade() -> None:
    # Keep data on downgrade to avoid accidentally removing access user.
    pass
