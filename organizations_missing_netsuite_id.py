#!/usr/bin/env python3
"""
Zuper API - Organizations Missing NetSuite IDs
This script identifies organizations that don't have NetSuite Customer IDs
"""

import json
import os
import csv
from datetime import datetime

def load_detailed_organizations(file='organizations_detailed.json'):
    """Load detailed organizations from JSON file"""
    filepath = os.path.join(os.path.dirname(__file__), file)

    if not os.path.exists(filepath):
        print(f"Error: {file} not found.")
        return None

    with open(filepath, 'r') as f:
        data = json.load(f)

    return data.get('organizations', [])

def find_organizations_without_netsuite_id(organizations):
    """Find organizations that don't have NetSuite Customer ID"""

    orgs_without_netsuite = []
    orgs_with_netsuite = []

    for org in organizations:
        org_uid = org.get('organization_uid')
        org_name = org.get('organization_name')

        # Get custom fields from details
        details = org.get('details', {})
        data = details.get('data', {}) if isinstance(details, dict) else {}
        custom_fields = data.get('custom_fields', [])

        # Extract relevant info
        org_info = {
            'organization_uid': org_uid,
            'organization_name': org_name,
            'organization_email': data.get('organization_email'),
            'no_of_customers': data.get('no_of_customers', 0),
            'is_active': data.get('is_active'),
            'is_portal_enabled': data.get('is_portal_enabled'),
            'created_at': data.get('created_at'),
            'updated_at': data.get('updated_at'),
            'netsuite_customer_id': '',
            'external_id': '',
            'hubspot_company_id': '',
            'has_custom_fields': len(custom_fields) > 0
        }

        # Extract custom field values
        for field in custom_fields:
            label = field.get('label', '')
            value = field.get('value', '')

            if label == 'Netsuite Customer ID':
                org_info['netsuite_customer_id'] = value
            elif label == 'External ID':
                org_info['external_id'] = value
            elif label == 'HubSpot Company ID':
                org_info['hubspot_company_id'] = value

        # Categorize organizations
        if org_info['netsuite_customer_id'] and str(org_info['netsuite_customer_id']).strip():
            orgs_with_netsuite.append(org_info)
        else:
            orgs_without_netsuite.append(org_info)

    return orgs_without_netsuite, orgs_with_netsuite

def print_missing_netsuite_summary(orgs_without_netsuite):
    """Print summary of organizations missing NetSuite IDs"""

    print("\n" + "=" * 80)
    print("ORGANIZATIONS MISSING NETSUITE CUSTOMER ID")
    print("=" * 80)
    print(f"\nTotal Organizations Missing NetSuite ID: {len(orgs_without_netsuite)}")

    if orgs_without_netsuite:
        print("\n" + "-" * 80)
        print("DETAILED LIST")
        print("-" * 80)

        for i, org in enumerate(orgs_without_netsuite, 1):
            print(f"\n{i}. {org['organization_name']}")
            print(f"   Organization UID: {org['organization_uid']}")
            print(f"   Email: {org['organization_email']}")
            print(f"   Number of Customers: {org['no_of_customers']}")
            print(f"   Active: {org['is_active']}")
            print(f"   Has Custom Fields: {org['has_custom_fields']}")

            if org['external_id']:
                print(f"   External ID: {org['external_id']}")
            if org['hubspot_company_id']:
                print(f"   HubSpot Company ID: {org['hubspot_company_id']}")

            print(f"   Created: {org['created_at']}")

    print("\n" + "=" * 80)

def save_missing_organizations_json(orgs_without_netsuite, filename='organizations_missing_netsuite_id.json'):
    """Save organizations without NetSuite ID to JSON file"""

    filepath = os.path.join(os.path.dirname(__file__), filename)

    output = {
        'timestamp': datetime.now().isoformat(),
        'total_missing': len(orgs_without_netsuite),
        'organizations': orgs_without_netsuite
    }

    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✓ Missing organizations JSON saved to: {filepath}")
    return filepath

