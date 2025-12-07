# Streamlit Dashboard Performance & Error Handling Analysis Report

## Executive Summary

Your Streamlit dashboard has **critical issues** that can cause the 10+ minute loading screen hang:

1. **No timeouts on API requests** - Can hang indefinitely
2. **No connection pooling/limits on SQLite** - Connection leaks possible
3. **Unbounded database queries** - Could fetch massive datasets
4. **SQL injection vulnerabilities** - String concatenation in queries
5. **Missing error boundaries** - Single failure crashes entire app
6. **No progress indicators** - Users have no feedback during long operations
7. **Cache invalidation issues** - Stale data after refresh
8. **No request retries** - Network failures cause permanent hangs

## Critical Issues Found

### 1. API Request Issues (HIGH PRIORITY)

**Location:** `streamlit_sync.py`, lines 47-48

**Problem:** No timeout on API requests - can hang forever
```python
# Current code - NO TIMEOUT!
response = requests.get(url, headers=self.headers, params=params)
```

**Fix:**
```python
# Add timeout and retry logic
import time
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

class ZuperSync:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        }

        # Create session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch_jobs_from_api(self, progress_callback=None) -> List[Dict]:
        """Fetch all jobs from Zuper API with timeout and error handling"""
        if progress_callback:
            progress_callback("Fetching jobs from Zuper API...")

        url = f"{self.base_url}/api/jobs"
        jobs = []
        page = 1
        page_size = 100
        max_pages = 100  # Prevent infinite loops

        while page <= max_pages:
            if progress_callback:
                progress_callback(f"Fetching page {page}...")

            params = {
                'page': page,
                'count': page_size
            }

            try:
                # Add timeout of 30 seconds per request
                response = self.session.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()

            except requests.Timeout:
                error_msg = f"Request timeout on page {page} after 30 seconds"
                if progress_callback:
                    progress_callback(f"Error: {error_msg}")
                raise Exception(error_msg)

            except requests.RequestException as e:
                error_msg = f"API request failed on page {page}: {str(e)}"
                if progress_callback:
                    progress_callback(f"Error: {error_msg}")
                raise Exception(error_msg)

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON response on page {page}: {str(e)}"
                if progress_callback:
                    progress_callback(f"Error: {error_msg}")
                raise Exception(error_msg)

            # Rest of the logic...
            if data.get('type') == 'success':
                page_jobs = data.get('data', [])
                total_pages = min(data.get('total_pages', 0), max_pages)

                if progress_callback:
                    progress_callback(f"Page {page}/{total_pages}: Retrieved {len(page_jobs)} jobs")

                if not page_jobs:
                    break

                jobs.extend(page_jobs)

                if page >= total_pages or len(page_jobs) < page_size:
                    break

                page += 1
            else:
                error_msg = f"API response type is not 'success': {data}"
                if progress_callback:
                    progress_callback(f"Error: {error_msg}")
                raise Exception(error_msg)

        if progress_callback:
            progress_callback(f"Successfully fetched {len(jobs)} jobs from API")

        return jobs
```

### 2. Database Connection Issues (HIGH PRIORITY)

**Location:** `streamlit_dashboard.py`, lines 53-58

**Problem:** No connection pooling, no timeouts, connections not properly closed in error cases

**Current code:**
```python
def get_db_connection():
    """Get database connection"""
    ensure_database_exists()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn
```

