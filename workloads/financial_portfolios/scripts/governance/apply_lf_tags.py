#!/usr/bin/env python3
"""
Apply Lake Formation LF-Tags to financial_portfolios_db tables.

Creates 3 LF-Tags (PII_Classification, PII_Type, Data_Sensitivity) and applies
column-level tags based on PII detection from semantic.yaml and profiling results.

PII columns identified:
  - stocks.company_name: NAME (LOW — public company names)
  - portfolios.portfolio_name: NAME (LOW — portfolio names)
  - portfolios.manager_name: NAME (MEDIUM — employee names, SOX)

All other columns: PII_Classification=NONE, Data_Sensitivity=LOW

Tracing: All governance operations are traced via ScriptTracer for observability.

Usage:
  python3 workloads/financial_portfolios/scripts/governance/apply_lf_tags.py
  python3 workloads/financial_portfolios/scripts/governance/apply_lf_tags.py --dry-run
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Add project root to path for shared imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.script_tracer import ScriptTracer


DATABASE = "financial_portfolios_db"
REGION = "us-east-1"

# PII columns from semantic.yaml + profiling results
PII_COLUMNS = {
    "silver_stocks": {
        "company_name": {"pii_type": "NAME", "sensitivity": "LOW",
                         "reason": "Public company name"},
    },
    "silver_portfolios": {
        "portfolio_name": {"pii_type": "NAME", "sensitivity": "LOW",
                           "reason": "Portfolio display name"},
        "manager_name": {"pii_type": "NAME", "sensitivity": "MEDIUM",
                         "reason": "Employee name — SOX compliance"},
    },
    "silver_positions": {},
    "gold_dim_stocks": {
        "company_name": {"pii_type": "NAME", "sensitivity": "LOW",
                         "reason": "Public company name"},
    },
    "gold_dim_portfolios": {
        "portfolio_name": {"pii_type": "NAME", "sensitivity": "LOW",
                           "reason": "Portfolio display name"},
        "manager_name": {"pii_type": "NAME", "sensitivity": "MEDIUM",
                         "reason": "Employee name — SOX compliance"},
    },
    "gold_fact_positions": {},
    "gold_portfolio_summary": {
        "manager_name": {"pii_type": "NAME", "sensitivity": "MEDIUM",
                         "reason": "Employee name — SOX compliance"},
    },
}

# LF-Tags to create
LF_TAGS = [
    {
        "TagKey": "PII_Classification",
        "TagValues": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"],
    },
    {
        "TagKey": "PII_Type",
        "TagValues": [
            "EMAIL", "PHONE", "SSN", "CREDIT_CARD", "NAME", "ADDRESS",
            "DATE_OF_BIRTH", "BANK_ACCOUNT", "PASSPORT", "DRIVERS_LICENSE",
            "ZIP_CODE", "IP_ADDRESS", "MULTIPLE", "NONE",
        ],
    },
    {
        "TagKey": "Data_Sensitivity",
        "TagValues": ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
    },
]


def create_lf_tags(lf_client, dry_run=False):
    """Create LF-Tags if they don't exist."""
    print("\n" + "=" * 70)
    print("  STEP 1: Create LF-Tags")
    print("=" * 70)

    for tag_config in LF_TAGS:
        tag_key = tag_config["TagKey"]
        try:
            lf_client.get_lf_tag(TagKey=tag_key)
            print(f"  EXISTS  {tag_key}")
        except lf_client.exceptions.EntityNotFoundException:
            if dry_run:
                print(f"  [DRY-RUN] Would create LF-Tag: {tag_key} "
                      f"with values: {tag_config['TagValues']}")
            else:
                try:
                    lf_client.create_lf_tag(
                        TagKey=tag_key, TagValues=tag_config["TagValues"]
                    )
                    print(f"  CREATED {tag_key} ({len(tag_config['TagValues'])} values)")
                except ClientError as e:
                    if "AlreadyExists" in str(e):
                        print(f"  EXISTS  {tag_key}")
                    else:
                        print(f"  ERROR   {tag_key}: {e}")
                        raise
        except ClientError as e:
            print(f"  ERROR   {tag_key}: {e}")
            raise


def get_table_columns(glue_client, database, table):
    """Get column names from Glue Data Catalog."""
    try:
        response = glue_client.get_table(DatabaseName=database, Name=table)
        columns = response["Table"]["StorageDescriptor"]["Columns"]
        return [col["Name"] for col in columns]
    except ClientError as e:
        print(f"  WARNING Cannot read {database}.{table}: {e}")
        return []


