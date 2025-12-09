#!/usr/bin/env python3
"""
Scheduled Sync Script for GitHub Actions
Runs automated syncs on a schedule to keep job data fresh

Usage:
  python scheduled_sync.py --mode incremental  # Quick sync of recent jobs
  python scheduled_sync.py --mode full         # Full refresh of all jobs

Environment variables required:
  ZUPER_API_KEY - Zuper API key
  ZUPER_BASE_URL - Zuper API base URL (optional, defaults to us-east-1)
  SLACK_WEBHOOK_URL - Zapier/Slack webhook for notifications
"""

import os
import sys
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from streamlit_sync import ZuperSync, init_database
from sync_jobs_to_db import sync_jobs_to_database


def log(message):
    """Print timestamped log message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def run_sync(mode: str = "incremental"):
    """
    Run a sync of job data from Zuper API

    Args:
        mode: "incremental" for recent jobs only, "full" for all jobs
    """
    # Get credentials from environment
    api_key = os.environ.get("ZUPER_API_KEY")
    base_url = os.environ.get("ZUPER_BASE_URL", "https://us-east-1.zuperpro.com")
    slack_webhook = os.environ.get("SLACK_WEBHOOK_URL", "")

    if not api_key:
        log("ERROR: ZUPER_API_KEY environment variable not set")
        sys.exit(1)

    log(f"Starting {mode.upper()} sync...")
    log(f"API Base URL: {base_url}")
    log(f"Slack notifications: {'enabled' if slack_webhook else 'disabled'}")

    # Initialize
    init_database()
    syncer = ZuperSync(api_key=api_key, base_url=base_url, max_workers=20)

    # Fetch jobs
    if mode == "incremental":
        log("Fetching recently updated jobs...")
        jobs = syncer.fetch_updated_jobs_only(progress_callback=log)
    else:
        log("Fetching ALL jobs (full refresh)...")
        jobs = syncer.fetch_jobs_from_api(progress_callback=log)

    if not jobs:
        log("No jobs to sync")
        return

    log(f"Found {len(jobs)} jobs to process")

    # Enrich with asset details
    log("Enriching jobs with asset details...")
    enriched_jobs = syncer.enrich_jobs_with_assets(jobs, progress_callback=log)

    # Sync to database with notifications
    log("Syncing to database...")
    sync_jobs_to_database(enriched_jobs, slack_webhook_url=slack_webhook)

    log(f"Sync complete! Processed {len(enriched_jobs)} jobs")


def main():
    parser = argparse.ArgumentParser(description="Scheduled Zuper Jobs Sync")
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="Sync mode: 'incremental' for recent jobs, 'full' for all jobs"
    )

    args = parser.parse_args()

    try:
        run_sync(mode=args.mode)
    except Exception as e:
        log(f"ERROR: Sync failed - {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
