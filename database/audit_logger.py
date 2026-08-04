# database/audit_logger.py
#
# Non-fatal audit logging for the HITL workflow.
# Both functions swallow exceptions — audit failure must never block
# the pipeline or a human workflow action.
#
# Tables written:
#   audit_log         — full action history (actor, action, details)
#   decision_timeline — ordered lifecycle events per email

import json
import logging
import sqlite3
from datetime import datetime, timezone

from database.db_manager import DB_PATH

logger = logging.getLogger(__name__)

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def log_action(
    email_id: str,
    actor: str,                          # "AI" | "USER"
    action: str,                         # e.g. DRAFT_CREATED, APPROVED, SENT
    details: "str | dict | None" = None,
) -> None:
    """
    Appends one row to audit_log.
    Non-fatal: exceptions are logged as warnings and suppressed.
    """
    if isinstance(details, dict):
        details = json.dumps(details, ensure_ascii=False)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO audit_log (email_id, actor, action, details, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (email_id, actor, action, details, _NOW()),
            )
    except Exception as exc:
        logger.warning("audit_logger.log_action failed (email_id=%s): %s", email_id, exc)


def record_timeline(
    email_id: str,
    event: str,                          # DRAFT_CREATED|APPROVED|REJECTED|SENT|…
    actor: str,                          # "AI" | "USER"
    note: "str | None" = None,
) -> None:
    """
    Appends one row to decision_timeline.
    Non-fatal: exceptions are logged as warnings and suppressed.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO decision_timeline (email_id, event, actor, note, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (email_id, event, actor, note, _NOW()),
            )
    except Exception as exc:
        logger.warning("audit_logger.record_timeline failed (email_id=%s): %s", email_id, exc)