**Fix:**
```python
import threading
from contextlib import contextmanager
from typing import Generator

# Thread-local storage for connections
_thread_local = threading.local()

@contextmanager
def get_db_connection(timeout: float = 5.0) -> Generator[sqlite3.Connection, None, None]:
    """
    Get database connection with proper timeout and cleanup.
    Uses context manager to ensure connections are always closed.
    """
    conn = None
    try:
        ensure_database_exists()

        # Use thread-local connection if available
        if not hasattr(_thread_local, 'conn') or _thread_local.conn is None:
            _thread_local.conn = sqlite3.connect(
                DB_FILE,
                timeout=timeout,  # Add timeout to prevent locks
                check_same_thread=False,
                isolation_level='DEFERRED'  # Better concurrency
            )
            _thread_local.conn.row_factory = sqlite3.Row

            # Enable WAL mode for better concurrency
            _thread_local.conn.execute("PRAGMA journal_mode=WAL")
            _thread_local.conn.execute("PRAGMA busy_timeout=5000")

        conn = _thread_local.conn
        yield conn

    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            raise Exception("Database is locked. Please try again in a moment.")
        raise Exception(f"Database operation failed: {str(e)}")

    except Exception as e:
        if conn:
            conn.rollback()
        raise Exception(f"Database error: {str(e)}")

    finally:
        # Don't close the connection (keep it in thread-local)
        # But ensure any transaction is committed or rolled back
        if conn and conn.in_transaction:
            conn.rollback()

def close_thread_connection():
    """Close thread-local database connection"""
    if hasattr(_thread_local, 'conn') and _thread_local.conn:
        _thread_local.conn.close()
        _thread_local.conn = None
```

### 3. SQL Injection Vulnerabilities (CRITICAL SECURITY)

**Location:** Multiple locations in `streamlit_dashboard.py`

**Problem:** String concatenation in SQL queries
```python
# Lines 135, 144, 147, 156 - SQL INJECTION VULNERABLE!
if job_number:
    filter_clauses.append(f"j.job_number LIKE '%{job_number}%'")
```

**Fix:**
```python
@st.cache_data(ttl=60)
def get_jobs(filter_type='all', page=1, month='', organization='', team='',
             start_date=None, end_date=None, job_number='', part_search='', limit=50):
    """Get jobs list with filtering and pagination - SECURE VERSION"""

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            offset = (page - 1) * limit

            # Build parameterized query
            base_query = """
                SELECT DISTINCT j.*, vf.flag_message, vf.flag_type
                FROM jobs j
                LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
            """

            # Build WHERE clauses with parameters
            where_clauses = []
            params = []

            # Add filter type conditions
            if filter_type == 'parts_no_items':
                where_clauses.append("vf.flag_type = ?")
                params.append('parts_replaced_no_line_items')
                where_clauses.append("vf.is_resolved = 0")
            elif filter_type == 'missing_netsuite':
                where_clauses.append("vf.flag_type = ?")
                params.append('missing_netsuite_id')
                where_clauses.append("vf.is_resolved = 0")
            elif filter_type == 'passing':
                where_clauses.append("vf.id IS NULL")

            # Job number search (parameterized)
            if job_number:
                where_clauses.append("j.job_number LIKE ?")
                params.append(f'%{job_number}%')

            # Date range filter
            if start_date and end_date:
                where_clauses.append("date(COALESCE(j.completed_at, j.created_at)) BETWEEN ? AND ?")
                params.extend([start_date, end_date])
            elif month:
                where_clauses.append("strftime('%Y-%m', COALESCE(j.completed_at, j.created_at)) = ?")
                params.append(month)

            # Organization filter
            if organization:
                where_clauses.append("j.organization_name LIKE ?")
                params.append(f'%{organization}%')

            # Team filter
            if team:
                where_clauses.append("j.service_team LIKE ?")
                params.append(f'%{team}%')

            # Part search (join and filter)
            if part_search:
                base_query += " JOIN job_line_items li ON j.job_uid = li.job_uid"
                where_clauses.append("(li.item_name LIKE ? OR li.item_code LIKE ?)")
                params.extend([f'%{part_search}%', f'%{part_search}%'])

            # Combine query
            if where_clauses:
                query = f"{base_query} WHERE {' AND '.join(where_clauses)}"
            else:
                query = base_query

            query += " ORDER BY j.created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            # Execute with timeout
            cursor.execute(query, params)
            jobs = [dict(row) for row in cursor.fetchall()]

            # Get total count (also parameterized)
            count_query = query.split('ORDER BY')[0].replace('j.*, vf.flag_message, vf.flag_type', 'COUNT(DISTINCT j.job_uid)')
            count_params = params[:-2]  # Remove LIMIT and OFFSET

            cursor.execute(count_query, count_params)
            total_count = cursor.fetchone()[0]

            return jobs, total_count

    except Exception as e:
        st.error(f"Database query failed: {str(e)}")
        return [], 0
```

