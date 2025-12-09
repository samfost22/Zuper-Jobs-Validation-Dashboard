# CLAUDE.md - AI Assistant Guide for Zuper Jobs Validation Dashboard

## Project Overview

This is an internal monitoring and validation dashboard for tracking **Zuper field service jobs** and their integration with **NetSuite**. The system monitors job data quality, tracks line items, validates checklist parts, and alerts on missing NetSuite Sales Order IDs.

**Primary Use Case**: Ensure jobs with parts/line items have corresponding NetSuite Sales Order IDs for proper billing and inventory tracking.

## Architecture

The project contains **two dashboard implementations**:

| Component | Technology | Port | Database | Purpose |
|-----------|------------|------|----------|---------|
| `streamlit_dashboard.py` | Streamlit | 8501 | `jobs_validation.db` | **PRIMARY** - Jobs validation dashboard |
| `dashboard.py` | Flask | 5001 | `zuper_netsuite.db` | Organization NetSuite ID monitoring |

**Primary Dashboard**: The Streamlit dashboard (`streamlit_dashboard.py`) is the main application for job validation.

## Technology Stack

- **Python 3.11+**
- **Streamlit** >= 1.28.0 - Primary dashboard UI
- **Flask** 3.0.0 - Secondary organization dashboard
- **SQLite** - Local database storage
- **Requests** 2.31.0 - Zuper API integration
- **Pandas** >= 2.0.0 - Data manipulation

## File Structure

```
├── streamlit_dashboard.py     # PRIMARY: Jobs validation dashboard (Streamlit)
├── streamlit_sync.py          # API sync module for Streamlit dashboard
├── sync_jobs_to_db.py         # Core job sync logic and validation rules
├── database_jobs_schema.sql   # Jobs database schema
│
├── dashboard.py               # SECONDARY: Organization monitoring (Flask)
├── sync_to_database.py        # Organization sync to database
├── database_schema.sql        # Organization database schema
├── templates/
│   ├── dashboard.html         # Flask organization dashboard template
│   └── jobs_dashboard.html    # Flask jobs dashboard template
│
├── .streamlit/
│   ├── config.toml            # Streamlit theme and server config
│   └── secrets.toml           # API credentials (gitignored)
│
├── .devcontainer/
│   └── devcontainer.json      # GitHub Codespaces/VS Code dev container
│
└── [Various utility scripts]  # Analysis and search utilities
```

## Databases

### Jobs Validation Database (`jobs_validation.db`)

**Tables:**
- `jobs` - Core job data (job_uid, job_number, job_title, organization, service_team, asset_name, has_line_items, has_netsuite_id)
- `job_line_items` - Parts/products used on jobs
- `job_checklist_parts` - Parts mentioned in job checklists
- `job_custom_fields` - Custom field data from Zuper
- `validation_flags` - Validation issues (missing_netsuite_id, parts_replaced_no_line_items)
- `organizations` - Organization lookup table
- `sync_log` - Sync operation history

**Key View:**
- `job_validation_summary` - Aggregated job data with flag counts

### Organization Database (`zuper_netsuite.db`)

**Tables:**
- `organizations` - Organization master data
- `organization_custom_fields` - Custom fields including NetSuite IDs
- `alerts` - Missing NetSuite ID alerts
- `sync_log` - Sync history

**Key View:**
- `netsuite_mapping` - Organizations with NetSuite ID status

## API Integration

### Zuper API

**Base URL**: `https://us-east-1.zuperpro.com`

**Authentication**: API key via `x-api-key` header

**Key Endpoints:**
- `GET /api/jobs` - List jobs (paginated with `page` and `count` params)
- `GET /api/jobs/{job_uid}` - Job details with assets
- `GET /api/organization` - List organizations
- `GET /api/organization/{org_uid}` - Organization details

**Credentials Location**: `.streamlit/secrets.toml` (gitignored)

```toml
[zuper]
api_key = "your_api_key"
base_url = "https://us-east-1.zuperpro.com"
```

## Validation Rules

Defined in `sync_jobs_to_db.py:validate_job()`:

1. **missing_netsuite_id** (error): Jobs with non-consumable line items but no NetSuite Sales Order ID
2. **parts_replaced_no_line_items** (error): Checklist shows parts replaced but no line items added

**Excluded from validation:**
- Consumable items (supplies, services)
- Preventive maintenance jobs (Reaper PM, Slayer PM)
- Parts request jobs

**Allowed Job Categories** (only these are synced):
- `LaserWeeder Service Call`
- `WM Service - In Field`
- `WM Repair - In Shop`

