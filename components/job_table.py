"""
Job table display component for the dashboard.
"""

import streamlit as st
from typing import List, Dict, Callable, Optional

from config import ZUPER_JOB_URL_TEMPLATE, JOBS_PER_PAGE
from database.queries import get_part_match_details


def render_job_row(
    job: Dict,
    idx: int,
    total: int,
    on_review: Callable[[str], int],
    part_search: Optional[str] = None
) -> None:
    """
    Render a single job row.

    Args:
        job: Job dictionary with job data.
        idx: Index of this job in the list.
        total: Total number of jobs being displayed.
        on_review: Callback function when review button is clicked.
        part_search: Optional part search term to show match details.
    """
    completed_date = job.get('completed_at') or job.get('created_at')
    zuper_url = ZUPER_JOB_URL_TEMPLATE.format(job_uid=job['job_uid'])

    with st.container():
        col1, col2, col3 = st.columns([5, 1.5, 1.5])

        with col1:
            # Job details
            title = job.get('job_title', '')
            if len(title) > 60:
                title = title[:60] + '...'

            st.markdown(f"**#{job.get('job_number', 'N/A')}** - {title}")
            st.caption(
                f"{job.get('organization_name') or '-'} | "
                f"{job.get('service_team') or '-'} | "
                f"Completed: {completed_date[:10] if completed_date else '-'}"
            )

            # Show match details if part search is active
            if part_search:
                matches = get_part_match_details(job['job_uid'], part_search)
                match_info = []
                if matches['line_items']:
                    match_info.append(f"**Line Item:** {matches['line_items'][0]}")
                if matches['notes']:
                    match_info.append(f"**Notes:** {matches['notes'][0]}")
                if matches['checklists']:
                    match_info.append(f"**Checklist:** {matches['checklists'][0]}")
                if match_info:
                    st.markdown(" | ".join(match_info[:2]), help="Where the search term was found")

        with col2:
            # Status
            if job.get('flag_type'):
                st.markdown(":red[**Issues**]")
                msg = job.get('flag_message', '')
                if msg:
                    st.caption(msg[:40] + '...' if len(msg) > 40 else msg)
            else:
                st.markdown(":green[**Passing**]")

        with col3:
            # Actions
            st.link_button("View Job", zuper_url, use_container_width=True)

            if job.get('flag_type'):
                if st.button(
                    "Reviewed",
                    key=f"review_{job['job_uid']}",
                    use_container_width=True,
                    type="secondary"
                ):
                    rows_updated = on_review(job['job_uid'])
                    if rows_updated > 0:
                        st.success(f"Job #{job.get('job_number')} marked as reviewed!")
                        st.rerun()
                    else:
                        st.warning("No changes made")

        # Divider between rows
        if idx < total - 1:
            st.divider()


def render_job_table(
    jobs: List[Dict],
    on_review: Callable[[str], int],
    part_search: Optional[str] = None
) -> None:
    """
    Render the job table.

    Args:
        jobs: List of job dictionaries.
        on_review: Callback function when review button is clicked.
        part_search: Optional part search term to show match details.
    """
    if not jobs:
        st.info("No jobs found matching the current filters.")
        return

    for idx, job in enumerate(jobs):
        render_job_row(job, idx, len(jobs), on_review, part_search)


def render_pagination(total_count: int, limit: int = JOBS_PER_PAGE) -> None:
    """
    Render pagination controls.

    Args:
        total_count: Total number of results.
        limit: Results per page.
    """
    total_pages = max(1, (total_count + limit - 1) // limit)
    current_page = st.session_state.current_page

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button(
            "Previous",
            disabled=current_page <= 1,
            use_container_width=True
        ):
            st.session_state.current_page -= 1
            st.rerun()

    with col2:
        st.markdown(
            f"<div style='text-align: center'>Page {current_page} of {total_pages}</div>",
            unsafe_allow_html=True
        )

    with col3:
        if st.button(
            "Next",
            disabled=current_page >= total_pages,
            use_container_width=True
        ):
            st.session_state.current_page += 1
            st.rerun()
