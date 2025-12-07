# Data Directory

This directory contains persistent database files for the Zuper Jobs Validation Dashboard.

## Files (not tracked in git)

- `jobs_validation.db` - Main jobs database with validation data
- `zuper_netsuite.db` - Organization NetSuite mapping database

## Database Persistence

The database files in this directory persist across app restarts and deployments. This allows:

1. **Fast startup** - App loads existing data immediately
2. **Incremental syncs** - Only fetch new/updated jobs via Quick Sync
3. **Data continuity** - Historical data is preserved

## Initial Setup

On first deployment or fresh installation:

1. Run "Full Sync" from the dashboard to populate the database
2. After initial sync, use "Quick Sync" for regular updates
3. Database will automatically be created if it doesn't exist

## Deployment Notes

When deploying to hosting services (Streamlit Cloud, etc.):

- This directory should be configured as persistent storage
- Database files should NOT be committed to git (see `.gitignore`)
- After deployment, perform one full sync to populate data
