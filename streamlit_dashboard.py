#!/usr/bin/env python3
"""
Zuper Jobs Validation Dashboard - Streamlit Version
"""

import streamlit as st
import sqlite3
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
import re
from streamlit_sync import ZuperSync, test_api_connection
from sync_jobs_to_db import normalize_serial, SERIAL_PATTERN
from github_artifact import ensure_database_from_artifact

# Use persistent data directory
DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(exist_ok=True)
DB_FILE = str(DATA_DIR / 'jobs_validation.db')

# Page config
st.set_page_config(
    page_title="Zuper Jobs Validation Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'current_filter' not in st.session_state:
    st.session_state.current_filter = 'all'
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1
if 'month_filter' not in st.session_state:
    st.session_state.month_filter = ''
if 'org_filter' not in st.session_state:
    st.session_state.org_filter = ''
if 'team_filter' not in st.session_state:
    st.session_state.team_filter = ''
if 'start_date' not in st.session_state:
    st.session_state.start_date = None
if 'end_date' not in st.session_state:
    st.session_state.end_date = None
if 'job_number_search' not in st.session_state:
    st.session_state.job_number_search = ''
if 'part_search' not in st.session_state:
    st.session_state.part_search = ''
if 'serial_search' not in st.session_state:
    st.session_state.serial_search = ''
if 'asset_filter' not in st.session_state:
    st.session_state.asset_filter = ''


def ensure_database_exists():
    """Initialize database if it doesn't exist, downloading from GitHub artifact if available"""
    import os
    if not os.path.exists(DB_FILE):
        # Try to download from GitHub artifact first (for Streamlit Cloud)
        if not ensure_database_from_artifact(DB_FILE):
            # Fall back to creating empty database
            from streamlit_sync import init_database
            init_database()


def get_db_connection():
    """Get database connection with timeout"""
    ensure_database_exists()
    conn = sqlite3.connect(DB_FILE, timeout=30.0)  # 30 second timeout
    conn.row_factory = sqlite3.Row
    return conn


def normalize_search_input(search_term):
    """Normalize serial number search input to handle human error.

    Handles:
    - Extra spaces/tabs: "WM 250613 004" → "WM-250613-004"
    - Missing dashes: "wm250613004" → "WM-250613-004"
    - Mixed case: "wM-250613-004" → "WM-250613-004"
    - Partial input: "250613" → "250613" (unchanged, for partial matches)

    Returns normalized serial if it matches a known pattern, otherwise
    returns cleaned input for partial matching.
    """
    if not search_term:
        return ''

    # Remove ALL whitespace (spaces, tabs, newlines) for pattern matching
    cleaned = ''.join(search_term.split())

    # Try to match against known serial patterns
    matches = re.findall(SERIAL_PATTERN, cleaned, re.IGNORECASE)
    if matches:
        # Found a valid serial pattern - normalize it
        return normalize_serial(matches[0])

    # No pattern match - return cleaned input for partial search
    # This allows searching by partial serial like "250613" or "000571"
    return cleaned.upper()


def search_serials_batch(serial_pairs, cursor):
    """
    Search for multiple serial numbers in a single batched query.

    Args:
        serial_pairs: List of (raw_serial, normalized_serial) tuples
        cursor: Database cursor

    Returns:
        List of result dicts with 'searched_serial' properly attributed
    """
    if not serial_pairs:
        return []

    # Get unique normalized serials for the query
    unique_serials = list(set(normalized for _, normalized in serial_pairs if normalized))

    if not unique_serials:
        return []

    # Build a single query with OR conditions for all serials
    # This replaces N queries with 1 query
    or_conditions = []
    params = []
    for serial in unique_serials:
        or_conditions.append("(li.item_serial LIKE ? OR cp.part_serial LIKE ?)")
        params.extend([f'%{serial}%', f'%{serial}%'])

    query = f"""
        SELECT DISTINCT j.job_uid, j.job_number, j.job_title, j.customer_name,
               j.created_at, j.asset_name, j.service_team,
               li.item_serial as line_item_serial,
               li.item_name as line_item_name,
               cp.part_serial as checklist_serial,
               cp.checklist_question as checklist_question
        FROM jobs j
        LEFT JOIN job_line_items li ON j.job_uid = li.job_uid
        LEFT JOIN job_checklist_parts cp ON j.job_uid = cp.job_uid
        WHERE ({' OR '.join(or_conditions)})
        ORDER BY j.created_at DESC
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # Build a mapping from normalized serial to raw serial for display
    serial_display_map = {}
    for raw, normalized in serial_pairs:
        if normalized:
            if normalized not in serial_display_map:
                serial_display_map[normalized] = raw if raw != normalized else normalized

    results = []
    for row in rows:
        line_serial = row['line_item_serial'] or ''
        check_serial = row['checklist_serial'] or ''

        # Determine which searched serial(s) matched this row
        matched_serials = set()
        for raw, normalized in serial_pairs:
            if not normalized:
                continue
            if normalized.upper() in line_serial.upper() or normalized.upper() in check_serial.upper():
                display = f"{raw} → {normalized}" if raw != normalized else normalized
                matched_serials.add(display)

        # Determine source context
        if check_serial:
            source = row['checklist_question'] or 'Checklist'
        elif line_serial:
            source = row['line_item_name'] or 'Line Item'
        else:
            source = 'Unknown'

        # Create a result entry for each matched serial
        for searched in matched_serials:
            results.append({
                'searched_serial': searched,
                'source': source,
                'job_number': row['job_number'],
                'job_title': row['job_title'],
                'customer': row['customer_name'],
                'asset': row['asset_name'] or 'N/A',
                'service_team': row['service_team'] or 'N/A',
                'created_at': row['created_at'],
                'job_uid': row['job_uid']
            })

    return results


@st.cache_data(ttl=60)  # Cache for 60 seconds
def get_metrics():
    """Get dashboard metrics with a single optimized query"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Combined query: get all metrics in one database round-trip
        cursor.execute("""
            SELECT
                COUNT(DISTINCT j.job_uid) as total_jobs,
                COUNT(DISTINCT CASE
                    WHEN vf.flag_type = 'parts_replaced_no_line_items' AND vf.is_resolved = 0
                    THEN vf.job_uid
                END) as parts_no_items_count,
                COUNT(DISTINCT CASE
                    WHEN vf.flag_type = 'missing_netsuite_id' AND vf.is_resolved = 0
                    THEN vf.job_uid
                END) as missing_netsuite_count,
                COUNT(DISTINCT CASE
                    WHEN vf.id IS NULL
                    THEN j.job_uid
                END) as passing_count
            FROM jobs j
            LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
        """)

        row = cursor.fetchone()
        conn.close()

        return {
            'total_jobs': row['total_jobs'] or 0,
            'parts_no_items_count': row['parts_no_items_count'] or 0,
            'missing_netsuite_count': row['missing_netsuite_count'] or 0,
            'passing_count': row['passing_count'] or 0
        }
    except Exception as e:
        # Return zeros if database is empty or has issues
        return {
            'total_jobs': 0,
            'parts_no_items_count': 0,
            'missing_netsuite_count': 0,
            'passing_count': 0
        }


@st.cache_data(ttl=60)  # Cache for 60 seconds
def get_jobs(filter_type='all', page=1, month='', organization='', team='', start_date=None, end_date=None, job_number='', part_search='', serial_search='', asset='', limit=50):
    """Get jobs list with filtering and pagination using parameterized queries"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * limit
    except:
        # Return empty result if database has issues
        return [], 0

    try:
        # Build filter clauses with parameterized queries (prevents SQL injection)
        filter_clauses = []
        params = []

        # Job number search (exact or partial match)
        if job_number:
            filter_clauses.append("j.job_number LIKE ?")
            params.append(f"%{job_number}%")

        # Date range filter (takes precedence over month filter)
        if start_date and end_date:
            filter_clauses.append("date(COALESCE(j.completed_at, j.created_at)) BETWEEN ? AND ?")
            params.extend([start_date, end_date])
        elif month:
            filter_clauses.append("strftime('%Y-%m', COALESCE(j.completed_at, j.created_at)) = ?")
            params.append(month)

        if organization:
            filter_clauses.append("j.organization_name LIKE ?")
            params.append(f"%{organization}%")

        if team:
            filter_clauses.append("j.service_team LIKE ?")
            params.append(f"%{team}%")

        if asset:
            filter_clauses.append("j.asset_name = ?")
            params.append(asset)

        date_clause = ("AND " + " AND ".join(filter_clauses)) if filter_clauses else ""

        # Add part search join if needed
        part_join = ""
        part_where = ""
        part_params = []
        if part_search:
            part_join = "JOIN job_line_items li ON j.job_uid = li.job_uid"
            part_where = "AND (li.item_name LIKE ? OR li.item_code LIKE ?)"
            part_params.extend([f"%{part_search}%", f"%{part_search}%"])

        # Add serial number search join if needed
        serial_join = ""
        serial_where = ""
        serial_params = []
        if serial_search:
            # Search in both line items and checklist parts
            serial_join = """
            LEFT JOIN job_line_items li2 ON j.job_uid = li2.job_uid
            LEFT JOIN job_checklist_parts cp ON j.job_uid = cp.job_uid
            """
            serial_where = "AND (li2.item_serial LIKE ? OR cp.part_serial LIKE ?)"
            serial_params.extend([f"%{serial_search}%", f"%{serial_search}%"])
            # If both part and serial search, combine the joins
            if part_search:
                serial_join = "LEFT JOIN job_checklist_parts cp ON j.job_uid = cp.job_uid"
                part_where = "AND (li.item_name LIKE ? OR li.item_code LIKE ? OR li.item_serial LIKE ? OR cp.part_serial LIKE ?)"
                part_params = [f"%{part_search}%", f"%{part_search}%", f"%{serial_search}%", f"%{serial_search}%"]
                serial_where = ""
                serial_params = []

        # Combine all parameters in order
        all_params = params + part_params + serial_params

        # Build query based on filter
        if filter_type == 'parts_no_items':
            query = f"""
                SELECT DISTINCT j.*, vf.flag_message, vf.flag_type
                FROM jobs j
                JOIN validation_flags vf ON j.job_uid = vf.job_uid
                {part_join}
                {serial_join}
                WHERE vf.flag_type = 'parts_replaced_no_line_items'
                AND vf.is_resolved = 0
                {date_clause}
                {part_where}
                {serial_where}
                ORDER BY j.created_at DESC
                LIMIT ? OFFSET ?
            """
        elif filter_type == 'missing_netsuite':
            query = f"""
                SELECT DISTINCT j.*, vf.flag_message, vf.flag_type
                FROM jobs j
                JOIN validation_flags vf ON j.job_uid = vf.job_uid
                {part_join}
                {serial_join}
                WHERE vf.flag_type = 'missing_netsuite_id'
                AND vf.is_resolved = 0
                {date_clause}
                {part_where}
                {serial_where}
                ORDER BY j.created_at DESC
                LIMIT ? OFFSET ?
            """
        elif filter_type == 'passing':
            query = f"""
                SELECT DISTINCT j.*, NULL as flag_message, NULL as flag_type
                FROM jobs j
                LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
                {part_join}
                {serial_join}
                WHERE vf.id IS NULL
                {date_clause}
                {part_where}
                {serial_where}
                ORDER BY j.created_at DESC
                LIMIT ? OFFSET ?
            """
        else:  # all
            query = f"""
                SELECT DISTINCT j.*, vf.flag_message, vf.flag_type
                FROM jobs j
                LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
                {part_join}
                {serial_join}
                WHERE 1=1
                {date_clause}
                {part_where}
                {serial_where}
                ORDER BY j.created_at DESC
                LIMIT ? OFFSET ?
            """

        # Execute with parameterized values
        query_params = all_params + [limit, offset]
        cursor.execute(query, query_params)
        jobs = [dict(row) for row in cursor.fetchall()]

        # Get total count using same parameterized approach
        if filter_type == 'parts_no_items':
            count_query = f"""
                SELECT COUNT(DISTINCT j.job_uid) FROM jobs j
                JOIN validation_flags vf ON j.job_uid = vf.job_uid
                {part_join} {serial_join}
                WHERE vf.flag_type = 'parts_replaced_no_line_items' AND vf.is_resolved = 0
                {date_clause} {part_where} {serial_where}
            """
        elif filter_type == 'missing_netsuite':
            count_query = f"""
                SELECT COUNT(DISTINCT j.job_uid) FROM jobs j
                JOIN validation_flags vf ON j.job_uid = vf.job_uid
                {part_join} {serial_join}
                WHERE vf.flag_type = 'missing_netsuite_id' AND vf.is_resolved = 0
                {date_clause} {part_where} {serial_where}
            """
        elif filter_type == 'passing':
            count_query = f"""
                SELECT COUNT(DISTINCT j.job_uid) FROM jobs j
                LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
                {part_join} {serial_join}
                WHERE vf.id IS NULL
                {date_clause} {part_where} {serial_where}
            """
        else:
            count_query = f"""
                SELECT COUNT(DISTINCT j.job_uid) FROM jobs j
                {part_join} {serial_join}
                WHERE 1=1
                {date_clause} {part_where} {serial_where}
            """

        cursor.execute(count_query, all_params)
        total_count = cursor.fetchone()[0]

        conn.close()

        return jobs, total_count
    except Exception as e:
        # Return empty result on error
        return [], 0


@st.cache_data(ttl=60)  # Cache for 60 seconds
def get_filter_options():
    """Get available filter options"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT organization_name
            FROM jobs
            WHERE organization_name IS NOT NULL AND organization_name != ''
            ORDER BY organization_name
        """)
        organizations = [row['organization_name'] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT service_team
            FROM jobs
            WHERE service_team IS NOT NULL AND service_team != ''
            ORDER BY service_team
        """)
        teams = [row['service_team'] for row in cursor.fetchall()]

        conn.close()

        return organizations, teams
    except:
        # Return empty lists if database has issues
        return [], []


