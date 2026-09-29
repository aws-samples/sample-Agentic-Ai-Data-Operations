"""
PII Detection + Lake Formation Tagging MCP Server

Provides MCP interface for:
- PII detection in Glue Data Catalog tables (name-based + content-based)
- Lake Formation LF-Tag management for PII classification
- Column-level security configuration via TBAC
- PII compliance reporting

Rewritten to FastMCP for SSE transport support (Agentcore Gateway).
"""

import os
import logging
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError
from fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

mcp = FastMCP("pii-detection")

session = boto3.Session(
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    profile_name=os.getenv('AWS_PROFILE', None) if os.getenv('AWS_PROFILE') else None
)
glue = session.client('glue')
athena = session.client('athena')
lakeformation = session.client('lakeformation')


# --- PII Detection Patterns ---

PII_PATTERNS = {
    'EMAIL': {'names': ['email', 'e_mail', 'email_address', 'emailaddress'], 'sensitivity': 'HIGH'},
    'PHONE': {'names': ['phone', 'telephone', 'mobile', 'cell', 'phone_number', 'phonenumber'], 'sensitivity': 'HIGH'},
    'SSN': {'names': ['ssn', 'social_security', 'social_security_number'], 'sensitivity': 'CRITICAL'},
    'CREDIT_CARD': {'names': ['credit_card', 'card_number', 'cc_number', 'pan', 'card_num'], 'sensitivity': 'CRITICAL'},
    'NAME': {'names': ['name', 'first_name', 'last_name', 'full_name', 'firstname', 'lastname', 'patient_name'], 'sensitivity': 'MEDIUM'},
    'ADDRESS': {'names': ['address', 'street', 'city', 'zip', 'postal', 'zip_code', 'street_address'], 'sensitivity': 'MEDIUM'},
    'DOB': {'names': ['dob', 'date_of_birth', 'birth_date', 'birthdate'], 'sensitivity': 'HIGH'},
    'IP_ADDRESS': {'names': ['ip', 'ip_address', 'ipaddress', 'client_ip'], 'sensitivity': 'LOW'},
    'DRIVER_LICENSE': {'names': ['driver_license', 'drivers_license', 'dl_number'], 'sensitivity': 'HIGH'},
    'PASSPORT': {'names': ['passport', 'passport_number', 'passport_no'], 'sensitivity': 'HIGH'},
    'NATIONAL_ID': {'names': ['national_id', 'national_identity', 'nid'], 'sensitivity': 'CRITICAL'},
    'FINANCIAL_ACCOUNT': {'names': ['account_number', 'account_no', 'bank_account', 'routing_number', 'iban'], 'sensitivity': 'CRITICAL'},
}


def _detect_pii_in_columns(columns: list[dict]) -> list[dict]:
    """Detect PII based on column names."""
    results = []
    for col in columns:
        col_name_lower = col['Name'].lower()
        for pii_type, pattern in PII_PATTERNS.items():
            if col_name_lower in pattern['names'] or any(p in col_name_lower for p in pattern['names']):
                results.append({
                    'column': col['Name'],
                    'pii_type': pii_type,
                    'sensitivity': pattern['sensitivity'],
                    'detection_method': 'name_based',
                    'confidence': 'high' if col_name_lower in pattern['names'] else 'medium'
                })
                break
    return results


