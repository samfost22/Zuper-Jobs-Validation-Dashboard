#!/usr/bin/env python3
"""
Zuper API - Batch Serial Number Search
Search for multiple serial numbers at once
"""

import requests
import json
import os
import time

# API Configuration
API_KEY = os.environ.get('ZUPER_API_KEY', '0c73f76f734550cab45861cfaa4939d8')
BASE_URL = os.environ.get('ZUPER_BASE_URL', 'https://us-east-1.zuperpro.com')

# Headers
headers = {
    'x-api-key': API_KEY,
    'Content-Type': 'application/json'
}

def fetch_all_assets():
    """Fetch all assets from Zuper API"""
    endpoint = f"{BASE_URL}/api/assets"
    params = {
        'sort_by': 'created_at',
        'sort': 'DESC',
        'page': 1,
        'count': 100
    }

    all_assets = []
    current_page = 1

    print("Fetching all assets from Zuper...")

    while True:
        params['page'] = current_page
        response = requests.get(endpoint, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            assets = data.get('data', [])
            total_pages = data.get('total_pages', 0)

            all_assets.extend(assets)
            print(f"  Page {current_page}/{total_pages}: {len(assets)} assets")

            if current_page >= total_pages:
                break
            current_page += 1
        else:
            print(f"Error: HTTP {response.status_code}")
            break

    return all_assets

def search_serials_batch(serial_numbers, all_assets):
    """Search for multiple serial numbers"""

    results = {
        'found': [],
        'not_found': [],
        'summary': {}
    }

    print(f"\n{'='*80}")
    print(f"SEARCHING FOR {len(serial_numbers)} SERIAL NUMBERS")
    print(f"{'='*80}\n")

    for serial in serial_numbers:
        found = False

        for asset in all_assets:
            asset_serial = asset.get('asset_serial_number', '') or ''

            # Check exact match or if serial is contained in asset serial
            if asset_serial and (serial == asset_serial or serial in asset_serial):
                found = True

                asset_info = {
                    'serial_searched': serial,
                    'asset_serial_number': asset_serial,
                    'asset_uid': asset.get('asset_uid'),
                    'asset_code': asset.get('asset_code'),
                    'asset_name': asset.get('asset_name'),
                    'asset_status': asset.get('asset_status'),
                    'category': asset.get('asset_category', {}).get('category_name') if asset.get('asset_category') else None,
                    'is_active': asset.get('is_active'),
                    'created_at': asset.get('created_at'),
                    'custom_fields': {}
                }

                # Extract custom fields
                for field in asset.get('custom_fields', []):
                    if field.get('value'):
                        asset_info['custom_fields'][field.get('label')] = field.get('value')

                results['found'].append(asset_info)

                print(f"✓ FOUND: {serial}")
                print(f"  Asset Code: {asset_info['asset_code']}")
                print(f"  Asset Name: {asset_info['asset_name']}")
                print(f"  Serial Number: {asset_serial}")
                print(f"  Status: {asset_info['asset_status']}")
                print(f"  Category: {asset_info['category']}")
                if asset_info['custom_fields']:
                    print(f"  Custom Fields:")
                    for label, value in asset_info['custom_fields'].items():
                        print(f"    - {label}: {value}")
                print()
                break

        if not found:
            results['not_found'].append(serial)
            print(f"✗ NOT FOUND: {serial}")
            print()

    # Summary
    results['summary'] = {
        'total_searched': len(serial_numbers),
        'found_count': len(results['found']),
        'not_found_count': len(results['not_found']),
        'success_rate': round((len(results['found']) / len(serial_numbers) * 100), 1) if serial_numbers else 0
    }

    return results

def print_summary(results):
    """Print search summary"""
    print(f"\n{'='*80}")
    print("SEARCH SUMMARY")
    print(f"{'='*80}\n")

    summary = results['summary']
    print(f"Total Serial Numbers Searched: {summary['total_searched']}")
    print(f"Found: {summary['found_count']} ({summary['success_rate']}%)")
    print(f"Not Found: {summary['not_found_count']}")

    if results['not_found']:
        print(f"\n{'='*80}")
        print("SERIAL NUMBERS NOT FOUND IN ZUPER")
        print(f"{'='*80}\n")
        for serial in results['not_found']:
            print(f"  • {serial}")

def save_results(results, filename='serial_search_results.json'):
    """Save results to JSON file"""
    filepath = os.path.join(os.path.dirname(__file__), filename)

    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Results saved to: {filepath}")

def save_results_csv(results, filename='serial_search_results.csv'):
    """Save results to CSV file"""
    import csv
    filepath = os.path.join(os.path.dirname(__file__), filename)

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'Serial Searched',
            'Status',
            'Asset UID',
            'Asset Code',
            'Asset Name',
            'Asset Serial Number',
            'Asset Status',
            'Category',
            'Active',
            'Created At',
            'Netsuite Internal ID',
            'Laser Model'
        ])

        # Found assets
        for asset in results['found']:
            writer.writerow([
                asset['serial_searched'],
                'FOUND',
                asset['asset_uid'],
                asset['asset_code'],
                asset['asset_name'],
                asset['asset_serial_number'],
                asset['asset_status'],
                asset['category'],
                asset['is_active'],
                asset['created_at'],
                asset['custom_fields'].get('Netsuite Internal ID', ''),
                asset['custom_fields'].get('Laser Model', '')
            ])

        # Not found
        for serial in results['not_found']:
            writer.writerow([
                serial,
                'NOT FOUND',
                '', '', '', '', '', '', '', '', '', ''
            ])

    print(f"✓ Results saved to: {filepath}")

if __name__ == "__main__":
    # Serial numbers to search
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

    # Fetch all assets
    all_assets = fetch_all_assets()
    print(f"\n✓ Loaded {len(all_assets)} total assets\n")

    # Search for serial numbers
    results = search_serials_batch(serial_numbers, all_assets)

    # Print summary
    print_summary(results)

    # Save results
    save_results(results)
    save_results_csv(results)

    print("\n✓ Batch search completed!")
