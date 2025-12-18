#!/usr/bin/env python3
"""
Migration: Add composite indexes for performance optimization (Phase 3)

This migration adds composite indexes to support common query patterns:
- Date range + organization filtering
- Date range + service team filtering
- Job number lookups

Safe to run on a live database - uses CREATE INDEX IF NOT EXISTS.
SQLite allows concurrent reads during index creation.

Usage:
    python migrations/add_composite_indexes.py
"""

import sqlite3
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import JOBS_DB_FILE


def run_migration():
    """Add composite indexes to the jobs database."""

    if not os.path.exists(JOBS_DB_FILE):
        print(f"Database not found: {JOBS_DB_FILE}")
        print("Run the sync first to create the database.")
        return False

    print(f"Adding composite indexes to {JOBS_DB_FILE}...")

    indexes = [
        # Composite indexes for common query patterns
        ("idx_jobs_completed_org", "CREATE INDEX IF NOT EXISTS idx_jobs_completed_org ON jobs(completed_at, organization_name)"),
        ("idx_jobs_created_org", "CREATE INDEX IF NOT EXISTS idx_jobs_created_org ON jobs(created_at, organization_name)"),
        ("idx_jobs_org_name", "CREATE INDEX IF NOT EXISTS idx_jobs_org_name ON jobs(organization_name)"),
        ("idx_jobs_completed_team", "CREATE INDEX IF NOT EXISTS idx_jobs_completed_team ON jobs(completed_at, service_team)"),
        ("idx_jobs_job_number", "CREATE INDEX IF NOT EXISTS idx_jobs_job_number ON jobs(job_number)"),
    ]

    conn = sqlite3.connect(JOBS_DB_FILE, timeout=60)
    cursor = conn.cursor()

    created = 0
    skipped = 0

    for name, sql in indexes:
        try:
            # Check if index already exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,))
            if cursor.fetchone():
                print(f"  ⏭️  {name} (already exists)")
                skipped += 1
            else:
                cursor.execute(sql)
                conn.commit()
                print(f"  ✅ {name} (created)")
                created += 1
        except sqlite3.Error as e:
            print(f"  ❌ {name} (error: {e})")

    conn.close()

    print(f"\nMigration complete: {created} created, {skipped} skipped")
    return True


def verify_indexes():
    """Verify that all expected indexes exist."""

    if not os.path.exists(JOBS_DB_FILE):
        print("Database not found")
        return False

    expected = [
        "idx_jobs_completed_org",
        "idx_jobs_created_org",
        "idx_jobs_org_name",
        "idx_jobs_completed_team",
        "idx_jobs_job_number",
    ]

    conn = sqlite3.connect(JOBS_DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    existing = {row[0] for row in cursor.fetchall()}

    conn.close()

    print("\nIndex verification:")
    all_present = True
    for idx in expected:
        if idx in existing:
            print(f"  ✅ {idx}")
        else:
            print(f"  ❌ {idx} (missing)")
            all_present = False

    return all_present


if __name__ == "__main__":
    success = run_migration()
    if success:
        verify_indexes()