@st.cache_data(ttl=60)  # Cache for 60 seconds
def get_assets_with_counts():
    """Get list of assets with job counts, sorted by most jobs first"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                j.asset_name,
                COUNT(DISTINCT j.job_uid) as total_jobs,
                COUNT(DISTINCT CASE WHEN vf.id IS NOT NULL AND vf.is_resolved = 0 THEN j.job_uid END) as jobs_with_issues
            FROM jobs j
            LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
            WHERE j.asset_name IS NOT NULL AND j.asset_name != ''
            GROUP BY j.asset_name
            ORDER BY total_jobs DESC
        """)

        assets = []
        for row in cursor.fetchall():
            asset_label = f"{row['asset_name']} ({row['total_jobs']} jobs"
            if row['jobs_with_issues'] > 0:
                asset_label += f", {row['jobs_with_issues']} with issues"
            asset_label += ")"
            assets.append((row['asset_name'], asset_label))

        conn.close()

        return assets
    except:
        # Return empty list if database has issues
        return []


def mark_job_good(job_uid):
    """Mark all validation flags for a job as resolved"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE validation_flags
        SET is_resolved = 1,
            resolved_at = ?
        WHERE job_uid = ? AND is_resolved = 0
    """, (datetime.now().isoformat(), job_uid))
    
    rows_updated = cursor.rowcount
    conn.commit()
    conn.close()
    
    return rows_updated