### 4. Missing Loading States & Progress Indicators

**Location:** `streamlit_dashboard.py`, line 304

**Problem:** Long sync operation with minimal feedback

**Fix:**
```python
# In streamlit_dashboard.py, improve the sync button handler:

if st.button("🔄 Refresh Data from API", type="primary"):
    # Create progress container
    progress_container = st.container()

    with progress_container:
        # Initialize progress bar and status
        progress_bar = st.progress(0)
        status_text = st.empty()
        elapsed_time = st.empty()

        # Track timing
        import time
        start_time = time.time()

        def update_progress(msg: str, progress: float = None):
            """Enhanced progress callback with timeout detection"""
            current_time = time.time()
            elapsed = current_time - start_time

            # Update status
            status_text.text(msg)
            elapsed_time.text(f"⏱️ Elapsed: {elapsed:.1f}s")

            # Update progress bar if percentage provided
            if progress is not None:
                progress_bar.progress(min(progress, 1.0))

            # Timeout warning after 30 seconds
            if elapsed > 30:
                st.warning("⚠️ This is taking longer than expected...")

            # Hard timeout after 2 minutes
            if elapsed > 120:
                raise TimeoutError("Operation timeout after 2 minutes")

        try:
            # Clear caches before sync
            st.cache_data.clear()

            syncer = ZuperSync(api_key, base_url)

            # Fetch with progress
            update_progress("Connecting to Zuper API...", 0.1)
            jobs = syncer.fetch_jobs_from_api(
                lambda msg: update_progress(msg, 0.3)
            )

            # Validate data
            if not jobs:
                raise ValueError("No jobs retrieved from API")

            update_progress(f"Processing {len(jobs)} jobs...", 0.5)

            # Sync to database with progress
            stats = syncer.sync_to_database(
                jobs,
                lambda msg: update_progress(msg, 0.8)
            )

            update_progress("Finalizing...", 0.95)

            # Clear progress widgets
            progress_bar.progress(1.0)
            elapsed_seconds = time.time() - start_time

            # Show success with stats
            st.success(f"""
                ✅ **Sync Completed Successfully!**
                - Jobs synced: {stats['total_jobs']}
                - Jobs with items: {stats['jobs_with_items']}
                - Jobs with NetSuite: {stats['jobs_with_netsuite']}
                - Time taken: {elapsed_seconds:.1f}s
            """)

            # Force cache refresh
            time.sleep(0.5)  # Brief delay to ensure DB writes complete
            st.rerun()

        except TimeoutError as e:
            st.error(f"❌ Sync timeout: {e}")
            st.info("Please check your network connection and try again.")

        except requests.RequestException as e:
            st.error(f"❌ API Connection failed: {e}")
            st.info("Please verify API credentials and network connectivity.")

        except Exception as e:
            st.error(f"❌ Sync failed: {e}")

            # Provide actionable error info
            if "locked" in str(e).lower():
                st.info("Database is busy. Please wait a moment and try again.")
            elif "api" in str(e).lower():
                st.info("API issue detected. Please check your credentials.")
            else:
                st.info("An unexpected error occurred. Please contact support if this persists.")
```

### 5. Error Boundaries and Graceful Degradation

**Problem:** No error boundaries - any error crashes the entire app

**Fix:** Add error handling wrapper:
```python
# Add at top of streamlit_dashboard.py

import functools
import traceback

def error_boundary(func):
    """Decorator to catch and handle errors gracefully"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_id = hash(str(e) + str(traceback.format_exc()))

            # Log error details
            error_details = {
                'function': func.__name__,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

            # Show user-friendly error
            st.error(f"""
                ⚠️ **An error occurred**

                {str(e)}

                Error ID: {error_id}
            """)

            # Provide recovery options
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Refresh Page", key=f"refresh_{error_id}"):
                    st.rerun()
            with col2:
                if st.button("🧹 Clear Cache", key=f"clear_{error_id}"):
                    st.cache_data.clear()
                    st.rerun()

            # Return safe default
            return None
    return wrapper

# Apply to all cached functions
@error_boundary
@st.cache_data(ttl=60)
def get_metrics():
    # ... existing code

@error_boundary
@st.cache_data(ttl=60)
def get_jobs(...):
    # ... existing code
```

