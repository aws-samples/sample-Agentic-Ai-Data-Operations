#!/usr/bin/env python3
"""
Test PII Detection on Sample CSV Data

Demonstrates PII detection capabilities without requiring AWS Glue tables.
Uses the pattern-based detection from pii_detection_and_tagging.py.
"""

import pandas as pd
import re
import json
from datetime import datetime
from typing import Dict, List, Set

# ============================================================================
# PII Detection Patterns (from shared/utils/pii_detection_and_tagging.py)
# ============================================================================

PII_PATTERNS = {
    'EMAIL': {
        'regex': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'description': 'Email address',
        'sensitivity': 'HIGH'
    },
    'PHONE': {
        'regex': r'\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b',
        'description': 'Phone number',
        'sensitivity': 'MEDIUM'
    },
    'SSN': {
        'regex': r'\b\d{3}-\d{2}-\d{4}\b',
        'description': 'Social Security Number',
        'sensitivity': 'CRITICAL'
    },
    'CREDIT_CARD': {
        'regex': r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
        'description': 'Credit card number',
        'sensitivity': 'CRITICAL'
    },
    'ZIP_CODE': {
        'regex': r'\b\d{5}(?:-\d{4})?\b',
        'description': 'ZIP code',
        'sensitivity': 'LOW'
    },
    'DATE_OF_BIRTH': {
        'regex': r'\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12][0-9]|3[01])[/-](?:19|20)\d{2}\b',
        'description': 'Date of birth',
        'sensitivity': 'HIGH'
    },
    'IP_ADDRESS': {
        'regex': r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        'description': 'IP address',
        'sensitivity': 'LOW'
    }
}

# Column name patterns that indicate PII
COLUMN_NAME_PATTERNS = {
    'EMAIL': ['email', 'e_mail', 'email_address', 'contact_email'],
    'PHONE': ['phone', 'telephone', 'mobile', 'cell', 'contact_number'],
    'SSN': ['ssn', 'social_security', 'tax_id', 'national_id'],
    'NAME': ['first_name', 'last_name', 'full_name', 'name', 'customer_name', 'user_name'],
    'ADDRESS': ['address', 'street', 'city', 'state', 'zip', 'postal_code', 'country'],
    'DATE_OF_BIRTH': ['dob', 'date_of_birth', 'birth_date', 'birthdate'],
    'CREDIT_CARD': ['credit_card', 'cc_number', 'card_number', 'payment_card'],
    'BANK_ACCOUNT': ['account_number', 'bank_account', 'routing_number'],
    'PASSPORT': ['passport', 'passport_number'],
    'DRIVERS_LICENSE': ['license', 'drivers_license', 'dl_number']
}


def detect_pii_by_column_name(column_name: str) -> Set[str]:
    """Detect PII types based on column name patterns."""
    pii_types = set()
    col_lower = column_name.lower().replace('_', '').replace('-', '')

    for pii_type, patterns in COLUMN_NAME_PATTERNS.items():
        for pattern in patterns:
            pattern_clean = pattern.lower().replace('_', '').replace('-', '')
            if pattern_clean in col_lower:
                pii_types.add(pii_type)
                break

    return pii_types


def detect_pii_by_content(column_values: pd.Series, sample_size: int = 100) -> Dict[str, float]:
    """Detect PII types based on content patterns with confidence scores."""
    pii_confidence = {}

    # Sample values (non-null only)
    sample = column_values.dropna().astype(str).head(sample_size)

    if len(sample) == 0:
        return pii_confidence

    # Test each PII pattern
    for pii_type, pattern_info in PII_PATTERNS.items():
        regex = re.compile(pattern_info['regex'])
        matches = sample.apply(lambda x: bool(regex.search(str(x))))
        match_rate = matches.sum() / len(sample)

        # Confidence threshold: at least 50% of samples match
        if match_rate >= 0.5:
            pii_confidence[pii_type] = match_rate * 100.0

    return pii_confidence


