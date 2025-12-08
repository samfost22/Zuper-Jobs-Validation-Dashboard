"""
Database module for Zuper Jobs Validation Dashboard.

Provides centralized database connection handling and query utilities.
"""

from .connection import (
    get_db_connection,
    init_database,
    execute_query,
    execute_many,
)
from .queries import (
    get_metrics,
    get_jobs,
    get_filter_options,
    get_assets_with_counts,
    mark_job_resolved,
    search_serials_bulk,
)

__all__ = [
    'get_db_connection',
    'init_database',
    'execute_query',
    'execute_many',
    'get_metrics',
    'get_jobs',
    'get_filter_options',
    'get_assets_with_counts',
    'mark_job_resolved',
    'search_serials_bulk',
]
