#!/usr/bin/env python3
"""
Streamlit-compatible Zuper Jobs Sync Module
Fetches jobs from Zuper API and syncs to SQLite database
"""

import json
import os
import sqlite3
import re
import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from config import (
    JOBS_DB_FILE as DB_FILE,
    DATA_DIR,
    ROOT_DIR,
    API_TIMEOUT,
    API_MAX_RETRIES,
    API_PAGE_SIZE,
    DEFAULT_MAX_WORKERS,
    DEFAULT_BATCH_SIZE,
)

class ZuperSync:
    """Handles syncing Zuper jobs to database with progress callbacks"""
    
    def __init__(self, api_key: str, base_url: str, max_workers: int = 20):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        }
        self.max_workers = max_workers

        # Create a session for connection pooling (reuses TCP connections)
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Configure connection pool size to match max workers
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=max_workers,
            pool_maxsize=max_workers,
            max_retries=0  # We handle retries manually
        )
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
    
    def fetch_jobs_from_api(self, progress_callback=None) -> List[Dict]:
        """Fetch all jobs from Zuper API with robust error handling"""
        if progress_callback:
            progress_callback("🔄 Fetching jobs from Zuper API...")

        url = f"{self.base_url}/api/jobs"
        jobs = []
        page = 1
        page_size = 100
        max_retries = 3
        retry_count = 0

        while True:
            if progress_callback:
                progress_callback(f"📄 Fetching page {page}... ({len(jobs)} jobs fetched so far)")

            params = {
                'page': page,
                'count': page_size
            }

            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                retry_count = 0  # Reset retry count on success

            except requests.exceptions.Timeout:
                retry_count += 1
                if retry_count < max_retries:
                    if progress_callback:
                        progress_callback(f"⚠️ Request timeout on page {page}. Retry {retry_count}/{max_retries}...")
                    time.sleep(2)  # Wait before retry
                    continue
                else:
                    error_msg = f"❌ Failed to fetch page {page} after {max_retries} retries (timeout)"
                    if progress_callback:
                        progress_callback(error_msg)
                    raise Exception(error_msg)

            except requests.exceptions.HTTPError as e:
                error_msg = f"❌ HTTP error on page {page}: {e.response.status_code} - {str(e)}"
                if progress_callback:
                    progress_callback(error_msg)
                raise Exception(error_msg)

            except requests.exceptions.RequestException as e:
                error_msg = f"❌ Network error on page {page}: {str(e)}"
                if progress_callback:
                    progress_callback(error_msg)
                raise Exception(error_msg)

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                error_msg = f"❌ Invalid JSON response on page {page}: {str(e)}"
                if progress_callback:
                    progress_callback(error_msg)
                raise Exception(error_msg)

            # Check response structure
            if data.get('type') == 'success':
                page_jobs = data.get('data', [])  # Changed from 'jobs' to 'data'
                total_pages = data.get('total_pages', 0)

                if progress_callback:
                    progress_callback(f"Page {page}: Retrieved {len(page_jobs)} jobs (Total pages: {total_pages})")

                if not page_jobs:
                    break

                jobs.extend(page_jobs)

                # Check if there are more pages
                if page >= total_pages or len(page_jobs) < page_size:
                    break

                page += 1
            else:
                if progress_callback:
                    progress_callback(f"Error: API response type is not 'success': {data}")
                break

        if progress_callback:
            progress_callback(f"Fetched {len(jobs)} jobs from API")

        return jobs

    def fetch_updated_jobs_only(self, progress_callback=None) -> List[Dict]:
        """
        Fetch only jobs that have been updated since last sync (differential sync)
        Compares job updated_at timestamps with database synced_at timestamps
        """
        if progress_callback:
            progress_callback("🔍 Checking for updated jobs...")

        # Get last sync time from database
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(synced_at) FROM jobs")
            result = cursor.fetchone()
            last_sync = result[0] if result and result[0] else None
            conn.close()

            if last_sync:
                if progress_callback:
                    progress_callback(f"Last sync: {last_sync}")
        except:
            last_sync = None

        # Fetch all jobs from API
        all_jobs = self.fetch_jobs_from_api(progress_callback)

        if not last_sync:
            # First sync - return all jobs
            if progress_callback:
                progress_callback(f"First sync - processing all {len(all_jobs)} jobs")
            return all_jobs

        # Filter to only jobs updated after last sync
        updated_jobs = []
        for job in all_jobs:
            job_updated = job.get('updated_at') or job.get('created_at')
            if job_updated and job_updated > last_sync:
                updated_jobs.append(job)

        if progress_callback:
            progress_callback(f"Found {len(updated_jobs)} updated jobs (out of {len(all_jobs)} total)")

        return updated_jobs

    def fetch_job_details(self, job_uid: str, max_retries: int = 3) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Fetch detailed job information including assets with retry logic

        Returns:
            Tuple[Optional[Dict], Optional[str]]: (job_data, error_message)
        """
        url = f"{self.base_url}/api/jobs/{job_uid}"

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30)

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                data = response.json()

                if data.get('type') == 'success':
                    return data.get('data', {}), None
                else:
                    return None, f"API returned non-success: {data.get('type')}"

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    continue
                return None, "Timeout after 3 retries"

            except requests.exceptions.HTTPError as e:
                if e.response.status_code >= 500 and attempt < max_retries - 1:
                    # Server error - retry
                    time.sleep(2 ** attempt)
                    continue
                return None, f"HTTP {e.response.status_code}: {str(e)}"

            except requests.exceptions.RequestException as e:
                return None, f"Request failed: {str(e)}"
            except Exception as e:
                return None, f"Unexpected error: {str(e)}"

        return None, "Max retries exceeded"

    def enrich_jobs_with_assets(self, jobs: List[Dict], progress_callback=None) -> List[Dict]:
        """
        Fetch full job details for each job using parallel requests.

        Replaces partial job data from list API with complete data from detail API,
        including assets, line_items, checklists, custom_fields, and all other fields.

        Uses ThreadPoolExecutor for concurrent API calls, dramatically improving performance.
        Includes robust error handling, retry logic, and detailed progress tracking.
        """
        if progress_callback:
            progress_callback(f"🚀 Fetching full job details ({self.max_workers} parallel workers)...")

        total = len(jobs)
        if total == 0:
            return jobs

        # Thread-safe counters and results storage
        completed_count = 0
        error_count = 0
        timeout_count = 0
        rate_limit_count = 0
        counter_lock = threading.Lock()
        errors_by_type = {}

        # Store enriched jobs by index to maintain order
        enriched_jobs = [None] * total
        job_uid_to_index = {job.get('job_uid'): idx for idx, job in enumerate(jobs)}

        start_time = time.time()

        def fetch_full_details(job_uid: str) -> Tuple[str, Optional[Dict], Optional[str]]:
            """Fetch complete job details and return (job_uid, full_job_data, error)"""
            job_details, error = self.fetch_job_details(job_uid)

            if error:
                return job_uid, None, error
            elif job_details:
                return job_uid, job_details, None
            else:
                return job_uid, None, "Empty response"

        # Submit all jobs to the thread pool
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all fetch tasks
            future_to_uid = {
                executor.submit(fetch_full_details, job.get('job_uid')): job.get('job_uid')
                for job in jobs
            }

            # Process results as they complete
            for future in as_completed(future_to_uid):
                job_uid = future_to_uid[future]
                idx = job_uid_to_index.get(job_uid)

                try:
                    uid, full_job_data, error = future.result()

                    with counter_lock:
                        completed_count += 1

                        if error:
                            error_count += 1
                            error_type = error.split(':')[0] if ':' in error else error
                            errors_by_type[error_type] = errors_by_type.get(error_type, 0) + 1

                            if 'Timeout' in error:
                                timeout_count += 1
                            elif '429' in error or 'rate limit' in error.lower():
                                rate_limit_count += 1

                            # On error, keep original job data from list API
                            if idx is not None:
                                enriched_jobs[idx] = jobs[idx]
                                enriched_jobs[idx]['assets'] = []  # Ensure assets field exists
                        else:
                            # Use full job data from detail API
                            if idx is not None:
                                enriched_jobs[idx] = full_job_data

                        # Progress update every 100 jobs
                        if progress_callback and completed_count % 100 == 0:
                            elapsed = time.time() - start_time
                            rate = completed_count / elapsed if elapsed > 0 else 0
                            remaining = (total - completed_count) / rate if rate > 0 else 0
                            eta_secs = int(remaining)

                            if eta_secs >= 60:
                                eta_str = f"{eta_secs // 60}m {eta_secs % 60}s"
                            else:
                                eta_str = f"{eta_secs}s"

                            progress_msg = (
                                f"Fetching details: {completed_count}/{total} ({int(completed_count/total * 100)}%) | "
                                f"Rate: {rate:.1f} jobs/sec | ETA: {eta_str}"
                            )
                            if error_count > 0:
                                progress_msg += f" | Errors: {error_count}"

                            progress_callback(progress_msg)

                except Exception as e:
                    with counter_lock:
                        completed_count += 1
                        error_count += 1
                        # On exception, keep original job data
                        if idx is not None:
                            enriched_jobs[idx] = jobs[idx]
                            enriched_jobs[idx]['assets'] = []

        # Final summary
        if progress_callback:
            jobs_with_assets = sum(1 for j in enriched_jobs if j and j.get('assets'))
            elapsed = time.time() - start_time

            if elapsed >= 60:
                elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
            else:
                elapsed_str = f"{elapsed:.1f}s"

            summary = (
                f"✓ Fetched {total} job details in {elapsed_str} | "
                f"{jobs_with_assets} have assets"
            )

            if error_count > 0:
                summary += f" | ⚠️ {error_count} errors ("
                if timeout_count > 0:
                    summary += f"{timeout_count} timeouts"
                if rate_limit_count > 0:
                    summary += f", {rate_limit_count} rate limits" if timeout_count > 0 else f"{rate_limit_count} rate limits"
                summary += ")"

            progress_callback(summary)

            # Log error details if significant
            if error_count > total * 0.05:  # More than 5% errors
                error_details = ", ".join([f"{k}: {v}" for k, v in errors_by_type.items()])
                progress_callback(f"⚠️ Error breakdown: {error_details}")

        return enriched_jobs

    def sync_jobs_in_batches(self, jobs: List[Dict], batch_size: int = 150, progress_callback=None) -> Dict:
        """
        Sync jobs to database in batches with asset enrichment
        This avoids timeout by processing smaller chunks at a time
        """
        if progress_callback:
            progress_callback("🔧 Initializing database...")

        init_database()

        total_jobs = len(jobs)
        total_synced = 0

        if progress_callback:
            progress_callback(f"📦 Processing {total_jobs} jobs in batches of {batch_size}...")

        # Process jobs in batches
        for batch_start in range(0, total_jobs, batch_size):
            batch_end = min(batch_start + batch_size, total_jobs)
            batch = jobs[batch_start:batch_end]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (total_jobs + batch_size - 1) // batch_size

            if progress_callback:
                progress_callback(f"🔄 Batch {batch_num}/{total_batches}: Enriching {len(batch)} jobs with assets...")

            # Enrich this batch with assets
            enriched_batch = self.enrich_jobs_with_assets(batch, progress_callback)

            if progress_callback:
                progress_callback(f"💾 Batch {batch_num}/{total_batches}: Saving to database...")

            # Sync this batch to database
            from sync_jobs_to_db import sync_jobs_to_database
            try:
                sync_jobs_to_database(enriched_batch)
                total_synced += len(enriched_batch)

                if progress_callback:
                    progress_callback(f"✅ Batch {batch_num}/{total_batches} complete ({total_synced}/{total_jobs} total)")

            except Exception as e:
                error_msg = f"❌ Error syncing batch {batch_num}: {str(e)}"
                if progress_callback:
                    progress_callback(error_msg)
                # Continue with next batch instead of failing completely
                continue

        # Get final stats
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM jobs")
            total_jobs_in_db = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_line_items = 1")
            jobs_with_items = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_netsuite_id = 1")
            jobs_with_netsuite = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT job_uid) FROM validation_flags WHERE is_resolved = 0")
            jobs_with_flags = cursor.fetchone()[0]

            conn.close()

            if progress_callback:
                progress_callback(f"✅ Sync complete! Processed {total_synced} jobs")

            return {
                'total_jobs': total_jobs_in_db,
                'jobs_with_items': jobs_with_items,
                'jobs_with_netsuite': jobs_with_netsuite,
                'jobs_with_flags': jobs_with_flags
            }

        except sqlite3.Error as e:
            error_msg = f"❌ Error getting final stats: {str(e)}"
            if progress_callback:
                progress_callback(error_msg)
            raise Exception(error_msg)

    def sync_to_database(self, jobs: List[Dict], progress_callback=None) -> Dict:
        """Sync jobs to database with robust error handling"""
        try:
            if progress_callback:
                progress_callback("🔧 Initializing database...")

            init_database()

            if progress_callback:
                progress_callback(f"💾 Syncing {len(jobs)} jobs to database...")

            from sync_jobs_to_db import sync_jobs_to_database

            # Use existing sync function with error handling
            try:
                sync_jobs_to_database(jobs)
            except Exception as e:
                error_msg = f"❌ Database sync error: {str(e)}"
                if progress_callback:
                    progress_callback(error_msg)
                raise Exception(error_msg)

            # Get summary stats with error handling
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM jobs")
                total_jobs = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_line_items = 1")
                jobs_with_items = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_netsuite_id = 1")
                jobs_with_netsuite = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(DISTINCT job_uid) FROM validation_flags WHERE is_resolved = 0")
                jobs_with_flags = cursor.fetchone()[0]

                conn.close()

                if progress_callback:
                    progress_callback("✅ Sync complete!")

                return {
                    'total_jobs': total_jobs,
                    'jobs_with_items': jobs_with_items,
                    'jobs_with_netsuite': jobs_with_netsuite,
                    'jobs_with_flags': jobs_with_flags
                }

            except sqlite3.Error as e:
                error_msg = f"❌ Database error: {str(e)}"
                if progress_callback:
                    progress_callback(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            # Catch-all for any other errors
            error_msg = f"❌ Unexpected sync error: {str(e)}"
            if progress_callback:
                progress_callback(error_msg)
            raise


def init_database():
    """Initialize the SQLite database with schema"""
    schema_file = os.path.join(os.path.dirname(__file__), 'database_jobs_schema.sql')
    
    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    
    with open(schema_file, 'r') as f:
        schema = f.read()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.executescript(schema)
    conn.commit()
    conn.close()


def test_api_connection(api_key: str, base_url: str) -> bool:
    """Test if API credentials are valid"""
    try:
        headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        }
        url = f"{base_url.rstrip('/')}/api/jobs?limit=1"
        response = requests.get(url, headers=headers, timeout=10)
        return response.status_code == 200
    except requests.exceptions.Timeout:
        print(f"API test failed: Connection timeout after 10 seconds")
        return False
    except Exception as e:
        print(f"API test failed: {e}")
        return False

