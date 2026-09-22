"""
Database Connection Manager using asyncpg
Provides connection pooling, lifecycle management, and schema migration runner.
"""

from contextlib import asynccontextmanager
from typing import Any, List, Optional
import asyncpg
import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Async PostgreSQL Database Manager."""

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Initialize connection pool."""
        if self._pool is not None:
            return

        try:
            self._pool = await asyncpg.create_pool(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                database=settings.DB_NAME,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                min_size=settings.DB_MIN_CONNECTIONS,
                max_size=settings.DB_MAX_CONNECTIONS,
                command_timeout=15.0,
            )
            logger.info(
                "Database connection pool initialized",
                host=settings.DB_HOST,
                db=settings.DB_NAME,
            )
        except Exception as e:
            logger.warning(
                "Could not connect to PostgreSQL database",
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                error=str(e),
            )
            self._pool = None

    async def disconnect(self) -> None:
        """Close connection pool gracefully."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Database connection pool closed")

    @property
    def is_connected(self) -> bool:
        """Check whether the pool is active."""
        return self._pool is not None

    @asynccontextmanager
    async def connection(self):
        """Acquire a connection from pool."""
        if self._pool is None:
            raise ConnectionError("Database pool is not connected. Call connect() first.")
        async with self._pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, *args) -> str:
        """Execute query without returning rows."""
        async with self.connection() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple records."""
        async with self.connection() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single record."""
        async with self.connection() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single scalar value."""
        async with self.connection() as conn:
            return await conn.fetchval(query, *args)

    async def run_migration_file(self, file_path: str) -> None:
        """Run SQL migration file."""
        with open(file_path, "r", encoding="utf-8") as f:
            sql = f.read()
        await self.execute(sql)
        logger.info("Migration executed successfully", file=file_path)


# Global Database Manager singleton
db_manager = DatabaseManager()
