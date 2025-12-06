#!/usr/bin/env python3
"""
Update organizations table with NetSuite Customer IDs from API data
"""

import json
import sqlite3
from datetime import datetime

DB_FILE = 'jobs_validation.db'
ORG_DATA_FILE = 'organizations_data.json'

def update_organizations():
    """Update organizations table with NetSuite IDs from API data"""
    print("Updating organizations table with NetSuite Customer IDs...")

    # Load organization data
    with open(ORG_DATA_FILE, 'r') as f:
        org_data = json.load(f)

    all_orgs = org_data['organizations_with_netsuite'] + org_data['organizations_without_netsuite']

    # Connect to database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    updated_count = 0
    inserted_count = 0

    for org in all_orgs:
        org_uid = org['organization_uid']
        org_name = org['organization_name']
        netsuite_id = org.get('netsuite_customer_id')

        # Check if organization exists
        cursor.execute("SELECT organization_uid FROM organizations WHERE organization_uid = ?", (org_uid,))
        exists = cursor.fetchone()

        if exists:
            # Update existing organization
            cursor.execute("""
                UPDATE organizations
                SET organization_name = ?,
                    netsuite_customer_id = ?,
                    updated_at = ?
                WHERE organization_uid = ?
            """, (org_name, netsuite_id, datetime.now().isoformat(), org_uid))
            updated_count += 1
        else:
            # Insert new organization
            cursor.execute("""
                INSERT INTO organizations (
                    organization_uid, organization_name, netsuite_customer_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (org_uid, org_name, netsuite_id, datetime.now().isoformat(), datetime.now().isoformat()))
            inserted_count += 1

    conn.commit()

    # Get counts
    cursor.execute("SELECT COUNT(*) FROM organizations WHERE netsuite_customer_id IS NOT NULL AND netsuite_customer_id != ''")
    with_netsuite = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM organizations WHERE netsuite_customer_id IS NULL OR netsuite_customer_id = ''")
    without_netsuite = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM organizations")
    total = cursor.fetchone()[0]

    conn.close()

    print(f"\n{'=' * 80}")
    print("ORGANIZATIONS UPDATE SUMMARY")
    print('=' * 80)
    print(f"Organizations updated: {updated_count}")
    print(f"Organizations inserted: {inserted_count}")
    print(f"Total organizations: {total}")
    print(f"With NetSuite ID: {with_netsuite}")
    print(f"Without NetSuite ID: {without_netsuite}")
    print(f"\n✓ Organizations table updated successfully")

if __name__ == "__main__":
    update_organizations()
