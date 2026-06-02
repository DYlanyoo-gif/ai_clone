from __future__ import annotations

import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from app.models.database import Base
from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _migrate_documents_table():
    """Add new columns to documents table if they don't exist (safe for existing DB)."""
    try:
        inspector = inspect(engine)
        if "documents" not in inspector.get_table_names():
            return  # Table will be created by create_all

        existing_cols = {col["name"] for col in inspector.get_columns("documents")}

        migrations = {
            "parser": ("VARCHAR(50)", "'builtin'"),
            "parsed_text_path": ("VARCHAR(1000)", "NULL"),
            "original_file_path": ("VARCHAR(1000)", "NULL"),
            "parse_status": ("VARCHAR(50)", "'success'"),
            "parse_error": ("TEXT", "NULL"),
        }

        with engine.connect() as conn:
            for col_name, (col_type, default_val) in migrations.items():
                if col_name not in existing_cols:
                    sql = f"ALTER TABLE documents ADD COLUMN {col_name} {col_type} DEFAULT {default_val}"
                    logger.info(f"Migration: {sql}")
                    conn.execute(text(sql))
            conn.commit()
    except Exception as e:
        logger.warning(f"Migration check failed (non-fatal): {e}")


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_documents_table()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