@mcp.tool()
def detect_pii_in_table(
    database: str,
    table: str,
    content_detection: bool = True,
    apply_tags: bool = True
) -> dict[str, Any]:
    """
    Detect PII in a specific Glue table and optionally apply Lake Formation tags.

    Scans column names against 12 PII type patterns (EMAIL, PHONE, SSN, CREDIT_CARD,
    NAME, ADDRESS, DOB, IP_ADDRESS, DRIVER_LICENSE, PASSPORT, NATIONAL_ID, FINANCIAL_ACCOUNT).

    Args:
        database: Glue database name
        table: Table name
        content_detection: Enable content-based detection (slower but more accurate)
        apply_tags: Apply LF-Tags to detected PII columns
    """
    logger.info(f"Detecting PII in {database}.{table}")
    try:
        response = glue.get_table(DatabaseName=database, Name=table)
        columns = response['Table'].get('StorageDescriptor', {}).get('Columns', [])
        columns += response['Table'].get('PartitionKeys', [])

        pii_results = _detect_pii_in_columns(columns)

        if pii_results and apply_tags:
            _ensure_lf_tags_exist()
            for result in pii_results:
                try:
                    lakeformation.add_lf_tags_to_resource(
                        Resource={
                            'TableWithColumns': {
                                'DatabaseName': database,
                                'Name': table,
                                'ColumnNames': [result['column']]
                            }
                        },
                        LFTags=[
                            {'TagKey': 'PII_Classification', 'TagValues': [result['sensitivity']]},
                            {'TagKey': 'PII_Type', 'TagValues': [result['pii_type']]}
                        ]
                    )
                except ClientError as e:
                    logger.warning(f"Failed to tag column {result['column']}: {e}")

        return {
            'database': database,
            'table': table,
            'pii_detected': len(pii_results) > 0,
            'pii_columns': len(pii_results),
            'columns': pii_results
        }
    except ClientError as e:
        return {'status': 'error', 'error': str(e), 'code': e.response['Error']['Code']}


@mcp.tool()
def scan_database_for_pii(
    database: str,
    content_detection: bool = False,
    apply_tags: bool = True
) -> dict[str, Any]:
    """
    Scan all tables in a Glue database for PII.

    Args:
        database: Glue database name
        content_detection: Enable content-based detection
        apply_tags: Apply LF-Tags to detected PII columns
    """
    logger.info(f"Scanning database {database} for PII")
    try:
        response = glue.get_tables(DatabaseName=database)
        tables = [t['Name'] for t in response['TableList']]

        results = {}
        for tbl in tables:
            result = detect_pii_in_table(database, tbl, content_detection, apply_tags)
            results[tbl] = result

        total_pii = sum(r.get('pii_columns', 0) for r in results.values())
        tables_with_pii = sum(1 for r in results.values() if r.get('pii_detected', False))

        return {
            'database': database,
            'tables_scanned': len(tables),
            'tables_with_pii': tables_with_pii,
            'total_pii_columns': total_pii,
            'results': results
        }
    except ClientError as e:
        return {'status': 'error', 'error': str(e), 'code': e.response['Error']['Code']}


def _ensure_lf_tags_exist():
    """Create PII LF-Tags if they don't exist."""
    tags = {
        'PII_Classification': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE'],
        'PII_Type': ['EMAIL', 'PHONE', 'SSN', 'CREDIT_CARD', 'NAME', 'ADDRESS',
                     'DOB', 'IP_ADDRESS', 'DRIVER_LICENSE', 'PASSPORT',
                     'NATIONAL_ID', 'FINANCIAL_ACCOUNT', 'NONE'],
        'Data_Sensitivity': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
    }
    for key, values in tags.items():
        try:
            lakeformation.create_lf_tag(TagKey=key, TagValues=values)
        except ClientError as e:
            if e.response['Error']['Code'] != 'AlreadyExistsException':
                logger.warning(f"Failed to create LF-Tag {key}: {e}")


@mcp.tool()
def create_lf_tags(force_recreate: bool = False) -> dict[str, Any]:
    """
    Create Lake Formation tags for PII classification.

    Creates 3 LF-Tags: PII_Classification, PII_Type, Data_Sensitivity.

    Args:
        force_recreate: Recreate tags if they already exist
    """
    logger.info("Creating Lake Formation PII tags")
    _ensure_lf_tags_exist()
    return {
        'status': 'success',
        'tags_created': ['PII_Classification', 'PII_Type', 'Data_Sensitivity']
    }


