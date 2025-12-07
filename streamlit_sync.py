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
from datetime import datetime
from typing import Dict, List, Optional

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
    
    def fetch_jobs_from_api(self, progress_callback=None) -> List[Dict]:
        """Fetch all jobs from Zuper API"""
        if progress_callback:
            progress_callback("Fetching jobs from Zuper API...")

        url = f"{self.base_url}/api/jobs"
        jobs = []
        page = 1
        page_size = 100

        while True:
            if progress_callback:
                progress_callback(f"Fetching page {page}...")

            params = {
                'page': page,
                'count': page_size  # Changed from 'limit' to 'count' to match working script
            }

            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                response.raise_for_status()
            except requests.exceptions.Timeout:
                if progress_callback:
                    progress_callback(f"⚠️ Request timeout on page {page}. Retrying...")
                continue  # Retry the same page
            except requests.exceptions.RequestException as e:
                if progress_callback:
                    progress_callback(f"❌ API error on page {page}: {str(e)}")
                break  # Stop fetching on error

            data = response.json()

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

    def fetch_job_details(self, job_uid: str) -> Optional[Dict]:
        """Fetch detailed job information including assets"""
        url = f"{self.base_url}/api/jobs/{job_uid}"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get('type') == 'success':
                return data.get('data', {})
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.RequestException:
            return None

        return None

    def enrich_jobs_with_assets(self, jobs: List[Dict], progress_callback=None) -> List[Dict]:
        """Enrich job list with asset data from individual job details"""
        if progress_callback:
            progress_callback(f"Enriching {len(jobs)} jobs with asset data...")

        enriched_jobs = []
        total = len(jobs)

        for idx, job in enumerate(jobs):
            job_uid = job.get('job_uid')

            # Progress update every 100 jobs
            if progress_callback and (idx + 1) % 100 == 0:
                progress_callback(f"Enriching jobs: {idx + 1}/{total} ({int((idx + 1)/total * 100)}%)")

            # Fetch job details
            job_details = self.fetch_job_details(job_uid)

            if job_details and 'assets' in job_details:
                # Add assets array to the job
                job['assets'] = job_details.get('assets', [])
            else:
                # No assets found
                job['assets'] = []

            enriched_jobs.append(job)

        if progress_callback:
            jobs_with_assets = sum(1 for j in enriched_jobs if j.get('assets'))
            progress_callback(f"✓ Enriched {total} jobs ({jobs_with_assets} have assets)")

        return enriched_jobs

    def sync_to_database(self, jobs: List[Dict], progress_callback=None) -> Dict:
        """Sync jobs to database and return stats"""
        if progress_callback:
            progress_callback("Initializing database...")
        
        init_database()
        
        if progress_callback:
            progress_callback(f"Syncing {len(jobs)} jobs to database...")
        
        from sync_jobs_to_db import (
            sync_jobs_to_database,
            extract_line_items,
            extract_checklist_parts,
            extract_netsuite_id
        )
        
        # Use existing sync function
        sync_jobs_to_database(jobs)
        
        # Get summary stats
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
            progress_callback("Sync complete!")
        
        return {
            'total_jobs': total_jobs,
            'jobs_with_items': jobs_with_items,
            'jobs_with_netsuite': jobs_with_netsuite,
            'jobs_with_flags': jobs_with_flags
        }


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

