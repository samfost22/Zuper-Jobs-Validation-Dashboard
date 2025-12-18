#!/usr/bin/env python3
"""
Sync Zuper Jobs to SQLite Database
Extracts jobs, line items, checklist parts, and runs validation logic
"""

import json
import os
import sqlite3
import re
from datetime import datetime
from pathlib import Path

# Use persistent data directory
DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(exist_ok=True)
DB_FILE = str(DATA_DIR / 'jobs_validation.db')
JOBS_DATA_FILE = 'jobs_data.json'

# Slack webhook URL (can be set via environment or passed to sync function)
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL', '')

# Feature flag for batch inserts (Phase 4 optimization)
# Set to "true" to use executemany() instead of individual INSERTs
# This significantly improves sync performance for large datasets
USE_BATCH_INSERTS = os.environ.get('USE_BATCH_INSERTS', 'true').lower() == 'true'

# Configuration constants
ALLOWED_JOB_CATEGORIES = [
    'LaserWeeder Service Call',
    'WM Service - In Field',
    'WM Repair - In Shop'
]

SKIP_VALIDATION_CATEGORIES = [
    'field requires parts',
    'reaper pm',
    'slayer pm',
]

CONSUMABLE_TERMS = ['consumable', 'consumables', 'supplies', 'service']

# Serial number patterns by part type
# Add new patterns here as needed - they will automatically be included in searches
# Note: -? makes dashes optional to handle input like "WM250613004" or "CRSM000571RW"
SERIAL_PATTERNS = {
    'scanner_module': r'CR-?SM-?\d{6}(?:-?RW)?',   # 0000144: CR-SM-000571, CR-SM-000571-RW
    'y150_component': r'CR-?Y150-?\d{6}-?R',       # 0000508-C: CR-Y150-005032-R
    'mpc_component': r'CR-?MPC-?\d{5}',            # G4000: CR-MPC-00278
    'sm_module': r'SM-?\d{6}-?\d{3}',              # 0000612-B: SM-250721-002
    'weeding_module': r'WM-?\d{6}-?\d{3}',         # 0000675: WM-250613-004
}

# Combined pattern for matching any serial number
SERIAL_PATTERN = '(?:' + '|'.join(SERIAL_PATTERNS.values()) + ')'

def init_database():
    """Initialize the SQLite database with schema"""
    print("Initializing database...")

    # Read schema file
    schema_file = os.path.join(os.path.dirname(__file__), 'database_jobs_schema.sql')
    with open(schema_file, 'r') as f:
        schema = f.read()

    # Connect and execute schema
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Execute schema (multiple statements)
    cursor.executescript(schema)

    conn.commit()
    conn.close()

    print(f"✓ Database initialized: {DB_FILE}")

def load_jobs_data():
    """Load jobs from JSON file"""
    filepath = os.path.join(os.path.dirname(__file__), JOBS_DATA_FILE)

    if not os.path.exists(filepath):
        print(f"Error: {JOBS_DATA_FILE} not found")
        return None

    with open(filepath, 'r') as f:
        data = json.load(f)

    jobs = data.get('jobs', [])
    print(f"✓ Loaded {len(jobs)} jobs from {JOBS_DATA_FILE}")

    return jobs