# Header
st.title("📊 Zuper Jobs Validation Dashboard")

# Sidebar for API and Sync
with st.sidebar:
    st.header("🔄 Data Sync")

    # Check for API credentials
    try:
        api_key = st.secrets["zuper"]["api_key"]
        base_url = st.secrets["zuper"]["base_url"]
        has_credentials = True
    except:
        has_credentials = False
        st.warning("⚠️ API credentials not configured")
        st.info("Add credentials to `.streamlit/secrets.toml` to enable sync")

    # Check for Slack webhook
    try:
        slack_webhook = st.secrets.get("slack", {}).get("webhook_url", "")
        if slack_webhook:
            st.success("🔔 Slack notifications: ON")
        else:
            st.info("🔕 Slack notifications: OFF")
    except:
        slack_webhook = ""
        st.info("🔕 Slack notifications: OFF")

    if has_credentials:
        # Smart sync button - auto-detects if database is empty
        if st.button("🔄 Sync Data", type="primary", use_container_width=True, help="Automatically syncs data (smart mode)"):
            progress_text = st.empty()
            status_text = st.empty()

            def progress_callback(msg):
                progress_text.info(msg)

            try:
                syncer = ZuperSync(api_key, base_url)

                # Check if database has data
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM jobs")
                job_count = cursor.fetchone()[0]
                conn.close()

                # Auto-detect sync type
                if job_count == 0:
                    # Empty database - do full sync with batch processing
                    status_text.info("🔄 Database empty - performing initial sync in batches...")
                    jobs = syncer.fetch_jobs_from_api(progress_callback)
                    # Use batch sync which includes enrichment
                    stats = syncer.sync_jobs_in_batches(jobs, batch_size=150, progress_callback=progress_callback)

                    progress_text.empty()
                    status_text.success(f"✅ Initial sync complete! Loaded {stats['total_jobs']} jobs with asset data.")
                    st.rerun()
                else:
                    # Database has data - do quick sync
                    status_text.info("⚡ Checking for updates...")
                    jobs = syncer.fetch_updated_jobs_only(progress_callback)

                    if jobs:
                        # Use batch sync for consistency - handles both small and large updates
                        stats = syncer.sync_jobs_in_batches(jobs, batch_size=150, progress_callback=progress_callback)

                        progress_text.empty()
                        status_text.success(f"✅ Updated {len(jobs)} jobs")
                        st.rerun()
                    else:
                        progress_text.empty()
                        status_text.info("ℹ️ No updates found - data is current!")

            except Exception as e:
                progress_text.empty()
                # Show detailed error with expandable details
                status_text.error(f"❌ Sync failed: {str(e)}")
                with st.expander("📋 Error Details", expanded=False):
                    st.code(f"Error Type: {type(e).__name__}\nError Message: {str(e)}", language="text")
                    st.caption("If this error persists, try using 'Force Quick Sync' or 'Force Full Sync' in Advanced Options.")

        # Advanced options in expander (for admins who need full resync)
        with st.expander("⚙️ Advanced Sync Options"):
            st.caption("For troubleshooting or manual control")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("⚡ Force Quick Sync", use_container_width=True, help="Only fetch updated jobs"):
                    progress_text = st.empty()
                    status_text = st.empty()

                    def progress_callback(msg):
                        progress_text.info(msg)

                    try:
                        status_text.info("⚡ Starting quick sync...")
                        syncer = ZuperSync(api_key, base_url)
                        jobs = syncer.fetch_updated_jobs_only(progress_callback)

                        if jobs:
                            jobs = syncer.enrich_jobs_with_assets(jobs, progress_callback)
                            stats = syncer.sync_to_database(jobs, progress_callback)
                            progress_text.empty()
                            status_text.success(f"✅ Updated {len(jobs)} jobs")
                            st.rerun()
                        else:
                            progress_text.empty()
                            status_text.info("ℹ️ No updates found")
                    except Exception as e:
                        progress_text.empty()
                        status_text.error(f"❌ Sync failed: {e}")

            with col2:
                if st.button("🔄 Force Full Sync", use_container_width=True, help="Resync all jobs with batch processing"):
                    progress_text = st.empty()
                    status_text = st.empty()

                    def progress_callback(msg):
                        progress_text.info(msg)

                    try:
                        status_text.info("🔄 Starting full sync in batches...")
                        syncer = ZuperSync(api_key, base_url)
                        jobs = syncer.fetch_jobs_from_api(progress_callback)
                        # Use batch sync with enrichment
                        stats = syncer.sync_jobs_in_batches(jobs, batch_size=150, progress_callback=progress_callback)

                        progress_text.empty()
                        status_text.success(f"✅ Synced {stats['total_jobs']} jobs with asset data!")
                        st.rerun()
                    except Exception as e:
                        progress_text.empty()
                        status_text.error(f"❌ Sync failed: {e}")

    st.divider()
    
    # Last sync info
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT sync_completed_at FROM sync_log WHERE status = 'completed' ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
        if result:
            last_sync = result['sync_completed_at']
            st.caption(f"Last synced: {last_sync}")
        conn.close()
    except:
        pass

