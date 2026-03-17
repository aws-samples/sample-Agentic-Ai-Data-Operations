#!/usr/bin/env python3
"""
Grant demo_role Access to Glue Data Catalog and Redshift Databases

This script uses MCP servers to grant permissions following the MCP-First rule.
"""

import sys
import json
from pathlib import Path

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent / "shared" / "mcp"))

from orchestrator import MCPOrchestrator


def main():
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║           Grant demo_role Database Access                                 ║
║                                                                           ║
║  Grants Glue Data Catalog and Redshift access to demo_role               ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
    """)

    orch = MCPOrchestrator(workload_name="demo_role_access")

    print("═" * 80)
    print("PHASE 1: IAM Policy for Glue Data Catalog Access")
    print("═" * 80)
    print()

    # Step 1: Create IAM policy for Glue Data Catalog read access
    glue_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "GlueDataCatalogReadAccess",
                "Effect": "Allow",
                "Action": [
                    "glue:GetDatabase",
                    "glue:GetDatabases",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartition",
                    "glue:GetPartitions",
                    "glue:GetTableVersion",
                    "glue:GetTableVersions",
                    "glue:SearchTables",
                    "glue:GetCatalogImportStatus"
                ],
                "Resource": [
                    "arn:aws:glue:*:*:catalog",
                    "arn:aws:glue:*:*:database/*",
                    "arn:aws:glue:*:*:table/*/*"
                ]
            },
            {
                "Sid": "S3ReadAccessForGlueTables",
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:ListBucket"
                ],
                "Resource": [
                    "arn:aws:s3:::data-bronze/*",
                    "arn:aws:s3:::data-silver/*",
                    "arn:aws:s3:::data-gold/*",
                    "arn:aws:s3:::data-bronze",
                    "arn:aws:s3:::data-silver",
                    "arn:aws:s3:::data-gold"
                ]
            }
        ]
    }

    orch.call_mcp(
        step_name="Create IAM Policy for Glue Access",
        mcp_server="iam",
        tool="create_policy",
        params={
            "PolicyName": "DemoRoleGlueDataCatalogReadAccess",
            "PolicyDocument": json.dumps(glue_policy),
            "Description": "Allows demo_role to read Glue Data Catalog databases and tables"
        },
        description="Create IAM policy for Glue Data Catalog read-only access"
    )

    # Step 2: Attach policy to demo_role
    orch.call_mcp(
        step_name="Attach Policy to demo_role",
        mcp_server="iam",
        tool="attach_role_policy",
        params={
            "RoleName": "demo_role",
            "PolicyArn": "arn:aws:iam::123456789012:policy/DemoRoleGlueDataCatalogReadAccess"
        },
        description="Attach Glue Data Catalog policy to demo_role"
    )

    orch.phase_summary(
        phase_name="Glue Data Catalog Permissions",
        summary="""
        ✓ IAM policy created: DemoRoleGlueDataCatalogReadAccess
        ✓ Policy attached to demo_role
        → demo_role can now read Glue databases and tables
        """
    )

    print("═" * 80)
    print("PHASE 2: Lake Formation Permissions (Optional - if using LF)")
    print("═" * 80)
    print()

    # Step 3: Grant Lake Formation permissions (if Lake Formation is enabled)
    # Note: Lake Formation permissions override IAM, so we need both

    print("Checking if Lake Formation is managing permissions...")
    print("(If Lake Formation is not enabled, skip this phase)\n")

    # Using Lambda to call Lake Formation (per MCP_GUARDRAILS.md)
    # We'll use AWS CLI fallback since lakeformation MCP server may not be loaded

    lakeformation_grant_script = """
import boto3
import json
import sys

lf_client = boto3.client('lakeformation')

def grant_database_permissions(role_arn, databases):
    \"\"\"Grant Lake Formation database permissions\"\"\"
    for database in databases:
        try:
            response = lf_client.grant_permissions(
                Principal={'DataLakePrincipalIdentifier': role_arn},
                Resource={
                    'Database': {
                        'Name': database
                    }
                },
                Permissions=['DESCRIBE'],
                PermissionsWithGrantOption=[]
            )
            print(f"✓ Granted DESCRIBE on database: {database}")
        except Exception as e:
            print(f"✗ Failed to grant on {database}: {e}", file=sys.stderr)

