#!/bin/bash
# Pre-Commit Security Check
# Run this before pushing to GitHub

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                    PRE-COMMIT SECURITY CHECK                         ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

EXIT_CODE=0

echo "🔍 Checking for sensitive data..."
echo ""

# Files to exclude from all scans
EXCLUDE_FILES="--exclude=pre-commit-check.sh --exclude=SECURITY.md --exclude=CLEANUP_SUMMARY.md --exclude=GITHUB_RELEASE_LOG.txt --exclude=*test_dag.py"

# Check 1: AWS Access Keys
echo -n "   [1/6] AWS Access Keys (AKIA*)... "
COUNT=$(grep -rE "AKIA[A-Z0-9]{16}" . --exclude-dir=.git $EXCLUDE_FILES 2>/dev/null | wc -l | tr -d ' ')
if [ "$COUNT" -eq "0" ]; then
    echo "✅ PASS (0 found)"
else
    echo "❌ FAIL ($COUNT found)"
    grep -rnE "AKIA[A-Z0-9]{16}" . --exclude-dir=.git $EXCLUDE_FILES 2>/dev/null | head -5
    EXIT_CODE=1
fi

# Check 2: AWS Secret Keys (exclude test files checking for these strings)
echo -n "   [2/6] AWS Secret Keys... "
COUNT=$(grep -r "aws_secret_access_key.*=" . --exclude-dir=.git $EXCLUDE_FILES 2>/dev/null | wc -l | tr -d ' ')
if [ "$COUNT" -eq "0" ]; then
    echo "✅ PASS (0 found)"
else
    echo "❌ FAIL ($COUNT found)"
    grep -rn "aws_secret_access_key.*=" . --exclude-dir=.git $EXCLUDE_FILES 2>/dev/null | head -5
    EXIT_CODE=1
fi

# Check 3: Real AWS Account ID (except documentation files)
echo -n "   [3/6] Real AWS Account ID... "
COUNT=$(grep -r "133661573128" . --exclude-dir=.git $EXCLUDE_FILES --exclude="*.md" 2>/dev/null | wc -l | tr -d ' ')
if [ "$COUNT" -eq "0" ]; then
    echo "✅ PASS (0 found)"
else
    echo "❌ FAIL ($COUNT found)"
    grep -rn "133661573128" . --exclude-dir=.git $EXCLUDE_FILES --exclude="*.md" 2>/dev/null | head -5
    EXIT_CODE=1
fi

# Check 4: Real S3 Bucket Name (except documentation files)
echo -n "   [4/6] Real S3 Bucket Names... "
COUNT=$(grep -r "finsights-datalake" . --exclude-dir=.git $EXCLUDE_FILES --exclude="*.md" 2>/dev/null | wc -l | tr -d ' ')
if [ "$COUNT" -eq "0" ]; then
    echo "✅ PASS (0 found)"
else
    echo "❌ FAIL ($COUNT found)"
    grep -rn "finsights-datalake" . --exclude-dir=.git $EXCLUDE_FILES --exclude="*.md" 2>/dev/null | head -5
    EXIT_CODE=1
fi

# Check 5: Local Absolute Paths in Code (except .md files)
echo -n "   [5/6] Local Paths in Code... "
COUNT=$(grep -r "/Users/hcherian" . --exclude-dir=.git $EXCLUDE_FILES --exclude="*.md" 2>/dev/null | wc -l | tr -d ' ')
if [ "$COUNT" -eq "0" ]; then
    echo "✅ PASS (0 found)"
else
    echo "❌ FAIL ($COUNT found)"
    grep -rn "/Users/hcherian" . --exclude-dir=.git $EXCLUDE_FILES --exclude="*.md" 2>/dev/null | head -5
    EXIT_CODE=1
fi

# Check 6: .mcp.json (should not exist, only .mcp.json.example)
echo -n "   [6/6] Local MCP Config... "
if [ -f ".mcp.json" ]; then
    echo "❌ FAIL (.mcp.json exists - should be gitignored)"
    EXIT_CODE=1
else
    echo "✅ PASS (.mcp.json not in repo)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ ALL CHECKS PASSED - Safe to commit!"
    echo ""
    echo "Next steps:"
    echo "   git add ."
    echo "   git commit -m \"Initial commit - sanitized for public release\""
    echo "   git push origin main"
else
    echo "❌ SECURITY ISSUES FOUND - DO NOT COMMIT"
    echo ""
    echo "Fix the issues above before committing."
    echo "See SECURITY.md for sanitization guidelines."
fi

echo ""
exit $EXIT_CODE
