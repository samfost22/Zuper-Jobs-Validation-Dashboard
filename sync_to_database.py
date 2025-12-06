#!/usr/bin/env python3
"""
Zuper-NetSuite Database Sync
This script syncs organization data from Zuper API to SQLite database
"""

import sqlite3
import json
import os
from datetime import datetime
import requests

# API Configuration
API_KEY = os.environ.get('ZUPER_API_KEY', '0c73f76f734550cab45861cfaa4939d8')
BASE_URL = os.environ.get('ZUPER_BASE_URL', 'https://us-east-1.zuperpro.com')

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'zuper_netsuite.db')

def init_database():
    """Initialize the database with schema"""
    conn = sqlite3.connect(DB_PATH)

    # Read and execute schema
    schema_path = os.path.join(os.path.dirname(__file__), 'database_schema.sql')
    with open(schema_path, 'r') as f:
        schema = f.read()

    conn.executescript(schema)
    conn.commit()

    print(f"✓ Database initialized: {DB_PATH}")
    return conn

def start_sync_log(conn):
    """Start a new sync log entry"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sync_log (sync_started_at, status)
        VALUES (?, 'in_progress')
    """, (datetime.now(),))
    conn.commit()
    return cursor.lastrowid

def complete_sync_log(conn, log_id, orgs_fetched, orgs_updated, orgs_created, errors=None):
    """Complete the sync log entry"""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sync_log
        SET sync_completed_at = ?,
            organizations_fetched = ?,
            organizations_updated = ?,
            organizations_created = ?,
            errors = ?,
            status = 'completed'
        WHERE id = ?
    """, (datetime.now(), orgs_fetched, orgs_updated, orgs_created, errors, log_id))
    conn.commit()

def fetch_organizations_from_api():
    """Fetch all organizations from Zuper API"""
    headers = {
        'x-api-key': API_KEY,
        'Content-Type': 'application/json'
    }

    endpoint = f"{BASE_URL}/api/organization"
    params = {
        'sort_by': 'created_at',
        'sort': 'DESC',
        'page': 1,
        'count': 100
    }

    all_organizations = []
    current_page = 1

    print("Fetching organizations from Zuper API...")

    while True:
        params['page'] = current_page
        response = requests.get(endpoint, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            organizations = data.get('data', [])
            total_pages = data.get('total_pages', 0)

            all_organizations.extend(organizations)
            print(f"  Page {current_page}/{total_pages}: {len(organizations)} organizations")

            if current_page >= total_pages:
                break
            current_page += 1
        else:
            print(f"  Error: HTTP {response.status_code}")
            break

    return all_organizations

def fetch_organization_details(org_uid):
    """Fetch detailed information for a specific organization"""
    headers = {
        'x-api-key': API_KEY,
        'Content-Type': 'application/json'
    }

    endpoint = f"{BASE_URL}/api/organization/{org_uid}"
    response = requests.get(endpoint, headers=headers)

    if response.status_code == 200:
        return response.json()
    return None

def sync_organization(conn, org_data):
    """Sync a single organization to the database"""
    cursor = conn.cursor()

    # Check if organization exists
    cursor.execute("SELECT organization_uid FROM organizations WHERE organization_uid = ?",
                   (org_data['organization_uid'],))
    exists = cursor.fetchone() is not None

    # Insert or update organization
    cursor.execute("""
        INSERT OR REPLACE INTO organizations (
            organization_uid, organization_name, organization_email,
            organization_description, no_of_customers, is_active,
            is_portal_enabled, is_deleted, created_at, updated_at, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        org_data['organization_uid'],
        org_data['organization_name'],
        org_data.get('organization_email'),
        org_data.get('organization_description'),
        org_data.get('no_of_customers', 0),
        org_data.get('is_active', True),
        org_data.get('is_portal_enabled', False),
        org_data.get('is_deleted', False),
        org_data.get('created_at'),
        org_data.get('updated_at'),
        datetime.now()
    ))

    return 0 if exists else 1  # Return 1 if new organization

