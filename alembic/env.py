import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure app package is importable
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.core.config import settings  # noqa: E402
from app.models.legacy import Base  # noqa: E402
from app.models import attachment, capture, daily_report, engineering, hierarchy, npt, planning, planning_capture, registers, roles, time_summary, validation  # noqa: E402,F401 (register ops tables on the shared metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# app.models.OpsBase shares Base's MetaData (see app/ops/models/base.py),
# so importing the ops model modules above is enough to register their
# tables here — no second target_metadata needed.
target_metadata = Base.metadata

# well_data/annotations are reflected at runtime (app/db/session.py), not
# ORM-declared — without this filter, autogenerate sees them as "not in
# target_metadata" and proposes dropping them on every future revision.
REFLECTED_ONLY_TABLES = {"well_data", "annotations"}


def include_name(name, type_, parent_names):
    if type_ == "table" and name in REFLECTED_ONLY_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    if configuration is None:
        raise RuntimeError("Alembic configuration section missing")

    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