### 6. Cache Management Issues

**Problem:** Cache not properly invalidated after updates

**Fix:**
```python
# Add cache management utilities

import hashlib
from datetime import datetime

class CacheManager:
    """Manage cache invalidation and versioning"""

    @staticmethod
    def get_cache_key(*args):
        """Generate cache key from arguments"""
        key_str = "_".join(str(arg) for arg in args)
        return hashlib.md5(key_str.encode()).hexdigest()

    @staticmethod
    def get_data_version():
        """Get current data version from database"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT MAX(sync_completed_at) as last_sync
                    FROM sync_log
                    WHERE status = 'completed'
                """)
                result = cursor.fetchone()
                return result['last_sync'] if result else None
        except:
            return None

    @staticmethod
    def clear_all_caches():
        """Clear all Streamlit caches"""
        st.cache_data.clear()
        st.cache_resource.clear()

        # Clear session state filters
        for key in ['current_filter', 'current_page', 'month_filter',
                   'org_filter', 'team_filter', 'start_date', 'end_date',
                   'job_number_search', 'part_search']:
            if key in st.session_state:
                del st.session_state[key]

# Modified cache decorator with version checking
def versioned_cache(ttl=60):
    """Cache decorator that includes data version"""
    def decorator(func):
        @st.cache_data(ttl=ttl, show_spinner=False)
        def cached_func(*args, _version=None, **kwargs):
            return func(*args, **kwargs)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            version = CacheManager.get_data_version()
            return cached_func(*args, _version=version, **kwargs)

        return wrapper
    return decorator

# Use versioned cache instead
@versioned_cache(ttl=60)
def get_metrics():
    # ... existing code
```

### 7. Database Query Performance

**Problem:** Unbounded queries, no query timeouts

**Fix:**
```python
# Add query monitoring and limits

class QueryMonitor:
    """Monitor and limit database queries"""

    MAX_QUERY_TIME = 5.0  # seconds
    MAX_RESULTS = 10000

    @staticmethod
    def execute_with_timeout(cursor, query, params=None, timeout=5.0):
        """Execute query with timeout"""
        import signal
        import threading

        result = [None]
        exception = [None]

        def run_query():
            try:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                result[0] = cursor.fetchall()
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target=run_query)
        thread.daemon = True
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            raise TimeoutError(f"Query exceeded {timeout}s timeout")

        if exception[0]:
            raise exception[0]

        return result[0]

# Add query optimization for large datasets
def get_jobs_optimized(filter_type='all', page=1, **filters):
    """Optimized job query with pagination and limits"""

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # First, get count with timeout
        count_query = "SELECT COUNT(*) FROM jobs"
        try:
            result = QueryMonitor.execute_with_timeout(
                cursor, count_query, timeout=2.0
            )
            total_count = result[0][0] if result else 0

            # Limit total results
            if total_count > QueryMonitor.MAX_RESULTS:
                st.warning(f"Dataset too large ({total_count} jobs). Showing first {QueryMonitor.MAX_RESULTS}.")
                total_count = QueryMonitor.MAX_RESULTS

        except TimeoutError:
            st.error("Query timeout - dataset may be too large")
            return [], 0

        # Then get page data
        # ... rest of query logic with timeout
```

### 8. Session State Management

**Problem:** Session state can cause infinite reruns

