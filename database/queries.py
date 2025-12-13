"""
Database queries for Zuper Jobs Validation Dashboard.

All queries use parameterized SQL to prevent injection attacks.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from .connection import get_db_connection, db_session, ensure_database_exists
from config import JOBS_DB_FILE, JOBS_PER_PAGE

logger = logging.getLogger(__name__)

# Initialize database once at module load time (not on every query)
# This avoids redundant file existence checks on every database operation
_db_initialized = False

def _ensure_db_ready():
    """Ensure database is initialized (called once per process)."""
    global _db_initialized
    if not _db_initialized:
        ensure_database_exists()
        _db_initialized = True

# Initialize on module import
_ensure_db_ready()


def get_metrics() -> Dict[str, int]:
    """
    Get dashboard metrics with proper error handling.

    Returns:
        Dictionary with total_jobs, parts_no_items_count,
        missing_netsuite_count, and passing_count.
    """
    default = {
        'total_jobs': 0,
        'parts_no_items_count': 0,
        'missing_netsuite_count': 0,
        'passing_count': 0
    }

    try:
        with db_session() as conn:
            cursor = conn.cursor()

            # Total jobs
            cursor.execute("SELECT COUNT(*) as total FROM jobs")
            default['total_jobs'] = cursor.fetchone()['total']

            # Jobs with parts replaced but no line items
            cursor.execute("""
                SELECT COUNT(DISTINCT job_uid) as count
                FROM validation_flags
                WHERE flag_type = 'parts_replaced_no_line_items'
                AND is_resolved = 0
            """)
            default['parts_no_items_count'] = cursor.fetchone()['count']

            # Jobs with line items but missing NetSuite ID
            cursor.execute("""
                SELECT COUNT(DISTINCT job_uid) as count
                FROM validation_flags
                WHERE flag_type = 'missing_netsuite_id'
                AND is_resolved = 0
            """)
            default['missing_netsuite_count'] = cursor.fetchone()['count']

            # Jobs passing all validations
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM jobs j
                LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
                WHERE vf.id IS NULL
            """)
            default['passing_count'] = cursor.fetchone()['count']

        return default

    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return default


def _build_job_filters(
    filter_type: str,
    month: str,
    organization: str,
    team: str,
    start_date: Optional[str],
    end_date: Optional[str],
    job_number: str,
    part_search: str,
    serial_search: str,
    asset: str
) -> Tuple[List[str], List[Any], str, str]:
    """
    Build parameterized filter clauses for job queries.

    Returns:
        Tuple of (where_clauses, params, join_clause, extra_where)
    """
    clauses = []
    params = []
    joins = []
    extra_where = []

    # Job number search
    if job_number:
        clauses.append("j.job_number LIKE ?")
        params.append(f"%{job_number}%")

    # Date filtering
    if start_date and end_date:
        clauses.append("date(COALESCE(j.completed_at, j.created_at)) BETWEEN ? AND ?")
        params.extend([start_date, end_date])
    elif month:
        clauses.append("strftime('%Y-%m', COALESCE(j.completed_at, j.created_at)) = ?")
        params.append(month)

    # Organization filter
    if organization:
        clauses.append("j.organization_name LIKE ?")
        params.append(f"%{organization}%")

    # Team filter
    if team:
        clauses.append("j.service_team LIKE ?")
        params.append(f"%{team}%")

    # Asset filter
    if asset:
        clauses.append("j.asset_name = ?")
        params.append(asset)

    # Part search - requires join
    if part_search:
        joins.append("JOIN job_line_items li ON j.job_uid = li.job_uid")
        extra_where.append("(li.item_name LIKE ? OR li.item_code LIKE ?)")
        params.extend([f"%{part_search}%", f"%{part_search}%"])

    # Serial search - requires join to both tables
    if serial_search:
        if not part_search:
            joins.append("LEFT JOIN job_line_items li2 ON j.job_uid = li2.job_uid")
        joins.append("LEFT JOIN job_checklist_parts cp ON j.job_uid = cp.job_uid")

        if part_search:
            # Combine with part search
            extra_where[-1] = "(li.item_name LIKE ? OR li.item_code LIKE ? OR li.item_serial LIKE ? OR cp.part_serial LIKE ?)"
            params.extend([f"%{serial_search}%", f"%{serial_search}%"])
        else:
            extra_where.append("(li2.item_serial LIKE ? OR cp.part_serial LIKE ?)")
            params.extend([f"%{serial_search}%", f"%{serial_search}%"])

    join_clause = " ".join(joins)
    where_clause = " AND ".join(clauses) if clauses else ""
    extra_where_clause = " AND ".join(extra_where) if extra_where else ""

    return clauses, params, join_clause, extra_where_clause


