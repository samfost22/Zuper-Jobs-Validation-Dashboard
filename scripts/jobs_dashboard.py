#!/usr/bin/env python3
"""
Zuper Jobs Validation Dashboard
Flask web dashboard with clickable metric cards
"""

from flask import Flask, render_template, jsonify, request
import sqlite3
import json
from datetime import datetime

app = Flask(__name__)
DB_FILE = 'jobs_validation.db'

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('jobs_dashboard.html')

@app.route('/api/metrics')
def get_metrics():
    """Get dashboard metrics"""
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

    # Organizations missing NetSuite ID (count unique organizations, not jobs)
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM organizations
        WHERE netsuite_customer_id IS NULL OR netsuite_customer_id = ''
    """)
    org_missing_netsuite_count = cursor.fetchone()['count']

    # Jobs passing all validations
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM jobs j
        LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
        WHERE vf.id IS NULL
    """)
    passing_count = cursor.fetchone()['count']

    # Jobs with checklist parts
    cursor.execute("SELECT COUNT(*) as count FROM jobs WHERE has_checklist_parts = 1")
    jobs_with_parts = cursor.fetchone()['count']

    # Jobs with NetSuite IDs
    cursor.execute("SELECT COUNT(*) as count FROM jobs WHERE has_netsuite_id = 1")
    jobs_with_netsuite = cursor.fetchone()['count']

    conn.close()

    return jsonify({
        'total_jobs': total_jobs,
        'parts_no_items_count': parts_no_items_count,
        'missing_netsuite_count': missing_netsuite_count,
        'org_missing_netsuite_count': org_missing_netsuite_count,
        'passing_count': passing_count,
        'jobs_with_parts': jobs_with_parts,
        'jobs_with_netsuite': jobs_with_netsuite,
        'updated_at': datetime.now().isoformat()
    })

@app.route('/api/jobs')
def get_jobs():
    """Get jobs list with optional filtering"""
    filter_type = request.args.get('filter', 'all')
    month_filter = request.args.get('month', '')  # Format: YYYY-MM
    org_filter = request.args.get('organization', '')
    team_filter = request.args.get('service_team', '')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 50))
    offset = (page - 1) * limit

    conn = get_db_connection()
    cursor = conn.cursor()

    # Build filter clauses
    filter_clauses = []

    if month_filter:
        # Use completed_at if available, otherwise created_at
        filter_clauses.append(f"(strftime('%Y-%m', COALESCE(j.completed_at, j.created_at)) = '{month_filter}')")

    if org_filter:
        filter_clauses.append(f"j.organization_name LIKE '%{org_filter}%'")

    if team_filter:
        filter_clauses.append(f"j.service_team LIKE '%{team_filter}%'")

    date_clause = ("AND " + " AND ".join(filter_clauses)) if filter_clauses else ""

    # Build query based on filter
    if filter_type == 'parts_no_items':
        query = f"""
            SELECT DISTINCT j.*, vf.flag_message, vf.flag_type
            FROM jobs j
            JOIN validation_flags vf ON j.job_uid = vf.job_uid
            WHERE vf.flag_type = 'parts_replaced_no_line_items'
            AND vf.is_resolved = 0
            {date_clause}
            ORDER BY j.created_at DESC
            LIMIT ? OFFSET ?
        """
    elif filter_type == 'missing_netsuite':
        query = f"""
            SELECT DISTINCT j.*, vf.flag_message, vf.flag_type
            FROM jobs j
            JOIN validation_flags vf ON j.job_uid = vf.job_uid
            WHERE vf.flag_type = 'missing_netsuite_id'
            AND vf.is_resolved = 0
            {date_clause}
            ORDER BY j.created_at DESC
            LIMIT ? OFFSET ?
        """
    elif filter_type == 'passing':
        query = f"""
            SELECT j.*, NULL as flag_message, NULL as flag_type
            FROM jobs j
            LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
            WHERE vf.id IS NULL
            {date_clause}
            ORDER BY j.created_at DESC
            LIMIT ? OFFSET ?
        """
    else:  # all
        query = f"""
            SELECT j.*, vf.flag_message, vf.flag_type
            FROM jobs j
            LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
            WHERE 1=1
            {date_clause}
            ORDER BY j.created_at DESC
            LIMIT ? OFFSET ?
        """

    cursor.execute(query, (limit, offset))
    rows = cursor.fetchall()

    # Get total count for pagination
    if filter_type == 'parts_no_items':
        cursor.execute(f"""
            SELECT COUNT(DISTINCT j.job_uid)
            FROM jobs j
            JOIN validation_flags vf ON j.job_uid = vf.job_uid
            WHERE vf.flag_type = 'parts_replaced_no_line_items' AND vf.is_resolved = 0
            {date_clause}
        """)
    elif filter_type == 'missing_netsuite':
        cursor.execute(f"""
            SELECT COUNT(DISTINCT j.job_uid)
            FROM jobs j
            JOIN validation_flags vf ON j.job_uid = vf.job_uid
            WHERE vf.flag_type = 'missing_netsuite_id' AND vf.is_resolved = 0
            {date_clause}
        """)
    elif filter_type == 'passing':
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM jobs j
            LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
            WHERE vf.id IS NULL
            {date_clause}
        """)
    else:
        count_where = f"WHERE {date_clause[4:]}" if date_clause else ""
        cursor.execute(f"SELECT COUNT(*) FROM jobs j {count_where}")

    total_count = cursor.fetchone()[0]

    # Convert rows to dicts
    jobs = []
    for row in rows:
        job = dict(row)
        # Get all flags for this job
        cursor.execute("""
            SELECT flag_type, flag_severity, flag_message, details
            FROM validation_flags
            WHERE job_uid = ? AND is_resolved = 0
        """, (job['job_uid'],))

        flags = []
        for flag_row in cursor.fetchall():
            flags.append({
                'flag_type': flag_row['flag_type'],
                'flag_severity': flag_row['flag_severity'],
                'flag_message': flag_row['flag_message'],
                'details': json.loads(flag_row['details']) if flag_row['details'] else {}
            })

        job['flags'] = flags
        jobs.append(job)

    conn.close()

    return jsonify({
        'jobs': jobs,
        'total': total_count,
        'page': page,
        'limit': limit,
        'total_pages': (total_count + limit - 1) // limit
    })

@app.route('/api/job/<job_uid>')
def get_job_detail(job_uid):
    """Get detailed job information"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get job
    cursor.execute("SELECT * FROM jobs WHERE job_uid = ?", (job_uid,))
    job = cursor.fetchone()

    if not job:
        conn.close()
        return jsonify({'error': 'Job not found'}), 404

    job_dict = dict(job)

    # Get line items
    cursor.execute("SELECT * FROM job_line_items WHERE job_uid = ?", (job_uid,))
    line_items = [dict(row) for row in cursor.fetchall()]

    # Get checklist parts
    cursor.execute("SELECT * FROM job_checklist_parts WHERE job_uid = ?", (job_uid,))
    checklist_parts = [dict(row) for row in cursor.fetchall()]

    # Get validation flags
    cursor.execute("""
        SELECT * FROM validation_flags
        WHERE job_uid = ? AND is_resolved = 0
    """, (job_uid,))
    flags = []
    for row in cursor.fetchall():
        flag = dict(row)
        if flag['details']:
            flag['details'] = json.loads(flag['details'])
        flags.append(flag)

    # Get custom fields
    cursor.execute("SELECT * FROM job_custom_fields WHERE job_uid = ?", (job_uid,))
    custom_fields = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'job': job_dict,
        'line_items': line_items,
        'checklist_parts': checklist_parts,
        'flags': flags,
        'custom_fields': custom_fields
    })

