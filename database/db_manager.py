# database/db_manager.py

import sqlite3
from datetime import datetime

DB_NAME = "emails.db"


def init_db():
    """
    Creates database + tables if they don't exist.
    """

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS processed_emails (
        id TEXT PRIMARY KEY,
        sender TEXT,
        subject TEXT,
        summary TEXT,
        category TEXT,
        priority TEXT,
        processed_at TEXT
    )
    """)

    conn.commit()
    conn.close()


def save_email(email_data):
    """
    Saves processed email into database.
    """

    conn = sqlite3.connect(DB_NAME)
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


def email_exists(email_id):
    """
    Checks whether email already processed.
    """

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id FROM processed_emails
    WHERE id = ?
    """, (email_id,))

    result = cursor.fetchone()

    conn.close()

    return result is not None