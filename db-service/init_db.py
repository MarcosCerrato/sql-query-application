"""Load data.csv into PostgreSQL on startup."""
import logging

import pandas as pd
from sqlalchemy import create_engine, text

from config import settings

logger = logging.getLogger(__name__)


def init():
    engine = create_engine(settings.database_url)

    df = pd.read_csv("/data/data.csv")
    df.columns = [c.strip().lower() for c in df.columns]

    # Drop the id column if present so autoincrement works correctly
    if "id" in df.columns:
        df = df.drop(columns=["id"])

    with engine.begin() as conn:
        count = conn.execute(
            text(f"SELECT COUNT(*) FROM {settings.table_name}")  # noqa: S608
        ).scalar()
        if count == 0:
            df.to_sql(settings.table_name, conn, if_exists="append", index=False)
            logger.info("Loaded %d rows into '%s'.", len(df), settings.table_name)
        else:
            logger.info(
                "Table '%s' already has %d rows, skipping load.",
                settings.table_name,
                count,
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init()
