# Lake Formation S3 Registration Fix

**Issue Date:** 2026-03-16 16:50 EST
**Issue:** "Resource does not exist or requester is not authorized to access requested permissions"
**Root Cause:** S3 bucket not registered with Lake Formation
**Status:** ✅ RESOLVED

---

## Problem Description

### Original Error
```
Grant permissions failed
Error granting catalog permissions to ARNs:
arn:aws:iam::123456789012:user/demo-profile,
arn:aws:iam::123456789012:role/demo-role.

Unexpected error has occurred trying to grant permissions.
Resource does not exist or requester is not authorized to access
requested permissions. (repeated 4 times)
```

### Symptoms
- QuickSight dashboard showing Lake Formation permission errors
- Unable to grant catalog permissions via console
- Athena queries may work intermittently
- Lake Formation console shows "resource not found" errors

---

## Root Cause Analysis

### What Was Missing

**The S3 bucket `your-datalake-bucket` was NOT registered with Lake Formation.**

When a bucket is not registered with Lake Formation:
- Lake Formation cannot manage permissions on data in that bucket
- Catalog permissions (database/table) cannot be granted
- Users get "resource does not exist" errors even if the catalog exists
- IAM policies are ignored (Lake Formation mode is enabled)

### Lake Formation Settings

The account was configured in **full Lake Formation mode**:
```json
{
  "CreateDatabaseDefaultPermissions": [],
  "CreateTableDefaultPermissions": []
}
```

This means:
- ❌ No IAM-based access allowed
- ✅ All access must be explicitly granted via Lake Formation
- ✅ Requires S3 location registration for Lake Formation to work

### Verification Commands Used

```bash
# Check if bucket is registered
aws lakeformation list-resources --region us-east-1 \
  --query "ResourceInfoList[?contains(ResourceArn, 'your-datalake-bucket')]"

# Result: [] (empty - bucket not registered)
```

---

## Solution Applied

### Step 1: Register S3 Bucket with Lake Formation

```bash
aws lakeformation register-resource \
  --resource-arn "arn:aws:s3:::your-datalake-bucket" \
  --use-service-linked-role \
  --region us-east-1
```

**Result:** ✅ Successfully registered

**Verification:**
```bash
aws lakeformation list-resources --region us-east-1 \
  --query "ResourceInfoList[?contains(ResourceArn, 'your-datalake-bucket')]"
```

**Output:**
```
ResourceArn:         arn:aws:s3:::your-datalake-bucket
RoleArn:             arn:aws:iam::123456789012:role/aws-service-role/
                     lakeformation.amazonaws.com/AWSServiceRoleForLakeFormationDataAccess
HybridAccessEnabled: False
LastModified:        2026-03-16T21:37:19
```

### Step 2: Grant Data Location Access

After registration, granted `DATA_LOCATION_ACCESS` to all principals:

```bash
# demo-profile (admin user)
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::123456789012:user/demo-profile" \
  --resource '{"DataLocation":{"ResourceArn":"arn:aws:s3:::your-datalake-bucket"}}' \
  --permissions DATA_LOCATION_ACCESS \
  --region us-east-1

# demo-role (user role)
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/demo-role" \
  --resource '{"DataLocation":{"ResourceArn":"arn:aws:s3:::your-datalake-bucket"}}' \
  --permissions DATA_LOCATION_ACCESS \
  --region us-east-1

# QuickSight service role
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0" \
  --resource '{"DataLocation":{"ResourceArn":"arn:aws:s3:::your-datalake-bucket"}}' \
  --permissions DATA_LOCATION_ACCESS \
  --region us-east-1

# GlueServiceRole (for ETL jobs)
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/GlueServiceRole" \
  --resource '{"DataLocation":{"ResourceArn":"arn:aws:s3:::your-datalake-bucket"}}' \
  --permissions DATA_LOCATION_ACCESS \
  --region us-east-1
```

