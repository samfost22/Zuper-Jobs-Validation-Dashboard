#!/usr/bin/env python3
"""
Search for RMA/Returned Scanners - including -RW variants
"""

import json
import os
from datetime import datetime
from collections import defaultdict

# Original scanner serial numbers
ORIGINAL_SERIALS = [
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

# Generate -RW variants
RW_VARIANTS = [s + "-RW" for s in ORIGINAL_SERIALS]
ALL_SERIALS = ORIGINAL_SERIALS + RW_VARIANTS

def load_jobs():
    """Load jobs data"""
    filepath = os.path.join(os.path.dirname(__file__), 'jobs_data.json')

    if not os.path.exists(filepath):
        print("Error: jobs_data.json not found")
        return None

    with open(filepath, 'r') as f:
        data = json.load(f)

    return data.get('jobs', [])

def search_rma_scanners(jobs):
    """Search for RMA scanners including -RW variants"""

    results = {
        'original_found': {},
        'rw_found': {},
        'removal_jobs': [],
        'installation_jobs': [],
        'rework_jobs': [],
        'all_matches': []
    }

    print("=" * 80)
    print("SEARCHING FOR RMA SCANNERS (INCLUDING -RW VARIANTS)")
    print("=" * 80)

    # Search for all variants
    for serial in ORIGINAL_SERIALS:
        serial_lower = serial.lower()
        rw_serial = serial + "-RW"
        rw_serial_lower = rw_serial.lower()

        original_jobs = []
        rw_jobs = []

        print(f"\nSearching for: {serial} and {rw_serial}")

        for job in jobs:
            job_str = json.dumps(job).lower()
            job_title = job.get('job_title', '').lower()

            # Check for original serial
            if serial_lower in job_str:
                original_jobs.append(job)

                # Classify job type
                if any(word in job_title for word in ['remove', 'replace', 'repair', 'return']):
                    results['removal_jobs'].append({
                        'serial': serial,
                        'job_uid': job.get('job_uid'),
                        'job_title': job.get('job_title'),
                        'created_at': job.get('created_at'),
                        'type': 'removal/replacement'
                    })
                    print(f"  🔴 REMOVAL/REPLACEMENT: {job.get('job_title')}")

                elif 'install' in job_title or 'new' in job_title:
                    results['installation_jobs'].append({
                        'serial': serial,
                        'job_uid': job.get('job_uid'),
                        'job_title': job.get('job_title'),
                        'created_at': job.get('created_at'),
                        'type': 'installation'
                    })
                    print(f"  🟢 INSTALLATION: {job.get('job_title')}")

                elif 'audit' in job_title:
                    print(f"  📋 AUDIT: {job.get('job_title')}")
                else:
                    print(f"  ℹ️  OTHER: {job.get('job_title')}")

            # Check for -RW variant
            if rw_serial_lower in job_str:
                rw_jobs.append(job)
                results['rework_jobs'].append({
                    'serial': serial,
                    'rw_serial': rw_serial,
                    'job_uid': job.get('job_uid'),
                    'job_title': job.get('job_title'),
                    'created_at': job.get('created_at')
                })
                print(f"  ⚠️  FOUND -RW VARIANT: {job.get('job_title')}")

        if original_jobs:
            results['original_found'][serial] = original_jobs

        if rw_jobs:
            results['rw_found'][rw_serial] = rw_jobs

        if not original_jobs and not rw_jobs:
            print(f"  ✗ Not found in any form")

    return results

def analyze_rma_timeline(results):
    """Analyze the timeline of removals and reworks"""

    print("\n" + "=" * 80)
    print("RMA SCANNER TIMELINE ANALYSIS")
    print("=" * 80)

    # Group by serial
    scanner_timeline = defaultdict(lambda: {
        'removals': [],
        'reworks': [],
        'audits': []
    })

    for item in results['removal_jobs']:
        scanner_timeline[item['serial']]['removals'].append(item)

    for item in results['rework_jobs']:
        scanner_timeline[item['serial']]['reworks'].append(item)

    # Print timeline for each scanner
    for serial in ORIGINAL_SERIALS:
        timeline = scanner_timeline[serial]

        if timeline['removals'] or timeline['reworks']:
            print(f"\n{'-' * 80}")
            print(f"SCANNER: {serial}")
            print(f"{'-' * 80}")

            # Removals
            if timeline['removals']:
                print(f"\n  🔴 REMOVED FROM FIELD ({len(timeline['removals'])} time(s)):")
                for removal in sorted(timeline['removals'], key=lambda x: x['created_at']):
                    print(f"    {removal['created_at'][:10]} - {removal['job_title']}")

            # Reworks
            if timeline['reworks']:
                print(f"\n  ⚠️  REWORKED ({len(timeline['reworks'])} time(s)):")
                for rework in sorted(timeline['reworks'], key=lambda x: x['created_at']):
                    print(f"    {rework['created_at'][:10]} - {rework['job_title']}")
                    print(f"       Using: {rework['rw_serial']}")

            # Conclusion
            if timeline['removals'] and timeline['reworks']:
                print(f"\n  ✅ RMA FLOW: Scanner removed → reworked → ready for redeployment")
            elif timeline['removals'] and not timeline['reworks']:
                print(f"\n  ⏳ STATUS: Scanner removed, rework pending or not tracked in Zuper")
            elif timeline['reworks'] and not timeline['removals']:
                print(f"\n  ℹ️  STATUS: Rework recorded, removal may be in different job")

def print_summary(results):
    """Print summary statistics"""

    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)

    print(f"\nOriginal Serials Found: {len(results['original_found'])}")
    print(f"-RW Variant Serials Found: {len(results['rw_found'])}")
    print(f"Removal/Replacement Jobs: {len(results['removal_jobs'])}")
    print(f"Installation Jobs: {len(results['installation_jobs'])}")
    print(f"Rework Jobs (with -RW): {len(results['rework_jobs'])}")

    # Scanners with complete RMA flow
    serials_with_removal = {item['serial'] for item in results['removal_jobs']}
    serials_with_rework = {item['serial'] for item in results['rework_jobs']}
    complete_rma_flow = serials_with_removal & serials_with_rework

    print(f"\n✅ Scanners with Complete RMA Flow (removal + rework): {len(complete_rma_flow)}")
    for serial in sorted(complete_rma_flow):
        print(f"  • {serial}")

    # Scanners removed but not reworked yet
    removed_not_reworked = serials_with_removal - serials_with_rework
    if removed_not_reworked:
        print(f"\n⏳ Scanners Removed But Not Reworked (pending): {len(removed_not_reworked)}")
        for serial in sorted(removed_not_reworked):
            print(f"  • {serial}")

    # Scanners reworked but removal not tracked
    reworked_not_removed = serials_with_rework - serials_with_removal
    if reworked_not_removed:
        print(f"\nℹ️  Scanners Reworked (removal not in Zuper): {len(reworked_not_removed)}")
        for serial in sorted(reworked_not_removed):
            print(f"  • {serial}")

    # Not found at all
    all_found_serials = set(results['original_found'].keys()) | {item['serial'] for item in results['rework_jobs']}
    not_found = set(ORIGINAL_SERIALS) - all_found_serials

    if not_found:
        print(f"\n❌ Scanners NOT Found in Zuper: {len(not_found)}")
        print("   (These may be recent RMAs not yet in work orders)")
        for serial in sorted(not_found):
            print(f"  • {serial}")