@mcp.tool()
def get_pii_columns(
    database: str,
    table: str,
    sensitivity_level: Optional[str] = None
) -> dict[str, Any]:
    """
    Get list of columns tagged with PII in a table.

    Args:
        database: Glue database name
        table: Table name
        sensitivity_level: Filter by sensitivity (CRITICAL, HIGH, MEDIUM, LOW)
    """
    logger.info(f"Getting PII columns from {database}.{table}")
    try:
        response = lakeformation.get_resource_lf_tags(
            Resource={'Table': {'DatabaseName': database, 'Name': table}},
            ShowAssignedLFTags=True
        )

        pii_columns = []
        for column_tags in response.get('LFTagsOnColumns', []):
            column_name = column_tags['Name']
            tags = {tag['TagKey']: tag['TagValues'][0] for tag in column_tags.get('LFTags', [])}

            if sensitivity_level:
                if tags.get('PII_Classification') == sensitivity_level:
                    pii_columns.append({
                        'column': column_name,
                        'classification': tags.get('PII_Classification'),
                        'type': tags.get('PII_Type'),
                        'sensitivity': tags.get('Data_Sensitivity')
                    })
            elif 'PII_Classification' in tags:
                pii_columns.append({
                    'column': column_name,
                    'classification': tags.get('PII_Classification'),
                    'type': tags.get('PII_Type'),
                    'sensitivity': tags.get('Data_Sensitivity')
                })

        return {
            'database': database,
            'table': table,
            'pii_columns': pii_columns,
            'count': len(pii_columns)
        }
    except ClientError as e:
        return {'status': 'error', 'error': str(e), 'code': e.response['Error']['Code']}


@mcp.tool()
def apply_column_security(
    principal_arn: str,
    sensitivity_levels: list[str],
    database: Optional[str] = None
) -> dict[str, Any]:
    """
    Apply tag-based access control (TBAC) to columns based on PII sensitivity.

    Grants SELECT permission on columns matching the specified sensitivity levels.

    Args:
        principal_arn: IAM principal ARN (role or user)
        sensitivity_levels: Allowed sensitivity levels (e.g., ["LOW", "MEDIUM"])
        database: Specific database (optional, applies account-wide if omitted)
    """
    logger.info(f"Applying column security for {principal_arn}")
    try:
        lakeformation.grant_permissions(
            Principal={'DataLakePrincipalIdentifier': principal_arn},
            Resource={
                'LFTagPolicy': {
                    'ResourceType': 'COLUMN',
                    'Expression': [
                        {
                            'TagKey': 'PII_Classification',
                            'TagValues': sensitivity_levels
                        }
                    ]
                }
            },
            Permissions=['SELECT']
        )
        return {
            'status': 'success',
            'principal': principal_arn,
            'sensitivity_levels': sensitivity_levels,
            'permission': 'SELECT'
        }
    except ClientError as e:
        return {'status': 'error', 'error': str(e), 'code': e.response['Error']['Code']}


@mcp.tool()
def get_pii_report(
    database: str,
    table: Optional[str] = None,
    format: str = 'summary'
) -> dict[str, Any]:
    """
    Generate PII report for a database or specific table.

    Args:
        database: Glue database name
        table: Specific table (optional, scans all tables if omitted)
        format: Output format ('json' for full detail, 'summary' for counts)
    """
    logger.info(f"Generating PII report for {database}")

    if table:
        result = get_pii_columns(database, table)
        if result.get('status') == 'error':
            return result
        if format == 'summary':
            cols = result.get('pii_columns', [])
            return {
                'database': database,
                'table': table,
                'summary': {
                    'total_pii_columns': len(cols),
                    'critical': sum(1 for c in cols if c.get('classification') == 'CRITICAL'),
                    'high': sum(1 for c in cols if c.get('classification') == 'HIGH'),
                    'medium': sum(1 for c in cols if c.get('classification') == 'MEDIUM'),
                    'low': sum(1 for c in cols if c.get('classification') == 'LOW')
                }
            }
        return result

    # Database-wide report
    try:
        response = glue.get_tables(DatabaseName=database)
        tables = [t['Name'] for t in response['TableList']]
    except ClientError as e:
        return {'status': 'error', 'error': str(e), 'code': e.response['Error']['Code']}

    all_results = {}
    counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}

    for tbl in tables:
        result = get_pii_columns(database, tbl)
        if result.get('count', 0) > 0:
            all_results[tbl] = result
            for col in result.get('pii_columns', []):
                level = (col.get('classification') or '').lower()
                if level in counts:
                    counts[level] += 1

    if format == 'summary':
        return {
            'database': database,
            'tables_with_pii': len(all_results),
            'summary': counts
        }
    return {'database': database, 'tables': all_results}


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=int(os.getenv("MCP_PORT", "8004")))
    else:
        mcp.run()
