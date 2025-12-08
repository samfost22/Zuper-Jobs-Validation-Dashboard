"""
Sidebar component for sync controls and status.
"""

import streamlit as st
from typing import Optional, Callable

from database.queries import get_last_sync_time, get_job_count


def render_sidebar(
    api_key: Optional[str],
    base_url: Optional[str],
    on_sync: Callable[[], None],
    on_quick_sync: Callable[[], None],
    on_full_sync: Callable[[], None]
) -> None:
    """
    Render the sidebar with sync controls.

    Args:
        api_key: API key or None if not configured.
        base_url: API base URL or None if not configured.
        on_sync: Callback for smart sync button.
        on_quick_sync: Callback for quick sync button.
        on_full_sync: Callback for full sync button.
    """
    with st.sidebar:
        st.header("Data Sync")

        if not api_key or not base_url:
            st.warning("API credentials not configured")
            st.info("Add credentials to `.streamlit/secrets.toml` to enable sync")
            return

        # Main sync button
        if st.button(
            "Sync Data",
            type="primary",
            use_container_width=True,
            help="Smart sync - detects if full or incremental sync is needed"
        ):
            on_sync()

        # Advanced options
        with st.expander("Advanced Sync Options"):
            st.caption("For troubleshooting or manual control")

            col1, col2 = st.columns(2)

            with col1:
                if st.button(
                    "Quick Sync",
                    use_container_width=True,
                    help="Only fetch updated jobs"
                ):
                    on_quick_sync()

            with col2:
                if st.button(
                    "Full Sync",
                    use_container_width=True,
                    help="Resync all jobs"
                ):
                    on_full_sync()

        st.divider()

        # Last sync info
        last_sync = get_last_sync_time()
        if last_sync:
            st.caption(f"Last synced: {last_sync}")

        job_count = get_job_count()
        if job_count > 0:
            st.caption(f"Jobs in database: {job_count:,}")