# Metrics
metrics = get_metrics()

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button(f"📋 Total Jobs\n{metrics['total_jobs']}", use_container_width=True):
        st.session_state.current_filter = 'all'
        st.session_state.current_page = 1

with col2:
    if st.button(f"❌ Missing NetSuite\n{metrics['missing_netsuite_count']}", use_container_width=True):
        st.session_state.current_filter = 'missing_netsuite'
        st.session_state.current_page = 1

with col3:
    if st.button(f"⚠️ Parts w/o Line Items\n{metrics['parts_no_items_count']}", use_container_width=True):
        st.session_state.current_filter = 'parts_no_items'
        st.session_state.current_page = 1

with col4:
    if st.button(f"✅ Passing\n{metrics['passing_count']}", use_container_width=True):
        st.session_state.current_filter = 'passing'
        st.session_state.current_page = 1

# Filters
organizations, teams = get_filter_options()

# Text search filters wrapped in a form to prevent re-renders on every keystroke
with st.form(key="search_filters_form"):
    # First row: Job number search, Part search, Serial search, and date range
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        job_number_input = st.text_input(
            "🔍 Job Number",
            value=st.session_state.job_number_search,
            placeholder="Enter job number...",
            key="job_number_input"
        )

    with col2:
        part_input = st.text_input(
            "🔧 Part Name/Code",
            value=st.session_state.part_search,
            placeholder="Enter part name or code...",
            key="part_input"
        )

    with col3:
        serial_input = st.text_input(
            "🏷️ Serial Number",
            value=st.session_state.serial_search,
            placeholder="Enter serial number...",
            key="serial_input"
        )

    with col4:
        start_date_input = st.date_input("Start Date", value=None, key="start_date_input")

    with col5:
        end_date_input = st.date_input("End Date", value=None, key="end_date_input")

    # Submit button for text searches
    search_submitted = st.form_submit_button("🔍 Apply Search Filters", use_container_width=True)

    if search_submitted:
        # Update session state only when form is submitted
        st.session_state.job_number_search = job_number_input if job_number_input else ''
        st.session_state.part_search = part_input if part_input else ''
        st.session_state.serial_search = normalize_search_input(serial_input) if serial_input else ''
        st.session_state.start_date = start_date_input.isoformat() if start_date_input else None
        st.session_state.end_date = end_date_input.isoformat() if end_date_input else None
        st.session_state.current_page = 1  # Reset to page 1 when searching
        st.rerun()

