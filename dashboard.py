#!/usr/bin/env python3
"""
Zuper-NetSuite Monitoring Dashboard
Flask web application for monitoring organizations and NetSuite ID coverage
"""

from flask import Flask, render_template, jsonify, request
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'zuper_netsuite.db')

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/stats')
def get_stats():
    """Get dashboard statistics"""
    conn = get_db()
    cursor = conn.cursor()

    # Total organizations
    cursor.execute("SELECT COUNT(*) as count FROM organizations WHERE is_active = 1")
    total_orgs = cursor.fetchone()['count']

    # Organizations with NetSuite ID
    cursor.execute("SELECT COUNT(*) as count FROM netsuite_mapping WHERE is_active = 1 AND has_netsuite_id = 1")
    orgs_with_netsuite = cursor.fetchone()['count']

    # Organizations without NetSuite ID
    cursor.execute("SELECT COUNT(*) as count FROM netsuite_mapping WHERE is_active = 1 AND has_netsuite_id = 0")
    orgs_without_netsuite = cursor.fetchone()['count']

    # New organizations in last 7 days
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute("SELECT COUNT(*) as count FROM organizations WHERE created_at >= ? AND is_active = 1", (seven_days_ago,))
    new_orgs_7days = cursor.fetchone()['count']

    # New organizations in last 30 days
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute("SELECT COUNT(*) as count FROM organizations WHERE created_at >= ? AND is_active = 1", (thirty_days_ago,))
    new_orgs_30days = cursor.fetchone()['count']

    # Open alerts
    cursor.execute("SELECT COUNT(*) as count FROM alerts WHERE is_resolved = 0")
    open_alerts = cursor.fetchone()['count']

    # Last sync time
    cursor.execute("SELECT sync_completed_at FROM sync_log WHERE status = 'completed' ORDER BY sync_completed_at DESC LIMIT 1")
    last_sync_row = cursor.fetchone()
    last_sync = last_sync_row['sync_completed_at'] if last_sync_row else None

    conn.close()

    return jsonify({
        'total_organizations': total_orgs,
        'with_netsuite_id': orgs_with_netsuite,
        'without_netsuite_id': orgs_without_netsuite,
        'coverage_percentage': round((orgs_with_netsuite / total_orgs * 100) if total_orgs > 0 else 0, 1),
        'new_orgs_7days': new_orgs_7days,
        'new_orgs_30days': new_orgs_30days,
        'open_alerts': open_alerts,
        'last_sync': last_sync
    })

