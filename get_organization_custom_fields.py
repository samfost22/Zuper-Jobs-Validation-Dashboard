#!/usr/bin/env python3
"""
Zuper API - Extract and Analyze Organization Custom Fields
This script extracts all custom fields from organizations and provides analysis
"""

import json
import os
import csv
from collections import defaultdict
from datetime import datetime

def load_detailed_organizations(file='organizations_detailed.json'):
    """Load detailed organizations from JSON file"""
    filepath = os.path.join(os.path.dirname(__file__), file)

    if not os.path.exists(filepath):
        print(f"Error: {file} not found. Please run get_organization_details.py first.")
        return None

    with open(filepath, 'r') as f:
        data = json.load(f)

    return data.get('organizations', [])

def extract_custom_fields(organizations):
    """Extract all custom fields from organizations"""

    # Track all unique custom field labels
    field_labels = set()

    # Track field values by label
    field_data = defaultdict(lambda: {
        'count': 0,
        'values': [],
        'non_empty_count': 0,
        'types': set(),
        'examples': []
    })

    # Organizations with custom fields
    orgs_with_custom_fields = []

    for org in organizations:
        org_uid = org.get('organization_uid')
        org_name = org.get('organization_name')

        # Get custom fields from details
        details = org.get('details', {})
        data = details.get('data', {}) if isinstance(details, dict) else {}
        custom_fields = data.get('custom_fields', [])

        if custom_fields:
            org_custom_data = {
                'organization_uid': org_uid,
                'organization_name': org_name,
                'organization_email': data.get('organization_email'),
                'custom_fields': {}
            }

            for field in custom_fields:
                label = field.get('label', 'Unknown')
                value = field.get('value', '')
                field_type = field.get('type', 'unknown')
                hide_to_fe = field.get('hide_to_fe', False)
                hide_field = field.get('hide_field', False)
                read_only = field.get('read_only', False)

                field_labels.add(label)

                # Track field statistics
                field_data[label]['count'] += 1
                field_data[label]['types'].add(field_type)

                if value and str(value).strip():
                    field_data[label]['non_empty_count'] += 1
                    field_data[label]['values'].append(value)

                    # Keep only first 10 examples
                    if len(field_data[label]['examples']) < 10:
                        field_data[label]['examples'].append({
                            'organization_name': org_name,
                            'value': value
                        })

                # Add to org custom data
                org_custom_data['custom_fields'][label] = {
                    'value': value,
                    'type': field_type,
                    'hide_to_fe': hide_to_fe,
                    'hide_field': hide_field,
                    'read_only': read_only
                }

            orgs_with_custom_fields.append(org_custom_data)

    return {
        'field_labels': sorted(list(field_labels)),
        'field_data': dict(field_data),
        'orgs_with_custom_fields': orgs_with_custom_fields,
        'total_organizations': len(organizations),
        'orgs_with_fields_count': len(orgs_with_custom_fields)
    }

def print_custom_fields_summary(analysis):
    """Print summary of custom fields"""

    print("\n" + "=" * 80)
    print("ORGANIZATION CUSTOM FIELDS SUMMARY")
    print("=" * 80)

    print(f"\nTotal Organizations: {analysis['total_organizations']}")
    print(f"Organizations with Custom Fields: {analysis['orgs_with_fields_count']}")
    print(f"Unique Custom Field Labels: {len(analysis['field_labels'])}")

    print("\n" + "-" * 80)
    print("CUSTOM FIELD LABELS")
    print("-" * 80)

    for i, label in enumerate(analysis['field_labels'], 1):
        field_info = analysis['field_data'][label]
        types = ', '.join(sorted(field_info['types']))

        print(f"\n{i}. {label}")
        print(f"   Total Occurrences: {field_info['count']}")
        print(f"   Non-Empty Values: {field_info['non_empty_count']}")
        print(f"   Empty Values: {field_info['count'] - field_info['non_empty_count']}")
        print(f"   Field Type(s): {types}")

        if field_info['examples']:
            print(f"   Examples:")
            for ex in field_info['examples'][:5]:
                value_display = ex['value'] if ex['value'] else '(empty)'
                print(f"      • {ex['organization_name']}: '{value_display}'")

    print("\n" + "=" * 80)

def get_orgs_with_netsuite_id(orgs_with_custom_fields):
    """Get organizations that have NetSuite Customer ID"""

    orgs_with_netsuite = []

    for org in orgs_with_custom_fields:
        if 'Netsuite Customer ID' in org['custom_fields']:
            netsuite_id = org['custom_fields']['Netsuite Customer ID']['value']

            if netsuite_id and str(netsuite_id).strip():
                orgs_with_netsuite.append({
                    'organization_uid': org['organization_uid'],
                    'organization_name': org['organization_name'],
                    'organization_email': org['organization_email'],
                    'netsuite_customer_id': netsuite_id
                })

    return orgs_with_netsuite