# Second row: Dropdown filters (these don't need form wrapper - they're discrete selections)
col1, col2, col3, col4 = st.columns(4)

with col1:
    # Only show month filter if date range is not set
    if not (st.session_state.start_date and st.session_state.end_date):
        month_filter = st.selectbox("Month", ["All Months"] + [f"2025-{m:02d}" for m in range(1, 13)], key="month_select")
        if month_filter != "All Months":
            st.session_state.month_filter = month_filter
        else:
            st.session_state.month_filter = ''
    else:
        st.info("📅 Using date range filter")
        st.session_state.month_filter = ''

with col2:
    org_filter = st.selectbox("Organization", ["All Organizations"] + organizations, key="org_select")
    if org_filter != "All Organizations":
        st.session_state.org_filter = org_filter
    else:
        st.session_state.org_filter = ''

with col3:
    team_filter = st.selectbox("Service Team", ["All Teams"] + teams, key="team_select")
    if team_filter != "All Teams":
        st.session_state.team_filter = team_filter
    else:
        st.session_state.team_filter = ''

with col4:
    # Get assets with job counts
    assets_with_counts = get_assets_with_counts()
    asset_options = ["All Assets"] + [label for _, label in assets_with_counts]
    asset_values = [""] + [name for name, _ in assets_with_counts]

    asset_filter = st.selectbox("Asset (by job count)", asset_options, key="asset_select")
    if asset_filter != "All Assets":
        # Find the actual asset name from the label
        selected_index = asset_options.index(asset_filter)
        st.session_state.asset_filter = asset_values[selected_index]
        st.session_state.current_page = 1  # Reset to page 1
    else:
        st.session_state.asset_filter = ''