def get_jobs(
    filter_type: str = 'all',
    page: int = 1,
    month: str = '',
    organization: str = '',
    team: str = '',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    job_number: str = '',
    part_search: str = '',
    serial_search: str = '',
    asset: str = '',
    limit: int = JOBS_PER_PAGE
) -> Tuple[List[Dict], int]:
    """
    Get jobs list with filtering and pagination using parameterized queries.

    Args:
        filter_type: 'all', 'parts_no_items', 'missing_netsuite', or 'passing'
        page: Page number (1-indexed)
        month: Month filter in 'YYYY-MM' format
        organization: Organization name to filter by
        team: Service team to filter by
        start_date: Start date for range filter (ISO format)
        end_date: End date for range filter (ISO format)
        job_number: Job number to search for
        part_search: Part name/code to search for
        serial_search: Serial number to search for
        asset: Asset name to filter by
        limit: Number of results per page

    Returns:
        Tuple of (jobs list, total count)
    """
    try:
        offset = (page - 1) * limit

        # Build filter components
        filter_clauses, params, join_clause, extra_where = _build_job_filters(
            filter_type, month, organization, team, start_date, end_date,
            job_number, part_search, serial_search, asset
        )

        # Combine filter clauses
        where_parts = []
        if filter_clauses:
            where_parts.extend(filter_clauses)

        # Build base query based on filter type
        if filter_type == 'parts_no_items':
            base_join = f"JOIN validation_flags vf ON j.job_uid = vf.job_uid {join_clause}"
            type_where = "vf.flag_type = 'parts_replaced_no_line_items' AND vf.is_resolved = 0"
            select_extra = ", vf.flag_message, vf.flag_type"
        elif filter_type == 'missing_netsuite':
            base_join = f"JOIN validation_flags vf ON j.job_uid = vf.job_uid {join_clause}"
            type_where = "vf.flag_type = 'missing_netsuite_id' AND vf.is_resolved = 0"
            select_extra = ", vf.flag_message, vf.flag_type"
        elif filter_type == 'passing':
            base_join = f"LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0 {join_clause}"
            type_where = "vf.id IS NULL"
            select_extra = ", NULL as flag_message, NULL as flag_type"
        else:  # all
            base_join = f"LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0 {join_clause}"
            type_where = "1=1"
            select_extra = ", vf.flag_message, vf.flag_type"

        # Build WHERE clause
        all_where = [type_where]
        if where_parts:
            all_where.extend([f"({c})" for c in where_parts])
        if extra_where:
            all_where.append(f"({extra_where})")

        where_clause = " AND ".join(all_where)

        # Build and execute query
        query = f"""
            SELECT DISTINCT j.*{select_extra}
            FROM jobs j
            {base_join}
            WHERE {where_clause}
            ORDER BY j.created_at DESC
            LIMIT ? OFFSET ?
        """

        query_params = params + [limit, offset]

        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(query, query_params)
            jobs = [dict(row) for row in cursor.fetchall()]

            # Get total count
            count_query = f"""
                SELECT COUNT(DISTINCT j.job_uid)
                FROM jobs j
                {base_join}
                WHERE {where_clause}
            """
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]

        return jobs, total_count

    except Exception as e:
        logger.error(f"Error getting jobs: {e}")
        return [], 0


