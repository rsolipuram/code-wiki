"""FastAPI dependency providers for database sessions and job queues."""

from collections.abc import Generator

from fastapi import Depends
from redis import Redis
from rq import Queue
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.config import get_settings


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy database session."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        yield session


def get_job_queue() -> Queue:
    """Return the RQ analysis job queue."""
    settings = get_settings()
    redis_conn = Redis.from_url(settings.redis_url)
    return Queue("analysis", connection=redis_conn)
