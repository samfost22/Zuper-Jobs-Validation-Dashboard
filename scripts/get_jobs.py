#!/usr/bin/env python3
"""
Zuper API - Get All Jobs (Work Orders)
This script fetches all jobs/work orders from the Zuper API
"""

import requests
import json
import os
from datetime import datetime

# API Configuration
API_KEY = os.environ.get('ZUPER_API_KEY', '0c73f76f734550cab45861cfaa4939d8')
BASE_URL = os.environ.get('ZUPER_BASE_URL', 'https://us-east-1.zuperpro.com')

# Endpoint
JOBS_ENDPOINT = f"{BASE_URL}/api/jobs"

# Headers
headers = {
    'x-api-key': API_KEY,
    'Content-Type': 'application/json'
}

def get_all_jobs():
    """Fetch all jobs from Zuper API with pagination"""
    params = {
        'page': 1,
        'count': 100,
    }

    all_jobs = []
    current_page = 1

    print(f"Fetching jobs from: {JOBS_ENDPOINT}")
    print(f"Using API Key: {API_KEY[:10]}...")
    print("-" * 60)

    while True:
        params['page'] = current_page

        try:
            response = requests.get(
                JOBS_ENDPOINT,
                headers=headers,
                params=params
            )

            print(f"\nPage {current_page}: Status Code {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                if data.get('type') == 'success':
                    jobs = data.get('data', [])
                    total_records = data.get('total_records', 0)
                    total_pages = data.get('total_pages', 0)

                    print(f"Retrieved {len(jobs)} jobs")
                    print(f"Total records: {total_records}")
                    print(f"Total pages: {total_pages}")

                    all_jobs.extend(jobs)

                    # Check if there are more pages
                    if current_page >= total_pages or not jobs:
                        break

                    current_page += 1
                else:
                    print(f"Error: {data}")
                    break

            elif response.status_code == 401:
                print("Error: Unauthorized - Check your API key")
                print(f"Response: {response.text}")
                break

            elif response.status_code == 404:
                print("Error: Endpoint not found")
                print(f"Response: {response.text}")
                break

            else:
                print(f"Error: HTTP {response.status_code}")
                print(f"Response: {response.text}")
                break

        except Exception as e:
            print(f"Exception occurred: {str(e)}")
            break

    return all_jobs

def save_jobs_to_file(jobs, filename='jobs_data.json'):
    """Save jobs data to a JSON file"""
    filepath = os.path.join(os.path.dirname(__file__), filename)

    output = {
        'timestamp': datetime.now().isoformat(),
        'total_jobs': len(jobs),
        'jobs': jobs
    }

    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Jobs saved to: {filepath}")
    return filepath

def print_job_summary(jobs):
    """Print a summary of the jobs"""
    print("\n" + "=" * 60)
    print(f"JOBS SUMMARY")
    print("=" * 60)
    print(f"Total Jobs: {len(jobs)}")

    if jobs:
        print("\nFirst 5 Jobs:")
        print("-" * 60)

        for i, job in enumerate(jobs[:5], 1):
            print(f"\n{i}. Job #{job.get('job_number')}")
            print(f"   Job UID: {job.get('job_uid')}")
            print(f"   Title: {job.get('job_title')}")
            print(f"   Status: {job.get('job_status')}")
            print(f"   Customer: {job.get('customer_name')}")

            # Check for asset info
            if job.get('asset'):
                asset = job.get('asset')
                print(f"   Asset: {asset.get('asset_name') if isinstance(asset, dict) else asset}")

            # Check for serial number in custom fields or other fields
            if job.get('custom_fields'):
                for field in job.get('custom_fields', []):
                    if 'serial' in field.get('label', '').lower():
                        print(f"   {field.get('label')}: {field.get('value')}")

            print(f"   Created: {job.get('created_at')}")

    print("=" * 60)

def search_jobs_for_serials(jobs, serial_numbers):
    """Search jobs for serial numbers"""
    print("\n" + "=" * 60)
    print("SEARCHING JOBS FOR SERIAL NUMBERS")
    print("=" * 60)

    found_jobs = []

    for serial in serial_numbers:
        print(f"\nSearching for: {serial}")
        found_in_jobs = []

        for job in jobs:
            job_str = json.dumps(job).lower()

            if serial.lower() in job_str:
                found_in_jobs.append(job)
                print(f"  ✓ Found in Job #{job.get('job_number')}: {job.get('job_title')}")

                # Show where it was found
                for key, value in job.items():
                    if isinstance(value, str) and serial.lower() in value.lower():
                        print(f"    - Found in field '{key}': {value}")
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                item_str = json.dumps(item).lower()
                                if serial.lower() in item_str:
                                    print(f"    - Found in {key}: {item}")

        if found_in_jobs:
            found_jobs.extend(found_in_jobs)
        else:
            print(f"  ✗ Not found in any jobs")

    return found_jobs

if __name__ == "__main__":
    print("ZUPER API - GET ALL JOBS (WORK ORDERS)")
    print("=" * 60)

    # Fetch jobs
    jobs = get_all_jobs()

    if jobs:
        # Print summary
        print_job_summary(jobs)

        # Save to file
        save_jobs_to_file(jobs)

        # Search for specific serial numbers
        serial_numbers = [
            "CR-SM-00282",
            "CR-SM-003349",
            "CR-SM-003549",
            "CR-SM-003560",
            "CR-SM-003584",
            "CR-SM-003587",
            "CR-SM-003605",
            "CR-SM-003609",
            "CR-SM-003615",
            "CR-SM-003641",
            "CR-SM-003666",
            "CR-SM-003669",
            "CR-SM-003673",
            "CR-SM-003685",
            "CR-SM-003806",
            "CR-SM-003865",
            "CR-SM-003868",
            "CR-SM-004088",
            "CR-SM-004111"
        ]

        found_jobs = search_jobs_for_serials(jobs, serial_numbers)

        if found_jobs:
            # Save found jobs
            output = {
                'timestamp': datetime.now().isoformat(),
                'serial_numbers_searched': serial_numbers,
                'jobs_with_serials': found_jobs
            }

            with open('jobs_with_serials.json', 'w') as f:
                json.dump(output, f, indent=2)

            print(f"\n✓ Jobs containing serial numbers saved to: jobs_with_serials.json")

        print("\n✓ Script completed successfully")
    else:
        print("\n✗ No jobs retrieved or an error occurred")