def save_custom_fields_analysis(analysis, filename='organization_custom_fields_analysis.json'):
    """Save custom fields analysis to JSON file"""

    filepath = os.path.join(os.path.dirname(__file__), filename)

    # Convert sets to lists for JSON serialization
    output = {
        'timestamp': datetime.now().isoformat(),
        'total_organizations': analysis['total_organizations'],
        'orgs_with_fields_count': analysis['orgs_with_fields_count'],
        'field_labels': analysis['field_labels'],
        'field_data': {
            label: {
                'count': data['count'],
                'non_empty_count': data['non_empty_count'],
                'types': sorted(list(data['types'])),
                'examples': data['examples']
            }
            for label, data in analysis['field_data'].items()
        },
        'orgs_with_custom_fields': analysis['orgs_with_custom_fields']
    }

    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Custom fields analysis saved to: {filepath}")
    return filepath

def create_custom_fields_csv(analysis, filename='organization_custom_fields.csv'):
    """Create a CSV file with all custom fields per organization"""

    filepath = os.path.join(os.path.dirname(__file__), filename)

    # Get all unique field labels
    all_fields = analysis['field_labels']

    # Create CSV
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header row
        header = ['organization_uid', 'organization_name', 'organization_email'] + all_fields
        writer.writerow(header)

        # Data rows
        for org in analysis['orgs_with_custom_fields']:
            row = [
                org['organization_uid'],
                org['organization_name'],
                org['organization_email']
            ]

            # Add custom field values in order
            for field_label in all_fields:
                if field_label in org['custom_fields']:
                    value = org['custom_fields'][field_label]['value']
                    row.append(value if value else '')
                else:
                    row.append('')

            writer.writerow(row)

    print(f"✓ Custom fields CSV saved to: {filepath}")
    return filepath

def create_netsuite_mapping_csv(orgs_with_netsuite, filename='zuper_netsuite_mapping.csv'):
    """Create a CSV mapping Zuper orgs to NetSuite IDs"""

    filepath = os.path.join(os.path.dirname(__file__), filename)

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header row
        header = ['zuper_organization_uid', 'organization_name', 'organization_email', 'netsuite_customer_id']
        writer.writerow(header)

        # Data rows
        for org in orgs_with_netsuite:
            row = [
                org['organization_uid'],
                org['organization_name'],
                org['organization_email'],
                org['netsuite_customer_id']
            ]
            writer.writerow(row)

    print(f"✓ NetSuite mapping CSV saved to: {filepath}")
    return filepath

if __name__ == "__main__":
    print("ZUPER API - ORGANIZATION CUSTOM FIELDS EXTRACTION")
    print("=" * 80)

    # Load detailed organizations
    print("\nLoading detailed organizations from organizations_detailed.json...")
    organizations = load_detailed_organizations()

    if not organizations:
        print("Error: No organizations found.")
        exit(1)

    print(f"✓ Loaded {len(organizations)} organizations")

    # Extract custom fields
    print("\nAnalyzing custom fields...")
    analysis = extract_custom_fields(organizations)

    # Print summary
    print_custom_fields_summary(analysis)

    # Save analysis
    save_custom_fields_analysis(analysis)

    # Create CSV
    create_custom_fields_csv(analysis)

    # Get organizations with NetSuite ID
    orgs_with_netsuite = get_orgs_with_netsuite_id(analysis['orgs_with_custom_fields'])

    print("\n" + "=" * 80)
    print("NETSUITE INTEGRATION")
    print("=" * 80)
    print(f"\nOrganizations with NetSuite Customer ID: {len(orgs_with_netsuite)}")

    if orgs_with_netsuite:
        print("\nOrganizations with NetSuite IDs:")
        for org in orgs_with_netsuite[:10]:
            print(f"  • {org['organization_name']}: {org['netsuite_customer_id']}")

        if len(orgs_with_netsuite) > 10:
            print(f"  ... and {len(orgs_with_netsuite) - 10} more")

        # Create NetSuite mapping CSV
        create_netsuite_mapping_csv(orgs_with_netsuite)

    print("\n" + "=" * 80)
    print("CUSTOM FIELDS EXTRACTION COMPLETE")
    print("=" * 80)
    print("\nFiles created:")
    print("  • organization_custom_fields_analysis.json - Complete analysis with examples")
    print("  • organization_custom_fields.csv - Spreadsheet view of all custom fields")
    if orgs_with_netsuite:
        print("  • zuper_netsuite_mapping.csv - Mapping of Zuper orgs to NetSuite IDs")
    print("\n✓ Script completed successfully")
