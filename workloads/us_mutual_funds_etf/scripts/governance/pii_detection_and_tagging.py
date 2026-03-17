"""
PII Detection and Lake Formation Tagging
=========================================

Automatically identifies PII (Personally Identifiable Information) in data
and tags columns using AWS Lake Formation Tags (LF-Tags) for governance.

Features:
- Pattern-based PII detection (email, phone, SSN, credit card, etc.)
- Content-based detection (names, addresses via sampling)
- Lake Formation tag application
- Audit logging

Usage:
    python3 pii_detection_and_tagging.py --database finsights_silver --table funds_clean
    python3 pii_detection_and_tagging.py --database finsights_gold --all-tables
"""

import argparse
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Set, Tuple
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# AWS clients
glue = boto3.client('glue', region_name='us-east-1')
athena = boto3.client('athena', region_name='us-east-1')
lakeformation = boto3.client('lakeformation', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')

# Configuration
ATHENA_OUTPUT_BUCKET = 's3://your-datalake-bucket/athena-results/'
SAMPLE_SIZE = 100  # Number of rows to sample for content-based detection


# ============================================================================
# PII Detection Patterns
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
    'NAME': ['first_name', 'last_name', 'full_name', 'name', 'customer_name'],
    'ADDRESS': ['address', 'street', 'city', 'state', 'zip', 'postal_code', 'country'],
    'DATE_OF_BIRTH': ['dob', 'date_of_birth', 'birth_date', 'birthdate'],
    'CREDIT_CARD': ['credit_card', 'cc_number', 'card_number', 'payment_card'],
    'BANK_ACCOUNT': ['account_number', 'bank_account', 'routing_number'],
    'PASSPORT': ['passport', 'passport_number'],
    'DRIVERS_LICENSE': ['license', 'drivers_license', 'dl_number']
}


# ============================================================================
# PII Detection Functions
# ============================================================================

def detect_pii_by_column_name(column_name: str) -> List[Tuple[str, str]]:
    """
    Detect PII based on column name patterns.

    Returns list of (pii_type, sensitivity) tuples.
    """
    detected = []
    column_lower = column_name.lower().replace('_', '')

    for pii_type, patterns in COLUMN_NAME_PATTERNS.items():
        for pattern in patterns:
            pattern_clean = pattern.lower().replace('_', '')
            if pattern_clean in column_lower:
                sensitivity = PII_PATTERNS.get(pii_type, {}).get('sensitivity', 'MEDIUM')
                detected.append((pii_type, sensitivity))
                break

    return detected


def detect_pii_by_content(database: str, table: str, column: str, data_type: str) -> List[Tuple[str, str, float]]:
    """
    Detect PII by sampling column content and applying regex patterns.

    Returns list of (pii_type, sensitivity, confidence) tuples.
    """
    # Only check string columns
    if data_type.lower() not in ['string', 'varchar', 'char', 'text']:
        return []

    detected = []

    try:
        # Sample data from column
        query = f"""
        SELECT "{column}"
        FROM {database}.{table}
        WHERE "{column}" IS NOT NULL
        LIMIT {SAMPLE_SIZE}
        """

        logger.info(f"Sampling column {column} for content-based PII detection...")

        # Execute query
        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': database},
            ResultConfiguration={'OutputLocation': ATHENA_OUTPUT_BUCKET}
        )

        query_execution_id = response['QueryExecutionId']

        # Wait for query to complete
        import time
        max_wait = 30  # seconds
        waited = 0
        while waited < max_wait:
            status = athena.get_query_execution(QueryExecutionId=query_execution_id)
            state = status['QueryExecution']['Status']['State']

            if state == 'SUCCEEDED':
                break
            elif state in ['FAILED', 'CANCELLED']:
                logger.warning(f"Query failed for column {column}: {state}")
                return []

            time.sleep(2)
            waited += 2

        if waited >= max_wait:
            logger.warning(f"Query timed out for column {column}")
            return []

        # Get results
        results = athena.get_query_results(QueryExecutionId=query_execution_id)

        # Check samples against patterns
        matches = {pii_type: 0 for pii_type in PII_PATTERNS.keys()}
        total_samples = 0

        for row in results['ResultSet']['Rows'][1:]:  # Skip header
            if not row['Data']:
                continue

            value = row['Data'][0].get('VarCharValue', '')
            if not value:
                continue

            total_samples += 1

            for pii_type, pattern_info in PII_PATTERNS.items():
                if re.search(pattern_info['regex'], str(value)):
                    matches[pii_type] += 1

        # Calculate confidence (percentage of samples matching)
        if total_samples > 0:
            for pii_type, match_count in matches.items():
                if match_count > 0:
                    confidence = (match_count / total_samples) * 100
                    if confidence >= 10:  # At least 10% of samples match
                        sensitivity = PII_PATTERNS[pii_type]['sensitivity']
                        detected.append((pii_type, sensitivity, confidence))
                        logger.info(f"  Detected {pii_type} with {confidence:.1f}% confidence")

    except ClientError as e:
        logger.error(f"Error sampling column {column}: {e}")

    return detected


