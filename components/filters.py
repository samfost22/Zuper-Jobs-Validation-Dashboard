"""
Filter components for the dashboard.
"""

import streamlit as st
from typing import List, Tuple

from config import DEFAULT_SESSION_STATE


def init_session_state() -> None:
    """Initialize all session state variables with defaults."""
    for key, default in DEFAULT_SESSION_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = default


def render_search_inputs() -> None:
    """Render the search input row (job number, part, serial, dates)."""
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        job_number = st.text_input(
            "Job Number",
            placeholder="Search job #...",
            key="job_number_input"
        )
        if job_number != st.session_state.job_number_search:
            st.session_state.job_number_search = job_number
            st.session_state.current_page = 1

    with col2:
        part = st.text_input(
            "Part # / Notes / Checklist",
            placeholder="Search parts, notes, checklists...",
            key="part_input",
            help="Searches line items, job notes, and checklist answers"
        )
        if part != st.session_state.part_search:
            st.session_state.part_search = part
            st.session_state.current_page = 1

    with col3:
        serial = st.text_input(
            "Serial Number",
            placeholder="Search serial...",
            key="serial_input"
        )
        if serial != st.session_state.serial_search:
            st.session_state.serial_search = serial
            st.session_state.current_page = 1

    with col4:
        start_date = st.date_input("Start Date", value=None, key="start_date_input")
        st.session_state.start_date = start_date.isoformat() if start_date else None

    with col5:
        end_date = st.date_input("End Date", value=None, key="end_date_input")
        st.session_state.end_date = end_date.isoformat() if end_date else None


def render_filters(
    organizations: List[str],
    teams: List[str],
    assets: List[Tuple[str, str]]
) -> None:
    """
    Render the filter dropdowns row.

    Args:
        organizations: List of organization names.
        teams: List of service team names.
        assets: List of (asset_name, display_label) tuples.
    """
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # Only show month filter if date range is not set
        if not (st.session_state.start_date and st.session_state.end_date):
            months = ["All Months"] + [f"2025-{m:02d}" for m in range(1, 13)]
            month = st.selectbox("Month", months, key="month_select")
            st.session_state.month_filter = month if month != "All Months" else ''
        else:
            st.info("Using date range")
            st.session_state.month_filter = ''

    with col2:
        org_options = ["All Organizations"] + organizations
        org = st.selectbox("Organization", org_options, key="org_select")
        st.session_state.org_filter = org if org != "All Organizations" else ''

    with col3:
        team_options = ["All Teams"] + teams
        team = st.selectbox("Service Team", team_options, key="team_select")
        st.session_state.team_filter = team if team != "All Teams" else ''

    with col4:
        asset_labels = ["All Assets"] + [label for _, label in assets]
        asset_values = [""] + [name for name, _ in assets]

        selected = st.selectbox("Asset (by job count)", asset_labels, key="asset_select")
        if selected != "All Assets":
            idx = asset_labels.index(selected)
            st.session_state.asset_filter = asset_values[idx]
            st.session_state.current_page = 1
        else:
            st.session_state.asset_filter = ''


def get_active_filters() -> List[str]:
    """
    Get list of currently active filter descriptions.

    Returns:
        List of filter description strings.
    """
    filters = []

    if st.session_state.month_filter:
        filters.append(f"Month: {st.session_state.month_filter}")
    if st.session_state.org_filter:
        filters.append(f"Org: {st.session_state.org_filter}")
    if st.session_state.team_filter:
        filters.append(f"Team: {st.session_state.team_filter}")
    if st.session_state.asset_filter:
        filters.append(f"Asset: {st.session_state.asset_filter}")
    if st.session_state.start_date or st.session_state.end_date:
        date_str = f"{st.session_state.start_date or '...'} to {st.session_state.end_date or '...'}"
        filters.append(f"Date Range: {date_str}")
    if st.session_state.job_number_search:
        filters.append(f"Job#: {st.session_state.job_number_search}")
    if st.session_state.part_search:
        filters.append(f"Part: {st.session_state.part_search}")
    if st.session_state.serial_search:
        filters.append(f"Serial: {st.session_state.serial_search}")

    return filters


def clear_all_filters() -> None:
    """Reset all filters to default values."""
    for key, default in DEFAULT_SESSION_STATE.items():
        st.session_state[key] = default


def render_filter_header(total_count: int, total_jobs: int) -> None:
    """
    Render the filter status header with clear button.

    Args:
        total_count: Number of filtered results.
        total_jobs: Total jobs in database.
    """
    active_filters = get_active_filters()

    col1, col2 = st.columns([3, 1])

    with col1:
        if active_filters:
            st.subheader(f"Jobs: Showing {total_count} of {total_jobs} total")
            st.caption(f"Active filters: {' | '.join(active_filters)}")
        else:
            st.subheader(f"Jobs ({total_count} total)")

    with col2:
        if active_filters:
            if st.button("Clear All Filters", use_container_width=True):
                clear_all_filters()
                st.rerun()