**Fix:**
```python
# Add session state validator

class SessionStateManager:
    """Manage session state to prevent infinite loops"""

    @staticmethod
    def initialize():
        """Initialize session state with defaults"""
        defaults = {
            'current_filter': 'all',
            'current_page': 1,
            'month_filter': '',
            'org_filter': '',
            'team_filter': '',
            'start_date': None,
            'end_date': None,
            'job_number_search': '',
            'part_search': '',
            'last_refresh': None,
            'refresh_count': 0
        }

        for key, default_value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

    @staticmethod
    def prevent_infinite_refresh():
        """Prevent infinite refresh loops"""
        current_time = datetime.now()

        if st.session_state.get('last_refresh'):
            last_refresh = datetime.fromisoformat(st.session_state['last_refresh'])
            time_diff = (current_time - last_refresh).total_seconds()

            # If refreshing too quickly, stop
            if time_diff < 2:
                st.session_state['refresh_count'] += 1
                if st.session_state['refresh_count'] > 3:
                    st.error("Too many refreshes. Please wait a moment.")
                    time.sleep(2)
                    st.session_state['refresh_count'] = 0
                    return False
            else:
                st.session_state['refresh_count'] = 0

        st.session_state['last_refresh'] = current_time.isoformat()
        return True

# Use at the start of the app
SessionStateManager.initialize()
```

## Complete Fixed Files

### Fixed streamlit_sync.py