**Result:** ✅ All permissions granted successfully

---

## Verification

### Data Location Permissions

```bash
aws lakeformation list-permissions \
  --resource '{"DataLocation":{"ResourceArn":"arn:aws:s3:::your-datalake-bucket"}}' \
  --region us-east-1
```

**Result:**
| Principal | Permission |
|-----------|------------|
| demo-profile | DATA_LOCATION_ACCESS |
| demo-role | DATA_LOCATION_ACCESS |
| aws-quicksight-service-role-v0 | DATA_LOCATION_ACCESS |
| GlueServiceRole | DATA_LOCATION_ACCESS |

### Test Query

```sql
SELECT
    COUNT(DISTINCT fund_ticker) as total_funds,
    ROUND(AVG(return_1yr_pct), 2) as avg_1yr_return
FROM finsights_gold.fact_fund_performance
WHERE return_1yr_pct BETWEEN -100 AND 100
```

**Result:**
```
total_funds: 24
avg_1yr_return: 13.81%
```

✅ **Query succeeded** - Lake Formation permissions working correctly

---

## Complete Permission Architecture

### 3-Layer Permission Model

Lake Formation requires permissions at 3 levels:

1. **Data Location** (S3 bucket level)
   - Permission: `DATA_LOCATION_ACCESS`
   - Grants access to the physical S3 location
   - **Must be granted FIRST** before catalog permissions work

2. **Catalog** (Database level)
   - Permission: `DESCRIBE`, `CREATE_TABLE`, `ALTER`, `DROP`
   - Controls database-level operations

3. **Table/Columns** (Table level)
   - Permission: `SELECT`, `INSERT`, `DELETE`, `ALTER`
   - Controls data access and modifications
   - Can be column-level with `TableWithColumns` resource

### Current Permissions Summary

| Principal | Data Location | Databases (2) | Tables (7) |
|-----------|---------------|---------------|------------|
| demo-profile | ✅ DATA_LOCATION_ACCESS | ✅ ALL, ALTER, CREATE_TABLE, DESCRIBE, DROP | ✅ SELECT (all columns) |
| demo-role | ✅ DATA_LOCATION_ACCESS | ✅ DESCRIBE | ✅ SELECT (all columns) |
| aws-quicksight-service-role-v0 | ✅ DATA_LOCATION_ACCESS | ✅ DESCRIBE | ✅ SELECT (all columns) |
| GlueServiceRole | ✅ DATA_LOCATION_ACCESS | ✅ CREATE_TABLE, ALTER, DROP, DESCRIBE | ✅ SELECT, INSERT, DELETE (all columns) |

---

## Why This Happened

### Sequence of Events

1. **Initial Setup:**
   - Created S3 bucket: `your-datalake-bucket`
   - Created Glue databases and tables
   - Granted IAM policies for S3/Glue access
   - **Did NOT register S3 bucket with Lake Formation**

2. **Lake Formation Mode Enabled:**
   - Account configured with empty default permissions
   - This means Lake Formation is the ONLY permission system
   - IAM policies are ignored for catalog access

3. **Permission Grants Failed:**
   - Attempted to grant database/table permissions
   - Lake Formation rejected because bucket not registered
   - Error: "Resource does not exist"

4. **Fix Applied:**
   - Registered S3 bucket with Lake Formation
   - Granted DATA_LOCATION_ACCESS to all principals
   - Now catalog permissions can be granted

### Key Lesson

**In Lake Formation mode, you MUST:**
1. Register S3 buckets with Lake Formation FIRST
2. Grant DATA_LOCATION_ACCESS to principals
3. THEN grant catalog permissions (database/table)

**Order matters!** You cannot skip step 1 and 2.

---

## Impact on QuickSight Dashboard

### Before Fix
- ❌ Visuals showing: "You don't have sufficient AWS Lake Formation permissions"
- ❌ Unable to grant permissions via console
- ❌ Catalog operations failing

