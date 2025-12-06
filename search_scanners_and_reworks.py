#!/usr/bin/env python3
"""
Search Zuper jobs for specific scanner serials and rework information
"""

import json
import os
from datetime import datetime
from collections import defaultdict

# Scanner serial numbers to search
SCANNER_SERIALS = [
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

def load_jobs():
    """Load jobs data"""
    filepath = os.path.join(os.path.dirname(__file__), 'jobs_data.json')

    if not os.path.exists(filepath):
        print("Error: jobs_data.json not found. Run get_jobs.py first.")
        return None

    with open(filepath, 'r') as f:
        data = json.load(f)

    return data.get('jobs', [])

def search_serial_in_text(text, serial):
    """Check if serial appears in text"""
    if not text:
        return False
    return serial.lower() in str(text).lower()

def extract_scanner_info_from_job(job, serial):
    """Extract detailed scanner information from a job"""
    info = {
        'job_uid': job.get('job_uid'),
        'job_title': job.get('job_title'),
        'job_number': job.get('job_number'),
        'job_status': None,
        'customer_name': job.get('customer_name'),
        'created_at': job.get('created_at'),
        'updated_at': job.get('updated_at'),
        'asset_info': None,
        'scanner_position': None,
        'checklist_data': [],
        'is_rework': False,
        'rework_info': []
    }

    # Check job title for rework indicators
    title = job.get('job_title', '').lower()
    if any(word in title for word in ['rework', 'replace', 'repair', 'fix', 'issue']):
        info['is_rework'] = True
        info['rework_info'].append(f"Title indicates rework/repair: {job.get('job_title')}")

    # Get current status
    job_status_list = job.get('job_status', [])
    if job_status_list and isinstance(job_status_list, list):
        current_status = job_status_list[0]
        info['job_status'] = current_status.get('status_name')

        # Check checklist for serial
        checklist = current_status.get('checklist', [])
        for item in checklist:
            answer = item.get('answer', '')
            question = item.get('question', '')

            if search_serial_in_text(answer, serial):
                info['scanner_position'] = question
                info['checklist_data'].append({
                    'position': question,
                    'serial': answer,
                    'updated_at': item.get('updated_at')
                })

    # Check asset information
    asset = job.get('asset')
    if asset:
        if isinstance(asset, dict):
            info['asset_info'] = {
                'asset_name': asset.get('asset_name'),
                'asset_uid': asset.get('asset_uid')
            }
        else:
            info['asset_info'] = {'asset_name': str(asset)}

    # Check description for rework indicators
    description = job.get('job_description', '')
    if any(word in description.lower() for word in ['rework', 'replace', 'warranty', 'defect', 'return']):
        info['is_rework'] = True
        info['rework_info'].append(f"Description mentions rework: {description[:100]}")

    # Check custom fields for rework info
    for field in job.get('custom_fields', []):
        label = field.get('label', '').lower()
        value = field.get('value', '')

        if 'rework' in label or 'warranty' in label or 'return' in label:
            info['is_rework'] = True
            info['rework_info'].append(f"{field.get('label')}: {value}")

    return info

def search_scanners_in_jobs(jobs, serials):
    """Search for scanner serials in all jobs"""

    results = {
        'found': defaultdict(list),
        'not_found': [],
        'rework_jobs': [],
        'scanner_history': defaultdict(list)
    }

    print("=" * 80)
    print("SEARCHING FOR SCANNER SERIALS IN JOBS")
    print("=" * 80)

    # Search each serial
    for serial in serials:
        print(f"\nSearching for: {serial}")
        found = False

        for job in jobs:
            job_str = json.dumps(job).lower()

            if serial.lower() in job_str:
                found = True
                job_info = extract_scanner_info_from_job(job, serial)
                results['found'][serial].append(job_info)
                results['scanner_history'][serial].append({
                    'job_title': job.get('job_title'),
                    'date': job.get('created_at'),
                    'position': job_info['scanner_position']
                })

                if job_info['is_rework']:
                    results['rework_jobs'].append({
                        'serial': serial,
                        'job': job_info
                    })

                print(f"  ✓ Found in: {job.get('job_title')}")
                if job_info['scanner_position']:
                    print(f"    Position: {job_info['scanner_position']}")
                if job_info['is_rework']:
                    print(f"    ⚠️  REWORK/REPAIR JOB")
                if job_info['asset_info']:
                    print(f"    Machine: {job_info['asset_info']}")

        if not found:
            results['not_found'].append(serial)
            print(f"  ✗ Not found in any jobs")

    return results

def print_detailed_results(results):
    """Print detailed analysis of results"""

    print("\n" + "=" * 80)
    print("DETAILED SCANNER ANALYSIS")
    print("=" * 80)

    # Summary
    print(f"\nScanner Serials Found: {len(results['found'])}")
    print(f"Scanner Serials Not Found: {len(results['not_found'])}")
    print(f"Rework/Repair Jobs: {len(results['rework_jobs'])}")

    # Detailed findings for each serial
    for serial, jobs in results['found'].items():
        print(f"\n{'-' * 80}")
        print(f"SERIAL: {serial}")
        print(f"{'-' * 80}")
        print(f"Total Jobs: {len(jobs)}")

        # Show all jobs for this serial
        for i, job_info in enumerate(jobs, 1):
            print(f"\n  Job {i}: {job_info['job_title']}")
            print(f"    Job UID: {job_info['job_uid']}")
            print(f"    Status: {job_info['job_status']}")
            print(f"    Created: {job_info['created_at']}")

            if job_info['scanner_position']:
                print(f"    Scanner Position: {job_info['scanner_position']}")

            if job_info['asset_info']:
                print(f"    Machine: {job_info['asset_info']['asset_name']}")

            if job_info['is_rework']:
                print(f"    ⚠️  REWORK/REPAIR JOB")
                for rework_detail in job_info['rework_info']:
                    print(f"      - {rework_detail}")

    # Rework summary
    if results['rework_jobs']:
        print(f"\n{'=' * 80}")
        print("REWORK/REPAIR JOBS SUMMARY")
        print(f"{'=' * 80}")

        for item in results['rework_jobs']:
            serial = item['serial']
            job = item['job']
            print(f"\nSerial: {serial}")
            print(f"  Job: {job['job_title']}")
            print(f"  Created: {job['created_at']}")
            print(f"  Rework Details:")
            for detail in job['rework_info']:
                print(f"    - {detail}")

    # Not found
    if results['not_found']:
        print(f"\n{'=' * 80}")
        print("SERIALS NOT FOUND IN JOBS")
        print(f"{'=' * 80}")
        for serial in results['not_found']:
            print(f"  • {serial}")

def save_results(results, filename='scanner_search_results.json'):
    """Save results to JSON file"""
    filepath = os.path.join(os.path.dirname(__file__), filename)

    # Convert defaultdict to regular dict for JSON serialization
    output = {
        'timestamp': datetime.now().isoformat(),
        'serials_searched': SCANNER_SERIALS,
        'found': {k: v for k, v in results['found'].items()},
        'not_found': results['not_found'],
        'rework_jobs': results['rework_jobs'],
        'scanner_history': {k: v for k, v in results['scanner_history'].items()},
        'summary': {
            'total_searched': len(SCANNER_SERIALS),
            'found_count': len(results['found']),
            'not_found_count': len(results['not_found']),
            'rework_count': len(results['rework_jobs'])
        }
    }

    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Results saved to: {filepath}")

def create_csv_report(results, filename='scanner_analysis.csv'):
    """Create CSV report of scanner findings"""
    import csv
    filepath = os.path.join(os.path.dirname(__file__), filename)

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'Serial Number',
            'Job Title',
            'Job UID',
            'Status',
            'Scanner Position',
            'Machine/Asset',
            'Is Rework',
            'Created Date',
            'Rework Details'
        ])

        # Data
        for serial, jobs in results['found'].items():
            for job in jobs:
                writer.writerow([
                    serial,
                    job['job_title'],
                    job['job_uid'],
                    job['job_status'],
                    job['scanner_position'] or '',
                    job['asset_info']['asset_name'] if job['asset_info'] else '',
                    'YES' if job['is_rework'] else 'NO',
                    job['created_at'],
                    '; '.join(job['rework_info']) if job['rework_info'] else ''
                ])

        # Add not found
        for serial in results['not_found']:
            writer.writerow([
                serial,
                'NOT FOUND',
                '', '', '', '', '', '', ''
            ])

    print(f"✓ CSV report saved to: {filepath}")

if __name__ == "__main__":
    print("ZUPER SCANNER SERIAL & REWORK ANALYSIS")
    print("=" * 80)

    # Load jobs
    jobs = load_jobs()

    if not jobs:
        print("Error: No jobs data available")
        exit(1)

    print(f"Loaded {len(jobs)} jobs")

    # Search for scanners
    results = search_scanners_in_jobs(jobs, SCANNER_SERIALS)

    # Print detailed results
    print_detailed_results(results)

    # Save results
    save_results(results)
    create_csv_report(results)

    print("\n✓ Analysis complete!")