## Key Data Extraction Patterns

### Asset Extraction
```python
# From job['assets'][0]['asset']['asset_code'] or 'asset_name'
extract_asset_from_job(job)
```

### NetSuite ID Extraction
```python
# From job['custom_fields'] where label contains 'netsuite', 'sales order', etc.
extract_netsuite_id(job)
```

### Service Team Extraction
```python
# From job['job_status'][].done_by cross-referenced with job['assigned_to'][].team
# Falls back to job['assigned_to_team'][0].team.team_name
get_service_team(job)
```

### Serial Number Extraction

Serial patterns are defined in `SERIAL_PATTERNS` dict in `sync_jobs_to_db.py`. To add a new pattern, add an entry to the dictionary.

| Part # | Part Type | Pattern | Example |
|--------|-----------|---------|---------|
| 0000144 | Scanner Module | `CR-SM-NNNNNN[-RW]` | `CR-SM-000571-RW` |
| 0000508-C | Y150 Component | `CR-Y150-NNNNNN-R` | `CR-Y150-005032-R` |
| G4000 | MPC Component | `CR-MPC-NNNNN` | `CR-MPC-00278` |
| 0000612-B | SM Module | `SM-YYMMDD-NNN` | `SM-250721-002` |
| 0000675 | Weeding Module | `WM-YYMMDD-NNN` | `WM-250613-004` |

```python
extract_serial_from_text(text)  # Returns list of matched serial numbers
```

## Development Workflows

### Running the Streamlit Dashboard (Primary)

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API credentials
# Create .streamlit/secrets.toml with zuper.api_key and zuper.base_url

# Run dashboard
streamlit run streamlit_dashboard.py
```

Dashboard runs at `http://localhost:8501`

### Running the Flask Dashboard (Secondary)

```bash
# Sync organization data
python sync_to_database.py

# Start Flask server
python dashboard.py
```

Dashboard runs at `http://localhost:5001`

### Syncing Job Data

The Streamlit dashboard has a built-in "Refresh Data from API" button. For manual sync:

```bash
python sync_jobs_to_db.py  # Requires jobs_data.json to exist
```

### GitHub Codespaces

The `.devcontainer/devcontainer.json` is configured for Codespaces with auto-start of Streamlit on port 8501.

## Code Conventions

### Database Connections

Always use row factory for dict-like access:
```python
conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
```

### Error Handling

- API calls use retry logic with exponential backoff
- Database operations wrapped in try/except with fallback to empty results
- Progress callbacks for long-running operations

### Session State (Streamlit)

Filter state stored in `st.session_state`:
- `current_filter`, `current_page`
- `month_filter`, `org_filter`, `team_filter`, `asset_filter`
- `start_date`, `end_date`
- `job_number_search`, `part_search`

### Caching (Streamlit)

Use `@st.cache_data(ttl=60)` for database queries to reduce load.

## Common Tasks

### Adding a New Validation Rule

1. Edit `sync_jobs_to_db.py:validate_job()`
2. Add new flag_type to the flags list
3. Update dashboard to display the new flag type

### Adding a New Job Category to Sync

1. Edit `sync_jobs_to_db.py:sync_jobs_to_database()`
2. Add category to `allowed_categories` list

### Adding a New Filter to Dashboard

1. Add session state variable in `streamlit_dashboard.py`
2. Add UI element (selectbox, text_input, etc.)
3. Update `get_jobs()` function to handle the filter

### Modifying Database Schema

1. Edit `database_jobs_schema.sql` or `database_schema.sql`
2. Delete existing database file to recreate
3. Re-run sync to populate

## Zuper URL Patterns

- Job details: `https://web.zuperpro.com/jobs/{job_uid}/details`
- Organization: `https://web.zuperpro.com/organizations/{organization_uid}`

## Gitignored Files

- `.streamlit/secrets.toml` - API credentials
- `*.db`, `*.db-journal` - SQLite databases
- `jobs_data.json`, `organizations_data.json` - Raw API data
- `__pycache__/`, `*.pyc` - Python bytecode
- `check_*.py`, `analyze_*.py`, `test_*.py` - Test/analysis scripts

## Important Notes

1. **Always enrich jobs with asset data** - The list API doesn't return assets; must call individual job detail API
2. **Job categories are allowlisted** - Only specific categories are synced; others are skipped
3. **Consumables are excluded from validation** - Line items with "consumable", "supplies", or "service" in name/code are not flagged
4. **API rate limits** - The enrichment process handles 429 responses with retry-after headers
5. **Date filtering** - Uses `completed_at` with fallback to `created_at`
