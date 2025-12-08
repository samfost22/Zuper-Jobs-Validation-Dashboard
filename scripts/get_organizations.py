#!/usr/bin/env python3
"""
Zuper API - Get All Organizations
This script fetches all organizations from the Zuper API
"""

import requests
import json
import os
from datetime import datetime

# API Configuration
API_KEY = os.environ.get('ZUPER_API_KEY', '0c73f76f734550cab45861cfaa4939d8')
BASE_URL = os.environ.get('ZUPER_BASE_URL', 'https://us-east-1.zuperpro.com')

# Endpoint
ORGANIZATIONS_ENDPOINT = f"{BASE_URL}/api/organization"

# Headers
headers = {
    'x-api-key': API_KEY,
    'Content-Type': 'application/json'
}

# Query parameters with defaults
params = {
    'sort_by': 'created_at',
    'sort': 'DESC',
    'page': 1,
    'count': 100,  # Fetch 100 organizations per page
}

def get_all_organizations():
    """Fetch all organizations from Zuper API with pagination"""
    all_organizations = []
    current_page = 1

    print(f"Fetching organizations from: {ORGANIZATIONS_ENDPOINT}")
    print(f"Using API Key: {API_KEY[:10]}...")
    print("-" * 60)

    while True:
        params['page'] = current_page

        try:
            response = requests.get(
                ORGANIZATIONS_ENDPOINT,
                headers=headers,
                params=params
            )

            print(f"\nPage {current_page}: Status Code {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                if data.get('type') == 'success':
                    organizations = data.get('data', [])
                    total_records = data.get('total_records', 0)
                    total_pages = data.get('total_pages', 0)

                    print(f"Retrieved {len(organizations)} organizations")
                    print(f"Total records: {total_records}")
                    print(f"Total pages: {total_pages}")

                    all_organizations.extend(organizations)

                    # Check if there are more pages
                    if current_page >= total_pages:
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

    return all_organizations

def save_organizations_to_file(organizations, filename='organizations_data.json'):
    """Save organizations data to a JSON file"""
    filepath = os.path.join(os.path.dirname(__file__), filename)

    output = {
        'timestamp': datetime.now().isoformat(),
        'total_organizations': len(organizations),
        'organizations': organizations
    }

    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Organizations saved to: {filepath}")
    return filepath

def print_organization_summary(organizations):
    """Print a summary of the organizations"""
    print("\n" + "=" * 60)
    print(f"ORGANIZATION SUMMARY")
    print("=" * 60)
    print(f"Total Organizations: {len(organizations)}")

    if organizations:
        print("\nFirst 5 Organizations:")
        print("-" * 60)

        for i, org in enumerate(organizations[:5], 1):
            print(f"\n{i}. {org.get('organization_name')}")
            print(f"   Organization UID: {org.get('organization_uid')}")
            print(f"   Email: {org.get('organization_email')}")
            print(f"   Number of Customers: {org.get('no_of_customers', 0)}")
            print(f"   Portal Enabled: {org.get('is_portal_enabled')}")
            print(f"   Active: {org.get('is_active')}")
            print(f"   Created: {org.get('created_at')}")

            # Address
            if org.get('organization_address'):
                addr = org.get('organization_address')
                if addr.get('city') or addr.get('state'):
                    print(f"   Location: {addr.get('city', '')}, {addr.get('state', '')}")

        # Statistics
        print("\n" + "-" * 60)
        print("STATISTICS:")
        active_count = sum(1 for org in organizations if org.get('is_active'))
        portal_enabled_count = sum(1 for org in organizations if org.get('is_portal_enabled'))
        total_customers = sum(org.get('no_of_customers', 0) for org in organizations)

        print(f"Active Organizations: {active_count}")
        print(f"Portal Enabled: {portal_enabled_count}")
        print(f"Total Customers Across All Orgs: {total_customers}")

        # Organizations with custom fields
        orgs_with_custom_fields = [org for org in organizations if org.get('custom_fields')]
        print(f"Organizations with Custom Fields: {len(orgs_with_custom_fields)}")

    print("=" * 60)

if __name__ == "__main__":
    print("ZUPER API - GET ALL ORGANIZATIONS")
    print("=" * 60)

    # Fetch organizations
    organizations = get_all_organizations()

    if organizations:
        # Print summary
        print_organization_summary(organizations)

        # Save to file
        save_organizations_to_file(organizations)

        print("\n✓ Script completed successfully")
    else:
        print("\n✗ No organizations retrieved or an error occurred")
