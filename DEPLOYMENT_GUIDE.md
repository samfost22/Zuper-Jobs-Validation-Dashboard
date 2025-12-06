#!/usr/bin/env python3
"""
Zuper-NetSuite Monitoring Dashboard with Basic Authentication
"""

from flask import Flask, render_template, jsonify, request, Response
from functools import wraps
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'zuper_netsuite.db')

# Authentication Configuration
USERNAME = os.environ.get('DASHBOARD_USERNAME', 'admin')
PASSWORD = os.environ.get('DASHBOARD_PASSWORD', 'changeme123')

def check_auth(username, password):
    """Check if username/password is valid"""
    return username == USERNAME and password == PASSWORD

def authenticate():
    """Send 401 response for authentication"""
    return Response(
        'Please login to access the dashboard.\n'
        'Use your credentials.', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
@requires_auth
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

# All other routes from original dashboard.py...
# (Copy all the @app.route methods from dashboard.py and add @requires_auth decorator)

@app.route('/api/stats')
@requires_auth
def get_stats():
    """Get dashboard statistics"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM organizations WHERE is_active = 1")
    total_orgs = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM netsuite_mapping WHERE is_active = 1 AND has_netsuite_id = 1")
    orgs_with_netsuite = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM netsuite_mapping WHERE is_active = 1 AND has_netsuite_id = 0")
    orgs_without_netsuite = cursor.fetchone()['count']

    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute("SELECT COUNT(*) as count FROM organizations WHERE created_at >= ? AND is_active = 1", (seven_days_ago,))
    new_orgs_7days = cursor.fetchone()['count']

    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute("SELECT COUNT(*) as count FROM organizations WHERE created_at >= ? AND is_active = 1", (thirty_days_ago,))
    new_orgs_30days = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM alerts WHERE is_resolved = 0")
    open_alerts = cursor.fetchone()['count']

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

# Add all other routes with @requires_auth decorator...

if __name__ == '__main__':
    print("Starting Zuper-NetSuite Monitoring Dashboard with Authentication...")
    print(f"Username: {USERNAME}")
    print(f"Password: {PASSWORD}")
    print("Dashboard will be available at: http://localhost:5001")
    print("IMPORTANT: Change the password before deploying!")
    app.run(debug=True, host='0.0.0.0', port=5001)
