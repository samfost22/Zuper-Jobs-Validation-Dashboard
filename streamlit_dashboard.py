#!/usr/bin/env python3
"""
Zuper Jobs Validation Dashboard - Streamlit Version
"""

import streamlit as st
import sqlite3
import pandas as pd
import json
from datetime import datetime
from streamlit_sync import ZuperSync, test_api_connection

# Page config
st.set_page_config(
    page_title="Zuper Jobs Validation Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database file
DB_FILE = 'jobs_validation.db'

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
if 'asset_filter' not in st.session_state:
    st.session_state.asset_filter = ''


def ensure_database_exists():
    """Initialize database if it doesn't exist"""
    import os
    if not os.path.exists(DB_FILE):
        from streamlit_sync import init_database
        init_database()


def get_db_connection():
    """Get database connection with timeout"""
    ensure_database_exists()
    conn = sqlite3.connect(DB_FILE, timeout=30.0)  # 30 second timeout
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=60)  # Cache for 60 seconds
def get_metrics():
    """Get dashboard metrics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Total jobs
        cursor.execute("SELECT COUNT(*) as total FROM jobs")
        total_jobs = cursor.fetchone()['total']

        # Jobs with parts replaced but no line items
        cursor.execute("""
            SELECT COUNT(DISTINCT job_uid) as count
            FROM validation_flags
            WHERE flag_type = 'parts_replaced_no_line_items'
            AND is_resolved = 0
        """)
        parts_no_items_count = cursor.fetchone()['count']

        # Jobs with line items but missing NetSuite ID
        cursor.execute("""
            SELECT COUNT(DISTINCT job_uid) as count
            FROM validation_flags
            WHERE flag_type = 'missing_netsuite_id'
            AND is_resolved = 0
        """)
        missing_netsuite_count = cursor.fetchone()['count']

        # Jobs passing all validations
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM jobs j
            LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
            WHERE vf.id IS NULL
        """)
        passing_count = cursor.fetchone()['count']

        conn.close()

        return {
            'total_jobs': total_jobs,
            'parts_no_items_count': parts_no_items_count,
            'missing_netsuite_count': missing_netsuite_count,
            'passing_count': passing_count
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
def get_jobs(filter_type='all', page=1, month='', organization='', team='', start_date=None, end_date=None, job_number='', part_search='', asset='', limit=50):
    """Get jobs list with filtering and pagination"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * limit
    except:
        # Return empty result if database has issues
        return [], 0

    try:
        # Build filter clauses
        filter_clauses = []

        # Job number search (exact or partial match)
        if job_number:
            filter_clauses.append(f"j.job_number LIKE '%{job_number}%'")

        # Date range filter (takes precedence over month filter)
        if start_date and end_date:
            filter_clauses.append(f"(date(COALESCE(j.completed_at, j.created_at)) BETWEEN '{start_date}' AND '{end_date}')")
        elif month:
            filter_clauses.append(f"(strftime('%Y-%m', COALESCE(j.completed_at, j.created_at)) = '{month}')")

        if organization:
            filter_clauses.append(f"j.organization_name LIKE '%{organization}%'")

        if team:
            filter_clauses.append(f"j.service_team LIKE '%{team}%'")

        if asset:
            filter_clauses.append(f"j.asset_name = '{asset}'")

        date_clause = ("AND " + " AND ".join(filter_clauses)) if filter_clauses else ""

        # Add part search join if needed
        part_join = ""
        part_where = ""
        if part_search:
            part_join = "JOIN job_line_items li ON j.job_uid = li.job_uid"
            part_where = f"AND (li.item_name LIKE '%{part_search}%' OR li.item_code LIKE '%{part_search}%')"

        # Build query based on filter
        if filter_type == 'parts_no_items':
            query = f"""
                SELECT DISTINCT j.*, vf.flag_message, vf.flag_type
                FROM jobs j
                JOIN validation_flags vf ON j.job_uid = vf.job_uid
                {part_join}
                WHERE vf.flag_type = 'parts_replaced_no_line_items'
                AND vf.is_resolved = 0
                {date_clause}
                {part_where}
                ORDER BY j.created_at DESC
                LIMIT ? OFFSET ?
            """
        elif filter_type == 'missing_netsuite':
            query = f"""
                SELECT DISTINCT j.*, vf.flag_message, vf.flag_type
                FROM jobs j
                JOIN validation_flags vf ON j.job_uid = vf.job_uid
                {part_join}
                WHERE vf.flag_type = 'missing_netsuite_id'
                AND vf.is_resolved = 0
                {date_clause}
                {part_where}
                ORDER BY j.created_at DESC
                LIMIT ? OFFSET ?
            """
        elif filter_type == 'passing':
            query = f"""
                SELECT DISTINCT j.*, NULL as flag_message, NULL as flag_type
                FROM jobs j
                LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
                {part_join}
                WHERE vf.id IS NULL
                {date_clause}
                {part_where}
                ORDER BY j.created_at DESC
                LIMIT ? OFFSET ?
            """
        else:  # all
            query = f"""
                SELECT DISTINCT j.*, vf.flag_message, vf.flag_type
                FROM jobs j
                LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
                {part_join}
                WHERE 1=1
                {date_clause}
                {part_where}
                ORDER BY j.created_at DESC
                LIMIT ? OFFSET ?
            """

        cursor.execute(query, (limit, offset))
        jobs = [dict(row) for row in cursor.fetchall()]

        # Get total count (with part search if applicable)
        if filter_type == 'parts_no_items':
            count_query = f"SELECT COUNT(DISTINCT j.job_uid) FROM jobs j JOIN validation_flags vf ON j.job_uid = vf.job_uid {part_join} WHERE vf.flag_type = 'parts_replaced_no_line_items' AND vf.is_resolved = 0 {date_clause} {part_where}"
        elif filter_type == 'missing_netsuite':
            count_query = f"SELECT COUNT(DISTINCT j.job_uid) FROM jobs j JOIN validation_flags vf ON j.job_uid = vf.job_uid {part_join} WHERE vf.flag_type = 'missing_netsuite_id' AND vf.is_resolved = 0 {date_clause} {part_where}"
        elif filter_type == 'passing':
            count_query = f"SELECT COUNT(DISTINCT j.job_uid) FROM jobs j LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0 {part_join} WHERE vf.id IS NULL {date_clause} {part_where}"
        else:
            count_where = f"WHERE {date_clause[4:]}" if date_clause else ""
            count_query = f"SELECT COUNT(DISTINCT j.job_uid) FROM jobs j {part_join} {count_where} {part_where if part_search else ''}"

        cursor.execute(count_query)
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
    
    if has_credentials:
        if st.button("🔄 Refresh Data from API", type="primary"):
            with st.spinner("Syncing data..."):
                progress_text = st.empty()
                
                def progress_callback(msg):
                    progress_text.text(msg)
                
                try:
                    syncer = ZuperSync(api_key, base_url)
                    jobs = syncer.fetch_jobs_from_api(progress_callback)
                    stats = syncer.sync_to_database(jobs, progress_callback)
                    
                    st.success(f"✅ Synced {stats['total_jobs']} jobs!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Sync failed: {e}")
    
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

# First row: Job number search, Part search, and date range
col1, col2, col3, col4 = st.columns(4)

with col1:
    job_number_input = st.text_input("🔍 Job Number", placeholder="Enter job number...", key="job_number_input")
    if job_number_input:
        st.session_state.job_number_search = job_number_input
        st.session_state.current_page = 1  # Reset to page 1 when searching
    else:
        st.session_state.job_number_search = ''

with col2:
    part_input = st.text_input("🔧 Part Name/Code", placeholder="Enter part name or code...", key="part_input")
    if part_input:
        st.session_state.part_search = part_input
        st.session_state.current_page = 1  # Reset to page 1 when searching
    else:
        st.session_state.part_search = ''

with col3:
    start_date_input = st.date_input("Start Date", value=None, key="start_date_input")
    if start_date_input:
        st.session_state.start_date = start_date_input.isoformat()
    else:
        st.session_state.start_date = None

with col3:
    end_date_input = st.date_input("End Date", value=None, key="end_date_input")
    if end_date_input:
        st.session_state.end_date = end_date_input.isoformat()
    else:
        st.session_state.end_date = None

# Second row: Month, Organization, Service Team, Asset
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
    st.session_state.asset_filter
)

st.subheader(f"Jobs ({total_count} total)")

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