# Bulk Serial Number Lookup
with st.expander("📋 Bulk Serial Number Lookup"):
    st.caption("Search for multiple serial numbers at once - paste a list or upload a CSV")

    tab1, tab2 = st.tabs(["📝 Paste List", "📁 Upload CSV"])

    with tab1:
        bulk_serials_text = st.text_area(
            "Paste serial numbers (one per line)",
            placeholder="CR-SM-12345\nCR-SM-12346\nCR-SM-12347\n...",
            height=150,
            key="bulk_serials_input"
        )

        if st.button("🔍 Search Serial Numbers", type="primary"):
            if bulk_serials_text:
                # Parse and normalize serial numbers from text
                raw_serials = [s.strip() for s in bulk_serials_text.split('\n') if s.strip()]
                serial_pairs = [(raw, normalize_search_input(raw)) for raw in raw_serials]

                # Batched search - single query instead of N queries
                conn = get_db_connection()
                cursor = conn.cursor()
                results = search_serials_batch(serial_pairs, cursor)
                conn.close()

                if results:
                    st.success(f"✅ Found {len(results)} job(s) across {len(raw_serials)} serial numbers")

                    # Display results in a dataframe
                    df = pd.DataFrame(results)
                    df['Zuper Link'] = df['job_uid'].apply(lambda x: f"https://web.zuperpro.com/jobs/{x}/details")

                    # Reorder columns
                    display_df = df[['searched_serial', 'source', 'job_number', 'customer', 'asset', 'service_team', 'created_at', 'Zuper Link']]
                    display_df.columns = ['Serial Searched', 'Source', 'Job #', 'Customer', 'Asset', 'Team', 'Date', 'Zuper Link']

                    st.dataframe(display_df, use_container_width=True)

                    # Download button
                    csv = display_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Results as CSV",
                        data=csv,
                        file_name="serial_lookup_results.csv",
                        mime="text/csv"
                    )

                    # Show which serials weren't found
                    found_serials = set(df['searched_serial'].unique())
                    normalized_serials = [n for _, n in serial_pairs]
                    not_found = [s for s in normalized_serials if s and s not in found_serials and not any(s in fs for fs in found_serials)]
                    if not_found:
                        st.warning(f"⚠️ {len(not_found)} serial(s) not found: {', '.join(not_found)}")
                else:
                    st.error("❌ No jobs found for the provided serial numbers")
            else:
                st.warning("⚠️ Please enter serial numbers to search")

    with tab2:
        uploaded_file = st.file_uploader("Upload CSV with serial numbers", type=['csv'])

        if uploaded_file is not None:
            try:
                # Read CSV
                csv_data = pd.read_csv(uploaded_file)

                # Try to find serial column
                serial_column = None
                for col in csv_data.columns:
                    if 'serial' in col.lower():
                        serial_column = col
                        break

                if serial_column:
                    raw_serials = csv_data[serial_column].dropna().astype(str).tolist()
                    st.info(f"📊 Found {len(raw_serials)} serial numbers in column '{serial_column}'")

                    if st.button("🔍 Search from CSV", type="primary"):
                        # Build serial pairs for batched search
                        serial_pairs = []
                        for raw_serial in raw_serials:
                            raw_serial = raw_serial.strip()
                            if raw_serial:
                                serial_pairs.append((raw_serial, normalize_search_input(raw_serial)))

                        # Batched search - single query instead of N queries
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        results = search_serials_batch(serial_pairs, cursor)
                        conn.close()

                        if results:
                            st.success(f"✅ Found {len(results)} job(s) across {len(raw_serials)} serial numbers")

                            df = pd.DataFrame(results)
                            df['Zuper Link'] = df['job_uid'].apply(lambda x: f"https://web.zuperpro.com/jobs/{x}/details")

                            display_df = df[['searched_serial', 'source', 'job_number', 'customer', 'asset', 'service_team', 'created_at', 'Zuper Link']]
                            display_df.columns = ['Serial Searched', 'Source', 'Job #', 'Customer', 'Asset', 'Team', 'Date', 'Zuper Link']

                            st.dataframe(display_df, use_container_width=True)

                            csv = display_df.to_csv(index=False)
                            st.download_button(
                                label="📥 Download Results as CSV",
                                data=csv,
                                file_name="serial_lookup_results.csv",
                                mime="text/csv"
                            )

                            found_serials = set(df['searched_serial'].unique())
                            normalized_serials = [n for _, n in serial_pairs]
                            not_found = [s for s in normalized_serials if s and s not in found_serials and not any(s in fs for fs in found_serials)]
                            if not_found:
                                with st.expander(f"⚠️ {len(not_found)} serial(s) not found"):
                                    st.write(', '.join(not_found))
                        else:
                            st.error("❌ No jobs found for the provided serial numbers")
                else:
                    st.warning("⚠️ Could not find a column with 'serial' in the name. Please make sure your CSV has a column containing serial numbers.")
                    st.caption(f"Available columns: {', '.join(csv_data.columns)}")

            except Exception as e:
                st.error(f"❌ Error reading CSV: {e}")

