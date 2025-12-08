#!/usr/bin/env python3
"""
Zuper API - Get Organization Details
This script fetches detailed information for organizations including custom fields
"""

import requests
import json
import os
import sys
import time
from datetime import datetime

# API Configuration
API_KEY = os.environ.get('ZUPER_API_KEY', '0c73f76f734550cab45861cfaa4939d8')
BASE_URL = os.environ.get('ZUPER_BASE_URL', 'https://us-east-1.zuperpro.com')

# Headers
headers = {
    'x-api-key': API_KEY,
    'Content-Type': 'application/json'
}

def get_organization_details(organization_uid):
    """Fetch detailed information for a specific organization"""
    endpoint = f"{BASE_URL}/api/organization/{organization_uid}"

    print(f"Fetching details for organization: {organization_uid}")

    try:
        response = requests.get(endpoint, headers=headers)

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            return data
        elif response.status_code == 401:
            print("Error: Unauthorized - Check your API key")
            print(f"Response: {response.text}")
            return None
        elif response.status_code == 404:
            print(f"Error: Organization not found with UID: {organization_uid}")
            print(f"Response: {response.text}")
            return None
        else:
            print(f"Error: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return None

def get_all_organization_details_from_list(organizations_file='organizations_data.json'):
    """Fetch detailed information for all organizations from the organizations list"""
    filepath = os.path.join(os.path.dirname(__file__), organizations_file)

    if not os.path.exists(filepath):
        print(f"Error: {organizations_file} not found. Please run get_organizations.py first.")
        return []

    with open(filepath, 'r') as f:
        data = json.load(f)

    organizations = data.get('organizations', [])
    print(f"Found {len(organizations)} organizations to fetch details for")
    print("=" * 60)

    detailed_organizations = []

    for i, org in enumerate(organizations, 1):
        organization_uid = org.get('organization_uid')
        organization_name = org.get('organization_name', 'Unknown')

        print(f"\n[{i}/{len(organizations)}] Fetching: {organization_name}")

        details = get_organization_details(organization_uid)

        if details:
            detailed_organizations.append({
                'organization_uid': organization_uid,
                'organization_name': organization_name,
                'details': details,
                'fetched_at': datetime.now().isoformat()
            })
            print(f"✓ Success")
        else:
            print(f"✗ Failed")

        # Small delay to avoid rate limiting
        if i % 10 == 0:
            print(f"\nProgress: {i}/{len(organizations)} organizations processed...")
            time.sleep(0.5)

    return detailed_organizations

def save_detailed_organizations(detailed_organizations, filename='organizations_detailed.json'):
    """Save detailed organization data to a JSON file"""
    filepath = os.path.join(os.path.dirname(__file__), filename)

    output = {
        'timestamp': datetime.now().isoformat(),
        'total_organizations': len(detailed_organizations),
        'organizations': detailed_organizations
    }

    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Detailed organizations saved to: {filepath}")
    return filepath

def print_organization_detail(org_data):
    """Print detailed information about an organization"""
    if not org_data:
        return

    details = org_data.get('details', {})
    data = details.get('data', {}) if isinstance(details, dict) else {}

    print("\n" + "=" * 60)
    print("ORGANIZATION DETAILS")
    print("=" * 60)

    print(f"Organization UID: {data.get('organization_uid')}")
    print(f"Organization Name: {data.get('organization_name')}")
    print(f"Email: {data.get('organization_email')}")
    print(f"Description: {data.get('organization_description')}")
    print(f"Number of Customers: {data.get('no_of_customers', 0)}")
    print(f"Active: {data.get('is_active')}")
    print(f"Portal Enabled: {data.get('is_portal_enabled')}")
    print(f"Deleted: {data.get('is_deleted')}")

    # Address
    if data.get('organization_address'):
        addr = data.get('organization_address')
        print(f"\nOrganization Address:")
        print(f"  Street: {addr.get('street')}")
        print(f"  City: {addr.get('city')}")
        print(f"  State: {addr.get('state')}")
        print(f"  Country: {addr.get('country')}")
        print(f"  Zip Code: {addr.get('zip_code')}")
        if addr.get('geo_cordinates'):
            print(f"  Coordinates: {addr.get('geo_cordinates')}")

    # Billing Address
    if data.get('organization_billing_address'):
        billing = data.get('organization_billing_address')
        if billing.get('city') or billing.get('street'):
            print(f"\nBilling Address:")
            print(f"  Street: {billing.get('street')}")
            print(f"  City: {billing.get('city')}")
            print(f"  State: {billing.get('state')}")
            print(f"  Country: {billing.get('country')}")
            print(f"  Zip Code: {billing.get('zip_code')}")

    # Custom Fields
    if data.get('custom_fields'):
        print(f"\nCustom Fields:")
        for field in data.get('custom_fields', []):
            label = field.get('label')
            value = field.get('value')
            field_type = field.get('type')
            print(f"  {label}: {value} (Type: {field_type})")
    else:
        print(f"\nCustom Fields: None")

    # Teams
    if data.get('teams'):
        print(f"\nTeams: {len(data.get('teams'))} teams")

    # Attachments
    if data.get('attachments'):
        print(f"Attachments: {len(data.get('attachments'))} attachments")

    # Created By
    if data.get('created_by'):
        user = data.get('created_by')
        print(f"\nCreated By: {user.get('first_name')} {user.get('last_name')}")
        print(f"  Email: {user.get('email')}")

    # Dates
    print(f"\nCreated: {data.get('created_at')}")
    print(f"Updated: {data.get('updated_at')}")

    print("=" * 60)

if __name__ == "__main__":
    print("ZUPER API - GET ORGANIZATION DETAILS")
    print("=" * 60)

    # Check if a specific organization UID was provided
    if len(sys.argv) > 1:
        organization_uid = sys.argv[1]
        print(f"\nFetching details for single organization: {organization_uid}\n")

        details = get_organization_details(organization_uid)

        if details:
            org_data = {
                'organization_uid': organization_uid,
                'details': details
            }
            print_organization_detail(org_data)

            # Save to file
            filename = f'organization_{organization_uid}_details.json'
            filepath = os.path.join(os.path.dirname(__file__), filename)
            with open(filepath, 'w') as f:
                json.dump(details, f, indent=2)
            print(f"\n✓ Organization details saved to: {filepath}")
    else:
        print("\nFetching details for ALL 190 organizations...")
        print("This will fetch custom fields for each organization.")

        response = input("\nDo you want to continue? (yes/no): ").strip().lower()

        if response in ['yes', 'y']:
            detailed_organizations = get_all_organization_details_from_list()

            if detailed_organizations:
                save_detailed_organizations(detailed_organizations)
                print(f"\n✓ Successfully fetched details for {len(detailed_organizations)} organizations")

                # Print first organization as sample
                if detailed_organizations:
                    print("\nSample (first organization):")
                    print_organization_detail(detailed_organizations[0])

                # Count organizations with custom fields
                orgs_with_custom_fields = [
                    org for org in detailed_organizations
                    if org.get('details', {}).get('data', {}).get('custom_fields')
                ]
                print(f"\n✓ Organizations with custom fields: {len(orgs_with_custom_fields)}")
            else:
                print("\n✗ No detailed organizations retrieved")
        else:
            print("\nOperation cancelled.")
            print("\nTo fetch a single organization, run:")
            print("  python3 get_organization_details.py <organization_uid>")
            print("\nExample:")
            print("  python3 get_organization_details.py 216cf874-adde-4e40-a820-6e568df3ec90")
