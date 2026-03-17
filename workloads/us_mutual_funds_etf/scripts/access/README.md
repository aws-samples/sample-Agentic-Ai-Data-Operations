# Access Grant Scripts — US Mutual Funds & ETF Workload

Scripts for granting comprehensive access to principals (users/roles) for the workload.

---

## Quick Start

**Grant access to `demo-role/demo-user`:**

```bash
./grant_access_hcherian.sh
```

This grants all necessary permissions in parallel:
- ✅ IAM policy for backend access (S3, Glue, Lake Formation, Athena)
- ✅ Lake Formation SELECT permissions on all Gold tables
- ✅ QuickSight dashboard view access

---

## Scripts

### `grant_access_to_principal.py`

Comprehensive access grant script using boto3. Supports any principal (role or user).

**Usage:**
```bash
python3 grant_access_to_principal.py --principal PRINCIPAL
```

**Examples:**
```bash
# Grant access using role/user format
python3 grant_access_to_principal.py --principal demo-role/demo-user

# Grant access using full ARN
python3 grant_access_to_principal.py --principal arn:aws:iam::123456789012:role/MyRole

# Skip specific steps
python3 grant_access_to_principal.py --principal demo-role/demo-user --skip-qs
```

**Options:**
- `--principal` (required): Principal to grant access to
- `--skip-iam`: Skip IAM policy attachment
- `--skip-lf`: Skip Lake Formation grants
- `--skip-qs`: Skip QuickSight access

**What it grants:**

1. **IAM Inline Policy (`FinsightsWorkloadAccess`):**
   - S3: `GetObject`, `ListBucket` on `s3://your-datalake-bucket/*`
   - Glue: `GetDatabase`, `GetTable` on `finsights_silver` and `finsights_gold`
   - Lake Formation: `GetDataAccess` (required for LF-governed tables)
   - Athena: `StartQueryExecution`, `GetQueryResults` on all workgroups

2. **Lake Formation Permissions:**
   - Database: `DESCRIBE` on `finsights_gold`
   - Tables: `SELECT`, `DESCRIBE` on:
     - `finsights_gold.dim_fund`
     - `finsights_gold.dim_category`
     - `finsights_gold.dim_date`
     - `finsights_gold.fact_fund_performance`

3. **QuickSight Permissions:**
   - Dashboard: `DescribeDashboard`, `QueryDashboard` on `finsights-finance-dashboard`
   - Analysis: `DescribeAnalysis`, `QueryAnalysis` on `finsights-finance-analysis`

**Exit codes:**
- `0`: Success (all grants verified)
- `1`: Failure or warnings (check output for details)

---

### `grant_access_hcherian.sh`

Convenience wrapper for granting access to the specific principal `demo-role/demo-user`.

**Usage:**
```bash
./grant_access_hcherian.sh
```

**Prerequisites:**
- Python 3.11+
- AWS CLI configured (`aws configure`)
- Valid AWS credentials with IAM, Lake Formation, and QuickSight permissions

---

## Access Summary

After running the script, the principal will have:

### Backend Access (via IAM Policy)
- **S3:** Read access to `s3://your-datalake-bucket/bronze/`, `/silver/`, `/gold/`
- **Glue Data Catalog:** Read access to `finsights_silver` and `finsights_gold` databases
- **Athena:** Query execution on all workgroups
- **Lake Formation:** Data access via LF temporary credentials

### Table Access (via Lake Formation)
- **Silver Zone:** (Optionally grant via `--grant-silver` flag)
  - `finsights_silver.funds_clean`
  - `finsights_silver.market_data_clean`
  - `finsights_silver.nav_clean`

- **Gold Zone:** (Always granted)
  - `finsights_gold.dim_fund`
  - `finsights_gold.dim_category`
  - `finsights_gold.dim_date`
  - `finsights_gold.fact_fund_performance`

### QuickSight Access
- **Dashboard:** View-only access to `finsights-finance-dashboard`
- **Analysis:** View-only access to `finsights-finance-analysis`

---

## Verification

