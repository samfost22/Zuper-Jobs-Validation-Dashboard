# Zuper-NetSuite Monitoring Dashboard

A real-time monitoring dashboard for tracking Zuper organizations and their NetSuite ID coverage.

## Features

- **Real-time Monitoring**: Track all organizations and their NetSuite Customer ID status
- **Automated Alerts**: Get notified when organizations are missing NetSuite IDs
- **Advanced Filtering**: Filter by status, creation date, and search by name/email
- **SQLite Backend**: Lightweight database for fast queries and reporting
- **Export Capabilities**: Export data to CSV for further analysis
- **Sync History**: Track all API synchronizations

## Quick Start

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Set Environment Variables (Optional)

The dashboard uses these environment variables:
- `ZUPER_API_KEY` - Your Zuper API key (default: pre-configured)
- `ZUPER_BASE_URL` - Your Zuper API base URL (default: pre-configured)

### 3. Initial Database Sync

Sync all organizations from Zuper API to the local database:

```bash
python3 sync_to_database.py
```

This will:
- Create the SQLite database (`zuper_netsuite.db`)
- Fetch all 190 organizations
- Extract custom fields
- Create alerts for missing NetSuite IDs

### 4. Start the Dashboard

```bash
python3 dashboard.py
```

The dashboard will be available at: **http://localhost:5000**

## Dashboard Overview

### Statistics Cards
- **Total Organizations**: Active organizations count
- **With NetSuite ID**: Organizations that have NetSuite Customer ID
- **Missing NetSuite ID**: Organizations that need attention
- **Open Alerts**: Unresolved alerts count
- **New (7 days)**: Recently created organizations
- **New (30 days)**: Organizations created in last month

### Tabs

#### 1. Organizations Tab
- View all organizations with filtering options
- Search by name or email
- Filter by:
  - All Active
  - Missing NetSuite ID
  - With NetSuite ID
  - New (7 days)
  - New (30 days)
  - Inactive
- Export to CSV

#### 2. Alerts Tab
- View all active alerts for organizations missing NetSuite IDs
- Mark alerts as resolved
- Toggle between active and resolved alerts

#### 3. Sync History Tab
- View history of all data synchronizations
- See sync statistics (fetched, updated, created)
- Monitor sync errors

## Database Schema

### Tables

**organizations**
- Primary table storing organization data
- Fields: organization_uid, name, email, no_of_customers, etc.

**organization_custom_fields**
- Stores all custom fields for each organization
- Tracks NetSuite Customer ID, External ID, HubSpot ID, etc.

**alerts**
- Tracks alerts for missing NetSuite IDs
- Can be marked as resolved

**sync_log**
- Logs all synchronization operations
- Tracks success/failure and timing

### Views

**netsuite_mapping**
- Convenient view joining organizations with their NetSuite IDs
- Includes `has_netsuite_id` flag for easy filtering

## Keeping Data Fresh

### Manual Sync

Run the sync script whenever you want to update the database:

```bash
python3 sync_to_database.py
```

### Automated Sync (Recommended)

Set up a cron job to sync daily:

```bash
# Edit crontab
crontab -e

# Add this line to sync every day at 6 AM
0 6 * * * cd /path/to/zuper-netsuite\ interals\ ID && /usr/local/bin/python3 sync_to_database.py >> sync.log 2>&1
```

Or use a system scheduler like launchd on macOS.

## Files Overview

- `database_schema.sql` - SQLite database schema
- `sync_to_database.py` - Script to sync Zuper data to database
- `dashboard.py` - Flask web application
- `templates/dashboard.html` - Dashboard HTML/CSS/JavaScript
- `requirements.txt` - Python dependencies
- `zuper_netsuite.db` - SQLite database (created on first sync)

## Data Files (Generated)

- `organizations_data.json` - Raw organization data from API
- `organizations_detailed.json` - Detailed organization data with custom fields
- `organization_custom_fields_analysis.json` - Custom fields analysis
- `organizations_missing_netsuite_id.json` - Organizations without NetSuite IDs
- `zuper_netsuite_mapping.csv` - Mapping of Zuper orgs to NetSuite IDs
- Various CSV exports for analysis

## API Endpoints

The dashboard provides these API endpoints:

- `GET /api/stats` - Dashboard statistics
- `GET /api/organizations` - List organizations (with filtering)
- `GET /api/alerts` - List alerts
- `POST /api/alerts/<id>/resolve` - Resolve an alert
- `GET /api/sync_history` - Sync history
- `GET /api/export/csv` - Export to CSV

## Monitoring Best Practices

1. **Daily Sync**: Set up automated daily syncs to keep data current
2. **Review Alerts**: Check the alerts tab regularly for missing NetSuite IDs
3. **Track New Orgs**: Monitor the "New (7 days)" filter to catch new organizations early
4. **Export Reports**: Use CSV export for weekly/monthly reports to stakeholders
5. **Resolve Alerts**: Mark alerts as resolved once NetSuite IDs are added

## Troubleshooting

### Database is empty
Run `python3 sync_to_database.py` to populate the database

### Dashboard won't start
- Check if Flask is installed: `pip3 install flask`
- Ensure port 5000 is not in use
- Check for errors in terminal output

### Data is outdated
Run `python3 sync_to_database.py` to refresh from Zuper API

### Missing organizations
Check sync_log table for errors during last sync

## Current Status

- **Total Organizations**: 190
- **Organizations with NetSuite ID**: 171 (90.0% coverage)
- **Organizations without NetSuite ID**: 19 (need attention)
- **Active Alerts**: 10

## Support

For issues or questions, contact your internal development team.
