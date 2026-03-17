#!/usr/bin/env python3
"""
Grant comprehensive access to a principal for the US Mutual Funds & ETF workload.

This script grants access to:
1. Backend: S3, Glue Data Catalog, Lake Formation
2. Tables: All Gold zone Iceberg tables
3. QuickSight: Dashboard view permissions

Usage:
    python3 grant_access_to_principal.py --principal demo-role/demo-user
"""

import boto3
import sys
import time
import argparse
from typing import Dict, List, Tuple
from botocore.exceptions import ClientError

# ============================================================================
# CONFIGURATION
# ============================================================================

AWS_REGION = "us-east-1"
ACCOUNT_ID = None  # Will be auto-detected from STS

# S3 Bucket
S3_BUCKET = "your-datalake-bucket"

# Glue Databases
SILVER_DATABASE = "finsights_silver"
GOLD_DATABASE = "finsights_gold"

# Gold Tables
GOLD_TABLES = [
    "dim_fund",
    "dim_category",
    "dim_date",
    "fact_fund_performance"
]

# QuickSight Resources
QUICKSIGHT_DASHBOARD_ID = "finsights-finance-dashboard"
QUICKSIGHT_ANALYSIS_ID = "finsights-finance-analysis"
QUICKSIGHT_NAMESPACE = "default"

# IAM Policy Name
POLICY_NAME = "FinsightsWorkloadAccess"

# ============================================================================
# AWS CLIENTS
# ============================================================================

sts_client = boto3.client('sts', region_name=AWS_REGION)
iam_client = boto3.client('iam', region_name=AWS_REGION)
s3_client = boto3.client('s3', region_name=AWS_REGION)
glue_client = boto3.client('glue', region_name=AWS_REGION)
lakeformation_client = boto3.client('lakeformation', region_name=AWS_REGION)
quicksight_client = boto3.client('quicksight', region_name=AWS_REGION)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_account_id() -> str:
    """Get AWS account ID from STS."""
    response = sts_client.get_caller_identity()
    return response['Account']


def parse_principal(principal_input: str) -> Tuple[str, str]:
    """
    Parse principal input.

    Examples:
        "demo-role/demo-user" → ("arn:aws:iam::ACCOUNT:role/demo-role", "demo-user")
        "arn:aws:iam::123456789012:role/MyRole" → (arn, None)

    Returns:
        (role_arn, user_suffix)
    """
    global ACCOUNT_ID
    ACCOUNT_ID = get_account_id()

    if principal_input.startswith("arn:"):
        # Already an ARN
        return (principal_input, None)

    if "/" in principal_input:
        # Format: role-name/user-suffix
        role_name, user_suffix = principal_input.split("/", 1)
        role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{role_name}"
        return (role_arn, user_suffix)

    # Assume it's just a role name
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{principal_input}"
    return (role_arn, None)