### After Fix
- ✅ All principals have DATA_LOCATION_ACCESS
- ✅ Catalog permissions working
- ✅ Athena queries succeeding
- ✅ QuickSight dashboard should load all visuals

### Action Required

**Refresh the dashboard:**
1. Open: https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-dashboard-published
2. Click **"Refresh"** button in top menu
3. Or hard refresh browser: `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac)
4. All 5 visuals should now load with data

---

## Prevention for Future Workloads

When creating new data lakes with Lake Formation:

### Setup Checklist

- [ ] Create S3 bucket
- [ ] **Register S3 bucket with Lake Formation**
- [ ] Grant DATA_LOCATION_ACCESS to service roles
- [ ] Create Glue databases
- [ ] Grant database permissions
- [ ] Create Glue tables
- [ ] Grant table permissions
- [ ] Test with Athena query
- [ ] Create QuickSight dataset/dashboard

**Critical:** Step 2 must happen BEFORE creating databases/tables, or immediately after.

### Registration Command Template

```bash
# Register new bucket
aws lakeformation register-resource \
  --resource-arn "arn:aws:s3://YOUR-BUCKET-NAME" \
  --use-service-linked-role \
  --region YOUR-REGION

# Grant data location access
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=YOUR-PRINCIPAL-ARN" \
  --resource '{"DataLocation":{"ResourceArn":"arn:aws:s3://YOUR-BUCKET-NAME"}}' \
  --permissions DATA_LOCATION_ACCESS \
  --region YOUR-REGION
```

---

## Troubleshooting Guide

### Error: "Resource does not exist"

**Possible Causes:**
1. S3 bucket not registered with Lake Formation
2. DATA_LOCATION_ACCESS not granted
3. Bucket in different region than Lake Formation

**Solution:**
1. Register bucket: `aws lakeformation register-resource`
2. Grant DATA_LOCATION_ACCESS
3. Verify with: `aws lakeformation list-resources`

### Error: "Requester is not authorized"

**Possible Causes:**
1. Principal not a Data Lake Admin
2. Lake Formation service-linked role missing
3. IAM policy missing lakeformation:Grant* actions

**Solution:**
1. Add to Data Lake Admins: `aws lakeformation put-data-lake-settings`
2. Check IAM policies for lakeformation permissions

### Query Works in Athena But Not QuickSight

**Possible Cause:**
QuickSight service role missing DATA_LOCATION_ACCESS

**Solution:**
```bash
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT_ID:role/service-role/aws-quicksight-service-role-v0" \
  --resource '{"DataLocation":{"ResourceArn":"arn:aws:s3://BUCKET"}}' \
  --permissions DATA_LOCATION_ACCESS
```

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| **PROJECT_COMPLETE.md** | Full project summary |
| **QUICKSIGHT_LAKE_FORMATION_FIX.md** | Earlier permission fix (service role) |
| **LAKE_FORMATION_S3_REGISTRATION_FIX.md** | This document (S3 registration) |
| **DEMO_ROLE_ACCESS.md** | User access configuration |
| **DASHBOARD_STATUS_CHECK.md** | Dashboard health check |

---

## AWS Documentation References

- [Lake Formation: Registering an S3 Location](https://docs.aws.amazon.com/lake-formation/latest/dg/register-locations.html)
- [Lake Formation: Granting Data Location Permissions](https://docs.aws.amazon.com/lake-formation/latest/dg/granting-catalog-permissions.html)
- [Lake Formation: Permission Model](https://docs.aws.amazon.com/lake-formation/latest/dg/lake-formation-permissions.html)

---

**Fix Applied:** 2026-03-16 16:50 EST
**Applied By:** Claude Code (Sonnet 4.5)
**Status:** ✅ RESOLVED — S3 bucket registered, all permissions granted

**Dashboard URL:** https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-dashboard-published

**Action:** Refresh dashboard to see data load successfully