@app.route('/api/organizations')
def get_organizations():
    """Get list of organizations with filtering"""
    conn = get_db()
    cursor = conn.cursor()

    # Get filter parameters
    filter_type = request.args.get('filter', 'all')
    search = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'DESC')

    # Build query
    query = """
        SELECT
            organization_uid,
            organization_name,
            organization_email,
            no_of_customers,
            is_active,
            created_at,
            updated_at,
            netsuite_customer_id,
            external_id,
            hubspot_company_id,
            has_netsuite_id
        FROM netsuite_mapping
        WHERE 1=1
    """
    params = []

    # Apply filters
    if filter_type == 'missing_netsuite':
        query += " AND has_netsuite_id = 0 AND is_active = 1"
    elif filter_type == 'with_netsuite':
        query += " AND has_netsuite_id = 1 AND is_active = 1"
    elif filter_type == 'new_7days':
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
        query += " AND created_at >= ? AND is_active = 1"
        params.append(seven_days_ago)
    elif filter_type == 'new_30days':
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        query += " AND created_at >= ? AND is_active = 1"
        params.append(thirty_days_ago)
    elif filter_type == 'inactive':
        query += " AND is_active = 0"
    else:  # all active
        query += " AND is_active = 1"

    # Apply search
    if search:
        query += " AND (organization_name LIKE ? OR organization_email LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])

    # Apply sorting
    valid_sort_columns = ['organization_name', 'created_at', 'no_of_customers', 'updated_at']
    if sort_by in valid_sort_columns:
        query += f" ORDER BY {sort_by} {sort_order}"
    else:
        query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    organizations = []
    for row in rows:
        organizations.append({
            'organization_uid': row['organization_uid'],
            'organization_name': row['organization_name'],
            'organization_email': row['organization_email'],
            'no_of_customers': row['no_of_customers'],
            'is_active': row['is_active'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'netsuite_customer_id': row['netsuite_customer_id'],
            'external_id': row['external_id'],
            'hubspot_company_id': row['hubspot_company_id'],
            'has_netsuite_id': row['has_netsuite_id']
        })

    conn.close()
    return jsonify(organizations)

@app.route('/api/alerts')
def get_alerts():
    """Get list of alerts"""
    conn = get_db()
    cursor = conn.cursor()

    show_resolved = request.args.get('show_resolved', 'false') == 'true'

    query = """
        SELECT
            a.id,
            a.organization_uid,
            a.alert_type,
            a.alert_message,
            a.is_resolved,
            a.created_at,
            a.resolved_at,
            o.organization_name,
            o.organization_email
        FROM alerts a
        JOIN organizations o ON a.organization_uid = o.organization_uid
    """

    if not show_resolved:
        query += " WHERE a.is_resolved = 0"

    query += " ORDER BY a.created_at DESC"

    cursor.execute(query)
    rows = cursor.fetchall()

    alerts = []
    for row in rows:
        alerts.append({
            'id': row['id'],
            'organization_uid': row['organization_uid'],
            'organization_name': row['organization_name'],
            'organization_email': row['organization_email'],
            'alert_type': row['alert_type'],
            'alert_message': row['alert_message'],
            'is_resolved': row['is_resolved'],
            'created_at': row['created_at'],
            'resolved_at': row['resolved_at']
        })

    conn.close()
    return jsonify(alerts)

@app.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
def resolve_alert(alert_id):
    """Mark an alert as resolved"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE alerts
        SET is_resolved = 1, resolved_at = ?
        WHERE id = ?
    """, (datetime.now(), alert_id))

    conn.commit()
    conn.close()

    return jsonify({'success': True})

@app.route('/api/sync_history')
def get_sync_history():
    """Get sync history"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            sync_started_at,
            sync_completed_at,
            organizations_fetched,
            organizations_updated,
            organizations_created,
            errors,
            status
        FROM sync_log
        ORDER BY sync_started_at DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()

    history = []
    for row in rows:
        history.append({
            'id': row['id'],
            'sync_started_at': row['sync_started_at'],
            'sync_completed_at': row['sync_completed_at'],
            'organizations_fetched': row['organizations_fetched'],
            'organizations_updated': row['organizations_updated'],
            'organizations_created': row['organizations_created'],
            'errors': row['errors'],
            'status': row['status']
        })

    conn.close()
    return jsonify(history)

@app.route('/api/export/csv')
def export_csv():
    """Export organizations to CSV"""
    import csv
    from io import StringIO

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            organization_uid,
            organization_name,
            organization_email,
            no_of_customers,
            is_active,
            created_at,
            netsuite_customer_id,
            external_id,
            hubspot_company_id,
            has_netsuite_id
        FROM netsuite_mapping
        WHERE is_active = 1
        ORDER BY created_at DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'Organization UID', 'Organization Name', 'Email', 'No. of Customers',
        'Active', 'Created At', 'NetSuite Customer ID', 'External ID',
        'HubSpot Company ID', 'Has NetSuite ID'
    ])

    # Data
    for row in rows:
        writer.writerow([
            row['organization_uid'],
            row['organization_name'],
            row['organization_email'],
            row['no_of_customers'],
            'Yes' if row['is_active'] else 'No',
            row['created_at'],
            row['netsuite_customer_id'] or '',
            row['external_id'] or '',
            row['hubspot_company_id'] or '',
            'Yes' if row['has_netsuite_id'] else 'No'
        ])

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=zuper_organizations.csv'}
    )

if __name__ == '__main__':
    print("Starting Zuper-NetSuite Monitoring Dashboard...")
    print("Dashboard will be available at: http://localhost:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)
