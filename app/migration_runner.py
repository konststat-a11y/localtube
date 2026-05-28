from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from .config import BASE_DIR
from .database import engine


BASELINE_REVISION = "001_baseline"


def run_database_migrations() -> None:
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "migrations"))

    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        has_version = "alembic_version" in tables
        has_existing_schema = bool(tables - {"alembic_version"})
        if has_existing_schema and not has_version:
            connection.execute(
                text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
            )
            connection.execute(text("DELETE FROM alembic_version"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
                {"version_num": BASELINE_REVISION},
            )
            connection.commit()

    command.upgrade(config, "head")