The script includes a verification step that checks:
- ✅ IAM policy exists and is attached to the role
- ✅ Lake Formation permissions are in place
- ✅ QuickSight dashboard permissions are set

**Manual verification:**

1. **Test Athena query:**
   ```sql
   SELECT COUNT(*) FROM finsights_gold.dim_fund;
   ```

2. **Test QuickSight access:**
   - Navigate to: https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-finance-dashboard
   - Verify dashboard loads and visuals render

3. **Check Lake Formation permissions:**
   ```bash
   aws lakeformation list-permissions \
     --principal DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT:role/demo-role \
     --resource Database={Name=finsights_gold}
   ```

---

## Troubleshooting

### Error: "Role does not exist"
**Cause:** The specified role name is incorrect or doesn't exist.
**Fix:** Verify the role exists:
```bash
aws iam get-role --role-name demo-role
```

### Error: "Access Denied" when attaching IAM policy
**Cause:** Your AWS credentials don't have `iam:PutRolePolicy` permission.
**Fix:** Run as a user with IAM admin permissions, or ask an admin to run the script.

### Error: "InvalidInputException" from Lake Formation
**Cause:** The table doesn't exist yet in Glue Data Catalog.
**Fix:** Run the Glue ETL jobs first to create the tables, then re-run the access grant script.

### Error: "ResourceNotFoundException" for QuickSight dashboard
**Cause:** The dashboard hasn't been published yet.
**Fix:** Run `scripts/quicksight/quicksight_dashboard_setup.py` first to create the dashboard.

### Warning: "Principal not found in dashboard permissions" during verification
**Cause:** QuickSight user principal format mismatch.
**Fix:** For federated users, ensure you provide the user suffix:
```bash
python3 grant_access_to_principal.py --principal demo-role/demo-user
```

### Error: "ThrottlingException"
**Cause:** AWS API rate limiting.
**Fix:** The script automatically retries with exponential backoff. If it persists, wait 30 seconds and re-run.

---

## Security Notes

1. **Least Privilege:** This script grants read-only access to Gold zone tables. No write/delete permissions are granted.

2. **Lake Formation Governance:** All table access is governed by Lake Formation, ensuring audit logs are captured.

3. **QuickSight Isolation:** Users can only view the dashboard, not edit or delete it.

4. **S3 Encryption:** All data in S3 is encrypted at rest with KMS. IAM policy includes implicit KMS decrypt access for the bucket's KMS key.

5. **Audit Trail:** All API calls (IAM, Lake Formation, QuickSight) are logged in CloudTrail for compliance.

---

## Revoke Access

To revoke all access granted by this script:

```bash
# 1. Remove IAM policy
aws iam delete-role-policy --role-name demo-role --policy-name FinsightsWorkloadAccess

# 2. Revoke Lake Formation permissions
aws lakeformation revoke-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT:role/demo-role \
  --resource Database={Name=finsights_gold} \
  --permissions DESCRIBE

# For each table:
aws lakeformation revoke-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT:role/demo-role \
  --resource Table={DatabaseName=finsights_gold,Name=dim_fund} \
  --permissions SELECT DESCRIBE

# 3. Remove QuickSight permissions
aws quicksight update-dashboard-permissions \
  --aws-account-id ACCOUNT \
  --dashboard-id finsights-finance-dashboard \
  --revoke-permissions Principal=arn:aws:quicksight:us-east-1:ACCOUNT:user/default/demo-role/demo-user
```

---

## Integration with MCP

This script is designed to work alongside MCP-based deployment:

- **Phase 5.3 (IAM):** MCP IAM server can simulate permissions before granting
- **Phase 5.4 (Lake Formation):** MCP Lambda (`LF_access_grant_new`) can be used as alternative to boto3
- **Phase 5.7 (Audit):** MCP CloudTrail can verify all grants were logged

**Using MCP for Lake Formation grants:**

See `shared/scripts/grant_lf_permissions.py` for MCP Lambda-based alternative.

---

## Contact

**Questions?** Reach out to:
- Data Engineering Team: data-eng@company.com
- Slack: #data-pipeline-alerts