def save_missing_organizations_csv(orgs_without_netsuite, filename='organizations_missing_netsuite_id.csv'):
    """Save organizations without NetSuite ID to CSV file"""

    filepath = os.path.join(os.path.dirname(__file__), filename)

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header row
        header = [
            'organization_uid',
            'organization_name',
            'organization_email',
            'no_of_customers',
            'is_active',
            'is_portal_enabled',
            'external_id',
            'hubspot_company_id',
            'has_custom_fields',
            'created_at',
            'updated_at'
        ]
        writer.writerow(header)

        # Data rows
        for org in orgs_without_netsuite:
            row = [
                org['organization_uid'],
                org['organization_name'],
                org['organization_email'],
                org['no_of_customers'],
                org['is_active'],
                org['is_portal_enabled'],
                org['external_id'],
                org['hubspot_company_id'],
                org['has_custom_fields'],
                org['created_at'],
                org['updated_at']
            ]
            writer.writerow(row)

    print(f"✓ Missing organizations CSV saved to: {filepath}")
    return filepath

def save_all_organizations_comparison(orgs_without_netsuite, orgs_with_netsuite, filename='organizations_netsuite_status.csv'):
    """Save all organizations with their NetSuite ID status"""

    filepath = os.path.join(os.path.dirname(__file__), filename)

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header row
        header = [
            'organization_uid',
            'organization_name',
            'organization_email',
            'has_netsuite_id',
            'netsuite_customer_id',
            'external_id',
            'hubspot_company_id',
            'no_of_customers',
            'is_active',
            'created_at'
        ]
        writer.writerow(header)

        # Organizations WITH NetSuite ID
        for org in orgs_with_netsuite:
            row = [
                org['organization_uid'],
                org['organization_name'],
                org['organization_email'],
                'YES',
                org['netsuite_customer_id'],
                org['external_id'],
                org['hubspot_company_id'],
                org['no_of_customers'],
                org['is_active'],
                org['created_at']
            ]
            writer.writerow(row)

        # Organizations WITHOUT NetSuite ID
        for org in orgs_without_netsuite:
            row = [
                org['organization_uid'],
                org['organization_name'],
                org['organization_email'],
                'NO',
                '',
                org['external_id'],
                org['hubspot_company_id'],
                org['no_of_customers'],
                org['is_active'],
                org['created_at']
            ]
            writer.writerow(row)

    print(f"✓ Complete NetSuite status comparison saved to: {filepath}")
    return filepath

if __name__ == "__main__":
    print("ZUPER API - ORGANIZATIONS MISSING NETSUITE IDS")
    print("=" * 80)

    # Load detailed organizations
    print("\nLoading detailed organizations...")
    organizations = load_detailed_organizations()

    if not organizations:
        print("Error: No organizations found.")
        exit(1)

    print(f"✓ Loaded {len(organizations)} organizations")

    # Find organizations without NetSuite ID
    print("\nAnalyzing NetSuite Customer ID coverage...")
    orgs_without_netsuite, orgs_with_netsuite = find_organizations_without_netsuite_id(organizations)

    print(f"✓ Organizations WITH NetSuite ID: {len(orgs_with_netsuite)}")
    print(f"✓ Organizations WITHOUT NetSuite ID: {len(orgs_without_netsuite)}")

    # Print summary
    print_missing_netsuite_summary(orgs_without_netsuite)

    # Save to files
    print("\nSaving results to files...")
    save_missing_organizations_json(orgs_without_netsuite)
    save_missing_organizations_csv(orgs_without_netsuite)
    save_all_organizations_comparison(orgs_without_netsuite, orgs_with_netsuite)

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print("\nFiles created:")
    print("  • organizations_missing_netsuite_id.json - Detailed JSON of missing orgs")
    print("  • organizations_missing_netsuite_id.csv - CSV of missing orgs")
    print("  • organizations_netsuite_status.csv - Complete list with NetSuite status")
    print("\n✓ Script completed successfully")