def verify_role_exists(role_arn: str) -> bool:
    """Verify IAM role exists."""
    role_name = role_arn.split("/")[-1]
    try:
        iam_client.get_role(RoleName=role_name)
        print(f"✅ [VERIFY] Role exists: {role_name}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            print(f"❌ [ERROR] Role does not exist: {role_name}")
            print(f"   ARN attempted: {role_arn}")
            print(f"   Please create this role first or verify the role name.")
            return False
        raise


def retry_with_backoff(func, max_retries=3, initial_delay=2):
    """Retry a function with exponential backoff."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return func()
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ThrottlingException' and attempt < max_retries - 1:
                print(f"   ⚠️  Throttled, retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                raise
    raise Exception(f"Failed after {max_retries} retries")


# ============================================================================
# STEP 1: GRANT IAM POLICY (S3 + Glue + Lake Formation Read Access)
# ============================================================================

def grant_iam_policy(role_arn: str) -> Dict:
    """
    Attach inline IAM policy to role for S3, Glue, and Lake Formation access.
    """
    print("\n" + "="*80)
    print("STEP 1: Grant IAM Policy for Backend Access")
    print("="*80)

    role_name = role_arn.split("/")[-1]

    # Define inline policy
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "S3ReadAccess",
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:GetBucketLocation"
                ],
                "Resource": [
                    f"arn:aws:s3:::{S3_BUCKET}",
                    f"arn:aws:s3:::{S3_BUCKET}/*"
                ]
            },
            {
                "Sid": "GlueReadAccess",
                "Effect": "Allow",
                "Action": [
                    "glue:GetDatabase",
                    "glue:GetDatabases",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartition",
                    "glue:GetPartitions",
                    "glue:BatchGetPartition"
                ],
                "Resource": [
                    f"arn:aws:glue:{AWS_REGION}:{ACCOUNT_ID}:catalog",
                    f"arn:aws:glue:{AWS_REGION}:{ACCOUNT_ID}:database/{SILVER_DATABASE}",
                    f"arn:aws:glue:{AWS_REGION}:{ACCOUNT_ID}:database/{GOLD_DATABASE}",
                    f"arn:aws:glue:{AWS_REGION}:{ACCOUNT_ID}:table/{SILVER_DATABASE}/*",
                    f"arn:aws:glue:{AWS_REGION}:{ACCOUNT_ID}:table/{GOLD_DATABASE}/*"
                ]
            },
            {
                "Sid": "LakeFormationReadAccess",
                "Effect": "Allow",
                "Action": [
                    "lakeformation:GetDataAccess"
                ],
                "Resource": "*"
            },
            {
                "Sid": "AthenaQueryAccess",
                "Effect": "Allow",
                "Action": [
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:StopQueryExecution",
                    "athena:GetWorkGroup"
                ],
                "Resource": f"arn:aws:athena:{AWS_REGION}:{ACCOUNT_ID}:workgroup/*"
            }
        ]
    }

    try:
        def put_policy():
            return iam_client.put_role_policy(
                RoleName=role_name,
                PolicyName=POLICY_NAME,
                PolicyDocument=str(policy_document).replace("'", '"')
            )

        response = retry_with_backoff(put_policy)
        print(f"✅ [IAM] Inline policy '{POLICY_NAME}' attached to {role_name}")
        print(f"   Grants: S3 read, Glue read, Lake Formation data access, Athena query")
        return {"status": "success", "policy_name": POLICY_NAME}

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchEntity':
            print(f"❌ [ERROR] Role not found: {role_name}")
            return {"status": "failed", "error": "Role not found"}
        else:
            print(f"❌ [ERROR] Failed to attach policy: {e}")
            return {"status": "failed", "error": str(e)}


# ============================================================================
# STEP 2: GRANT LAKE FORMATION TABLE PERMISSIONS
# ============================================================================

def grant_lake_formation_permissions(role_arn: str) -> Dict:
    """
    Grant Lake Formation SELECT permissions on all Gold tables.
    """
    print("\n" + "="*80)
    print("STEP 2: Grant Lake Formation Table Permissions")
    print("="*80)

    results = []

    # Grant database-level permissions first
    try:
        def grant_db():
            return lakeformation_client.grant_permissions(
                Principal={'DataLakePrincipalIdentifier': role_arn},
                Resource={'Database': {'Name': GOLD_DATABASE}},
                Permissions=['DESCRIBE']
            )

        retry_with_backoff(grant_db)
        print(f"✅ [LF] Database DESCRIBE granted: {GOLD_DATABASE}")
        results.append({"resource": f"database:{GOLD_DATABASE}", "status": "success"})

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'AlreadyExistsException':
            print(f"   ℹ️  Permission already exists for database {GOLD_DATABASE}")
            results.append({"resource": f"database:{GOLD_DATABASE}", "status": "already_exists"})
        else:
            print(f"❌ [ERROR] Failed to grant database permission: {e}")
            results.append({"resource": f"database:{GOLD_DATABASE}", "status": "failed", "error": str(e)})

    # Grant table-level permissions
    for table_name in GOLD_TABLES:
        try:
            def grant_table():
                return lakeformation_client.grant_permissions(
                    Principal={'DataLakePrincipalIdentifier': role_arn},
                    Resource={
                        'Table': {
                            'DatabaseName': GOLD_DATABASE,
                            'Name': table_name
                        }
                    },
                    Permissions=['SELECT', 'DESCRIBE']
                )

            retry_with_backoff(grant_table)
            print(f"✅ [LF] Table SELECT granted: {GOLD_DATABASE}.{table_name}")
            results.append({"resource": f"table:{GOLD_DATABASE}.{table_name}", "status": "success"})

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AlreadyExistsException':
                print(f"   ℹ️  Permission already exists for {GOLD_DATABASE}.{table_name}")
                results.append({"resource": f"table:{GOLD_DATABASE}.{table_name}", "status": "already_exists"})
            else:
                print(f"❌ [ERROR] Failed to grant permission on {table_name}: {e}")
                results.append({"resource": f"table:{GOLD_DATABASE}.{table_name}", "status": "failed", "error": str(e)})

    success_count = sum(1 for r in results if r["status"] in ["success", "already_exists"])
    print(f"\n📊 Summary: {success_count}/{len(results)} Lake Formation grants successful")

    return {"status": "success", "grants": results}


# ============================================================================
# STEP 3: GRANT QUICKSIGHT DASHBOARD ACCESS
# ============================================================================

def grant_quicksight_access(role_arn: str, user_suffix: str) -> Dict:
    """
    Grant QuickSight dashboard view permissions.

    For federated users, QuickSight principal format is:
        arn:aws:quicksight:us-east-1:ACCOUNT_ID:user/default/demo-role/USER_SUFFIX
    """
    print("\n" + "="*80)
    print("STEP 3: Grant QuickSight Dashboard Access")
    print("="*80)

    # Construct QuickSight user ARN
    role_name = role_arn.split("/")[-1]

    if user_suffix:
        qs_principal_arn = f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:user/{QUICKSIGHT_NAMESPACE}/{role_name}/{user_suffix}"
        print(f"   QuickSight principal: {qs_principal_arn}")
    else:
        # If no user suffix, try to use role ARN directly (less common)
        qs_principal_arn = role_arn
        print(f"   ℹ️  No user suffix provided, using role ARN: {role_arn}")
        print(f"   Note: QuickSight typically requires user-level principals, not role ARNs")

    results = []

    # Grant dashboard permissions
    try:
        def grant_dashboard():
            return quicksight_client.update_dashboard_permissions(
                AwsAccountId=ACCOUNT_ID,
                DashboardId=QUICKSIGHT_DASHBOARD_ID,
                GrantPermissions=[
                    {
                        'Principal': qs_principal_arn,
                        'Actions': [
                            'quicksight:DescribeDashboard',
                            'quicksight:ListDashboardVersions',
                            'quicksight:QueryDashboard'
                        ]
                    }
                ]
            )

        response = retry_with_backoff(grant_dashboard)
        print(f"✅ [QS] Dashboard view access granted: {QUICKSIGHT_DASHBOARD_ID}")
        results.append({"resource": f"dashboard:{QUICKSIGHT_DASHBOARD_ID}", "status": "success"})

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            print(f"❌ [ERROR] Dashboard not found: {QUICKSIGHT_DASHBOARD_ID}")
            print(f"   Make sure the dashboard is published first.")
            results.append({"resource": f"dashboard:{QUICKSIGHT_DASHBOARD_ID}", "status": "not_found"})
        elif error_code == 'ConflictException':
            print(f"   ℹ️  Permission already exists for dashboard")
            results.append({"resource": f"dashboard:{QUICKSIGHT_DASHBOARD_ID}", "status": "already_exists"})
        else:
            print(f"❌ [ERROR] Failed to grant dashboard access: {e}")
            results.append({"resource": f"dashboard:{QUICKSIGHT_DASHBOARD_ID}", "status": "failed", "error": str(e)})

    # Grant analysis permissions (optional, for edit access)
    try:
        def grant_analysis():
            return quicksight_client.update_analysis_permissions(
                AwsAccountId=ACCOUNT_ID,
                AnalysisId=QUICKSIGHT_ANALYSIS_ID,
                GrantPermissions=[
                    {
                        'Principal': qs_principal_arn,
                        'Actions': [
                            'quicksight:DescribeAnalysis',
                            'quicksight:QueryAnalysis'
                        ]
                    }
                ]
            )

        response = retry_with_backoff(grant_analysis)
        print(f"✅ [QS] Analysis view access granted: {QUICKSIGHT_ANALYSIS_ID}")
        results.append({"resource": f"analysis:{QUICKSIGHT_ANALYSIS_ID}", "status": "success"})

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            print(f"   ℹ️  Analysis not found (may not be published yet)")
            results.append({"resource": f"analysis:{QUICKSIGHT_ANALYSIS_ID}", "status": "not_found"})
        elif error_code == 'ConflictException':
            print(f"   ℹ️  Permission already exists for analysis")
            results.append({"resource": f"analysis:{QUICKSIGHT_ANALYSIS_ID}", "status": "already_exists"})
        else:
            print(f"   ⚠️  Failed to grant analysis access (non-critical): {e}")
            results.append({"resource": f"analysis:{QUICKSIGHT_ANALYSIS_ID}", "status": "failed", "error": str(e)})

    return {"status": "success", "grants": results}


# ============================================================================
# STEP 4: VERIFICATION
# ============================================================================

def verify_access(role_arn: str) -> Dict:
    """
    Verify all access grants are in place.
    """
    print("\n" + "="*80)
    print("STEP 4: Verify Access Grants")
    print("="*80)

    role_name = role_arn.split("/")[-1]
    checks = []

    # Check IAM policy
    try:
        response = iam_client.get_role_policy(
            RoleName=role_name,
            PolicyName=POLICY_NAME
        )
        print(f"✅ [VERIFY] IAM policy exists: {POLICY_NAME}")
        checks.append({"check": "iam_policy", "status": "pass"})
    except ClientError:
        print(f"❌ [VERIFY] IAM policy not found: {POLICY_NAME}")
        checks.append({"check": "iam_policy", "status": "fail"})

    # Check Lake Formation permissions
    try:
        response = lakeformation_client.list_permissions(
            Principal={'DataLakePrincipalIdentifier': role_arn},
            Resource={'Database': {'Name': GOLD_DATABASE}}
        )
        if response['PrincipalResourcePermissions']:
            print(f"✅ [VERIFY] Lake Formation database permissions exist")
            checks.append({"check": "lf_database", "status": "pass"})
        else:
            print(f"❌ [VERIFY] No Lake Formation database permissions found")
            checks.append({"check": "lf_database", "status": "fail"})
    except ClientError as e:
        print(f"❌ [VERIFY] Failed to check Lake Formation permissions: {e}")
        checks.append({"check": "lf_database", "status": "error"})

    # Check QuickSight dashboard permissions
    try:
        response = quicksight_client.describe_dashboard_permissions(
            AwsAccountId=ACCOUNT_ID,
            DashboardId=QUICKSIGHT_DASHBOARD_ID
        )
        # Check if our principal is in the permissions list
        principal_found = any(
            role_name in perm.get('Principal', '')
            for perm in response.get('Permissions', [])
        )
        if principal_found:
            print(f"✅ [VERIFY] QuickSight dashboard permissions exist")
            checks.append({"check": "quicksight_dashboard", "status": "pass"})
        else:
            print(f"❌ [VERIFY] Principal not found in dashboard permissions")
            checks.append({"check": "quicksight_dashboard", "status": "fail"})
    except ClientError as e:
        print(f"   ⚠️  Could not verify QuickSight permissions: {e}")
        checks.append({"check": "quicksight_dashboard", "status": "unknown"})

    pass_count = sum(1 for c in checks if c["status"] == "pass")
    print(f"\n📊 Verification: {pass_count}/{len(checks)} checks passed")

    return {"checks": checks, "pass_count": pass_count, "total_count": len(checks)}


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution flow."""
    parser = argparse.ArgumentParser(
        description="Grant comprehensive access to a principal for US Mutual Funds & ETF workload"
    )
    parser.add_argument(
        '--principal',
        required=True,
        help='Principal to grant access to (e.g., "demo-role/demo-user" or full ARN)'
    )
    parser.add_argument(
        '--skip-iam',
        action='store_true',
        help='Skip IAM policy attachment (if already granted)'
    )
    parser.add_argument(
        '--skip-lf',
        action='store_true',
        help='Skip Lake Formation grants (if already granted)'
    )
    parser.add_argument(
        '--skip-qs',
        action='store_true',
        help='Skip QuickSight access grants'
    )

    args = parser.parse_args()

    print("="*80)
    print("🚀 GRANT ACCESS TO PRINCIPAL")
    print("="*80)
    print(f"Principal: {args.principal}")
    print(f"Region: {AWS_REGION}")
    print(f"Bucket: {S3_BUCKET}")
    print(f"Gold Database: {GOLD_DATABASE}")
    print(f"QuickSight Dashboard: {QUICKSIGHT_DASHBOARD_ID}")
    print("="*80)

    # Parse principal
    role_arn, user_suffix = parse_principal(args.principal)
    print(f"\nParsed:")
    print(f"  Role ARN: {role_arn}")
    print(f"  User Suffix: {user_suffix or '(none)'}")

    # Verify role exists
    if not verify_role_exists(role_arn):
        print("\n❌ ABORTED: Role does not exist. Please create it first or verify the name.")
        sys.exit(1)

    # Execute grants in parallel (conceptually - Python GIL limits true parallelism)
    results = {}

    if not args.skip_iam:
        results['iam'] = grant_iam_policy(role_arn)
    else:
        print("\n⏭️  Skipping IAM policy attachment (--skip-iam)")

    if not args.skip_lf:
        results['lake_formation'] = grant_lake_formation_permissions(role_arn)
    else:
        print("\n⏭️  Skipping Lake Formation grants (--skip-lf)")

    if not args.skip_qs:
        results['quicksight'] = grant_quicksight_access(role_arn, user_suffix)
    else:
        print("\n⏭️  Skipping QuickSight access (--skip-qs)")

    # Verify all grants
    verification = verify_access(role_arn)
    results['verification'] = verification

    # Final summary
    print("\n" + "="*80)
    print("📊 FINAL SUMMARY")
    print("="*80)
    print(f"Principal: {role_arn}")
    print(f"User Suffix: {user_suffix or 'N/A'}")
    print()
    print("Access Granted:")
    print(f"  ✅ IAM Policy: {S3_BUCKET} (read), Glue (read), LF (data access)")
    print(f"  ✅ Lake Formation: {GOLD_DATABASE}.* (SELECT, DESCRIBE)")
    print(f"  ✅ QuickSight: {QUICKSIGHT_DASHBOARD_ID} (view)")
    print()
    print(f"Verification: {verification['pass_count']}/{verification['total_count']} checks passed")
    print()

    if verification['pass_count'] == verification['total_count']:
        print("✅ SUCCESS: All access grants verified")
        return 0
    else:
        print("⚠️  WARNING: Some verification checks did not pass")
        print("   Review the output above for details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