def get_filter_options() -> Tuple[List[str], List[str]]:
    """
    Get available filter options for organizations and teams.

    Returns:
        Tuple of (organizations list, teams list)
    """
    try:
        with db_session() as conn:
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

        return organizations, teams

    except Exception as e:
        logger.error(f"Error getting filter options: {e}")
        return [], []


def get_assets_with_counts() -> List[Tuple[str, str]]:
    """
    Get list of assets with job counts, sorted by most jobs first.

    Returns:
        List of (asset_name, display_label) tuples.
    """
    try:
        with db_session() as conn:
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
                label = f"{row['asset_name']} ({row['total_jobs']} jobs"
                if row['jobs_with_issues'] > 0:
                    label += f", {row['jobs_with_issues']} with issues"
                label += ")"
                assets.append((row['asset_name'], label))

        return assets

    except Exception as e:
        logger.error(f"Error getting assets: {e}")
        return []


def mark_job_resolved(job_uid: str) -> int:
    """
    Mark all validation flags for a job as resolved.

    Args:
        job_uid: The job UID to mark as resolved.

    Returns:
        Number of flags updated.
    """
    try:
        with db_session() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE validation_flags
                SET is_resolved = 1, resolved_at = ?
                WHERE job_uid = ? AND is_resolved = 0
            """, (datetime.now().isoformat(), job_uid))

            rows_updated = cursor.rowcount
            conn.commit()

        return rows_updated

    except Exception as e:
        logger.error(f"Error marking job resolved: {e}")
        return 0


def search_serials_bulk(serials: List[str]) -> List[Dict]:
    """
    Search for jobs by multiple serial numbers.

    Args:
        serials: List of serial numbers to search for.

    Returns:
        List of matching job records with serial info.
    """
    try:
        results = []

        with db_session() as conn:
            cursor = conn.cursor()

            for serial in serials:
                serial = serial.strip()
                if not serial:
                    continue

                cursor.execute("""
                    SELECT DISTINCT
                        j.job_uid, j.job_number, j.job_title, j.customer_name,
                        j.created_at, j.asset_name, j.service_team,
                        li.item_serial as line_item_serial,
                        cp.part_serial as checklist_serial
                    FROM jobs j
                    LEFT JOIN job_line_items li ON j.job_uid = li.job_uid
                        AND li.item_serial LIKE ?
                    LEFT JOIN job_checklist_parts cp ON j.job_uid = cp.job_uid
                        AND cp.part_serial LIKE ?
                    WHERE li.item_serial IS NOT NULL OR cp.part_serial IS NOT NULL
                    ORDER BY j.created_at DESC
                """, (f'%{serial}%', f'%{serial}%'))

                for row in cursor.fetchall():
                    results.append({
                        'searched_serial': serial,
                        'job_uid': row['job_uid'],
                        'job_number': row['job_number'],
                        'job_title': row['job_title'],
                        'customer': row['customer_name'],
                        'asset': row['asset_name'] or 'N/A',
                        'service_team': row['service_team'] or 'N/A',
                        'created_at': row['created_at']
                    })

        return results

    except Exception as e:
        logger.error(f"Error searching serials: {e}")
        return []


def get_last_sync_time() -> Optional[str]:
    """
    Get the timestamp of the last successful sync.

    Returns:
        ISO format timestamp string or None.
    """
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sync_completed_at
                FROM sync_log
                WHERE status = 'completed'
                ORDER BY id DESC
                LIMIT 1
            """)
            result = cursor.fetchone()
            return result['sync_completed_at'] if result else None

    except Exception as e:
        logger.error(f"Error getting last sync time: {e}")
        return None


def get_job_count() -> int:
    """
    Get the total number of jobs in the database.

    Returns:
        Number of jobs, or 0 on error.
    """
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM jobs")
            return cursor.fetchone()[0]

    except Exception as e:
        logger.error(f"Error getting job count: {e}")
        return 0
