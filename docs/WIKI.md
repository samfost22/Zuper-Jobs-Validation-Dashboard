# Zuper Jobs Validation Dashboard - Wiki

> **Internal monitoring and validation dashboard for tracking Zuper field service jobs and their NetSuite integration**

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Getting Started](#getting-started)
4. [Primary Dashboard (Streamlit)](#primary-dashboard-streamlit)
5. [Secondary Dashboard (Flask)](#secondary-dashboard-flask)
6. [Database Schemas](#database-schemas)
7. [Validation Rules](#validation-rules)
8. [API Integration](#api-integration)
9. [Data Extraction](#data-extraction)
10. [Configuration](#configuration)
11. [Troubleshooting](#troubleshooting)

---

## Overview

### What is this application?

This is an internal monitoring system that ensures **field service jobs with parts/line items have corresponding NetSuite Sales Order IDs** for proper billing and inventory tracking.

### Why does it exist?

When technicians perform service calls and replace parts on equipment, those parts need to be:
1. Recorded as line items on the job in Zuper
2. Linked to a NetSuite Sales Order for billing

If this link is missing, the company may fail to invoice customers for parts used. This dashboard identifies those gaps.

### Key Use Cases

| Use Case | Description |
|----------|-------------|
| **Missing NetSuite IDs** | Find jobs with parts but no Sales Order ID |
| **Parts Without Line Items** | Find jobs where checklists show parts replaced but no items were added |
| **Organization Coverage** | Track which customers have NetSuite Customer IDs configured |
| **Service Team Performance** | Filter jobs by team to review data quality |

---

## Architecture

### Dual Dashboard Design

The system has two independent dashboards:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Zuper Jobs Validation System                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐ │
│  │   PRIMARY DASHBOARD     │    │   SECONDARY DASHBOARD       │ │
│  │   (Streamlit)           │    │   (Flask)                   │ │
│  ├─────────────────────────┤    ├─────────────────────────────┤ │
│  │ • Job Validation        │    │ • Organization Monitoring   │ │
│  │ • Line Item Tracking    │    │ • NetSuite ID Coverage      │ │
│  │ • Part Search           │    │ • Alerts Management         │ │
│  │ • Serial Number Search  │    │                             │ │
│  │                         │    │                             │ │
│  │ Port: 8501              │    │ Port: 5001                  │ │
│  │ DB: jobs_validation.db  │    │ DB: zuper_netsuite.db       │ │
│  └─────────────────────────┘    └─────────────────────────────┘ │
│                                                                  │
│                    ┌───────────────────┐                        │
│                    │    Zuper API      │                        │
│                    │  (Data Source)    │                        │
│                    └───────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.11+ |
| Primary UI | Streamlit | >= 1.28.0 |
| Secondary UI | Flask | 3.0.0 |
| Database | SQLite | Built-in |
| Data Processing | Pandas | >= 2.0.0 |
| HTTP Client | Requests | 2.31.0 |

### File Structure

```
Zuper-Jobs-Validation-Dashboard/
├── 📊 Primary Dashboard
│   ├── streamlit_dashboard.py    # Main dashboard application
│   ├── streamlit_sync.py         # API sync module
│   ├── sync_jobs_to_db.py        # Core sync logic & validation
│   └── database_jobs_schema.sql  # Database schema
│
├── 📈 Secondary Dashboard
│   ├── dashboard.py              # Flask application
│   ├── sync_to_database.py       # Organization sync
│   ├── database_schema.sql       # Organization schema
│   └── templates/
│       └── dashboard.html        # Flask template
│
├── ⚙️ Configuration
│   ├── .streamlit/
│   │   ├── config.toml           # Theme & server settings
│   │   └── secrets.toml          # API credentials (gitignored)
│   └── .devcontainer/
│       └── devcontainer.json     # GitHub Codespaces config
│
├── 🛠️ Utility Scripts
│   ├── get_jobs.py               # Fetch jobs from API
│   ├── search_serials.py         # Search by serial number
│   └── [other utilities]
│
├── 📚 Documentation
│   ├── README.md                 # User guide
│   ├── CLAUDE.md                 # AI assistant guide
│   ├── DEPLOYMENT_GUIDE.md       # Deployment instructions
│   └── docs/
│       └── WIKI.md               # This file
│
└── 📦 Data (Generated)
    ├── data/jobs_validation.db   # Jobs database
    └── zuper_netsuite.db         # Organizations database
```

---

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Zuper API credentials (API key)
- Git (for version control)

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/Zuper-Jobs-Validation-Dashboard.git
   cd Zuper-Jobs-Validation-Dashboard
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure API credentials**

   Create `.streamlit/secrets.toml`:
   ```toml
   [zuper]
   api_key = "your_api_key_here"
   base_url = "https://us-east-1.zuperpro.com"
   ```

4. **Run the dashboard**
   ```bash
   streamlit run streamlit_dashboard.py
   ```

5. **Access the dashboard**

   Open `http://localhost:8501` in your browser

### GitHub Codespaces

The project includes `.devcontainer/devcontainer.json` for seamless GitHub Codespaces setup:

1. Open repository in GitHub
2. Click "Code" → "Codespaces" → "Create codespace"
3. Dashboard auto-starts on port 8501

---

## Primary Dashboard (Streamlit)

### Dashboard Layout

```
┌────────────────────────────────────────────────────────────────────┐
│  🔄 Sync Data    📊 Zuper Jobs Validation Dashboard                │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────┐  ┌───────────┐ │
│  │  Total   │  │   Missing    │  │ Parts w/o      │  │  Passing  │ │
│  │  Jobs    │  │  NetSuite    │  │ Line Items     │  │   Jobs    │ │
│  │   248    │  │     12       │  │      5         │  │    231    │ │
│  └──────────┘  └──────────────┘  └────────────────┘  └───────────┘ │
│                                                                     │
│  Filters:                                                          │
│  ┌─────────────┬──────────────┬───────────────┬──────────────────┐ │
│  │ Job Number  │ Part Search  │ Serial Search │ Date Range       │ │
│  ├─────────────┼──────────────┼───────────────┼──────────────────┤ │
│  │ Month       │ Organization │ Service Team  │ Asset            │ │
│  └─────────────┴──────────────┴───────────────┴──────────────────┘ │
│                                                                     │
│  Jobs Table:                                                        │
│  ┌─────────┬────────────────┬───────────┬─────────┬──────────────┐ │
│  │ Status  │ Job            │ Customer  │ Asset   │ Actions      │ │
│  ├─────────┼────────────────┼───────────┼─────────┼──────────────┤ │
│  │ 🔴      │ JOB-12345      │ Acme Inc  │ S38     │ View | ✓     │ │
│  │ ✅      │ JOB-12346      │ Beta Co   │ S42     │ View         │ │
│  └─────────┴────────────────┴───────────┴─────────┴──────────────┘ │
│                                                                     │
│  ◄ Previous  Page 1 of 5  Next ►                                   │
└────────────────────────────────────────────────────────────────────┘
```

### Metric Cards

| Card | Description | Click Action |
|------|-------------|--------------|
| **Total Jobs** | All synced jobs in database | Show all jobs |
| **Missing NetSuite** | Jobs with parts but no SO ID | Filter to these jobs |
| **Parts w/o Line Items** | Checklist shows parts, no items | Filter to these jobs |
| **Passing** | Jobs with no validation issues | Filter to passing jobs |

### Filtering Options

#### Text Searches
- **Job Number**: Partial match on job number (e.g., "12345")
- **Part Name/Code**: Search line items by name or product code
- **Serial Number**: Search for equipment serials (e.g., "CR-SM-12345")

#### Dropdown Filters
- **Month**: Select one or more months (2025-01 through 2025-12)
- **Organization**: Filter by customer organization
- **Service Team**: Filter by assigned team
- **Asset**: Filter by equipment code (shows job count per asset)

#### Date Range
- **Start Date / End Date**: Custom date range (overrides month filter)

### Sync Button Features

The smart sync button adapts to database state:

| Scenario | Behavior |
|----------|----------|
| Empty database | Performs full sync automatically |
| Has data | Performs differential sync (only updated jobs) |
| Advanced → Quick Sync | Force differential sync |
| Advanced → Full Sync | Force complete re-sync |

### Progress Reporting

During sync, you'll see:
```
Syncing jobs... 150/248 (60%)
Rate: 2.5 jobs/sec | ETA: ~40 seconds
Errors: 0 timeouts, 0 rate limits
```

---

## Secondary Dashboard (Flask)

### Purpose

Track organization-level NetSuite integration status:
- Which organizations have NetSuite Customer IDs?
- Which are missing and need attention?
- Alert management for data quality issues

### Running the Flask Dashboard

```bash
# First, sync organization data
python sync_to_database.py

# Then start the server
python dashboard.py
```

Access at `http://localhost:5001`

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard (requires basic auth) |
| `/api/stats` | GET | KPI metrics |
| `/api/organizations` | GET | Organization list |
| `/api/alerts` | GET | Alert list |
| `/api/alerts/<id>/resolve` | POST | Resolve an alert |
| `/api/export/csv` | GET | Download CSV export |

---

## Database Schemas

### Jobs Database (`jobs_validation.db`)

#### Core Tables

**`jobs`** - Primary job records
```sql
job_uid          TEXT PRIMARY KEY,
job_number       TEXT,
job_title        TEXT,
job_status       TEXT,
job_category     TEXT,
customer_name    TEXT,
organization_uid TEXT,
organization_name TEXT,
service_team     TEXT,
asset_name       TEXT,
created_at       TEXT,
updated_at       TEXT,
completed_at     TEXT,
has_line_items   INTEGER,      -- Boolean: 0 or 1
has_checklist_parts INTEGER,   -- Boolean: 0 or 1
has_netsuite_id  INTEGER,      -- Boolean: 0 or 1
netsuite_sales_order_id TEXT,
synced_at        TEXT
```

**`job_line_items`** - Parts/products used on jobs
```sql
id          INTEGER PRIMARY KEY,
job_uid     TEXT,
item_name   TEXT,
item_code   TEXT,
item_serial TEXT,          -- Comma-separated if multiple
quantity    REAL,
price       REAL,
line_item_type TEXT,
created_at  TEXT
```

**`job_checklist_parts`** - Parts mentioned in checklists
```sql
id                 INTEGER PRIMARY KEY,
job_uid            TEXT,
checklist_question TEXT,
part_serial        TEXT,   -- e.g., "CR-SM-12345"
part_description   TEXT,
status_name        TEXT,
position           TEXT,
updated_at         TEXT
```

**`validation_flags`** - Quality control issues
```sql
id            INTEGER PRIMARY KEY,
job_uid       TEXT,
flag_type     TEXT,    -- 'missing_netsuite_id' or 'parts_replaced_no_line_items'
flag_severity TEXT,    -- 'error' or 'warning'
flag_message  TEXT,
details       TEXT,    -- JSON with additional info
created_at    TEXT,
is_resolved   INTEGER, -- Boolean: 0 or 1
resolved_at   TEXT
```

#### Entity Relationship

```
┌─────────────┐     ┌──────────────────┐     ┌────────────────────┐
│    jobs     │────<│  job_line_items  │     │  validation_flags  │
│             │     └──────────────────┘     │                    │
│  (1)        │                              │                    │
│             │────<│job_checklist_parts│────│  (many per job)    │
│             │     └──────────────────┘     └────────────────────┘
│             │
│             │────<│ job_custom_fields │
└─────────────┘     └──────────────────┘
```

### Organizations Database (`zuper_netsuite.db`)

**`organizations`** - Organization master data
```sql
organization_uid   TEXT PRIMARY KEY,
organization_name  TEXT,
organization_email TEXT,
no_of_customers    INTEGER,
is_active          INTEGER,
created_at         TEXT,
updated_at         TEXT,
synced_at          TEXT
```

**`organization_custom_fields`** - Custom fields including NetSuite IDs
```sql
id                INTEGER PRIMARY KEY,
organization_uid  TEXT,
field_label       TEXT,
field_value       TEXT,
field_type        TEXT
```

---

## Validation Rules

### Rule 1: Missing NetSuite ID

**Condition**: Job has non-consumable line items BUT no NetSuite Sales Order ID

```python
if has_line_items and not has_netsuite_id:
    if any_non_consumable_items:
        flag = "missing_netsuite_id"
```

**Consumables Excluded** (these don't trigger flags):
- Items containing: "consumable", "supplies", "service"

**Flag Details**:
- Type: `missing_netsuite_id`
- Severity: `error`
- Message: `"Job has N non-consumable line item(s) but missing NetSuite Sales Order ID"`

### Rule 2: Parts Replaced Without Line Items

**Condition**: Checklist shows parts replaced (serial numbers) BUT no line items added

```python
if has_checklist_parts and not has_line_items:
    flag = "parts_replaced_no_line_items"
```

**Serial Number Pattern**: `CR-SM-XXXXX` or `CR-SM-XXXXX-RW`

**Flag Details**:
- Type: `parts_replaced_no_line_items`
- Severity: `error`
- Message: `"Checklist shows N part(s) replaced but no line items added"`

### Skip Categories (No Validation)

These job categories bypass validation entirely:
- `field requires parts` (parts request jobs)
- `reaper pm` (preventive maintenance)
- `slayer pm` (preventive maintenance)

### Allowed Categories (Only These Sync)

Only these job types are synced and validated:
- `LaserWeeder Service Call`
- `WM Service - In Field`
- `WM Repair - In Shop`

---

## API Integration

### Zuper API

**Base URL**: `https://us-east-1.zuperpro.com`

**Authentication**:
```
Header: x-api-key: {your_api_key}
Content-Type: application/json
```

### Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /api/jobs?page=N&count=100` | List jobs (paginated) |
| `GET /api/jobs/{job_uid}` | Job details with assets |
| `GET /api/organization` | List organizations |
| `GET /api/organization/{org_uid}` | Organization details |

### Error Handling

The sync module includes robust error handling:

| Error Type | Handling |
|------------|----------|
| Timeout | Retry with exponential backoff (1s, 2s, 4s) |
| Rate Limit (429) | Wait for Retry-After header duration |
| Server Error (5xx) | Retry up to 3 times |
| Request Error | Log and skip, continue with next job |

### Zuper Web URLs

Direct links to Zuper platform:
- **Job Details**: `https://web.zuperpro.com/jobs/{job_uid}/details`
- **Organization**: `https://web.zuperpro.com/organizations/{organization_uid}`

---

## Data Extraction

### Key Extraction Functions

Located in `sync_jobs_to_db.py`:

| Function | Source | Output |
|----------|--------|--------|
| `extract_asset_from_job(job)` | `job.assets[0].asset.asset_code` | Asset code (e.g., "S38") |
| `extract_netsuite_id(job)` | `job.custom_fields[]` where label contains "netsuite" | Sales Order ID |
| `extract_line_items(job)` | `job.products[]` | List of line item dicts |
| `extract_checklist_parts(job)` | `job.job_status[].checklist[]` | List of parts with serials |
| `get_service_team(job)` | `job.assigned_to_team` or inferred from status | Team name |
| `get_completion_date(job)` | First COMPLETED/CLOSED status | Timestamp |

### Serial Number Pattern

```regex
CR-SM-\d{5,6}(?:-RW)?
```

Matches:
- `CR-SM-12345`
- `CR-SM-123456`
- `CR-SM-12345-RW` (rework units)

---

## Configuration

### Streamlit Theme (`.streamlit/config.toml`)

```toml
[theme]
primaryColor = "#4299e1"              # Blue accent
backgroundColor = "#ffffff"           # White background
secondaryBackgroundColor = "#f7fafc"  # Light gray sidebars
textColor = "#2d3748"                 # Dark gray text
font = "sans serif"

[server]
headless = true
port = 8501

[browser]
gatherUsageStats = false              # Disable telemetry
```

### API Credentials (`.streamlit/secrets.toml`)

**This file is gitignored - you must create it locally**

```toml
[zuper]
api_key = "your_api_key_here"
base_url = "https://us-east-1.zuperpro.com"
```

### Environment Variables

For production deployments, you can also use environment variables:

```bash
export ZUPER_API_KEY="your_api_key"
export ZUPER_BASE_URL="https://us-east-1.zuperpro.com"
```

---

## Troubleshooting

### Common Issues

#### "No data to display"
1. Click the sync button to fetch data from Zuper
2. Check API credentials in `.streamlit/secrets.toml`
3. Verify network connectivity

#### "Sync is slow"
- Full sync fetches all jobs and enriches each with asset data
- Use "Quick Sync" for differential updates after initial sync
- Expect ~2-3 jobs/second due to API rate limits

#### "Database locked"
1. Stop all running dashboard instances
2. Delete the `.db-journal` file if present
3. Restart the dashboard

#### "Missing secrets.toml"
Create the file:
```bash
mkdir -p .streamlit
cat > .streamlit/secrets.toml << 'EOF'
[zuper]
api_key = "your_api_key_here"
base_url = "https://us-east-1.zuperpro.com"
EOF
```

#### "Port already in use"
```bash
# Find process using port 8501
lsof -i :8501

# Kill the process
kill -9 <PID>
```

### Resetting the Database

To start fresh:
```bash
rm data/jobs_validation.db
# Then run sync from the dashboard
```

### Viewing Logs

Streamlit logs appear in the terminal where you ran `streamlit run`.

For more verbose output:
```bash
streamlit run streamlit_dashboard.py --logger.level=debug
```

---

## Glossary

| Term | Definition |
|------|------------|
| **Job** | A field service work order in Zuper |
| **Line Item** | A part or product added to a job |
| **Checklist** | Questions/answers technicians complete during job |
| **NetSuite SO ID** | Sales Order ID linking job to billing system |
| **Consumable** | Parts not tracked for billing (supplies, services) |
| **Asset** | Equipment being serviced (identified by code like "S38") |
| **Validation Flag** | A data quality issue detected by the system |

---

## Additional Resources

- [README.md](../README.md) - Quick start guide
- [CLAUDE.md](../CLAUDE.md) - Detailed technical reference for AI assistants
- [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) - Production deployment instructions
- [STREAMLIT_DEPLOYMENT.md](../STREAMLIT_DEPLOYMENT.md) - Streamlit Cloud deployment

---

*Last updated: December 2024*
