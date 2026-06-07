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


def _migrate_analysis_reports_table():
    """Add evidence_json column to analysis_reports if missing."""
    try:
        inspector = inspect(engine)
        if "analysis_reports" not in inspector.get_table_names():
            return

        existing_cols = {col["name"] for col in inspector.get_columns("analysis_reports")}

        if "evidence_json" not in existing_cols:
            with engine.connect() as conn:
                sql = "ALTER TABLE analysis_reports ADD COLUMN evidence_json TEXT DEFAULT ''"
                logger.info(f"Migration: {sql}")
                conn.execute(text(sql))
                conn.commit()
    except Exception as e:
        logger.warning(f"Analysis reports migration failed (non-fatal): {e}")


def _migrate_chunks_table():
    """Add parser column to chunks table if missing."""
    try:
        inspector = inspect(engine)
        if "chunks" not in inspector.get_table_names():
            return

        existing_cols = {col["name"] for col in inspector.get_columns("chunks")}

        if "parser" not in existing_cols:
            with engine.connect() as conn:
                sql = "ALTER TABLE chunks ADD COLUMN parser VARCHAR(50) DEFAULT 'builtin'"
                logger.info(f"Migration: {sql}")
                conn.execute(text(sql))
                conn.commit()
    except Exception as e:
        logger.warning(f"Chunks migration failed (non-fatal): {e}")


def _migrate_generated_skills_table():
    """Add generated skill tracking columns if an older local table exists."""
    try:
        inspector = inspect(engine)
        if "generated_skills" not in inspector.get_table_names():
            return

        existing_cols = {col["name"] for col in inspector.get_columns("generated_skills")}
        migrations = {
            "source_repo": ("VARCHAR(200)", "''"),
            "source_path": ("VARCHAR(1000)", "''"),
            "output_path": ("VARCHAR(1000)", "''"),
            "generated_files_json": ("TEXT", "'[]'"),
            "status": ("VARCHAR(50)", "'created'"),
            "repo_imported": ("INTEGER", "0"),
            "spec_parsed": ("INTEGER", "0"),
            "compatible_skill_generated": ("INTEGER", "0"),
            "original_cli_invoked": ("INTEGER", "0"),
            "validation_status": ("VARCHAR(80)", "'not_validated'"),
            "validation_score": ("INTEGER", "0"),
            "validation_passed_checks_json": ("TEXT", "'[]'"),
            "validation_errors_json": ("TEXT", "'[]'"),
            "validation_warnings_json": ("TEXT", "'[]'"),
            "runtime_simulated": ("INTEGER", "0"),
            "actual_runtime_invoked": ("INTEGER", "0"),
            "runtime_test_output_path": ("VARCHAR(1000)", "''"),
            "install_instructions_path": ("VARCHAR(1000)", "''"),
            "last_validated_at": ("DATETIME", "NULL"),
            "l5c_runtime_target": ("VARCHAR(80)", "''"),
            "l5c_passed": ("INTEGER", "0"),
            "l5c_score": ("INTEGER", "0"),
            "l5c_result_id": ("INTEGER", "NULL"),
            "l5c_validated_at": ("DATETIME", "NULL"),
            "error": ("TEXT", "NULL"),
            "updated_at": ("DATETIME", "NULL"),
        }

        with engine.connect() as conn:
            for col_name, (col_type, default_val) in migrations.items():
                if col_name not in existing_cols:
                    sql = f"ALTER TABLE generated_skills ADD COLUMN {col_name} {col_type} DEFAULT {default_val}"
                    logger.info(f"Migration: {sql}")
                    conn.execute(text(sql))
            conn.commit()
    except Exception as e:
        logger.warning(f"Generated skills migration failed (non-fatal): {e}")


def _migrate_runtime_validation_results_table():
    """Create runtime validation result table without touching existing local data."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.warning(f"Runtime validation results migration failed (non-fatal): {e}")


def _migrate_skill_runtime_tables():
    """Create website-native Skill runtime tables without touching existing local data."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.warning(f"Skill runtime tables migration failed (non-fatal): {e}")


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_documents_table()
    _migrate_analysis_reports_table()
    _migrate_chunks_table()
    _migrate_generated_skills_table()
    _migrate_runtime_validation_results_table()
    _migrate_skill_runtime_tables()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
