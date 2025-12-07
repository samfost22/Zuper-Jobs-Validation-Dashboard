#!/usr/bin/env python3
"""
Database setup and path management for deployment
Ensures database persists across restarts
"""
import os
import sqlite3
from pathlib import Path

# Define persistent data directory
# On Streamlit Cloud, this will be in /mount/src/app/data
# Locally, it's just ./data
DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(exist_ok=True)

# Database file paths
DB_FILE = str(DATA_DIR / 'jobs_validation.db')
NETSUITE_DB_FILE = str(DATA_DIR / 'zuper_netsuite.db')

def get_db_path():
    """Get the persistent database path"""
    return DB_FILE

def ensure_database_exists():
    """
    Ensure database exists and is initialized
    Creates empty database with schema if it doesn't exist
    """
    if not os.path.exists(DB_FILE):
        print(f"Database not found at {DB_FILE}, initializing...")

        # Import and run schema
        schema_file = Path(__file__).parent / 'database_jobs_schema.sql'

        if schema_file.exists():
            with open(schema_file, 'r') as f:
                schema = f.read()

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.executescript(schema)
            conn.commit()
            conn.close()
            print(f"✅ Database initialized at {DB_FILE}")
        else:
            print(f"⚠️ Schema file not found: {schema_file}")
    else:
        # Database exists - get some stats
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM jobs")
            job_count = cursor.fetchone()[0]
            print(f"✅ Database loaded: {job_count} jobs")
        except:
            print(f"✅ Database exists at {DB_FILE}")
        finally:
            conn.close()

if __name__ == '__main__':
    ensure_database_exists()
