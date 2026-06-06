"""Pytest bootstrap.

`app.db` builds a SQLAlchemy engine at import time and requires a database URL,
so importing anything under `app` needs one set. We provide a dummy URL before
any test imports run — engine creation is lazy, so no connection is attempted.
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