def normalize_serial(serial):
    """Normalize a serial number to canonical format with proper dashes.

    Converts any valid serial input to standard format:
    - WM250613004 → WM-250613-004
    - CRSM000571RW → CR-SM-000571-RW
    - sm250721002 → SM-250721-002
    """
    s = serial.upper().replace('-', '')  # Remove existing dashes, uppercase

    # CR-SM-NNNNNN or CR-SM-NNNNNN-RW (Scanner Module)
    if s.startswith('CRSM'):
        digits = s[4:]
        if digits.endswith('RW'):
            return f"CR-SM-{digits[:-2]}-RW"
        return f"CR-SM-{digits}"

    # CR-Y150-NNNNNN-R (Y150 Component)
    if s.startswith('CRY150'):
        digits = s[6:]
        if digits.endswith('R'):
            return f"CR-Y150-{digits[:-1]}-R"
        return f"CR-Y150-{digits}"

    # CR-MPC-NNNNN (MPC Component)
    if s.startswith('CRMPC'):
        return f"CR-MPC-{s[5:]}"

    # SM-YYMMDD-NNN (SM Module)
    if s.startswith('SM') and not s.startswith('CRSM'):
        digits = s[2:]
        if len(digits) >= 9:
            return f"SM-{digits[:6]}-{digits[6:]}"
        return f"SM-{digits}"

    # WM-YYMMDD-NNN (Weeding Module)
    if s.startswith('WM'):
        digits = s[2:]
        if len(digits) >= 9:
            return f"WM-{digits[:6]}-{digits[6:]}"
        return f"WM-{digits}"

    return serial.upper()  # Return as-is if no pattern matched


def extract_serial_from_text(text):
    """Extract serial numbers from text using regex.

    Matches patterns defined in SERIAL_PATTERNS dict:
    - CR-SM-NNNNNN[-RW]: Scanner Module (0000144)
    - CR-Y150-NNNNNN-R: Y150 Component (0000508-C)
    - CR-MPC-NNNNN: MPC Component (G4000)
    - SM-YYMMDD-NNN: SM Module (0000612-B)
    - WM-YYMMDD-NNN: Weeding Module (0000675)

    Handles common input errors like extra spaces or missing dashes.
    All serials are normalized to canonical format (e.g., WM-250613-004).
    To add new patterns, update the SERIAL_PATTERNS dictionary.
    """
    if not text:
        return []

    # Normalize: remove ALL whitespace (spaces, tabs) to handle typos like "WM - 250613-004"
    normalized = ''.join(str(text).split())
    matches = re.findall(SERIAL_PATTERN, normalized, re.IGNORECASE)
    # Normalize each match to canonical format with dashes
    return [normalize_serial(m) for m in matches]

def extract_asset_from_job(job):
    """Extract asset information from job's assets array"""
    assets = job.get('assets', [])

    if not assets:
        return ''

    # Take the first asset if multiple exist
    first_asset = assets[0] if isinstance(assets, list) else assets

    # Navigate the nested structure: assets[0].asset.asset_code or .asset_name
    if isinstance(first_asset, dict):
        asset_data = first_asset.get('asset', {})
        if isinstance(asset_data, dict):
            # Prefer asset_code (e.g., "S38"), fallback to asset_name
            return asset_data.get('asset_code', '') or asset_data.get('asset_name', '')

    return ''

def extract_netsuite_id(job):
    """Extract NetSuite Sales Order ID from custom fields"""
    custom_fields = job.get('custom_fields', [])

    for field in custom_fields:
        label = field.get('label', '').lower()

        # Look for various NetSuite ID field names
        if any(term in label for term in ['netsuite', 'sales order', 'so id', 'salesorder']):
            value = field.get('value', '')
            if value and str(value).strip():
                return str(value).strip()

    return None

def extract_line_items(job):
    """Extract line items from job products array"""
    line_items = []

    # Extract from 'products' field (this is where Zuper stores line items)
    products = job.get('products', [])

    for product in products:
        # Extract serial numbers if available
        serial_nos = product.get('serial_nos', [])
        item_serial = ', '.join(serial_nos) if serial_nos else ''

        # Product details are directly on the product object
        line_items.append({
            'item_name': product.get('product_name', ''),
            'item_code': product.get('product_id', ''),
            'item_serial': item_serial,
            'quantity': product.get('quantity', 1),
            'price': product.get('price', '0'),
            'line_item_type': product.get('product_type', '')
        })

    return line_items

