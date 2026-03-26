#!/bin/bash
# Quick Demo: Self-Healing Prompt Architecture
# Shows the full learning cycle in action

set -e

echo "========================================="
echo "DEMO: Self-Healing Prompt Architecture"
echo "========================================="
echo
echo "This demo shows how the system:"
echo "  1. Detects patterns across failed runs"
echo "  2. Generates actionable recommendations"
echo "  3. Learns from successes"
echo
read -p "Press ENTER to start..."
echo

# Step 1: Generate test failures
echo "STEP 1: Generating Test Failures"
echo "---------------------------------"
echo "Simulating 3 failed onboardings with the same mistake..."
echo
./shared/prompt_intelligence/create_test_data.sh
echo
read -p "Press ENTER to continue..."
echo

# Step 2: Run analysis
echo "STEP 2: Running Prompt Intelligence Analysis"
echo "---------------------------------------------"
echo "Analyzing trace logs across all workloads..."
echo
python3 -m shared.prompt_intelligence.cli analyze --all
echo
read -p "Press ENTER to view report..."
echo

# Step 3: Show report highlights
echo "STEP 3: Report Highlights"
echo "-------------------------"
REPORT_FILE="docs/prompt_intelligence/$(date +%Y-%m-%d)_report.md"

echo "📄 Full report: $REPORT_FILE"
echo

echo "Top Pattern Detected:"
echo "--------------------"
grep -A 10 "#### 1\." "$REPORT_FILE" | head -15 || echo "(Report section not found)"
echo

read -p "Press ENTER to see the recommendation..."
echo

echo "Recommended Fix:"
echo "---------------"
grep -A 15 "Recommendation:" "$REPORT_FILE" | head -20 || echo "(Recommendation not found)"
echo

read -p "Press ENTER to see prompt patch..."
echo

echo "Prompt Patch (ready to copy):"
echo "-----------------------------"
grep -A 10 "Suggested Patch:" "$REPORT_FILE" | head -12 || echo "(Patch not found)"
echo

read -p "Press ENTER to see full report..."
echo

# Step 4: Display full report
echo "STEP 4: Full Report"
echo "-------------------"
cat "$REPORT_FILE"
echo

read -p "Press ENTER for summary..."
echo

# Step 5: Summary
echo "========================================="
echo "DEMO SUMMARY"
echo "========================================="
echo
echo "✅ What the System Learned:"
echo
echo "  Pattern: KeyError: 'primary_key'"
echo "  Frequency: 3 occurrences across 3 workloads"
echo "  Confidence: ~0.78 (high)"
echo "  Impact: BLOCKING (test gate failures)"
echo
echo "  Root Cause:"
echo "    CSV sources lack explicit PK column."
echo "    Agent infers from uniqueness but often wrong."
echo
echo "  Fix:"
echo "    Add to prompts/data-onboarding-agent/:"
echo "    'ALWAYS ask user for primary key before profiling CSV sources'"
echo
echo "✅ Time Savings:"
echo "  - Before: 3 failures × 2 hours debugging = 6 hours wasted"
echo "  - After: 0 failures (pattern prevented) = 6 hours saved"
echo
echo "✅ Next Steps:"
echo "  1. Apply the prompt patch to prevent recurrence"
echo "  2. Monitor future runs to verify fix works"
echo "  3. System continues learning from new patterns"
echo

# Step 6: Cleanup option
echo "========================================="
echo
read -p "Clean up test data? (y/n): " cleanup

if [[ "$cleanup" == "y" || "$cleanup" == "Y" ]]; then
    echo "Cleaning up..."
    rm -rf workloads/test_*
    echo "✓ Test workloads removed"
    echo
    echo "Report preserved at: $REPORT_FILE"
else
    echo "Test data preserved for manual inspection"
    echo "To clean up later: rm -rf workloads/test_*"
fi

echo
echo "========================================="
echo "Demo Complete!"
echo "========================================="
echo
echo "Try it yourself:"
echo "  ./shared/prompt_intelligence/create_test_data.sh"
echo "  python3 -m shared.prompt_intelligence.cli analyze --all"
echo
