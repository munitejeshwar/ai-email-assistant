# database/db_manager.py
#
# Core database access layer for the Human-Centric Intelligent Email
# Workflow Framework.
#
# Responsibilities:
#   - Bootstrap the database on first run (original 7-column schema).
#   - Trigger schema_migration.init_schema() on every startup so the
#     extended schema (new columns + audit_log + decision_timeline) is
#     applied automatically and idempotently.
#   - Provide thin CRUD helpers used by the pipeline and dashboard.
#
# Public API:
#   init_db()                  — bootstraps DB + runs all migrations
#   save_email(email_data)     — legacy persistence (backward compatible)
#   save_envelope(envelope)    — new HITL persistence via DecisionEnvelope
#   email_exists(email_id)     — deduplication check
#
# DB_PATH is read from the environment for consistency with every other
# module in the project. Fallback: "emails.db".

import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Single source of truth for the database file path.
# Set DB_PATH in your .env file to override the default location.
# ---------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", "emails.db")


def init_db() -> None:
    """
    Initialises the database on application startup.

    Steps:
      1. Creates the original `processed_emails` table if it does not
         exist (safe first-run bootstrap — existing tables are untouched).
      2. Calls init_schema() from the migration module to apply any
         pending additive migrations (new columns, new tables).
         This is idempotent: running it on an already-migrated database
         is a no-op.

    Call this once at the start of main.py and monitor.py.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Original schema — preserved exactly as it was.
    # init_schema() will add the new columns on top of this.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS processed_emails (
        id           TEXT PRIMARY KEY,
        sender       TEXT,
        subject      TEXT,
        summary      TEXT,
        category     TEXT,
        priority     TEXT,
        processed_at TEXT
    )
    """)

    conn.commit()
    conn.close()

    # Apply all pending schema migrations (extended columns + new tables).
    # Import is deferred to here to avoid a circular-import risk at module
    # level (schema_migration also imports from dotenv, not from db_manager,
    # so there is no actual cycle — but the local import keeps the
    # dependency explicit and easy to trace).
    from database.schema_migration import init_schema
    init_schema()


def save_email(email_data: dict) -> None:
    """
    Persists a processed email record to the database.

    Backward-compatible interface used by main.py and monitor.py.
    Accepts the original 6-key dict (id, sender, subject, summary,
    category, priority) produced by the legacy pipeline.

    For new code, use save_envelope() instead.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR REPLACE INTO processed_emails (
        id,
        sender,
        subject,
        summary,
        category,
        priority,
        processed_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        email_data["id"],
        email_data["sender"],
        email_data["subject"],
        email_data["summary"],
        email_data["category"],
        email_data["priority"],
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def save_envelope(envelope) -> None:
    """
    Persists a DecisionEnvelope to the database.

    Architecture contract:
      - Calls envelope.to_database_record() to obtain a flat dict.
      - This function never inspects the nested dataclass fields directly
        (SummaryResult, ClassificationResult, PriorityResult, ReplyResult).
      - All flattening and column-mapping logic lives in DecisionEnvelope
        itself; db_manager is responsible only for SQL persistence.
      - processed_at is set here to datetime.now() — it is a DB-layer
        concern, not a domain concern, so it is intentionally excluded
        from to_database_record().

    Args:
        envelope: A DecisionEnvelope instance produced by
                  email_engine/processor.py. Typed as 'object' at runtime
                  to avoid a hard import dependency at module level;
                  the type annotation is enforced by the caller.

    Raises:
        sqlite3.Error: if the INSERT fails (e.g. disk full, locked DB).
                       The caller is responsible for handling this.
    """
    # Obtain the flat SQL-ready record from the domain model.
    # db_manager never reads envelope.summary.summary or any nested field
    # directly — that knowledge belongs exclusively to to_database_record().
    record = envelope.to_database_record()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR REPLACE INTO processed_emails (
        id,
        sender,
        subject,
        summary,
        category,
        priority,
        ai_confidence_estimate,
        risk_level,
        suggested_tone,
        reasoning,
        draft_reply,
        reply_rationale,
        status,
        processed_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record["id"],
        record["sender"],
        record["subject"],
        record["summary"],
        record["category"],
        record["priority"],
        record["ai_confidence_estimate"],
        record["risk_level"],
        record["suggested_tone"],
        record["reasoning"],
        record["draft_reply"],
        record["reply_rationale"],
        record["status"],
        datetime.now().isoformat(),     # processed_at: DB-layer timestamp
    ))

    conn.commit()
    conn.close()


def email_exists(email_id: str) -> bool:
    """
    Returns True if the email has already been processed and stored.
    Used by the pipeline to skip duplicate emails on repeated runs.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id FROM processed_emails
    WHERE id = ?
    """, (email_id,))

    result = cursor.fetchone()

    conn.close()

    return result is not None