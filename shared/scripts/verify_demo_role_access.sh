
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
