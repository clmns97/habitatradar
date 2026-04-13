import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


load_dotenv()


def build_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("PGHOST") or os.getenv("POSTGRES_HOST")
    port = os.getenv("PGPORT") or os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB")
    user = os.getenv("PGUSER") or os.getenv("POSTGRES_USER")
    password = os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD")

    if not all([host, database, user, password]):
        raise RuntimeError(
            "Database configuration missing. Set DATABASE_URL or PG*/POSTGRES* variables."
        )

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


engine = create_async_engine(build_database_url())
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
