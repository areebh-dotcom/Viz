"""SQLite database utilities and sample data for the Viz chatbot demo."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "viz.db"


CREATE_TABLE_STATEMENTS: Tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS subscribers (
        user_id TEXT PRIMARY KEY,
        region TEXT NOT NULL,
        plan_type TEXT NOT NULL,
        join_date TEXT NOT NULL,
        status TEXT NOT NULL,
        monthly_spend REAL NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS payments (
        payment_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL,
        payment_date TEXT NOT NULL,
        status TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS logins (
        login_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        login_date TEXT NOT NULL,
        login_count INTEGER NOT NULL,
        device_type TEXT NOT NULL,
        region TEXT NOT NULL,
        plan_type TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tickets (
        ticket_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        opened_at TEXT NOT NULL,
        resolved_at TEXT,
        category TEXT NOT NULL,
        severity TEXT NOT NULL,
        status TEXT NOT NULL,
        response_time_hours REAL NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS business_units (
        unit_id TEXT PRIMARY KEY,
        unit_name TEXT NOT NULL,
        region TEXT NOT NULL,
        revenue REAL NOT NULL,
        headcount INTEGER NOT NULL
    );
    """,
)


SAMPLE_ROWS: Dict[str, List[Sequence[Any]]] = {
    "subscribers": [
        ("user-001", "North America", "Premium", "2025-08-15", "active", 129.0),
        ("user-002", "Europe", "Standard", "2025-07-02", "active", 79.0),
        ("user-003", "India", "Premium", "2025-09-20", "paused", 119.0),
        ("user-004", "Latin America", "Basic", "2025-01-12", "churned", 39.0),
        ("user-005", "North America", "Premium", "2025-03-05", "active", 149.0),
    ],
    "payments": [
        ("pay-1001", "user-001", 129.0, "USD", "2025-10-01", "settled"),
        ("pay-1002", "user-002", 79.0, "EUR", "2025-10-03", "settled"),
        ("pay-1003", "user-003", 119.0, "INR", "2025-09-28", "pending"),
        ("pay-1004", "user-004", 39.0, "MXN", "2025-08-17", "refunded"),
        ("pay-1005", "user-005", 298.0, "USD", "2025-10-05", "settled"),
    ],
    "logins": [
        ("login-2001", "user-001", "2025-10-01", 12, "web", "North America", "Premium"),
        ("login-2002", "user-001", "2025-10-02", 7, "mobile", "North America", "Premium"),
        ("login-2003", "user-002", "2025-10-03", 5, "web", "Europe", "Standard"),
        ("login-2004", "user-003", "2025-10-01", 9, "mobile", "India", "Premium"),
        ("login-2005", "user-004", "2025-09-15", 1, "web", "Latin America", "Basic"),
        ("login-2006", "user-005", "2025-10-04", 15, "mobile", "North America", "Premium"),
    ],
    "tickets": [
        ("ticket-3001", "user-002", "2025-10-01T08:15:00", "2025-10-01T12:45:00", "Billing", "High", "resolved", 4.5),
        ("ticket-3002", "user-003", "2025-09-28T10:05:00", None, "Technical", "Critical", "open", 12.0),
        ("ticket-3003", "user-001", "2025-10-02T14:30:00", "2025-10-02T18:55:00", "Onboarding", "Medium", "resolved", 4.4),
        ("ticket-3004", "user-005", "2025-09-10T09:00:00", "2025-09-10T11:30:00", "Billing", "Low", "resolved", 2.5),
    ],
    "business_units": [
        ("unit-4001", "Consumer", "North America", 2_500_000.0, 120),
        ("unit-4002", "Enterprise", "Europe", 4_200_000.0, 80),
        ("unit-4003", "SMB", "India", 1_750_000.0, 65),
        ("unit-4004", "Partnerships", "Latin America", 950_000.0, 40),
    ],
}


INSERT_STATEMENTS: Dict[str, str] = {
    "subscribers": "INSERT INTO subscribers (user_id, region, plan_type, join_date, status, monthly_spend) VALUES (?, ?, ?, ?, ?, ?)",
    "payments": "INSERT INTO payments (payment_id, user_id, amount, currency, payment_date, status) VALUES (?, ?, ?, ?, ?, ?)",
    "logins": "INSERT INTO logins (login_id, user_id, login_date, login_count, device_type, region, plan_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
    "tickets": "INSERT INTO tickets (ticket_id, user_id, opened_at, resolved_at, category, severity, status, response_time_hours) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    "business_units": "INSERT INTO business_units (unit_id, unit_name, region, revenue, headcount) VALUES (?, ?, ?, ?, ?)",
}


_INITIALISED = False


def initialise_database(force: bool = False) -> None:
    """Create tables and populate seed data if the database is empty."""

    global _INITIALISED
    if _INITIALISED and not force:
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    try:
        cursor = connection.cursor()
        for statement in CREATE_TABLE_STATEMENTS:
            cursor.executescript(statement)

        for table, rows in SAMPLE_ROWS.items():
            count_query = f"SELECT COUNT(*) FROM {table}"
            existing_rows = cursor.execute(count_query).fetchone()[0]
            if existing_rows == 0:
                cursor.executemany(INSERT_STATEMENTS[table], rows)

        connection.commit()
    finally:
        connection.close()

    _INITIALISED = True


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row access enabled."""

    initialise_database()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def execute_query(sql: str) -> List[Dict[str, Any]]:
    """Execute a read-only SQL query and return the results as dictionaries."""

    with get_connection() as connection:
        cursor = connection.execute(sql)
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def list_rows(table: str) -> List[Dict[str, Any]]:
    """Convenience helper used in documentation and debugging."""

    query = f"SELECT * FROM {table}"
    return execute_query(query)