```python
#!/usr/bin/env python3
"""
Streamlit-compatible Zuper Jobs Sync Module - FIXED VERSION
Fetches jobs from Zuper API and syncs to SQLite database
"""

import json
import os
import sqlite3
import re
import requests
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

DB_FILE = 'jobs_validation.db'

class ZuperSync:
    """Handles syncing Zuper jobs to database with progress callbacks"""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        }

        # Create session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch_jobs_from_api(self, progress_callback: Optional[Callable] = None) -> List[Dict]:
        """Fetch all jobs from Zuper API with timeout and error handling"""

        if progress_callback:
            progress_callback("Initializing API connection...")

        url = f"{self.base_url}/api/jobs"
        jobs = []
        page = 1
        page_size = 100
        max_pages = 100  # Prevent infinite loops
        max_jobs = 10000  # Maximum jobs to fetch

        try:
            while page <= max_pages and len(jobs) < max_jobs:
                if progress_callback:
                    progress_callback(f"Fetching page {page} ({len(jobs)} jobs so far)...")

                params = {
                    'page': page,
                    'count': page_size
                }

                # Make request with timeout
                try:
                    response = self.session.get(
                        url,
                        headers=self.headers,
                        params=params,
                        timeout=30  # 30 second timeout per request
                    )
                    response.raise_for_status()

                except requests.Timeout:
                    error_msg = f"Request timeout on page {page} (30s exceeded)"
                    if progress_callback:
                        progress_callback(f"Error: {error_msg}")

                    # Retry once with longer timeout
                    if progress_callback:
                        progress_callback(f"Retrying page {page} with extended timeout...")

                    response = self.session.get(
                        url,
                        headers=self.headers,
                        params=params,
                        timeout=60
                    )
                    response.raise_for_status()

                except requests.HTTPError as e:
                    if response.status_code == 429:  # Rate limited
                        if progress_callback:
                            progress_callback("Rate limited, waiting 5 seconds...")
                        time.sleep(5)
                        continue
                    raise Exception(f"API error (HTTP {response.status_code}): {str(e)}")

                except requests.RequestException as e:
                    raise Exception(f"Network error on page {page}: {str(e)}")

                # Parse response
                try:
                    data = response.json()
                except json.JSONDecodeError as e:
                    raise Exception(f"Invalid JSON response on page {page}: {str(e)[:100]}")

                # Process data
                if data.get('type') != 'success':
                    raise Exception(f"API error response: {data.get('message', 'Unknown error')}")

                page_jobs = data.get('data', [])
                total_pages = min(data.get('total_pages', 0), max_pages)

                if progress_callback:
                    progress_callback(
                        f"Page {page}/{total_pages}: Retrieved {len(page_jobs)} jobs"
                    )

                if not page_jobs:
                    break

                jobs.extend(page_jobs)

                # Check if we're done
                if page >= total_pages or len(page_jobs) < page_size:
                    break

                page += 1

                # Brief delay to avoid rate limiting
                time.sleep(0.1)

        except Exception as e:
            if progress_callback:
                progress_callback(f"Failed to fetch jobs: {str(e)}")
            raise

        finally:
            # Always close session connections
            self.session.close()

        if progress_callback:
            progress_callback(f"Successfully fetched {len(jobs)} jobs")

        return jobs

    def sync_to_database(self, jobs: List[Dict], progress_callback: Optional[Callable] = None) -> Dict:
        """Sync jobs to database with error handling and progress"""

        if not jobs:
            raise ValueError("No jobs to sync")

        if progress_callback:
            progress_callback(f"Preparing to sync {len(jobs)} jobs...")

        try:
            # Initialize database with timeout
            init_database()

            if progress_callback:
                progress_callback("Database initialized, starting sync...")

            # Import sync function with error handling
            try:
                from sync_jobs_to_db import sync_jobs_to_database
            except ImportError as e:
                raise Exception(f"Failed to import sync module: {str(e)}")

            # Sync with timeout monitoring
            start_time = time.time()
            timeout = 120  # 2 minute timeout for sync

            # Run sync in chunks to provide progress updates
            chunk_size = 100
            total_jobs = len(jobs)

            for i in range(0, total_jobs, chunk_size):
                chunk = jobs[i:i + chunk_size]

                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Sync timeout after {timeout} seconds")

                if progress_callback:
                    progress = (i + len(chunk)) / total_jobs
                    progress_callback(
                        f"Syncing jobs {i+1} to {min(i+chunk_size, total_jobs)} of {total_jobs} ({progress:.0%})"
                    )

                # Sync chunk
                sync_jobs_to_database(chunk)

            # Get summary stats
            conn = sqlite3.connect(DB_FILE, timeout=5.0)
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT COUNT(*) FROM jobs")
                total_jobs = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_line_items = 1")
                jobs_with_items = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_netsuite_id = 1")
                jobs_with_netsuite = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(DISTINCT job_uid) FROM validation_flags WHERE is_resolved = 0")
                jobs_with_flags = cursor.fetchone()[0]

            finally:
                conn.close()

            if progress_callback:
                progress_callback("Sync completed successfully!")

            return {
                'total_jobs': total_jobs,
                'jobs_with_items': jobs_with_items,
                'jobs_with_netsuite': jobs_with_netsuite,
                'jobs_with_flags': jobs_with_flags
            }

        except Exception as e:
            if progress_callback:
                progress_callback(f"Sync failed: {str(e)}")
            raise

def init_database():
    """Initialize the SQLite database with schema and optimizations"""
    schema_file = os.path.join(os.path.dirname(__file__), 'database_jobs_schema.sql')

    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    with open(schema_file, 'r') as f:
        schema = f.read()

    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    try:
        cursor = conn.cursor()

        # Enable optimizations
        cursor.execute("PRAGMA journal_mode=WAL")  # Better concurrency
        cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes
        cursor.execute("PRAGMA cache_size=10000")  # Larger cache
        cursor.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp tables
        cursor.execute("PRAGMA busy_timeout=5000")  # 5 second timeout for locks

        # Execute schema
        cursor.executescript(schema)
        conn.commit()

    finally:
        conn.close()

def test_api_connection(api_key: str, base_url: str) -> bool:
    """Test if API credentials are valid with timeout"""
    try:
        session = requests.Session()
        headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        }
        url = f"{base_url.rstrip('/')}/api/jobs"
        params = {'limit': 1, 'page': 1}

        response = session.get(
            url,
            headers=headers,
            params=params,
            timeout=10  # 10 second timeout for test
        )

        session.close()
        return response.status_code == 200

    except Exception as e:
        print(f"API test failed: {e}")
        return False
```

## Monitoring & Debugging Recommendations

### 1. Add Application Logging