def sync_custom_fields(conn, org_uid, custom_fields):
    """Sync custom fields for an organization"""
    cursor = conn.cursor()

    # Delete existing custom fields for this org
    cursor.execute("DELETE FROM organization_custom_fields WHERE organization_uid = ?", (org_uid,))

    # Insert new custom fields
    for field in custom_fields:
        cursor.execute("""
            INSERT INTO organization_custom_fields (
                organization_uid, field_label, field_value, field_type,
                hide_to_fe, hide_field, read_only, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            org_uid,
            field.get('label'),
            field.get('value'),
            field.get('type'),
            field.get('hide_to_fe', False),
            field.get('hide_field', False),
            field.get('read_only', False),
            datetime.now()
        ))

def create_alerts_for_missing_netsuite_ids(conn):
    """Create alerts for organizations missing NetSuite IDs"""
    cursor = conn.cursor()

    # Find organizations without NetSuite ID
    cursor.execute("""
        SELECT organization_uid, organization_name, created_at
        FROM netsuite_mapping
        WHERE has_netsuite_id = 0 AND is_active = 1
    """)

    missing_orgs = cursor.fetchall()

    for org_uid, org_name, created_at in missing_orgs:
        # Check if alert already exists
        cursor.execute("""
            SELECT id FROM alerts
            WHERE organization_uid = ? AND alert_type = 'missing_netsuite_id' AND is_resolved = 0
        """, (org_uid,))

        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO alerts (organization_uid, alert_type, alert_message, created_at)
                VALUES (?, 'missing_netsuite_id', ?, ?)
            """, (org_uid, f"Organization '{org_name}' is missing NetSuite Customer ID", created_at))

    conn.commit()

    return len(missing_orgs)

def sync_all_organizations(conn):
    """Sync all organizations from API to database"""
    log_id = start_sync_log(conn)

    # Fetch basic organization list
    organizations = fetch_organizations_from_api()
    print(f"\n✓ Fetched {len(organizations)} organizations")

    orgs_created = 0
    orgs_updated = 0
    errors = []

    print("\nFetching detailed data for each organization...")
    for i, org in enumerate(organizations, 1):
        org_uid = org['organization_uid']
        org_name = org['organization_name']

        print(f"  [{i}/{len(organizations)}] {org_name}")

        try:
            # Fetch detailed data
            details = fetch_organization_details(org_uid)

            if details and details.get('data'):
                org_data = details['data']

                # Sync organization
                is_new = sync_organization(conn, org_data)
                if is_new:
                    orgs_created += 1
                else:
                    orgs_updated += 1

                # Sync custom fields
                custom_fields = org_data.get('custom_fields', [])
                sync_custom_fields(conn, org_uid, custom_fields)
            else:
                errors.append(f"Failed to fetch details for {org_name}")

        except Exception as e:
            error_msg = f"Error syncing {org_name}: {str(e)}"
            errors.append(error_msg)
            print(f"    ✗ {error_msg}")

    conn.commit()

    # Create alerts
    print("\nCreating alerts for missing NetSuite IDs...")
    alerts_created = create_alerts_for_missing_netsuite_ids(conn)
    print(f"✓ Created {alerts_created} alerts")

    # Complete sync log
    error_text = "; ".join(errors) if errors else None
    complete_sync_log(conn, log_id, len(organizations), orgs_updated, orgs_created, error_text)

    print("\n" + "=" * 60)
    print("SYNC COMPLETE")
    print("=" * 60)
    print(f"Organizations fetched: {len(organizations)}")
    print(f"New organizations: {orgs_created}")
    print(f"Updated organizations: {orgs_updated}")
    print(f"Alerts created: {alerts_created}")
    if errors:
        print(f"Errors: {len(errors)}")
    print("=" * 60)

if __name__ == "__main__":
    print("ZUPER-NETSUITE DATABASE SYNC")
    print("=" * 60)

    # Initialize database
    conn = init_database()

    # Sync all organizations
    sync_all_organizations(conn)

    conn.close()
    print("\n✓ Database sync completed successfully")