def extract_checklist_parts(job):
    """Extract parts mentioned in job checklists"""
    parts = []

    # Navigate through job_status -> checklist
    job_status_list = job.get('job_status', [])

    for status in job_status_list:
        status_name = status.get('status_name', '')
        checklist = status.get('checklist', [])

        for item in checklist:
            question = item.get('question', '')
            answer = item.get('answer', '')

            # Extract serial numbers from answer
            serials = extract_serial_from_text(answer)

            for serial in serials:
                parts.append({
                    'checklist_question': question,
                    'part_serial': serial,
                    'part_description': answer[:200],  # Truncate long answers
                    'status_name': status_name,
                    'position': question,  # Use question as position identifier
                    'updated_at': item.get('updated_at', '')
                })

    return parts

def extract_custom_fields(job):
    """Extract all custom fields for storage"""
    custom_fields = []

    for field in job.get('custom_fields', []):
        custom_fields.append({
            'field_label': field.get('label', ''),
            'field_value': str(field.get('value', '')),
            'field_type': field.get('type', '')
        })

    return custom_fields

def get_jira_link(job):
    """Extract or construct Jira link from job"""
    # Check custom fields for Jira link
    for field in job.get('custom_fields', []):
        if 'jira' in field.get('label', '').lower():
            return field.get('value', '')

    # Could also construct from job number if pattern exists
    return None

def get_slack_link(job):
    """Extract or construct Slack link from job"""
    # Check custom fields for Slack link
    for field in job.get('custom_fields', []):
        if 'slack' in field.get('label', '').lower():
            return field.get('value', '')

    return None

def get_completion_date(job):
    """Extract completion date from job status history"""
    job_statuses = job.get('job_status', [])

    # Look for the most recent COMPLETED or CLOSED status
    for status in reversed(job_statuses):
        status_type = status.get('status_type', '')
        if status_type in ['COMPLETED', 'CLOSED']:
            return status.get('updated_at', '')

    return None

def get_service_team(job):
    """
    Extract service team from the user who last worked on the job.
    Uses done_by from the most recent non-NEW status, cross-referenced with assigned_to for team info.
    Falls back to assigned_to_team if done_by not available.
    """
    # Try to get team from the most recent status change (done_by)
    job_statuses = job.get('job_status', [])
    assigned_to = job.get('assigned_to', [])

    # Look through statuses in reverse order to find most recent non-NEW status with done_by
    for status in reversed(job_statuses):
        if status.get('status_type') != 'NEW':
            done_by = status.get('done_by', {})
            if done_by:
                done_by_uid = done_by.get('user_uid')

                # Find this user in assigned_to to get their team
                for assignment in assigned_to:
                    user = assignment.get('user', {})
                    if user.get('user_uid') == done_by_uid:
                        team = assignment.get('team', {})
                        team_name = team.get('team_name', '')
                        if team_name:
                            return team_name
                        break

    # Fallback: use assigned_to_team (primary team)
    assigned_to_team = job.get('assigned_to_team', [])
    if assigned_to_team and len(assigned_to_team) > 0:
        first_team = assigned_to_team[0]
        team_info = first_team.get('team', {})
        team_name = team_info.get('team_name', '')
        if team_name:
            return team_name

    return None

def get_job_category(job):
    """Extract job category"""
    categories = job.get('job_category', [])
    if isinstance(categories, list) and categories:
        return categories[0].get('category_name', '')
    elif isinstance(categories, dict):
        return categories.get('category_name', '')
    return ''

