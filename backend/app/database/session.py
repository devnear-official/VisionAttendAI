"""Database session and connection management for PostgreSQL + pgvector."""

from typing import Generator, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import get_settings
from app.utils.logger import logger

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
    echo=False,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database session lifecycle."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_health() -> Dict[str, Any]:
    """Test PostgreSQL connection and pgvector extension readiness."""
    try:
        with engine.connect() as conn:
            # Check basic connection and version
            pg_ver = conn.execute(text("SELECT version();")).scalar()

            # Check pgvector extension
            vec_res = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
            ).scalar()

            return {
                "connected": True,
                "pg_version": pg_ver.split(" on ")[0] if pg_ver else "unknown",
                "pgvector_installed": vec_res is not None,
                "pgvector_version": vec_res or "not installed",
            }
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return {
            "connected": False,
            "error": str(e),
            "pgvector_installed": False,
        }
