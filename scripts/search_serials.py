#!/usr/bin/env python3
"""
Zuper API - Search Assets by Serial Number
This script helps you search and lookup assets by serial number
"""

import requests
import json
import os
import sys

# API Configuration
API_KEY = os.environ.get('ZUPER_API_KEY', '0c73f76f734550cab45861cfaa4939d8')
BASE_URL = os.environ.get('ZUPER_BASE_URL', 'https://us-east-1.zuperpro.com')

# Endpoint
ASSETS_ENDPOINT = f"{BASE_URL}/api/assets"

# Headers
headers = {
    'x-api-key': API_KEY,
    'Content-Type': 'application/json'
}

def search_assets_by_serial(serial_number):
    """Search for assets by serial number"""
    params = {
        'sort_by': 'created_at',
        'sort': 'DESC',
        'page': 1,
        'count': 100,
        'filter.serial_no': serial_number
    }

    print(f"Searching for serial number: {serial_number}")
    print("-" * 60)

    try:
        response = requests.get(ASSETS_ENDPOINT, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            assets = data.get('data', [])

            if assets:
                print(f"✓ Found {len(assets)} asset(s) with serial number: {serial_number}\n")

                for i, asset in enumerate(assets, 1):
                    print(f"Asset {i}:")
                    print(f"  Asset UID: {asset.get('asset_uid')}")
                    print(f"  Asset Code: {asset.get('asset_code')}")
                    print(f"  Asset Name: {asset.get('asset_name')}")
                    print(f"  Serial Number: {asset.get('asset_serial_number')}")
                    print(f"  Status: {asset.get('asset_status')}")

                    if asset.get('asset_category'):
                        print(f"  Category: {asset.get('asset_category', {}).get('category_name')}")

                    if asset.get('customer'):
                        print(f"  Customer: {asset.get('customer')}")

                    print(f"  Active: {asset.get('is_active')}")
                    print(f"  Created: {asset.get('created_at')}")

                    # Custom fields
                    if asset.get('custom_fields'):
                        print(f"  Custom Fields:")
                        for field in asset.get('custom_fields', []):
                            if field.get('value'):
                                print(f"    - {field.get('label')}: {field.get('value')}")

                    print()

                return assets
            else:
                print(f"✗ No assets found with serial number: {serial_number}")
                return []
        else:
            print(f"Error: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return []

    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return []

def search_all_assets_containing_serial(serial_partial):
    """Search all assets and filter by partial serial number match"""
    params = {
        'sort_by': 'created_at',
        'sort': 'DESC',
        'page': 1,
        'count': 100
    }

    print(f"Searching for assets containing: {serial_partial}")
    print("-" * 60)

    all_matching_assets = []
    current_page = 1

    try:
        while True:
            params['page'] = current_page
            response = requests.get(ASSETS_ENDPOINT, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                assets = data.get('data', [])
                total_pages = data.get('total_pages', 0)

                # Filter assets containing the partial serial
                for asset in assets:
                    serial = asset.get('asset_serial_number', '')
                    if serial and serial_partial.lower() in serial.lower():
                        all_matching_assets.append(asset)

                print(f"  Scanned page {current_page}/{total_pages}...")

                if current_page >= total_pages:
                    break
                current_page += 1
            else:
                print(f"Error: HTTP {response.status_code}")
                break

        if all_matching_assets:
            print(f"\n✓ Found {len(all_matching_assets)} asset(s) containing '{serial_partial}':\n")

            for i, asset in enumerate(all_matching_assets, 1):
                print(f"{i}. {asset.get('asset_code')} - {asset.get('asset_name')}")
                print(f"   Serial: {asset.get('asset_serial_number')}")
                print(f"   Status: {asset.get('asset_status')}")
                print()

            return all_matching_assets
        else:
            print(f"\n✗ No assets found containing: {serial_partial}")
            return []

    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return []

def get_asset_details(asset_uid):
    """Get detailed information for a specific asset"""
    endpoint = f"{BASE_URL}/api/assets/{asset_uid}"

    try:
        response = requests.get(endpoint, headers=headers)

        if response.status_code == 200:
            data = response.json()
            return data.get('data', {})
        else:
            print(f"Error: HTTP {response.status_code}")
            return None

    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return None

def interactive_search():
    """Interactive serial number search"""
    print("=" * 60)
    print("ZUPER ASSET SERIAL NUMBER SEARCH")
    print("=" * 60)
    print()

    while True:
        print("Options:")
        print("1. Search by exact serial number")
        print("2. Search by partial serial number (contains)")
        print("3. Get asset details by UID")
        print("4. Exit")
        print()

        choice = input("Choose an option (1-4): ").strip()

        if choice == '1':
            serial = input("\nEnter serial number: ").strip()
            if serial:
                assets = search_assets_by_serial(serial)

                if assets and len(assets) == 1:
                    get_more = input("\nGet detailed information? (y/n): ").strip().lower()
                    if get_more == 'y':
                        details = get_asset_details(assets[0]['asset_uid'])
                        if details:
                            print("\n" + "=" * 60)
                            print("DETAILED ASSET INFORMATION")
                            print("=" * 60)
                            print(json.dumps(details, indent=2))

        elif choice == '2':
            serial_part = input("\nEnter partial serial number: ").strip()
            if serial_part:
                search_all_assets_containing_serial(serial_part)

        elif choice == '3':
            asset_uid = input("\nEnter asset UID: ").strip()
            if asset_uid:
                details = get_asset_details(asset_uid)
                if details:
                    print("\n" + "=" * 60)
                    print("ASSET DETAILS")
                    print("=" * 60)
                    print(json.dumps(details, indent=2))

        elif choice == '4':
            print("\nExiting...")
            break

        else:
            print("\nInvalid choice. Please try again.")

        print("\n" + "-" * 60 + "\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command line mode
        serial = sys.argv[1]

        # Try exact match first
        assets = search_assets_by_serial(serial)

        # If no exact match, try partial
        if not assets:
            print(f"\nNo exact match found. Trying partial search...\n")
            search_all_assets_containing_serial(serial)
    else:
        # Interactive mode
        interactive_search()