def sync_jobs_to_database(jobs, slack_webhook_url=None):
    """
    Sync all jobs to database and send Slack notifications for completed jobs
    missing NetSuite IDs.

    Args:
        jobs: List of job dictionaries from Zuper API
        slack_webhook_url: Optional Slack webhook URL for notifications
    """
    print("\nSyncing jobs to database...")

    # Use provided webhook URL or fall back to environment variable
    webhook_url = slack_webhook_url or SLACK_WEBHOOK_URL

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Define allowed job categories (ALLOWLIST approach)
    allowed_categories = ALLOWED_JOB_CATEGORIES
    print(f"Filtering for allowed job categories: {', '.join(allowed_categories)}")

    # Clean up jobs not in allowed categories from previous syncs
    placeholders = ','.join('?' * len(allowed_categories))
    cursor.execute(f"""
        DELETE FROM jobs WHERE job_category NOT IN ({placeholders})
    """, allowed_categories)
    deleted_count = cursor.rowcount
    if deleted_count > 0:
        print(f"  Deleted {deleted_count} jobs from non-allowed categories")
    conn.commit()

    # Track all unique categories encountered (for detecting changes)
    categories_found = set()

    # Start sync log
    cursor.execute("""
        INSERT INTO sync_log (sync_started_at, status)
        VALUES (?, 'in_progress')
    """, (datetime.now().isoformat(),))
    sync_id = cursor.lastrowid

    jobs_processed = 0
    jobs_skipped = 0
    flags_created = 0
    errors = []
    organizations_synced = set()

    for job in jobs:
        try:
            job_uid = job.get('job_uid')
            if not job_uid:
                continue

            # Get and track job category
            job_category = get_job_category(job)
            if job_category:
                categories_found.add(job_category)

            # Only process jobs in allowed categories
            if job_category not in allowed_categories:
                jobs_skipped += 1
                continue

            # Extract organization data
            customer = job.get('customer')
            organization_uid = None
            organization_name = None

            if customer and isinstance(customer, dict):
                org = customer.get('customer_organization', {})
                if org:
                    organization_uid = org.get('organization_uid')
                    organization_name = org.get('organization_name', '')

                    # Sync organization if we haven't seen it yet
                    if organization_uid and organization_uid not in organizations_synced:
                        cursor.execute("""
                            INSERT OR IGNORE INTO organizations (
                                organization_uid, organization_name, updated_at
                            ) VALUES (?, ?, ?)
                        """, (organization_uid, organization_name, datetime.now().isoformat()))
                        organizations_synced.add(organization_uid)

            # Extract data
            line_items = extract_line_items(job)
            checklist_parts = extract_checklist_parts(job)
            netsuite_id = extract_netsuite_id(job)
            custom_fields = extract_custom_fields(job)

            # Insert/update job
            cursor.execute("""
                INSERT OR REPLACE INTO jobs (
                    job_uid, job_number, job_title, job_status, job_category,
                    customer_name, organization_uid, organization_name, service_team,
                    asset_name, created_at, updated_at, completed_at,
                    has_line_items, has_checklist_parts, has_netsuite_id,
                    netsuite_sales_order_id, jira_link, slack_link, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_uid,
                job.get('work_order_number', '') or job.get('job_number', ''),
                job.get('job_title', ''),
                job.get('job_status', [{}])[0].get('status_name', '') if job.get('job_status') else '',
                job_category,
                job.get('customer_name', ''),
                organization_uid,
                organization_name,
                get_service_team(job),
                extract_asset_from_job(job),
                job.get('created_at', ''),
                job.get('updated_at', ''),
                get_completion_date(job),
                1 if line_items else 0,
                1 if checklist_parts else 0,
                1 if netsuite_id else 0,
                netsuite_id,
                get_jira_link(job),
                get_slack_link(job),
                datetime.now().isoformat()
            ))

            # Insert line items
            cursor.execute("DELETE FROM job_line_items WHERE job_uid = ?", (job_uid,))
            if line_items:
                if USE_BATCH_INSERTS:
                    # Batch insert - significantly faster for multiple items
                    cursor.executemany("""
                        INSERT INTO job_line_items (
                            job_uid, item_name, item_code, item_serial,
                            quantity, price, line_item_type, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, [(
                        job_uid,
                        item['item_name'],
                        item['item_code'],
                        item['item_serial'],
                        item['quantity'],
                        item['price'],
                        item['line_item_type'],
                        job.get('created_at', '')
                    ) for item in line_items])
                else:
                    # Legacy: individual inserts
                    for item in line_items:
                        cursor.execute("""
                            INSERT INTO job_line_items (
                                job_uid, item_name, item_code, item_serial,
                                quantity, price, line_item_type, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            job_uid,
                            item['item_name'],
                            item['item_code'],
                            item['item_serial'],
                            item['quantity'],
                            item['price'],
                            item['line_item_type'],
                            job.get('created_at', '')
                        ))

            # Insert checklist parts
            cursor.execute("DELETE FROM job_checklist_parts WHERE job_uid = ?", (job_uid,))
            if checklist_parts:
                if USE_BATCH_INSERTS:
                    # Batch insert
                    cursor.executemany("""
                        INSERT INTO job_checklist_parts (
                            job_uid, checklist_question, part_serial,
                            part_description, status_name, position, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, [(
                        job_uid,
                        part['checklist_question'],
                        part['part_serial'],
                        part['part_description'],
                        part['status_name'],
                        part['position'],
                        part['updated_at']
                    ) for part in checklist_parts])
                else:
                    # Legacy: individual inserts
                    for part in checklist_parts:
                        cursor.execute("""
                            INSERT INTO job_checklist_parts (
                                job_uid, checklist_question, part_serial,
                                part_description, status_name, position, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            job_uid,
                            part['checklist_question'],
                            part['part_serial'],
                            part['part_description'],
                            part['status_name'],
                            part['position'],
                            part['updated_at']
                        ))

            # Insert custom fields
            cursor.execute("DELETE FROM job_custom_fields WHERE job_uid = ?", (job_uid,))
            if custom_fields:
                if USE_BATCH_INSERTS:
                    # Batch insert
                    cursor.executemany("""
                        INSERT OR IGNORE INTO job_custom_fields (
                            job_uid, field_label, field_value, field_type
                        ) VALUES (?, ?, ?, ?)
                    """, [(
                        job_uid,
                        field['field_label'],
                        field['field_value'],
                        field['field_type']
                    ) for field in custom_fields])
                else:
                    # Legacy: individual inserts
                    for field in custom_fields:
                        cursor.execute("""
                            INSERT OR IGNORE INTO job_custom_fields (
                                job_uid, field_label, field_value, field_type
                            ) VALUES (?, ?, ?, ?)
                        """, (
                            job_uid,
                            field['field_label'],
                            field['field_value'],
                            field['field_type']
                        ))

            # Run validation logic
            # Get job category
            job_category = job.get('job_category', {})
            category_name = job_category.get('category_name', '') if isinstance(job_category, dict) else ''

            validation_flags = validate_job(job_uid, line_items, checklist_parts, netsuite_id, category_name)

            # Clear old flags for this job
            cursor.execute("DELETE FROM validation_flags WHERE job_uid = ?", (job_uid,))

            # Insert new flags and send notifications
            job_number = job.get('work_order_number', '') or job.get('job_number', '')
            job_title = job.get('job_title', '')
            service_team = get_service_team(job)
            asset_name = extract_asset_from_job(job)
            completed_at = get_completion_date(job)

            for flag in validation_flags:
                cursor.execute("""
                    INSERT INTO validation_flags (
                        job_uid, flag_type, flag_severity, flag_message, details, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    job_uid,
                    flag['flag_type'],
                    flag['flag_severity'],
                    flag['flag_message'],
                    json.dumps(flag.get('details', {})),
                    datetime.now().isoformat()
                ))
                flags_created += 1

                # Send Slack notification for RECENTLY completed jobs missing NetSuite ID
                # Only notify jobs completed in the last 48 hours to avoid flooding on first sync
                if (webhook_url and
                    flag['flag_type'] == 'missing_netsuite_id' and
                    completed_at):
                    try:
                        from notifications.slack_notifier import send_missing_netsuite_notification

                        # Check if job was completed recently (within 48 hours)
                        is_recent = False
                        try:
                            # Handle various date formats from Zuper API
                            date_str = completed_at.replace('Z', '').replace('+00:00', '')
                            # Remove microseconds if present (take only first 19 chars: YYYY-MM-DDTHH:MM:SS)
                            if 'T' in date_str and len(date_str) > 19:
                                date_str = date_str[:19]
                            completed_dt = datetime.fromisoformat(date_str)
                            hours_ago = (datetime.now() - completed_dt).total_seconds() / 3600
                            is_recent = hours_ago <= 48
                            print(f"  Job {job_number}: completed {hours_ago:.1f} hours ago, is_recent={is_recent}")
                        except Exception as date_err:
                            print(f"  Warning: Could not parse date '{completed_at}' for job {job_number}: {date_err}")
                            is_recent = False

                        if is_recent:
                            line_item_names = flag.get('details', {}).get('line_items', [])
                            result = send_missing_netsuite_notification(
                                webhook_url=webhook_url,
                                job_uid=job_uid,
                                job_number=job_number,
                                job_title=job_title,
                                organization_name=organization_name,
                                asset_name=asset_name,
                                service_team=service_team,
                                completed_at=completed_at,
                                line_items=line_item_names
                            )
                            if result:
                                print(f"  ✓ Slack notification sent for job {job_number}")
                            else:
                                print(f"  ✗ Slack notification skipped/failed for job {job_number}")
                    except Exception as notif_error:
                        # Don't fail sync if notification fails
                        print(f"  Warning: Failed to send Slack notification for {job_number}: {notif_error}")

            jobs_processed += 1

            if jobs_processed % 100 == 0:
                print(f"  Processed {jobs_processed} jobs...")
                conn.commit()

        except Exception as e:
            error_msg = f"Error processing job {job.get('job_uid', 'unknown')}: {str(e)}"
            errors.append(error_msg)
            print(f"  ✗ {error_msg}")

    # Update sync log
    cursor.execute("""
        UPDATE sync_log
        SET sync_completed_at = ?,
            jobs_processed = ?,
            flags_created = ?,
            errors = ?,
            status = 'completed'
        WHERE id = ?
    """, (
        datetime.now().isoformat(),
        jobs_processed,
        flags_created,
        json.dumps(errors) if errors else None,
        sync_id
    ))

    conn.commit()
    conn.close()

    print(f"\n✓ Sync complete!")
    print(f"  Jobs processed: {jobs_processed}")
    print(f"  Jobs skipped: {jobs_skipped}")
    print(f"  Validation flags created: {flags_created}")
    if errors:
        print(f"  Errors: {len(errors)}")

    # Report all job categories found (for detecting unexpected changes)
    print(f"\n📊 Job categories found in API:")
    for category in sorted(categories_found):
        status = "✓ ALLOWED" if category in allowed_categories else "⚠️  SKIPPED"
        print(f"  {status}: {category}")

    # Warn about unexpected categories
    unexpected_categories = categories_found - set(allowed_categories)
    if unexpected_categories:
        print(f"\n⚠️  WARNING: Found {len(unexpected_categories)} unexpected job categories!")
        print(f"  These categories are being SKIPPED and NOT synced to database:")
        for category in sorted(unexpected_categories):
            print(f"    - {category}")
        print(f"  If these should be included, update the allowed_categories list in sync_jobs_to_db.py")

    return jobs_processed, flags_created

def validate_job(job_uid, line_items, checklist_parts, netsuite_id, job_category=''):
    """
    Run validation logic on a job
    Returns list of validation flags
    """
    flags = []

    # Skip validation for certain job categories that don't need NetSuite tracking
    if any(category in job_category.lower() for category in SKIP_VALIDATION_CATEGORIES):
        return flags

    # Rule 1: If job has line items but no NetSuite ID
    # Exclude consumables and services - they don't need NetSuite tracking
    if line_items and not netsuite_id:
        # Filter out consumables and services
        non_consumable_items = []
        for item in line_items:
            item_name = (item.get('item_name') or '').lower()
            item_code = (item.get('item_code') or '').lower()
            item_serial = (item.get('item_serial') or '').lower()
            item_type = (item.get('line_item_type') or '').lower()

            # Check if this is a consumable or service (these don't need NetSuite tracking)
            is_consumable = any(
                term in item_name or term in item_code or term in item_serial or term in item_type
                for term in CONSUMABLE_TERMS
            )

            if not is_consumable:
                non_consumable_items.append(item)

        # Only flag if there are non-consumable items without NetSuite ID
        if non_consumable_items:
            flags.append({
                'flag_type': 'missing_netsuite_id',
                'flag_severity': 'error',
                'flag_message': f'Job has {len(non_consumable_items)} non-consumable line item(s) but missing NetSuite Sales Order ID',
                'details': {
                    'line_items_count': len(non_consumable_items),
                    'line_items': [item['item_name'] for item in non_consumable_items],
                    'consumables_excluded': len(line_items) - len(non_consumable_items)
                }
            })

    # Rule 2: Checklist parts replaced but no line items
    # Flag when someone marked parts as replaced in checklist but didn't add any line items
    if checklist_parts and not line_items:
        parts_list = [part['part_serial'] for part in checklist_parts]
        flags.append({
            'flag_type': 'parts_replaced_no_line_items',
            'flag_severity': 'error',
            'flag_message': f'Checklist shows {len(checklist_parts)} part(s) replaced but no line items added',
            'details': {
                'parts_count': len(checklist_parts),
                'parts_replaced': parts_list
            }
        })

    return flags

def print_validation_summary():
    """Print summary of validation results"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    # Total jobs
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]
    print(f"\nTotal Jobs: {total_jobs}")

    # Jobs with line items
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_line_items = 1")
    jobs_with_line_items = cursor.fetchone()[0]
    print(f"Jobs with Line Items: {jobs_with_line_items}")

    # Jobs with checklist parts
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_checklist_parts = 1")
    jobs_with_checklist = cursor.fetchone()[0]
    print(f"Jobs with Checklist Parts: {jobs_with_checklist}")

    # Jobs with NetSuite ID
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_netsuite_id = 1")
    jobs_with_netsuite = cursor.fetchone()[0]
    print(f"Jobs with NetSuite Sales Order ID: {jobs_with_netsuite}")

    # Validation flags
    print("\n" + "-" * 80)
    print("VALIDATION FLAGS")
    print("-" * 80)

    cursor.execute("""
        SELECT flag_type, flag_severity, COUNT(*) as count
        FROM validation_flags
        WHERE is_resolved = 0
        GROUP BY flag_type, flag_severity
        ORDER BY flag_severity DESC, count DESC
    """)

    for row in cursor.fetchall():
        flag_type, severity, count = row
        emoji = "🔴" if severity == 'error' else "⚠️"
        print(f"{emoji} {flag_type} ({severity}): {count} jobs")

    # Jobs with no issues
    cursor.execute("""
        SELECT COUNT(*)
        FROM jobs j
        LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
        WHERE vf.id IS NULL
    """)
    jobs_passing = cursor.fetchone()[0]
    print(f"\n✅ Jobs Passing All Validations: {jobs_passing}")

    # Top 10 jobs with most flags
    print("\n" + "-" * 80)
    print("TOP 10 JOBS WITH MOST VALIDATION ISSUES")
    print("-" * 80)

    cursor.execute("""
        SELECT j.job_number, j.job_title, COUNT(vf.id) as flag_count
        FROM jobs j
        JOIN validation_flags vf ON j.job_uid = vf.job_uid
        WHERE vf.is_resolved = 0
        GROUP BY j.job_uid
        ORDER BY flag_count DESC
        LIMIT 10
    """)

    for row in cursor.fetchall():
        job_number, job_title, flag_count = row
        print(f"  {job_number}: {job_title} ({flag_count} flags)")

    conn.close()

if __name__ == "__main__":
    print("ZUPER JOBS VALIDATION - DATABASE SYNC")
    print("=" * 80)

    # Initialize database
    init_database()

    # Load jobs data
    jobs = load_jobs_data()

    if not jobs:
        print("Error: No jobs data available")
        exit(1)

    # Sync jobs to database
    sync_jobs_to_database(jobs)

    # Print validation summary
    print_validation_summary()

    print("\n✓ Database sync complete!")
    print(f"✓ Database file: {DB_FILE}")
