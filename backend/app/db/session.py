from sqlalchemy import create_engine, MetaData, Table, text
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, Dict, Any
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Base

logger = get_logger(__name__)


class DatabaseManager:
    """Manages connection to PostgreSQL database."""

    def __init__(self):
        self._engine = None
        self._session_factory = None
        self._metadata = None

    def initialize(self):
        """Initialize PostgreSQL connection."""
        logger.info("Initializing PostgreSQL connection...")

        self._engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        self._session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self._engine
        )
        # Create app tables (users, etc.) if they don't exist
        Base.metadata.create_all(bind=self._engine)

        # Ensure optional artifact columns exist for processed outlier results.
        # These are required to persist scaled values and PCA component scores.
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    ALTER TABLE IF EXISTS processed_records
                    ADD COLUMN IF NOT EXISTS scaled_data JSONB
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE IF EXISTS processed_records
                    ADD COLUMN IF NOT EXISTS component_scores JSONB
                    """
                )
            )

        # Ensure id sequences exist for all core tables (may be missing after
        # data migration from another database).
        for tbl in ("users", "wells", "processed_datasets", "processed_records"):
            seq = f"{tbl}_id_seq"
            conn.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq}"))
            conn.execute(text(
                f"ALTER TABLE IF EXISTS {tbl} "
                f"ALTER COLUMN id SET DEFAULT nextval('{seq}')"
            ))
            conn.execute(text(f"ALTER SEQUENCE {seq} OWNED BY {tbl}.id"))
            conn.execute(text(
                f"SELECT setval('{seq}', COALESCE("
                f"(SELECT MAX(id) FROM {tbl}), 0) + 1, false)"
            ))

        # Reflect existing tables (wells, well_data) for dynamic column access
        self._metadata = MetaData()
        self._metadata.reflect(bind=self._engine)

        logger.info(f"PostgreSQL connected: {settings.DATABASE_URL.split('@')[-1]}")

    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session."""
        if self._session_factory is None:
            raise RuntimeError("Database not initialized")
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def get_table(self, table_name: str) -> Table:
        """Get reflected table by name."""
        if self._metadata is None:
            raise RuntimeError("Database not initialized")
        return self._metadata.tables.get(table_name)

    def get_depth_table(self, table_name: str) -> Table:
        """Get reflected table (alias for compatibility)."""
        return self.get_table(table_name)

    def get_depth_columns(self) -> Dict[str, Any]:
        """Get all columns from well_data table."""
        table = self.get_table("well_data")
        if table is not None:
            return {col.name: str(col.type) for col in table.columns}
        return {}

    def close(self):
        """Close database connection."""
        if self._engine:
            self._engine.dispose()
            logger.info("PostgreSQL connection closed")


db_manager = DatabaseManager()


def get_db() -> Generator[Session, None, None]:
    """Dependency to get database session."""
    yield from db_manager.get_session()


# Alias for compatibility with endpoints that used get_depth_db
get_depth_db = get_db
