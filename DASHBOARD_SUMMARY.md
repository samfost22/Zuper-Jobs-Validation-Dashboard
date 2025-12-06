# Zuper-NetSuite Monitoring Dashboard - Summary

## What Was Built

A complete monitoring dashboard with SQLite backend to track Zuper organizations and their NetSuite ID coverage in real-time.

## Quick Start

```bash
# 1. Start the dashboard
./start_dashboard.sh

# 2. Open in browser
http://localhost:5001
```

## Current Statistics

- **Total Organizations**: 188 active
- **With NetSuite ID**: 178 (94.7% coverage)
- **Missing NetSuite ID**: 10 organizations need attention
- **Open Alerts**: 10 unresolved alerts
- **New Organizations (7 days)**: 1
- **New Organizations (30 days)**: 3

## Key Features

### 1. Real-Time Monitoring Dashboard
- Modern, responsive web interface
- Auto-refreshes every 5 minutes
- Color-coded statistics cards
- Easy filtering and search

### 2. Organization Tracking
View and filter organizations by:
- ✅ All Active Organizations
- ⚠️ Missing NetSuite ID (Need attention)
- ✓ With NetSuite ID (Complete)
- 🆕 New (Last 7 days)
- 📅 New (Last 30 days)
- 🔒 Inactive Organizations

### 3. Alert System
- Automatic alerts for missing NetSuite IDs
- Mark alerts as resolved
- Track alert history
- Filter active/resolved alerts

### 4. Sync Management
- Track all API synchronizations
- View sync history and statistics
- Monitor sync errors
- See organizations created/updated

### 5. Export & Reporting
- Export to CSV with one click
- Complete organization data
- NetSuite ID mapping included
- Ready for Excel/Google Sheets

## Files Created

### Core Application
- `dashboard.py` - Flask web application (main dashboard)
- `sync_to_database.py` - API sync script
- `database_schema.sql` - Database structure
- `templates/dashboard.html` - Dashboard UI

### Database
- `zuper_netsuite.db` - SQLite database with all organization data

### Documentation
- `README.md` - Complete setup and usage guide
- `DASHBOARD_SUMMARY.md` - This file
- `requirements.txt` - Python dependencies

### Utilities
- `start_dashboard.sh` - Quick startup script
- `get_organizations.py` - Fetch organizations from API
- `get_organization_details.py` - Get detailed org data
- `get_organization_custom_fields.py` - Extract custom fields
- `organizations_missing_netsuite_id.py` - Find missing IDs

### Data Files
- `organizations_data.json` - Raw org data
- `organizations_detailed.json` - Detailed org data with custom fields
- `organization_custom_fields_analysis.json` - Custom field analysis
- `organizations_missing_netsuite_id.json` - Orgs without NetSuite ID
- `organizations_missing_netsuite_id.csv` - CSV of missing orgs
- `organizations_netsuite_status.csv` - Complete status report
- `zuper_netsuite_mapping.csv` - Zuper to NetSuite mapping

## Dashboard URL

**http://localhost:5001**

## How Your Team Should Use This

### Daily Use
1. **Morning Check**: Open dashboard to see overnight activity
2. **Review Alerts**: Check "Alerts" tab for new organizations missing NetSuite IDs
3. **Track New Orgs**: Use "New (7 days)" filter to see recent additions

### Weekly Tasks
1. **Run Sync**: Execute `python3 sync_to_database.py` to refresh data
2. **Review Coverage**: Check that NetSuite ID coverage stays above 90%
3. **Export Report**: Use "Export CSV" for weekly status reports

### When New Organizations Are Created
1. Dashboard will show them in "Missing NetSuite ID" filter
2. An alert will be automatically created
3. After adding NetSuite ID in Zuper, run sync and resolve the alert

## Database Tables

### Organizations Table
Stores all organization data including:
- Organization UID, name, email
- Number of customers
- Active status
- Creation/update timestamps

### Organization Custom Fields Table
Stores all custom fields:
- NetSuite Customer ID
- External ID
- HubSpot Company ID
- And all other custom fields

### Alerts Table
Tracks missing NetSuite IDs:
- Organization reference
- Alert message
- Created/resolved timestamps
- Resolution status

### Sync Log Table
Logs all synchronizations:
- Sync timestamps
- Organizations fetched/updated/created
- Error tracking

## Keeping Data Fresh

### Manual Sync (Recommended for now)
```bash
python3 sync_to_database.py
```

### Automated Daily Sync
Set up a cron job:
```bash
# Run every day at 6 AM
0 6 * * * cd /Users/samfoster/zuper-netsuite\ interals\ ID && python3 sync_to_database.py >> sync.log 2>&1
```

## API Endpoints

The dashboard exposes these endpoints:

- `GET /` - Dashboard home page
- `GET /api/stats` - Dashboard statistics
- `GET /api/organizations` - List organizations (with filters)
- `GET /api/alerts` - List alerts
- `POST /api/alerts/<id>/resolve` - Resolve alert
- `GET /api/sync_history` - Sync history
- `GET /api/export/csv` - Export to CSV

## Production Deployment (Optional)

For production use, consider:

1. **Use a production WSGI server**:
   ```bash
   pip3 install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5001 dashboard:app
   ```

2. **Set up reverse proxy** (nginx/Apache)

3. **Enable authentication** (add login system)

4. **Set up automated backups** of `zuper_netsuite.db`

5. **Monitor dashboard uptime** (systemd service, supervisor, etc.)

## Troubleshooting

### Dashboard won't start
```bash
# Check if port 5001 is available
lsof -i :5001

# Use different port if needed (edit dashboard.py)
```

### Data is outdated
```bash
# Run sync manually
python3 sync_to_database.py
```

### Database errors
```bash
# Backup and recreate database
mv zuper_netsuite.db zuper_netsuite.db.backup
python3 sync_to_database.py
```

## Next Steps

1. ✅ **Dashboard is ready to use**
2. **Share with team**: Give access to http://localhost:5001 (or deploy to server)
3. **Set up daily sync**: Add cron job for automated updates
4. **Monitor alerts**: Check daily for new organizations missing NetSuite IDs
5. **Export reports**: Use CSV export for stakeholder reporting

## Support

For questions or issues:
- Check `README.md` for detailed documentation
- Review sync logs: `sync.log`
- Check dashboard console output for errors

---

**Dashboard Status**: ✅ Running and operational
**Last Sync**: Check dashboard or run sync script
**Access URL**: http://localhost:5001