def get_sensitivity_level(pii_types: Set[str]) -> str:
    """Determine overall sensitivity level based on detected PII types."""
    if not pii_types:
        return 'NONE'

    # Check for critical PII
    critical_types = {'SSN', 'CREDIT_CARD', 'BANK_ACCOUNT', 'PASSPORT', 'DRIVERS_LICENSE'}
    if pii_types & critical_types:
        return 'CRITICAL'

    # Check for high sensitivity
    high_types = {'EMAIL', 'DATE_OF_BIRTH', 'NAME'}
    if pii_types & high_types:
        return 'HIGH'

    # Check for medium sensitivity
    medium_types = {'PHONE', 'ADDRESS'}
    if pii_types & medium_types:
        return 'MEDIUM'

    return 'LOW'


def analyze_csv_for_pii(csv_path: str, content_detection: bool = True, sample_size: int = 100) -> Dict:
    """Analyze a CSV file for PII and return detection results."""

    print(f"\n{'='*80}")
    print(f"PII DETECTION REPORT")
    print(f"{'='*80}")
    print(f"File: {csv_path}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Content Detection: {'Enabled' if content_detection else 'Disabled'}")
    print(f"{'='*80}\n")

    # Load CSV
    df = pd.read_csv(csv_path)

    print(f"Dataset Overview:")
    print(f"  Rows: {len(df):,}")
    print(f"  Columns: {len(df.columns)}")
    print()

    # Results structure
    results = {
        'file': csv_path,
        'timestamp': datetime.now().isoformat(),
        'total_rows': len(df),
        'total_columns': len(df.columns),
        'pii_detected': False,
        'pii_columns': {},
        'summary': {}
    }

    # Analyze each column
    for column in df.columns:
        print(f"Analyzing column: {column}")
        print(f"  Data type: {df[column].dtype}")
        print(f"  Null rate: {df[column].isna().sum() / len(df) * 100:.1f}%")

        # Name-based detection
        name_pii_types = detect_pii_by_column_name(column)

        # Content-based detection
        content_pii_confidence = {}
        if content_detection and df[column].dtype == 'object':
            content_pii_confidence = detect_pii_by_content(df[column], sample_size)

        # Combine results
        all_pii_types = name_pii_types | set(content_pii_confidence.keys())

        if all_pii_types:
            results['pii_detected'] = True
            sensitivity = get_sensitivity_level(all_pii_types)

            results['pii_columns'][column] = {
                'pii_types': sorted(list(all_pii_types)),
                'sensitivity': sensitivity,
                'detection_methods': {
                    'name_based': sorted(list(name_pii_types)),
                    'content_based': content_pii_confidence
                }
            }

            print(f"  🔒 PII DETECTED:")
            print(f"     Types: {', '.join(sorted(all_pii_types))}")
            print(f"     Sensitivity: {sensitivity}")

            if name_pii_types:
                print(f"     Name-based: {', '.join(sorted(name_pii_types))}")
            if content_pii_confidence:
                print(f"     Content-based: {', '.join([f'{k} ({v:.0f}%)' for k, v in content_pii_confidence.items()])}")
        else:
            print(f"  ✓ No PII detected")

        print()

    # Summary
    if results['pii_detected']:
        sensitivity_counts = {}
        for col_info in results['pii_columns'].values():
            sensitivity = col_info['sensitivity']
            sensitivity_counts[sensitivity] = sensitivity_counts.get(sensitivity, 0) + 1

        results['summary'] = sensitivity_counts

        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        print(f"PII Columns Found: {len(results['pii_columns'])} / {len(df.columns)}")
        print()
        print("Sensitivity Distribution:")
        for level in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            if level in sensitivity_counts:
                print(f"  {level}: {sensitivity_counts[level]} column(s)")
        print()

        print("Columns by Sensitivity:")
        for level in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            cols = [col for col, info in results['pii_columns'].items() if info['sensitivity'] == level]
            if cols:
                print(f"  {level}: {', '.join(cols)}")
        print(f"{'='*80}\n")
    else:
        print(f"\n{'='*80}")
        print("✓ No PII detected in this dataset")
        print(f"{'='*80}\n")

    return results


def main():
    """Test PII detection on sample data."""

    # Test with sales_transactions.csv
    csv_path = 'sample_data/sales_transactions.csv'

    print("\n" + "="*80)
    print(" TEST: PII DETECTION ON SALES TRANSACTIONS DATA")
    print("="*80)

    results = analyze_csv_for_pii(csv_path, content_detection=True, sample_size=100)

    # Save results to JSON
    output_file = f"pii_detection_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"✓ Results saved to: {output_file}\n")

    return results


if __name__ == '__main__':
    main()