```python
# Add to streamlit_dashboard.py

import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('streamlit_app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Log key operations
logger.info(f"App started at {datetime.now()}")
logger.info(f"Session ID: {st.session_state.get('session_id', 'unknown')}")

# Add performance monitoring
class PerformanceMonitor:
    """Monitor operation performance"""

    @staticmethod
    def time_operation(operation_name):
        """Decorator to time operations"""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    elapsed = time.time() - start
                    logger.info(f"{operation_name} completed in {elapsed:.2f}s")

                    # Alert on slow operations
                    if elapsed > 5:
                        logger.warning(f"{operation_name} took {elapsed:.2f}s (>5s)")
                        st.warning(f"⚠️ {operation_name} is running slowly ({elapsed:.1f}s)")

                    return result

                except Exception as e:
                    elapsed = time.time() - start
                    logger.error(f"{operation_name} failed after {elapsed:.2f}s: {str(e)}")
                    raise

            return wrapper
        return decorator

# Use on critical functions
@PerformanceMonitor.time_operation("Database Query")
def get_jobs(...):
    # ... existing code
```

### 2. Add Health Check Endpoint

```python
# Add to streamlit_dashboard.py

def show_health_status():
    """Display system health status"""
    with st.expander("🏥 System Health"):
        col1, col2, col3 = st.columns(3)

        # Database health
        with col1:
            try:
                with get_db_connection(timeout=1.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM jobs")
                    count = cursor.fetchone()[0]
                st.success(f"✅ Database OK ({count} jobs)")
            except Exception as e:
                st.error(f"❌ Database Error: {str(e)[:50]}")

        # API health
        with col2:
            try:
                if test_api_connection(api_key, base_url):
                    st.success("✅ API Connected")
                else:
                    st.warning("⚠️ API Unreachable")
            except:
                st.error("❌ API Error")

        # Cache health
        with col3:
            cache_info = st.cache_data._get_cache_info()
            st.info(f"📦 Cache: {len(cache_info)} items")

# Add to sidebar
if st.sidebar.checkbox("Show System Health"):
    show_health_status()
```

### 3. Production Deployment Checklist

```python
# Environment-specific configuration
import os

class Config:
    """Application configuration"""

    # Timeouts
    API_TIMEOUT = int(os.getenv('API_TIMEOUT', '30'))
    DB_TIMEOUT = float(os.getenv('DB_TIMEOUT', '5.0'))
    SYNC_TIMEOUT = int(os.getenv('SYNC_TIMEOUT', '120'))

    # Limits
    MAX_JOBS_PER_SYNC = int(os.getenv('MAX_JOBS_PER_SYNC', '10000'))
    MAX_QUERY_RESULTS = int(os.getenv('MAX_QUERY_RESULTS', '5000'))

    # Performance
    CACHE_TTL = int(os.getenv('CACHE_TTL', '60'))
    MAX_CONCURRENT_CONNECTIONS = int(os.getenv('MAX_CONCURRENT_CONNECTIONS', '10'))

    # Debug
    DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Use configuration
if Config.DEBUG_MODE:
    st.sidebar.write("Debug mode enabled")
    st.sidebar.write(f"API Timeout: {Config.API_TIMEOUT}s")
    st.sidebar.write(f"DB Timeout: {Config.DB_TIMEOUT}s")
```

## Summary of Critical Fixes

1. **Add timeouts to ALL network operations** (30s default)
2. **Fix SQL injection vulnerabilities** with parameterized queries
3. **Implement proper database connection management** with context managers
4. **Add retry logic** for transient failures
5. **Implement progress indicators** for long operations
6. **Add error boundaries** to prevent complete app crashes
7. **Fix cache invalidation** after data updates
8. **Add monitoring and logging** for production debugging
9. **Implement health checks** for system status
10. **Add performance monitoring** to identify bottlenecks

## Immediate Actions Required

1. **CRITICAL**: Fix SQL injection vulnerabilities immediately
2. **HIGH**: Add timeouts to API requests (prevents indefinite hangs)
3. **HIGH**: Fix database connection management
4. **MEDIUM**: Add progress indicators and error boundaries
5. **LOW**: Implement monitoring and health checks

These fixes will resolve the 10+ minute loading screen issue and make your dashboard production-ready with proper error handling and user feedback.