st.divider()

# Jobs table
jobs, total_count = get_jobs(
    st.session_state.current_filter,
    st.session_state.current_page,
    st.session_state.month_filter,
    st.session_state.org_filter,
    st.session_state.team_filter,
    st.session_state.start_date,
    st.session_state.end_date,
    st.session_state.job_number_search,
    st.session_state.part_search,
    st.session_state.serial_search,
    st.session_state.asset_filter
)

# Show filter status with total database count
active_filters = []
if st.session_state.current_filter == 'flagged':
    active_filters.append("Flagged Only")
if st.session_state.month_filter:
    active_filters.append(f"Month: {st.session_state.month_filter}")
if st.session_state.org_filter:
    active_filters.append(f"Org: {st.session_state.org_filter}")
if st.session_state.team_filter:
    active_filters.append(f"Team: {st.session_state.team_filter}")
if st.session_state.asset_filter:
    active_filters.append(f"Asset: {st.session_state.asset_filter}")
if st.session_state.start_date or st.session_state.end_date:
    date_str = f"{st.session_state.start_date or '...'} to {st.session_state.end_date or '...'}"
    active_filters.append(f"Date Range: {date_str}")
if st.session_state.job_number_search:
    active_filters.append(f"Job#: {st.session_state.job_number_search}")
