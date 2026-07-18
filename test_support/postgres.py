from __future__ import annotations

import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_LIB_ROOT = REPO_ROOT / "libs" / "platform-common"


def bootstrap_repo_paths() -> None:
    for path in (REPO_ROOT, SHARED_LIB_ROOT):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def configure_postgres_test_environment(
    *,
    database_env_var: str,
    default_database_url: str,
    extra_env: Mapping[str, str] | None = None,
) -> str:
    bootstrap_repo_paths()

    database_url = os.environ.get(database_env_var, default_database_url)
    os.environ[database_env_var] = database_url

    if extra_env is not None:
        for key, value in extra_env.items():
            os.environ[key] = value

    ensure_postgres_database(database_url)
    return database_url


def ensure_postgres_database(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError(f"Expected a PostgreSQL URL, got {database_url!r}")
    if url.database is None:
        raise ValueError(f"Database name is required in {database_url!r}")

    connect_kwargs = {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "user": url.username or "postgres",
        "password": url.password,
        "dbname": "postgres",
    }

    deadline = time.monotonic() + 30
    last_error: psycopg.OperationalError | None = None

    while time.monotonic() < deadline:
        try:
            with psycopg.connect(**connect_kwargs, autocommit=True) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT 1 FROM pg_database WHERE datname = %s",
                        (url.database,),
                    )
                    if cursor.fetchone() is None:
                        cursor.execute(
                            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(url.database))
                        )
            return
        except psycopg.OperationalError as exc:
            last_error = exc
            time.sleep(0.5)

    location = f"{connect_kwargs['host']}:{connect_kwargs['port']}"
    raise RuntimeError(
        "Unable to connect to PostgreSQL while preparing the test database "
        f"{url.database!r} at {location}. Start the corresponding postgres "
        "container first."
    ) from last_error


def reset_database(engine, metadata) -> None:
    engine.dispose()
    metadata.drop_all(bind=engine)
    metadata.create_all(bind=engine)


def teardown_database(engine, metadata) -> None:
    metadata.drop_all(bind=engine)
    engine.dispose()