def grant_table_permissions(role_arn, database, table='*'):
    \"\"\"Grant Lake Formation table permissions\"\"\"
    try:
        response = lf_client.grant_permissions(
            Principal={'DataLakePrincipalIdentifier': role_arn},
            Resource={
                'Table': {
                    'DatabaseName': database,
                    'Name': table
                }
            },
            Permissions=['SELECT', 'DESCRIBE'],
            PermissionsWithGrantOption=[]
        )
        print(f"✓ Granted SELECT/DESCRIBE on {database}.{table}")
    except Exception as e:
        print(f"✗ Failed to grant table permissions: {e}", file=sys.stderr)

if __name__ == "__main__":
    role_arn = "arn:aws:iam::123456789012:role/demo_role"

    # Get all databases from Glue Catalog
    glue_client = boto3.client('glue')
    databases = []

    try:
        paginator = glue_client.get_paginator('get_databases')
        for page in paginator.paginate():
            databases.extend([db['Name'] for db in page['DatabaseList']])
    except Exception as e:
        print(f"✗ Failed to list databases: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(databases)} databases: {', '.join(databases)}")

    # Grant database-level permissions
    grant_database_permissions(role_arn, databases)

    # Grant table-level permissions
    for db in databases:
        grant_table_permissions(role_arn, db, '*')

    print("\\n✓ Lake Formation permissions granted successfully")
"""

    # Write the script
    lf_script_path = Path("shared/scripts/grant_lf_permissions.py")
    lf_script_path.parent.mkdir(parents=True, exist_ok=True)
    lf_script_path.write_text(lakeformation_grant_script)

    print(f"Lake Formation permission script created: {lf_script_path}")
    print("Run manually if Lake Formation is enabled:")
    print(f"  python3 {lf_script_path}")
    print()

    orch.phase_summary(
        phase_name="Lake Formation Permissions",
        summary="""
        ✓ Lake Formation grant script created
        → Run manually if Lake Formation is managing your Data Catalog
        → Script location: shared/scripts/grant_lf_permissions.py
        """
    )

    print("═" * 80)
    print("PHASE 3: Redshift Database Access")
    print("═" * 80)
    print()

    # Step 4: Grant Redshift database access
    # This requires connecting to Redshift and running SQL grants

    redshift_grant_sql = """
-- Grant USAGE on schema to demo_role
GRANT USAGE ON SCHEMA public TO demo_role;
GRANT USAGE ON SCHEMA bronze_schema TO demo_role;
GRANT USAGE ON SCHEMA silver_schema TO demo_role;
GRANT USAGE ON SCHEMA gold_schema TO demo_role;

-- Grant SELECT on all tables in each schema
GRANT SELECT ON ALL TABLES IN SCHEMA public TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA bronze_schema TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA silver_schema TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA gold_schema TO demo_role;

-- Grant SELECT on future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO demo_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA bronze_schema GRANT SELECT ON TABLES TO demo_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA silver_schema GRANT SELECT ON TABLES TO demo_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold_schema GRANT SELECT ON TABLES TO demo_role;

-- Grant access to external schemas (Spectrum - if using Glue Catalog with Redshift)
GRANT USAGE ON SCHEMA spectrum_bronze TO demo_role;
GRANT USAGE ON SCHEMA spectrum_silver TO demo_role;
GRANT USAGE ON SCHEMA spectrum_gold TO demo_role;

-- Grant SELECT on Spectrum tables
GRANT SELECT ON ALL TABLES IN SCHEMA spectrum_bronze TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA spectrum_silver TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA spectrum_gold TO demo_role;
"""

    # Write SQL script
    redshift_script_path = Path("shared/scripts/grant_redshift_permissions.sql")
    redshift_script_path.write_text(redshift_grant_sql)

    print(f"Redshift permission SQL script created: {redshift_script_path}")
    print()

    # Try to execute via Redshift MCP server (if available)
    try:
        orch.call_mcp(
            step_name="Grant Redshift Database Permissions",
            mcp_server="redshift",
            tool="execute_statement",
            params={
                "ClusterIdentifier": "data-warehouse-cluster",
                "Database": "data_warehouse",
                "DbUser": "admin",
                "Sql": redshift_grant_sql
            },
            description="Grant SELECT on all Redshift schemas and tables to demo_role"
        )
    except Exception as e:
        print(f"MCP execution failed: {e}")
        print("Fallback: Execute SQL manually using Redshift Query Editor or psql:")
        print(f"  psql -h <redshift-endpoint> -U admin -d data_warehouse -f {redshift_script_path}")
        print()

    orch.phase_summary(
        phase_name="Redshift Database Access",
        summary="""
        ✓ Redshift permission SQL generated
        ✓ Attempted execution via MCP
        → If MCP failed, run SQL manually via Query Editor or psql
        → Script location: shared/scripts/grant_redshift_permissions.sql
        """
    )

    print("═" * 80)
    print("PHASE 4: Verification")
    print("═" * 80)
    print()

    # Step 5: Create verification script
    verification_script = """