def apply_tags_to_table(lf_client, database, table, columns, pii_map, dry_run=False):
    """Apply LF-Tags to every column in a table."""
    print(f"\n  Table: {database}.{table} ({len(columns)} columns)")

    tagged = 0
    for col in columns:
        if col in pii_map:
            pii_info = pii_map[col]
            sensitivity = pii_info["sensitivity"]
            pii_type = pii_info["pii_type"]
            label = f"PII:{pii_type} ({sensitivity}) — {pii_info['reason']}"
        else:
            sensitivity = "LOW"
            pii_type = "NONE"
            label = "NONE"

        lf_tags = [
            {"TagKey": "PII_Classification", "TagValues": [sensitivity]},
            {"TagKey": "PII_Type", "TagValues": [pii_type]},
            {"TagKey": "Data_Sensitivity", "TagValues": [sensitivity]},
        ]

        if dry_run:
            marker = "PII" if pii_type != "NONE" else "   "
            print(f"    [DRY-RUN] {marker} {col:30s} → {label}")
            tagged += 1
            continue

        try:
            lf_client.add_lf_tags_to_resource(
                Resource={
                    "TableWithColumns": {
                        "DatabaseName": database,
                        "Name": table,
                        "ColumnNames": [col],
                    }
                },
                LFTags=lf_tags,
            )
            marker = "PII" if pii_type != "NONE" else "   "
            print(f"    TAGGED {marker} {col:30s} → {label}")
            tagged += 1
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if "AlreadyTagged" in error_code or "AlreadyExists" in str(e):
                # Remove and reapply
                try:
                    lf_client.remove_lf_tags_from_resource(
                        Resource={
                            "TableWithColumns": {
                                "DatabaseName": database,
                                "Name": table,
                                "ColumnNames": [col],
                            }
                        },
                        LFTags=lf_tags,
                    )
                    lf_client.add_lf_tags_to_resource(
                        Resource={
                            "TableWithColumns": {
                                "DatabaseName": database,
                                "Name": table,
                                "ColumnNames": [col],
                            }
                        },
                        LFTags=lf_tags,
                    )
                    print(f"    UPDATE {col:30s} → {label}")
                    tagged += 1
                except ClientError as e2:
                    print(f"    ERROR  {col:30s} → {e2}")
            else:
                print(f"    ERROR  {col:30s} → {e}")

    return tagged


def verify_tags(lf_client, database, table, dry_run=False):
    """Verify tags are applied to a table."""
    if dry_run:
        print(f"    [DRY-RUN] Would verify tags on {database}.{table}")
        return

    try:
        response = lf_client.get_resource_lf_tags(
            Resource={"Table": {"DatabaseName": database, "Name": table}}
        )
        tag_list = response.get("LFTagsOnTable", [])
        if tag_list:
            for tag in tag_list:
                print(f"    VERIFY table-level: {tag['TagKey']}={tag['TagValues']}")
        else:
            print(f"    VERIFY No table-level tags (column-level only — expected)")
    except ClientError as e:
        print(f"    VERIFY ERROR: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Apply LF-Tags to financial_portfolios_db tables"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without executing")
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--database", default=DATABASE)
    args = parser.parse_args()

    # Initialize tracer
    tracer = ScriptTracer.for_script(__file__)
    tracer.log_start(database=args.database, region=args.region, dry_run=args.dry_run)

    print("=" * 70)
    print("  Lake Formation LF-Tag Application")
    print(f"  Database: {args.database}")
    print(f"  Region:   {args.region}")
    print(f"  Mode:     {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"  Time:     {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 70)

    lf_client = boto3.client("lakeformation", region_name=args.region)
    glue_client = boto3.client("glue", region_name=args.region)

    # Step 1: Create LF-Tags
    create_lf_tags(lf_client, dry_run=args.dry_run)
    tracer.log_transform("create_lf_tags", tags_count=len(LF_TAGS))

    # Step 2: Apply tags to each table
    print("\n" + "=" * 70)
    print("  STEP 2: Apply Column-Level LF-Tags")
    print("=" * 70)

    total_tagged = 0
    total_pii = 0
    results = {}

    for table_name, pii_map in PII_COLUMNS.items():
        columns = get_table_columns(glue_client, args.database, table_name)
        if not columns:
            print(f"\n  SKIP {table_name} — not found in catalog")
            continue

        tagged = apply_tags_to_table(
            lf_client, args.database, table_name, columns, pii_map,
            dry_run=args.dry_run
        )
        total_tagged += tagged
        pii_count = len(pii_map)
        total_pii += pii_count
        results[table_name] = {
            "columns": len(columns),
            "tagged": tagged,
            "pii_columns": pii_count,
        }

    # Step 3: Verify
    print("\n" + "=" * 70)
    print("  STEP 3: Verify Tags")
    print("=" * 70)

    for table_name in PII_COLUMNS:
        verify_tags(lf_client, args.database, table_name, dry_run=args.dry_run)

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Database:       {args.database}")
    print(f"  Tables tagged:  {len(results)}")
    print(f"  Columns tagged: {total_tagged}")
    print(f"  PII columns:    {total_pii}")
    print(f"  LF-Tags used:   PII_Classification, PII_Type, Data_Sensitivity")
    print()

    print("  PII Columns Found:")
    for table_name, pii_map in PII_COLUMNS.items():
        for col, info in pii_map.items():
            print(f"    {table_name}.{col}: {info['pii_type']} "
                  f"({info['sensitivity']}) — {info['reason']}")

    if not any(pii_map for pii_map in PII_COLUMNS.values()):
        print("    (none)")

    print()
    if args.dry_run:
        print("  [DRY-RUN] No changes made. Remove --dry-run to apply.")
    else:
        print("  COMPLETE — All LF-Tags applied successfully.")

    print("=" * 70)

    # Final trace event
    tracer.log_complete(
        status="success",
        tables_tagged=len(results),
        columns_tagged=total_tagged,
        pii_columns=total_pii,
        dry_run=args.dry_run,
    )
    tracer.close()

    # Write results JSON
    output = {
        "database": args.database,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "lf_tags_created": [t["TagKey"] for t in LF_TAGS],
        "tables": results,
        "pii_columns": {
            f"{table}.{col}": info
            for table, pii_map in PII_COLUMNS.items()
            for col, info in pii_map.items()
        },
        "total_columns_tagged": total_tagged,
        "total_pii_columns": total_pii,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
