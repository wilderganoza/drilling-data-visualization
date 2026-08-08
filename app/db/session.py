from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, Dict, Any
from app.core.config import settings
from app.core.logging import get_logger
from app.models.legacy import Base

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
            # SQL statement echo is intentionally OFF even in DEBUG: it logs
            # every query (thousands of lines per request for the ops tree) and
            # is a real latency drag. Flip to settings.DEBUG only when actively
            # debugging SQL.
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        self._session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self._engine
        )
        # Create legacy app tables (users, etc.) if they don't exist. Scoped
        # to an explicit table list — not a blanket Base.metadata.create_all()
        # — because app.ops models share this same MetaData (for cross-module
        # FKs) but are Alembic-managed only; a blanket call would auto-create
        # ops_* tables here too if that package happened to be imported first.
        LEGACY_TABLES = [Base.metadata.tables[name] for name in ("users", "wells", "processed_datasets", "processed_records")]
        Base.metadata.create_all(bind=self._engine, tables=LEGACY_TABLES)

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

    def get_domain_table(self, domain: str = "depth") -> Table:
        """Sensor table for a data domain: 'depth' → well_data (indexed by depth),
        'time' → well_data_time (indexed by time). Reflects the time table on
        demand (it may have been created after startup by the import job)."""
        if domain == "time":
            t = self._metadata.tables.get("well_data_time")
            if t is None:
                from sqlalchemy import Table
                try:
                    t = Table("well_data_time", self._metadata, autoload_with=self._engine)
                except Exception:
                    t = None
            return t
        return self.get_table("well_data")

    def has_time_data(self) -> bool:
        """True if the time-indexed table exists (import has started)."""
        try:
            from sqlalchemy import text
            with self._engine.connect() as cx:
                return cx.execute(text("SELECT to_regclass('well_data_time')")).scalar() is not None
        except Exception:
            return False

    # Loose (skip) index scan: a plain DISTINCT on well_id seq-scans all ~39M rows
    # (~2s), because Postgres has no skip-scan for DISTINCT. This recursive form
    # walks the well_id btree one distinct value at a time (~800 index seeks, <0.1s).
    _TIME_WELL_IDS_SQL = """
        WITH RECURSIVE t AS (
            (SELECT well_id FROM well_data_time ORDER BY well_id LIMIT 1)
            UNION ALL
            SELECT (SELECT well_id FROM well_data_time WHERE well_id > t.well_id ORDER BY well_id LIMIT 1)
            FROM t WHERE t.well_id IS NOT NULL
        )
        SELECT well_id FROM t WHERE well_id IS NOT NULL
    """

    def time_well_ids(self, ttl: float = 120.0) -> set:
        """Set of well_ids that have time-indexed data, cached in-process.

        Uses a loose index scan (fast even on tens of millions of rows) and caches
        the result for ``ttl`` seconds so repeated domain toggles are instant. The
        TTL keeps the set fresh while the background import is still adding wells.
        """
        import time as _time

        if not self.has_time_data():
            return set()
        now = _time.monotonic()
        cached = getattr(self, "_time_well_ids_cache", None)
        cached_at = getattr(self, "_time_well_ids_cache_at", 0.0)
        if cached is not None and (now - cached_at) < ttl:
            return cached
        try:
            from sqlalchemy import text
            with self._engine.connect() as cx:
                ids = {r[0] for r in cx.execute(text(self._TIME_WELL_IDS_SQL)).fetchall()}
        except Exception:
            return cached if cached is not None else set()
        self._time_well_ids_cache = ids
        self._time_well_ids_cache_at = now
        return ids

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
