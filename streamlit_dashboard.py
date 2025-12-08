#!/usr/bin/env python3
"""
Zuper Jobs Validation Dashboard - Streamlit Version

Refactored to use modular components and parameterized queries.
"""

import streamlit as st

from config import CACHE_TTL_SHORT, CACHE_TTL_MEDIUM
from database.queries import (
    get_metrics,
    get_jobs,
    get_filter_options,
    get_assets_with_counts,
    mark_job_resolved,
    get_job_count,
)
from components.filters import (
    init_session_state,
    render_search_inputs,
    render_filters,
    render_filter_header,
)
from components.metrics import render_metrics
from components.job_table import render_job_table, render_pagination
from components.bulk_lookup import render_bulk_lookup
from streamlit_sync import ZuperSync

# Page config
st.set_page_config(
    page_title="Zuper Jobs Validation Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
init_session_state()


# Cached data functions
@st.cache_data(ttl=CACHE_TTL_SHORT)
def cached_get_metrics():
    """Get dashboard metrics with caching."""
    return get_metrics()


@st.cache_data(ttl=CACHE_TTL_MEDIUM)
def cached_get_filter_options():
    """Get filter options with caching."""
    return get_filter_options()


@st.cache_data(ttl=CACHE_TTL_MEDIUM)
def cached_get_assets():
    """Get assets with caching."""
    return get_assets_with_counts()


@st.cache_data(ttl=CACHE_TTL_SHORT)
def cached_get_jobs(
    filter_type, page, month, organization, team,
    start_date, end_date, job_number, part_search, serial_search, asset
):
    """Get jobs with caching."""
    return get_jobs(
        filter_type=filter_type,
        page=page,
        month=month,
        organization=organization,
        team=team,
        start_date=start_date,
        end_date=end_date,
        job_number=job_number,
        part_search=part_search,
        serial_search=serial_search,
        asset=asset
    )


def get_api_credentials():
    """Get API credentials from secrets."""
    try:
        return st.secrets["zuper"]["api_key"], st.secrets["zuper"]["base_url"]
    except (KeyError, FileNotFoundError):
        return None, None


def do_smart_sync(api_key: str, base_url: str) -> None:
    """Perform smart sync - auto-detects if full or incremental needed."""
    progress = st.empty()
    status = st.empty()

    def callback(msg):
        progress.info(msg)

    try:
        syncer = ZuperSync(api_key, base_url)
        job_count = get_job_count()

        if job_count == 0:
            status.info("Database empty - performing initial sync...")
            jobs = syncer.fetch_jobs_from_api(callback)
            syncer.sync_jobs_in_batches(jobs, batch_size=150, progress_callback=callback)
            progress.empty()
            status.success("Initial sync complete!")
            st.rerun()
        else:
            status.info("Checking for updates...")
            jobs = syncer.fetch_updated_jobs_only(callback)

            if jobs:
                syncer.sync_jobs_in_batches(jobs, batch_size=150, progress_callback=callback)
                progress.empty()
                status.success(f"Updated {len(jobs)} jobs")
                st.rerun()
            else:
                progress.empty()
                status.info("No updates found - data is current!")

    except Exception as e:
        progress.empty()
        status.error(f"Sync failed: {e}")
        with st.expander("Error Details"):
            st.code(str(e))


def do_quick_sync(api_key: str, base_url: str) -> None:
    """Perform quick sync - only updated jobs."""
    progress = st.empty()
    status = st.empty()

    def callback(msg):
        progress.info(msg)

    try:
        status.info("Starting quick sync...")
        syncer = ZuperSync(api_key, base_url)
        jobs = syncer.fetch_updated_jobs_only(callback)

        if jobs:
            jobs = syncer.enrich_jobs_with_assets(jobs, callback)
            syncer.sync_to_database(jobs, callback)
            progress.empty()
            status.success(f"Updated {len(jobs)} jobs")
            st.rerun()
        else:
            progress.empty()
            status.info("No updates found")

    except Exception as e:
        progress.empty()
        status.error(f"Sync failed: {e}")


def do_full_sync(api_key: str, base_url: str) -> None:
    """Perform full sync - all jobs."""
    progress = st.empty()
    status = st.empty()

    def callback(msg):
        progress.info(msg)

    try:
        status.info("Starting full sync...")
        syncer = ZuperSync(api_key, base_url)
        jobs = syncer.fetch_jobs_from_api(callback)
        stats = syncer.sync_jobs_in_batches(jobs, batch_size=150, progress_callback=callback)
        progress.empty()
        status.success(f"Synced {stats['total_jobs']} jobs!")
        st.rerun()

    except Exception as e:
        progress.empty()
        status.error(f"Sync failed: {e}")


# Main app
def main():
    st.title("Zuper Jobs Validation Dashboard")

    # Sidebar
    api_key, base_url = get_api_credentials()

    with st.sidebar:
        st.header("Data Sync")

        if not api_key:
            st.warning("API credentials not configured")
            st.info("Add credentials to `.streamlit/secrets.toml`")
        else:
            if st.button("Sync Data", type="primary", use_container_width=True):
                do_smart_sync(api_key, base_url)

            with st.expander("Advanced Sync Options"):
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Quick Sync", use_container_width=True):
                        do_quick_sync(api_key, base_url)
                with col2:
                    if st.button("Full Sync", use_container_width=True):
                        do_full_sync(api_key, base_url)

        st.divider()

        from database.queries import get_last_sync_time
        last_sync = get_last_sync_time()
        if last_sync:
            st.caption(f"Last synced: {last_sync}")

    # Metrics
    metrics = cached_get_metrics()
    render_metrics(metrics)

    # Filters
    organizations, teams = cached_get_filter_options()
    assets = cached_get_assets()

    render_search_inputs()
    render_filters(organizations, teams, assets)

    # Bulk lookup
    render_bulk_lookup()

    st.divider()

    # Jobs table
    jobs, total_count = cached_get_jobs(
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

    render_filter_header(total_count, metrics['total_jobs'])
    render_job_table(jobs, mark_job_resolved)

    if jobs:
        render_pagination(total_count)


if __name__ == "__main__":
    main()
