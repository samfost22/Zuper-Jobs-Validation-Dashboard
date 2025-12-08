"""
Bulk serial number lookup component.
"""

import streamlit as st
import pandas as pd
from typing import List

from database.queries import search_serials_bulk
from config import ZUPER_JOB_URL_TEMPLATE


def _display_results(results: List[dict], serials: List[str]) -> None:
    """Display search results with download option."""
    if not results:
        st.error("No jobs found for the provided serial numbers")
        return

    st.success(f"Found {len(results)} job(s) across {len(serials)} serial numbers")

    # Build dataframe
    df = pd.DataFrame(results)
    df['Zuper Link'] = df['job_uid'].apply(
        lambda x: ZUPER_JOB_URL_TEMPLATE.format(job_uid=x)
    )

    display_df = df[[
        'searched_serial', 'job_number', 'customer',
        'asset', 'service_team', 'created_at', 'Zuper Link'
    ]]
    display_df.columns = [
        'Serial Searched', 'Job #', 'Customer',
        'Asset', 'Team', 'Date', 'Zuper Link'
    ]

    st.dataframe(display_df, use_container_width=True)

    # Download button
    csv = display_df.to_csv(index=False)
    st.download_button(
        label="Download Results as CSV",
        data=csv,
        file_name="serial_lookup_results.csv",
        mime="text/csv"
    )

    # Show which serials weren't found
    found_serials = set(df['searched_serial'].unique())
    not_found = [s for s in serials if s not in found_serials]
    if not_found:
        st.warning(f"{len(not_found)} serial(s) not found: {', '.join(not_found[:10])}")
        if len(not_found) > 10:
            st.caption(f"...and {len(not_found) - 10} more")


def render_bulk_lookup() -> None:
    """Render the bulk serial number lookup expander."""
    with st.expander("Bulk Serial Number Lookup"):
        st.caption("Search for multiple serial numbers at once")

        tab1, tab2 = st.tabs(["Paste List", "Upload CSV"])

        with tab1:
            bulk_text = st.text_area(
                "Paste serial numbers (one per line)",
                placeholder="CR-SM-12345\nCR-SM-12346\nCR-SM-12347\n...",
                height=150,
                key="bulk_serials_input"
            )

            if st.button("Search Serial Numbers", type="primary", key="search_pasted"):
                if not bulk_text:
                    st.warning("Please enter serial numbers to search")
                    return

                serials = [s.strip() for s in bulk_text.split('\n') if s.strip()]
                if not serials:
                    st.warning("No valid serial numbers found")
                    return

                with st.spinner(f"Searching {len(serials)} serial numbers..."):
                    results = search_serials_bulk(serials)

                _display_results(results, serials)

        with tab2:
            uploaded_file = st.file_uploader(
                "Upload CSV with serial numbers",
                type=['csv'],
                key="serial_csv_upload"
            )

            if uploaded_file is not None:
                try:
                    csv_data = pd.read_csv(uploaded_file)

                    # Find serial column
                    serial_column = None
                    for col in csv_data.columns:
                        if 'serial' in col.lower():
                            serial_column = col
                            break

                    if not serial_column:
                        st.warning(
                            "Could not find a column with 'serial' in the name. "
                            f"Available columns: {', '.join(csv_data.columns)}"
                        )
                        return

                    serials = csv_data[serial_column].dropna().astype(str).tolist()
                    st.info(f"Found {len(serials)} serial numbers in column '{serial_column}'")

                    if st.button("Search from CSV", type="primary", key="search_csv"):
                        with st.spinner(f"Searching {len(serials)} serial numbers..."):
                            results = search_serials_bulk(serials)

                        _display_results(results, serials)

                except Exception as e:
                    st.error(f"Error reading CSV: {e}")