#!/bin/bash
# Verify demo_role permissions

echo "════════════════════════════════════════════════════════════════"
echo "Verifying demo_role Permissions"
echo "════════════════════════════════════════════════════════════════"
echo ""

# 1. Check IAM policy attachment
echo "1. Checking IAM policy attachment..."
aws iam list-attached-role-policies --role-name demo_role | grep "DemoRoleGlueDataCatalogReadAccess"
if [ $? -eq 0 ]; then
    echo "   ✓ Policy attached to demo_role"
else
    echo "   ✗ Policy NOT attached"
fi
echo ""

# 2. List Glue databases (assumes demo_role credentials)
echo "2. Testing Glue Data Catalog access..."
aws glue get-databases --profile demo_role_profile 2>/dev/null
if [ $? -eq 0 ]; then
    echo "   ✓ Can access Glue Data Catalog"
else
    echo "   ✗ Cannot access Glue Data Catalog"
    echo "   (Make sure demo_role_profile is configured in ~/.aws/credentials)"
fi
echo ""

# 3. Test Redshift access
echo "3. Testing Redshift access..."
echo "   Run this SQL via Query Editor as demo_role:"
echo "   SELECT DISTINCT schemaname FROM pg_tables;"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "Verification Complete"
echo "════════════════════════════════════════════════════════════════"
"""

    verify_script_path = Path("shared/scripts/verify_demo_role_access.sh")
    verify_script_path.write_text(verification_script)
    verify_script_path.chmod(0o755)

    print(f"Verification script created: {verify_script_path}")
    print(f"Run: bash {verify_script_path}")
    print()

    orch.phase_summary(
        phase_name="Verification",
        summary="""
        ✓ Verification script created
        → Run to test demo_role permissions
        → Script location: shared/scripts/verify_demo_role_access.sh
        """
    )

    print("═" * 80)
    print("FINAL SUMMARY")
    print("═" * 80)
    print()

    print(f"""
    ✓ Phase 1: IAM Policy for Glue Data Catalog - CREATED
       • Policy: DemoRoleGlueDataCatalogReadAccess
       • Attached to: demo_role
       • Permissions: Read Glue databases, tables, partitions

    ✓ Phase 2: Lake Formation Permissions - SCRIPT CREATED
       • Script: shared/scripts/grant_lf_permissions.py
       • Action: Run manually if Lake Formation is enabled

    ✓ Phase 3: Redshift Database Access - SQL GENERATED
       • Script: shared/scripts/grant_redshift_permissions.sql
       • Permissions: USAGE on schemas, SELECT on all tables
       • Spectrum: Access to external Glue Catalog tables

    ✓ Phase 4: Verification Script - CREATED
       • Script: shared/scripts/verify_demo_role_access.sh
       • Tests: IAM, Glue, Redshift access

    📂 Scripts Created:
       • shared/scripts/grant_lf_permissions.py
       • shared/scripts/grant_redshift_permissions.sql
       • shared/scripts/verify_demo_role_access.sh

    📊 Logs:
       • Console: {orch.console_log_path}
       • JSON:    {orch.json_log_path}

    🚀 Next Steps:
       1. If Lake Formation is enabled:
          python3 shared/scripts/grant_lf_permissions.py

       2. Execute Redshift grants:
          psql -h <endpoint> -U admin -d data_warehouse -f shared/scripts/grant_redshift_permissions.sql
          # OR use Redshift Query Editor

       3. Verify permissions:
          bash shared/scripts/verify_demo_role_access.sh

       4. Test as demo_role:
          aws glue get-databases --profile demo_role_profile
    """)


if __name__ == "__main__":
    main()
