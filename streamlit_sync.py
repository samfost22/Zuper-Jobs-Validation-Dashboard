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
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Use persistent data directory
DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(exist_ok=True)
DB_FILE = str(DATA_DIR / 'jobs_validation.db')

class ZuperSync:
    """Handles syncing Zuper jobs to database with progress callbacks"""
    
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        }
    
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
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
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
                response = requests.get(url, headers=self.headers, timeout=30)

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
        Enrich job list with asset data from individual job details

        Includes robust error handling, retry logic, and detailed progress tracking
        """
        if progress_callback:
            progress_callback(f"🔍 Enriching {len(jobs)} jobs with asset data...")

        enriched_jobs = []
        total = len(jobs)

        # Error tracking
        error_count = 0
        timeout_count = 0
        rate_limit_count = 0
        errors_by_type = {}

        start_time = time.time()

        for idx, job in enumerate(jobs):
            job_uid = job.get('job_uid')

            # Progress update every 100 jobs with stats
            if progress_callback and (idx + 1) % 100 == 0:
                elapsed = time.time() - start_time
                rate = (idx + 1) / elapsed if elapsed > 0 else 0
                remaining = (total - idx - 1) / rate if rate > 0 else 0
                eta_mins = int(remaining / 60)

                progress_msg = (
                    f"Enriching: {idx + 1}/{total} ({int((idx + 1)/total * 100)}%) | "
                    f"Rate: {rate:.1f} jobs/sec | ETA: {eta_mins} min"
                )
                if error_count > 0:
                    progress_msg += f" | Errors: {error_count}"

                progress_callback(progress_msg)

            # Fetch job details with error handling
            job_details, error = self.fetch_job_details(job_uid)

            if error:
                error_count += 1
                # Track error types
                error_type = error.split(':')[0] if ':' in error else error
                errors_by_type[error_type] = errors_by_type.get(error_type, 0) + 1

                if 'Timeout' in error:
                    timeout_count += 1
                elif '429' in error or 'rate limit' in error.lower():
                    rate_limit_count += 1

                # Add empty assets on error
                job['assets'] = []
            elif job_details and 'assets' in job_details:
                # Successfully got assets
                job['assets'] = job_details.get('assets', [])
            else:
                # No error but no assets either
                job['assets'] = []

            enriched_jobs.append(job)

        # Final summary
        if progress_callback:
            jobs_with_assets = sum(1 for j in enriched_jobs if j.get('assets'))
            elapsed_mins = int((time.time() - start_time) / 60)

            summary = (
                f"✓ Enriched {total} jobs in {elapsed_mins} minutes | "
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

