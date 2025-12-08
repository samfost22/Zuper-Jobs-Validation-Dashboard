"""
Metrics display component for the dashboard.
"""

import streamlit as st
from typing import Dict


def render_metrics(metrics: Dict[str, int]) -> None:
    """
    Render the metrics cards as clickable filter buttons.

    Args:
        metrics: Dictionary with total_jobs, missing_netsuite_count,
                parts_no_items_count, and passing_count.
    """
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button(
            f"Total Jobs\n{metrics['total_jobs']}",
            use_container_width=True,
            help="Show all jobs"
        ):
            st.session_state.current_filter = 'all'
            st.session_state.current_page = 1

    with col2:
        if st.button(
            f"Missing NetSuite\n{metrics['missing_netsuite_count']}",
            use_container_width=True,
            help="Jobs with line items but no NetSuite ID"
        ):
            st.session_state.current_filter = 'missing_netsuite'
            st.session_state.current_page = 1

    with col3:
        if st.button(
            f"Parts w/o Line Items\n{metrics['parts_no_items_count']}",
            use_container_width=True,
            help="Checklist shows parts replaced but no line items added"
        ):
            st.session_state.current_filter = 'parts_no_items'
            st.session_state.current_page = 1

    with col4:
        if st.button(
            f"Passing\n{metrics['passing_count']}",
            use_container_width=True,
            help="Jobs with no validation issues"
        ):
            st.session_state.current_filter = 'passing'
            st.session_state.current_page = 1
