"""
Database connection utilities.

Provides centralized connection handling, initialization, and helper functions.
"""

import sqlite3
import os
import logging
from contextlib import contextmanager
from typing import Optional, List, Tuple, Any

from config import JOBS_DB_FILE, DB_TIMEOUT, ROOT_DIR

logger = logging.getLogger(__name__)


def get_db_connection(db_path: str = JOBS_DB_FILE) -> sqlite3.Connection:
    """
    Get a database connection with standard configuration.

    Args:
        db_path: Path to database file. Defaults to jobs validation DB.

    Returns:
        Configured sqlite3 connection with Row factory.
    """
    conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_session(db_path: str = JOBS_DB_FILE):
    """
    Context manager for database sessions with automatic cleanup.

    Usage:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs")

    Args:
        db_path: Path to database file.

    Yields:
        sqlite3.Connection with Row factory configured.
    """
    conn = None
    try:
        conn = get_db_connection(db_path)
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()


def init_database(db_path: str = JOBS_DB_FILE, schema_file: str = None) -> None:
    """
    Initialize the database with schema if it doesn't exist.

    Args:
        db_path: Path to database file.
        schema_file: Path to SQL schema file. Defaults to database_jobs_schema.sql.
    """
    if schema_file is None:
        schema_file = os.path.join(ROOT_DIR, 'database_jobs_schema.sql')

    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    with open(schema_file, 'r') as f:
        schema = f.read()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executescript(schema)
    conn.commit()
    conn.close()

    logger.info(f"Database initialized: {db_path}")


def ensure_database_exists(db_path: str = JOBS_DB_FILE) -> None:
    """
    Ensure the database exists, initializing if necessary.

    Args:
        db_path: Path to database file.
    """
    if not os.path.exists(db_path):
        init_database(db_path)


def execute_query(
    query: str,
    params: Tuple = (),
    db_path: str = JOBS_DB_FILE,
    fetch_one: bool = False
) -> Optional[List[sqlite3.Row]]:
    """
    Execute a SELECT query and return results.

    Args:
        query: SQL query string with ? placeholders.
        params: Tuple of parameters for the query.
        db_path: Path to database file.
        fetch_one: If True, return only first result.

    Returns:
        List of Row objects, single Row, or None on error.
    """
    ensure_database_exists(db_path)

    try:
        with db_session(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

            if fetch_one:
                return cursor.fetchone()
            return cursor.fetchall()

    except sqlite3.Error as e:
        logger.error(f"Query error: {e}\nQuery: {query}\nParams: {params}")
        return None


def execute_many(
    query: str,
    params_list: List[Tuple],
    db_path: str = JOBS_DB_FILE
) -> int:
    """
    Execute a query with multiple parameter sets (batch insert/update).

    Args:
        query: SQL query string with ? placeholders.
        params_list: List of parameter tuples.
        db_path: Path to database file.

    Returns:
        Number of rows affected.
    """
    ensure_database_exists(db_path)

    try:
        with db_session(db_path) as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount

    except sqlite3.Error as e:
        logger.error(f"Batch query error: {e}\nQuery: {query}")
        return 0


def execute_write(
    query: str,
    params: Tuple = (),
    db_path: str = JOBS_DB_FILE
) -> int:
    """
    Execute an INSERT, UPDATE, or DELETE query.

    Args:
        query: SQL query string with ? placeholders.
        params: Tuple of parameters for the query.
        db_path: Path to database file.

    Returns:
        Number of rows affected, or -1 on error.
    """
    ensure_database_exists(db_path)

    try:
        with db_session(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount

    except sqlite3.Error as e:
        logger.error(f"Write error: {e}\nQuery: {query}\nParams: {params}")
        return -1
