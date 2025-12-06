#!/usr/bin/env python3
"""
Fetch all organizations from Zuper API and extract NetSuite Customer IDs
"""

import requests
import json
import os

# Zuper API configuration
ZUPER_API_KEY = os.environ.get('ZUPER_API_KEY', '0c73f76f734550cab45861cfaa4939d8')
ZUPER_BASE_URL = os.environ.get('ZUPER_BASE_URL', 'https://us-east-1.zuperpro.com')

def fetch_all_organizations():
    """Fetch all organizations from Zuper API"""
    print("Fetching organizations from Zuper API...")

    headers = {
        'x-api-key': ZUPER_API_KEY,
        'Content-Type': 'application/json'
    }

    all_organizations = []
    page = 1
    count = 100  # Fetch 100 per page

    while True:
        url = f'{ZUPER_BASE_URL}/api/organization'
        params = {
            'page': page,
            'count': count,
            'sort': 'DESC',
            'sort_by': 'created_at'
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()

            if data.get('type') != 'success':
                print(f"Error: {data}")
                break

            organizations = data.get('data', [])

            if not organizations:
                break

            all_organizations.extend(organizations)

            total_pages = data.get('total_pages', 0)
            print(f"  Fetched page {page}/{total_pages} ({len(organizations)} organizations)")

            if page >= total_pages:
                break

            page += 1

        except Exception as e:
            print(f"Error fetching organizations page {page}: {e}")
            break

    print(f"\n✓ Fetched {len(all_organizations)} organizations")
    return all_organizations

def fetch_organization_details(organization_uid):
    """Fetch detailed organization data including custom fields"""
    headers = {
        'x-api-key': ZUPER_API_KEY,
        'Content-Type': 'application/json'
    }

    url = f'{ZUPER_BASE_URL}/api/organization/{organization_uid}'

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()

        if data.get('type') == 'success':
            return data.get('data', {})
        else:
            print(f"Error fetching org {organization_uid}: {data}")
            return None

    except Exception as e:
        print(f"Error fetching org details {organization_uid}: {e}")
        return None

def extract_netsuite_id(org_details):
    """Extract NetSuite Customer ID from organization custom fields"""
    if not org_details:
        return None

    custom_fields = org_details.get('custom_fields', [])

    for field in custom_fields:
        label = field.get('label', '').lower()

        # Look for NetSuite ID field
        if any(term in label for term in ['netsuite', 'customer id', 'customer_id', 'ns id', 'ns customer']):
            value = field.get('value', '')
            if value and str(value).strip():
                return str(value).strip()

    return None

def main():
    """Main function"""
    print("ZUPER ORGANIZATIONS FETCH")
    print("=" * 80)

    # Fetch all organizations (basic list)
    organizations = fetch_all_organizations()

    # Now fetch details for each organization to get custom fields
    print("\nFetching organization details with custom fields...")

    organizations_with_netsuite = []
    organizations_without_netsuite = []

    for i, org in enumerate(organizations, 1):
        org_uid = org.get('organization_uid')
        org_name = org.get('organization_name', 'Unknown')

        if i % 10 == 0:
            print(f"  Processing {i}/{len(organizations)} organizations...")

        # Fetch detailed org data
        org_details = fetch_organization_details(org_uid)

        if org_details:
            netsuite_id = extract_netsuite_id(org_details)

            org_data = {
                'organization_uid': org_uid,
                'organization_name': org_name,
                'netsuite_customer_id': netsuite_id,
                'is_active': org_details.get('is_active', True),
                'is_deleted': org_details.get('is_deleted', False),
                'custom_fields': org_details.get('custom_fields', [])
            }

            if netsuite_id:
                organizations_with_netsuite.append(org_data)
            else:
                organizations_without_netsuite.append(org_data)

    # Save to file
    output_data = {
        'organizations_with_netsuite': organizations_with_netsuite,
        'organizations_without_netsuite': organizations_without_netsuite,
        'total_organizations': len(organizations),
        'with_netsuite_count': len(organizations_with_netsuite),
        'without_netsuite_count': len(organizations_without_netsuite)
    }

    with open('organizations_data.json', 'w') as f:
        json.dump(output_data, f, indent=2)

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total Organizations: {len(organizations)}")
    print(f"With NetSuite ID: {len(organizations_with_netsuite)}")
    print(f"Without NetSuite ID: {len(organizations_without_netsuite)}")
    print(f"\n✓ Saved to organizations_data.json")

if __name__ == "__main__":
    main()