def save_results(results, filename='rma_scanner_analysis.json'):
    """Save results to JSON"""
    filepath = os.path.join(os.path.dirname(__file__), filename)

    output = {
        'timestamp': datetime.now().isoformat(),
        'serials_searched': ORIGINAL_SERIALS,
        'original_found': {k: [{'job_uid': j.get('job_uid'), 'job_title': j.get('job_title'), 'created_at': j.get('created_at')} for j in v] for k, v in results['original_found'].items()},
        'rw_found': {k: [{'job_uid': j.get('job_uid'), 'job_title': j.get('job_title'), 'created_at': j.get('created_at')} for j in v] for k, v in results['rw_found'].items()},
        'removal_jobs': results['removal_jobs'],
        'installation_jobs': results['installation_jobs'],
        'rework_jobs': results['rework_jobs']
    }

    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Results saved to: {filepath}")

def create_rma_csv(results, filename='rma_scanner_report.csv'):
    """Create CSV report"""
    import csv
    filepath = os.path.join(os.path.dirname(__file__), filename)

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'Serial Number',
            'Event Type',
            'Job Title',
            'Job UID',
            'Date',
            'RW Serial Used'
        ])

        # Removal jobs
        for item in results['removal_jobs']:
            writer.writerow([
                item['serial'],
                'REMOVAL/REPLACEMENT',
                item['job_title'],
                item['job_uid'],
                item['created_at'][:10],
                ''
            ])

        # Rework jobs
        for item in results['rework_jobs']:
            writer.writerow([
                item['serial'],
                'REWORK',
                item['job_title'],
                item['job_uid'],
                item['created_at'][:10],
                item['rw_serial']
            ])

        # Installation jobs
        for item in results['installation_jobs']:
            writer.writerow([
                item['serial'],
                'INSTALLATION',
                item['job_title'],
                item['job_uid'],
                item['created_at'][:10],
                ''
            ])

    print(f"✓ CSV report saved to: {filepath}")

if __name__ == "__main__":
    print("ZUPER RMA SCANNER ANALYSIS")
    print("Searching for returned scanners and -RW rework variants")
    print("=" * 80)

    # Load jobs
    jobs = load_jobs()

    if not jobs:
        print("Error: No jobs data available")
        exit(1)

    print(f"Loaded {len(jobs)} jobs\n")

    # Search for RMA scanners
    results = search_rma_scanners(jobs)

    # Analyze timeline
    analyze_rma_timeline(results)

    # Print summary
    print_summary(results)

    # Save results
    save_results(results)
    create_rma_csv(results)

    print("\n✓ RMA analysis complete!")
