# database/schema_migration.py
#
# Safe, additive schema migrations for the Human-Centric Intelligent
# Email Workflow Framework.
#
# Design principles:
#   - Every migration is idempotent (safe to run multiple times).
#   - ALTER TABLE columns use "ADD COLUMN IF NOT EXISTS" logic via
#     a try/except around the OperationalError SQLite raises when the
#     column already exists. This keeps us compatible with SQLite < 3.37
#     which does not support the native IF NOT EXISTS clause on ALTER.
#   - Existing rows receive column defaults automatically; no data is lost.
#   - New tables use CREATE TABLE IF NOT EXISTS.
#
# Workflow states stored in processed_emails.status:
#   PENDING           → AI processed; awaiting human decision in dashboard
#   DRAFT_SAVED       → User saved the AI draft for later without acting
#   APPROVED          → User approved the draft; email has been sent
#   REJECTED          → User rejected the draft; no email sent
#   SENT              → Confirmed delivery via Gmail API response
#   GMAIL_DRAFT_SAVED → Draft pushed to Gmail Drafts folder via API
#
# Public API:
#   init_schema()    ← call this from all other modules
#   run_migrations() ← internal implementation; do not call directly

import os
import sqlite3
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB_PATH is read from the environment so the migration system stays
# consistent with every other module in the project.
# Fallback to "emails.db" when the variable is not set.
# ---------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", "emails.db")

# ---------------------------------------------------------------------------
# Columns to add to the existing `processed_emails` table.
# Format: (column_name, column_definition)
# Order matters for readability; SQLite appends columns at the end.
# ---------------------------------------------------------------------------
PROCESSED_EMAILS_NEW_COLUMNS = [
    # --- XAI / Decision Engine outputs ---
    ("ai_confidence_estimate",  "REAL    DEFAULT 0.0"),
    ("risk_level",              "TEXT    DEFAULT 'UNKNOWN'"),
    ("suggested_tone",          "TEXT"),
    ("reasoning",               "TEXT"),
    ("draft_reply",             "TEXT"),
    ("reply_rationale",         "TEXT"),

    # --- Human-in-the-Loop workflow ---
    ("status",                  "TEXT    DEFAULT 'PENDING'"),
    ("user_edited_reply",       "TEXT"),
    ("rejection_reason",        "TEXT"),
    ("gmail_draft_id",          "TEXT"),

    # --- Timestamps for analytics ---
    ("approved_at",             "TEXT"),
    ("rejected_at",             "TEXT"),
    ("sent_at",                 "TEXT"),
    ("draft_saved_at",          "TEXT"),
]


def _add_column_if_missing(cursor, table: str, column: str, definition: str) -> bool:
    """
    Attempts to add a column to an existing table.
    Returns True if the column was added, False if it already existed.
    """
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        logger.info("Added column '%s' to table '%s'.", column, table)
        return True
    except sqlite3.OperationalError as exc:
        # SQLite raises: "table X already has a column named Y"
        if "already has a column" in str(exc):
            return False
        raise  # Re-raise unexpected errors


def _migrate_processed_emails(cursor) -> None:
    """Adds new columns to the existing processed_emails table."""
    for column, definition in PROCESSED_EMAILS_NEW_COLUMNS:
        _add_column_if_missing(cursor, "processed_emails", column, definition)


def _create_audit_log_table(cursor) -> None:
    """
    Creates the audit_log table if it does not yet exist.

    Tracks every action taken by either the AI pipeline or a human user,
    providing a tamper-evident record suitable for the IEEE/Springer paper's
    human-in-the-loop audit requirements.

    actor  : 'AI'   — action performed automatically by the pipeline
             'USER' — action triggered by a human in the dashboard
    action : e.g. 'SUMMARIZED', 'CLASSIFIED', 'DRAFT_CREATED',
                  'APPROVED', 'REJECTED', 'SENT', 'DRAFT_EDITED'
    details: optional JSON string with supplementary data
    """
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id   TEXT    NOT NULL,
        actor      TEXT    NOT NULL,
        action     TEXT    NOT NULL,
        details    TEXT,
        created_at TEXT    NOT NULL
    )
    """)


def _create_decision_timeline_table(cursor) -> None:
    """
    Creates the decision_timeline table if it does not yet exist.

    Stores the ordered sequence of lifecycle events for every email,
    enabling the per-email timeline view in the Streamlit dashboard
    and supporting the 'Decision Timeline' section of the paper.

    event  : one of DRAFT_CREATED | DRAFT_EDITED | DRAFT_SAVED |
                     APPROVED | REJECTED | SENT | GMAIL_DRAFT_SAVED
    actor  : 'AI' or 'USER'
    note   : optional human-readable context (e.g. rejection reason)
    """
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS decision_timeline (
        event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id   TEXT    NOT NULL,
        event      TEXT    NOT NULL,
        actor      TEXT    NOT NULL,
        note       TEXT,
        created_at TEXT    NOT NULL
    )
    """)


def run_migrations() -> None:
    """
    Internal implementation — runs all migrations in order.
    Safe to call on every application start (idempotent).

    Do not call this directly from other modules.
    Use the public init_schema() function instead.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        logger.info("Running schema migrations on '%s'...", DB_PATH)

        _migrate_processed_emails(cursor)
        _create_audit_log_table(cursor)
        _create_decision_timeline_table(cursor)

        conn.commit()
        logger.info("Schema migrations completed successfully.")

    except Exception:
        conn.rollback()
        logger.exception("Schema migration failed. Changes rolled back.")
        raise

    finally:
        conn.close()


def init_schema() -> None:
    """
    Public entry point for schema initialisation.

    All modules — db_manager, processor, main, monitor — should call
    this function. It delegates to run_migrations() internally, keeping
    the implementation detail hidden behind a stable public name.

    Example::

        from database.schema_migration import init_schema
        init_schema()  # safe to call on every startup
    """
    run_migrations()


# ---------------------------------------------------------------------------
# Allow running this file directly to manually trigger migration:
#   python database/schema_migration.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    init_schema()
    print(f"✅ Migration complete. Schema is up to date on '{DB_PATH}'.")