def scan_table_for_pii(database: str, table: str, content_detection: bool = True) -> Dict[str, Dict]:
    """
    Scan all columns in a table for PII.

    Returns dict mapping column_name to PII metadata.
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"Scanning table: {database}.{table}")
    logger.info(f"{'='*80}")

    pii_results = {}

    try:
        # Get table schema
        response = glue.get_table(DatabaseName=database, Name=table)
        columns = response['Table']['StorageDescriptor']['Columns']

        logger.info(f"Found {len(columns)} columns")

        for column in columns:
            column_name = column['Name']
            data_type = column['Type']

            logger.info(f"\nAnalyzing column: {column_name} ({data_type})")

            # Step 1: Name-based detection
            name_detected = detect_pii_by_column_name(column_name)

            # Step 2: Content-based detection (if enabled)
            content_detected = []
            if content_detection:
                content_detected = detect_pii_by_content(database, table, column_name, data_type)

            # Combine results
            all_detected = set()
            max_sensitivity = 'LOW'
            confidence_scores = {}

            for pii_type, sensitivity in name_detected:
                all_detected.add(pii_type)
                max_sensitivity = max(max_sensitivity, sensitivity, key=lambda x: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].index(x))
                confidence_scores[pii_type] = 100.0  # Name match is 100% confident
                logger.info(f"  ✓ Name-based: {pii_type} ({sensitivity})")

            for pii_type, sensitivity, confidence in content_detected:
                all_detected.add(pii_type)
                max_sensitivity = max(max_sensitivity, sensitivity, key=lambda x: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].index(x))
                confidence_scores[pii_type] = max(confidence_scores.get(pii_type, 0), confidence)

            if all_detected:
                pii_results[column_name] = {
                    'pii_types': list(all_detected),
                    'sensitivity': max_sensitivity,
                    'confidence_scores': confidence_scores,
                    'data_type': data_type,
                    'detection_methods': {
                        'name_based': len(name_detected) > 0,
                        'content_based': len(content_detected) > 0
                    }
                }

                logger.info(f"  ⚠️  PII DETECTED: {', '.join(all_detected)} (Sensitivity: {max_sensitivity})")
            else:
                logger.info(f"  ✓ No PII detected")

    except ClientError as e:
        logger.error(f"Error scanning table: {e}")
        raise

    return pii_results


# ============================================================================
# Lake Formation Tagging Functions
# ============================================================================

def ensure_lf_tags_exist():
    """
    Create LF-Tags if they don't exist.

    Tags:
    - PII_Classification: CRITICAL, HIGH, MEDIUM, LOW, NONE
    - PII_Type: EMAIL, PHONE, SSN, CREDIT_CARD, etc.
    - Data_Sensitivity: CRITICAL, HIGH, MEDIUM, LOW
    """
    logger.info("\n" + "="*80)
    logger.info("Ensuring Lake Formation Tags exist")
    logger.info("="*80)

    tags_to_create = [
        {
            'TagKey': 'PII_Classification',
            'TagValues': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE']
        },
        {
            'TagKey': 'PII_Type',
            'TagValues': ['EMAIL', 'PHONE', 'SSN', 'CREDIT_CARD', 'NAME', 'ADDRESS',
                         'DATE_OF_BIRTH', 'BANK_ACCOUNT', 'PASSPORT', 'DRIVERS_LICENSE',
                         'ZIP_CODE', 'IP_ADDRESS', 'MULTIPLE']
        },
        {
            'TagKey': 'Data_Sensitivity',
            'TagValues': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
        }
    ]

    for tag_config in tags_to_create:
        tag_key = tag_config['TagKey']

        try:
            # Check if tag exists
            lakeformation.get_lf_tag(TagKey=tag_key)
            logger.info(f"✓ LF-Tag already exists: {tag_key}")

        except lakeformation.exceptions.EntityNotFoundException:
            # Create tag
            try:
                lakeformation.create_lf_tag(
                    TagKey=tag_key,
                    TagValues=tag_config['TagValues']
                )
                logger.info(f"✓ Created LF-Tag: {tag_key}")
            except ClientError as e:
                if e.response['Error']['Code'] == 'AlreadyExistsException':
                    logger.info(f"✓ LF-Tag already exists: {tag_key}")
                else:
                    logger.error(f"✗ Failed to create LF-Tag {tag_key}: {e}")

        except ClientError as e:
            logger.error(f"Error checking LF-Tag {tag_key}: {e}")


def apply_lf_tags_to_columns(database: str, table: str, pii_results: Dict[str, Dict]):
    """
    Apply LF-Tags to columns based on PII detection results.
    """
    if not pii_results:
        logger.info("\nNo PII detected, skipping tagging")
        return

    logger.info(f"\n{'='*80}")
    logger.info(f"Applying LF-Tags to {database}.{table}")
    logger.info(f"{'='*80}")

    for column_name, pii_info in pii_results.items():
        logger.info(f"\nTagging column: {column_name}")

        sensitivity = pii_info['sensitivity']
        pii_types = pii_info['pii_types']

        # Determine PII_Type tag value
        if len(pii_types) == 1:
            pii_type_value = pii_types[0]
        else:
            pii_type_value = 'MULTIPLE'

        # Tags to apply
        lf_tags = [
            {'TagKey': 'PII_Classification', 'TagValues': [sensitivity]},
            {'TagKey': 'PII_Type', 'TagValues': [pii_type_value]},
            {'TagKey': 'Data_Sensitivity', 'TagValues': [sensitivity]}
        ]

        # Apply tags
        try:
            lakeformation.add_lf_tags_to_resource(
                Resource={
                    'TableWithColumns': {
                        'DatabaseName': database,
                        'Name': table,
                        'ColumnNames': [column_name]
                    }
                },
                LFTags=lf_tags
            )

            logger.info(f"  ✓ Applied tags: PII_Classification={sensitivity}, PII_Type={pii_type_value}")

        except ClientError as e:
            if e.response['Error']['Code'] == 'AlreadyTaggedException':
                logger.info(f"  ℹ️  Column already tagged, updating...")
                # Remove old tags and reapply
                try:
                    lakeformation.remove_lf_tags_from_resource(
                        Resource={
                            'TableWithColumns': {
                                'DatabaseName': database,
                                'Name': table,
                                'ColumnNames': [column_name]
                            }
                        },
                        LFTags=lf_tags
                    )
                    lakeformation.add_lf_tags_to_resource(
                        Resource={
                            'TableWithColumns': {
                                'DatabaseName': database,
                                'Name': table,
                                'ColumnNames': [column_name]
                            }
                        },
                        LFTags=lf_tags
                    )
                    logger.info(f"  ✓ Updated tags successfully")
                except ClientError as e2:
                    logger.error(f"  ✗ Failed to update tags: {e2}")
            else:
                logger.error(f"  ✗ Failed to apply tags: {e}")


def save_pii_report(database: str, table: str, pii_results: Dict[str, Dict], output_path: str = None):
    """
    Save PII detection results to JSON file.
    """
    if not output_path:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f"pii_report_{database}_{table}_{timestamp}.json"

    report = {
        'scan_timestamp': datetime.now().isoformat(),
        'database': database,
        'table': table,
        'total_columns_scanned': len(pii_results),
        'pii_columns': pii_results,
        'summary': {
            'critical': sum(1 for info in pii_results.values() if info['sensitivity'] == 'CRITICAL'),
            'high': sum(1 for info in pii_results.values() if info['sensitivity'] == 'HIGH'),
            'medium': sum(1 for info in pii_results.values() if info['sensitivity'] == 'MEDIUM'),
            'low': sum(1 for info in pii_results.values() if info['sensitivity'] == 'LOW')
        }
    }

    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    logger.info(f"\n✓ PII report saved to: {output_path}")
    return output_path


# ============================================================================
# Main Execution
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Detect PII and apply Lake Formation tags')
    parser.add_argument('--database', required=True, help='Glue database name')
    parser.add_argument('--table', help='Specific table name (if not using --all-tables)')
    parser.add_argument('--all-tables', action='store_true', help='Scan all tables in database')
    parser.add_argument('--no-content-detection', action='store_true',
                       help='Skip content-based detection (faster but less accurate)')
    parser.add_argument('--no-tagging', action='store_true',
                       help='Detect PII but do not apply LF-Tags')
    parser.add_argument('--output', help='Output path for PII report (default: auto-generated)')

    args = parser.parse_args()

    # Validate arguments
    if not args.table and not args.all_tables:
        parser.error("Must specify either --table or --all-tables")

    logger.info("="*80)
    logger.info("PII DETECTION AND LAKE FORMATION TAGGING")
    logger.info("="*80)
    logger.info(f"Database: {args.database}")
    logger.info(f"Content detection: {not args.no_content_detection}")
    logger.info(f"Apply LF-Tags: {not args.no_tagging}")

    # Ensure LF-Tags exist
    if not args.no_tagging:
        ensure_lf_tags_exist()

    # Get tables to scan
    tables_to_scan = []
    if args.all_tables:
        try:
            response = glue.get_tables(DatabaseName=args.database)
            tables_to_scan = [table['Name'] for table in response['TableList']]
            logger.info(f"\nFound {len(tables_to_scan)} tables in database")
        except ClientError as e:
            logger.error(f"Error listing tables: {e}")
            return 1
    else:
        tables_to_scan = [args.table]

    # Scan each table
    all_results = {}
    for table in tables_to_scan:
        try:
            pii_results = scan_table_for_pii(
                args.database,
                table,
                content_detection=not args.no_content_detection
            )

            if pii_results:
                all_results[table] = pii_results

                # Apply tags
                if not args.no_tagging:
                    apply_lf_tags_to_columns(args.database, table, pii_results)

                # Save report
                save_pii_report(args.database, table, pii_results, args.output)
            else:
                logger.info(f"\n✓ No PII detected in {table}")

        except Exception as e:
            logger.error(f"Error processing table {table}: {e}")
            continue

    # Final summary
    logger.info("\n" + "="*80)
    logger.info("SCAN COMPLETE")
    logger.info("="*80)
    logger.info(f"Tables scanned: {len(tables_to_scan)}")
    logger.info(f"Tables with PII: {len(all_results)}")

    total_pii_columns = sum(len(results) for results in all_results.values())
    logger.info(f"Total PII columns found: {total_pii_columns}")

    if total_pii_columns > 0:
        logger.info("\nPII Summary by Sensitivity:")
        for sensitivity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            count = sum(
                1 for results in all_results.values()
                for info in results.values()
                if info['sensitivity'] == sensitivity
            )
            if count > 0:
                logger.info(f"  {sensitivity}: {count} columns")

    return 0


if __name__ == '__main__':
    exit(main())
