"""
Centralized configuration for Zuper Jobs Validation Dashboard.

All constants, paths, and settings should be defined here.
"""

from pathlib import Path

# Base paths
ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)

# Database files
JOBS_DB_FILE = str(DATA_DIR / 'jobs_validation.db')
ORGS_DB_FILE = str(ROOT_DIR / 'zuper_netsuite.db')

# Database settings
DB_TIMEOUT = 30.0  # seconds

# API settings
DEFAULT_API_BASE_URL = "https://us-east-1.zuperpro.com"
API_TIMEOUT = 30  # seconds
API_MAX_RETRIES = 3
API_PAGE_SIZE = 100

# Sync settings
DEFAULT_BATCH_SIZE = 150
DEFAULT_MAX_WORKERS = 20

# Cache settings (TTL in seconds)
CACHE_TTL_SHORT = 60      # For frequently changing data (metrics)
CACHE_TTL_MEDIUM = 300    # For filter options
CACHE_TTL_LONG = 600      # For rarely changing data

# Pagination
JOBS_PER_PAGE = 50

# Allowed job categories for sync
ALLOWED_JOB_CATEGORIES = [
    'LaserWeeder Service Call',
    'WM Service - In Field',
    'WM Repair - In Shop'
]

# Job categories to skip validation
SKIP_VALIDATION_CATEGORIES = [
    'field requires parts',
    'reaper pm',
    'slayer pm',
]

# Consumable terms (items with these terms don't need NetSuite tracking)
CONSUMABLE_TERMS = ['consumable', 'consumables', 'supplies', 'service']

# Serial number pattern
SERIAL_PATTERN = r'CR-SM-\d{5,6}(?:-RW)?'

# URL patterns
ZUPER_JOB_URL_TEMPLATE = "https://web.zuperpro.com/jobs/{job_uid}/details"
ZUPER_ORG_URL_TEMPLATE = "https://web.zuperpro.com/organizations/{org_uid}"

# Default session state values
DEFAULT_SESSION_STATE = {
    'current_filter': 'all',
    'current_page': 1,
    'month_filter': '',
    'org_filter': '',
    'team_filter': '',
    'start_date': None,
    'end_date': None,
    'job_number_search': '',
    'part_search': '',
    'serial_search': '',
    'asset_filter': ''
}