if st.session_state.part_search:
    active_filters.append(f"Part: {st.session_state.part_search}")
if st.session_state.serial_search:
    active_filters.append(f"Serial: {st.session_state.serial_search}")

# Display header with filter status
col_header1, col_header2 = st.columns([3, 1])
with col_header1:
    if active_filters:
        st.subheader(f"Jobs: Showing {total_count} of {metrics['total_jobs']} total")
        st.caption(f"Active filters: {' | '.join(active_filters)}")
    else:
        st.subheader(f"Jobs ({total_count} total)")
with col_header2:
    if active_filters:
        if st.button("Clear All Filters", use_container_width=True):
            st.session_state.current_filter = 'all'
            st.session_state.month_filter = ''
            st.session_state.org_filter = ''
            st.session_state.team_filter = ''
            st.session_state.asset_filter = ''
            st.session_state.start_date = None
            st.session_state.end_date = None
            st.session_state.job_number_search = ''
            st.session_state.part_search = ''
            st.session_state.serial_search = ''
            st.rerun()

if jobs:
    # Display jobs as interactive rows with inline action buttons
    for idx, job in enumerate(jobs):
        completed_date = job['completed_at'] if job['completed_at'] else job['created_at']
        zuper_url = f"https://web.zuperpro.com/jobs/{job['job_uid']}/details"

        # Create a container for each job row
        with st.container():
            # Use columns for layout: Info | Status | Actions
            col1, col2, col3 = st.columns([5, 1.5, 1.5])

            with col1:
                # Job details
                st.markdown(f"**#{job['job_number']}** - {job['job_title'][:60] + '...' if len(job['job_title']) > 60 else job['job_title']}")
                st.caption(f"{job['organization_name'] or '-'} | {job['service_team'] or '-'} | Completed: {completed_date[:10] if completed_date else '-'}")

            with col2:
                # Status
                if job['flag_type']:
                    st.markdown("🔴 **Issues**")
                    if job['flag_message']:
                        st.caption(job['flag_message'][:40] + '...' if len(job['flag_message']) > 40 else job['flag_message'])
                else:
                    st.markdown("✅ **Passing**")

            with col3:
                # Actions
                st.link_button("View Job", zuper_url, use_container_width=True)
                # Show review button only for jobs with issues
                if job['flag_type']:
                    if st.button("✓ Reviewed", key=f"review_{job['job_uid']}", use_container_width=True, type="secondary"):
                        rows_updated = mark_job_good(job['job_uid'])
                        if rows_updated > 0:
                            st.success(f"✓ Job #{job['job_number']} marked as reviewed!")
                            st.rerun()
                        else:
                            st.warning("No changes made")

            # Divider between rows
            if idx < len(jobs) - 1:
                st.divider()

    # Pagination
    total_pages = (total_count + 49) // 50
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if st.button("⬅️ Previous", disabled=st.session_state.current_page <= 1):
            st.session_state.current_page -= 1
            st.rerun()
    
    with col2:
        st.write(f"Page {st.session_state.current_page} of {total_pages}")
    
    with col3:
        if st.button("Next ➡️", disabled=st.session_state.current_page >= total_pages):
            st.session_state.current_page += 1
            st.rerun()
else:
    st.info("No jobs found matching the current filters.")