@app.route('/api/job/<job_uid>/mark-good', methods=['POST'])
def mark_job_good(job_uid):
    """Mark all validation flags for a job as resolved"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Update all unresolved flags for this job
    cursor.execute("""
        UPDATE validation_flags
        SET is_resolved = 1,
            resolved_at = ?
        WHERE job_uid = ? AND is_resolved = 0
    """, (datetime.now().isoformat(), job_uid))

    rows_updated = cursor.rowcount
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': f'Marked {rows_updated} flag(s) as resolved',
        'job_uid': job_uid
    })

@app.route('/api/organizations')
def get_organizations():
    """Get list of organizations missing NetSuite IDs"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get organizations without NetSuite IDs
    cursor.execute("""
        SELECT
            o.organization_uid,
            o.organization_name,
            o.netsuite_customer_id,
            COUNT(j.job_uid) as job_count,
            MAX(j.created_at) as last_job_date
        FROM organizations o
        LEFT JOIN jobs j ON o.organization_uid = j.organization_uid
        WHERE o.netsuite_customer_id IS NULL OR o.netsuite_customer_id = ''
        GROUP BY o.organization_uid
        ORDER BY job_count DESC, o.organization_name
    """)

    organizations = []
    for row in cursor.fetchall():
        organizations.append({
            'organization_uid': row['organization_uid'],
            'organization_name': row['organization_name'],
            'job_count': row['job_count'],
            'last_job_date': row['last_job_date']
        })

    conn.close()

    return jsonify({
        'organizations': organizations,
        'total': len(organizations)
    })

@app.route('/api/filter-options')
def get_filter_options():
    """Get available filter options for organizations and service teams"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get unique organizations
    cursor.execute("""
        SELECT DISTINCT organization_name
        FROM jobs
        WHERE organization_name IS NOT NULL AND organization_name != ''
        ORDER BY organization_name
    """)
    organizations = [row['organization_name'] for row in cursor.fetchall()]

    # Get unique service teams
    cursor.execute("""
        SELECT DISTINCT service_team
        FROM jobs
        WHERE service_team IS NOT NULL AND service_team != ''
        ORDER BY service_team
    """)
    teams = [row['service_team'] for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'organizations': organizations,
        'service_teams': teams
    })

if __name__ == '__main__':
    print("Starting Zuper Jobs Validation Dashboard...")
    print("Dashboard will be available at: http://localhost:5002")
    app.run(debug=True, host='0.0.0.0', port=5002)
