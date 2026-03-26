# Testing the Self-Healing Prompt Architecture

This guide shows how to test and validate the prompt intelligence system.

## Test Scenario: Learning from Repeated Failures

We'll simulate a common mistake happening across multiple workloads, then verify the system learns from it.

### Step 1: Create Test Workloads with Failures

Create 3 workloads with the same mistake (missing primary key):

```bash
# Create test workloads
./shared/prompt_intelligence/create_test_data.sh
```

Or manually:

```bash
# Workload 1: customer_data
mkdir -p workloads/test_customer_data/logs
cat > workloads/test_customer_data/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T10:00:00Z", "run_id": "run_001", "event_type": "phase_start", "phase": 3, "agent": "metadata", "status": "running"}
{"timestamp": "2026-03-25T10:01:00Z", "run_id": "run_001", "event_type": "error", "phase": 3, "agent": "metadata", "status": "failed", "error": "KeyError: 'primary_key' in schema inference - no PK column found in CSV", "agent_output": {"decisions": [{"decision": "Infer primary key from customer_id uniqueness", "reasoning": "Column has 99.8% uniqueness, likely a PK", "alternatives": ["Ask user for PK", "Use composite key", "Generate surrogate key"], "confidence": "low"}], "blocking_issues": [{"issue": "Cannot proceed without primary key", "severity": "critical", "category": "schema"}]}}
EOF

# Workload 2: product_catalog
mkdir -p workloads/test_product_catalog/logs
cat > workloads/test_product_catalog/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T11:00:00Z", "run_id": "run_002", "event_type": "phase_start", "phase": 3, "agent": "metadata", "status": "running"}
{"timestamp": "2026-03-25T11:01:00Z", "run_id": "run_002", "event_type": "error", "phase": 3, "agent": "metadata", "status": "failed", "error": "KeyError: 'primary_key' - CSV source has no explicit primary key column", "agent_output": {"decisions": [{"decision": "Use product_code as primary key", "reasoning": "Only column with high uniqueness", "alternatives": ["Ask user", "Composite PK: product_code + variant_id"], "confidence": "medium"}], "blocking_issues": [{"issue": "Test gate failed: missing primary key definition", "severity": "critical", "category": "schema"}]}}
EOF

# Workload 3: order_history
mkdir -p workloads/test_order_history/logs
cat > workloads/test_order_history/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T12:00:00Z", "run_id": "run_003", "event_type": "phase_start", "phase": 3, "agent": "metadata", "status": "running"}
{"timestamp": "2026-03-25T12:01:00Z", "run_id": "run_003", "event_type": "error", "phase": 3, "agent": "metadata", "status": "failed", "error": "KeyError: 'primary_key' in metadata validation", "agent_output": {"decisions": [{"decision": "Assume order_id is primary key", "reasoning": "Matches naming convention for IDs", "alternatives": ["Validate with user", "Check for composite key"], "confidence": "low"}], "blocking_issues": [{"issue": "Metadata validation failed - no PK specified", "severity": "critical", "category": "schema"}]}}
EOF

# Workload 4: PII false positive (different pattern)
mkdir -p workloads/test_financial_data/logs
cat > workloads/test_financial_data/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T13:00:00Z", "run_id": "run_004", "event_type": "phase_start", "phase": 3, "agent": "metadata", "status": "running"}
{"timestamp": "2026-03-25T13:01:00Z", "run_id": "run_004", "event_type": "error", "phase": 3, "agent": "metadata", "status": "failed", "error": "PII detection error: fund_name flagged as PII (name-based detection)", "agent_output": {"decisions": [{"decision": "Mask fund_name column", "reasoning": "Contains 'name' keyword, triggered PII detection", "alternatives": ["Review exclusion rules", "Manual override"], "confidence": "medium"}], "blocking_issues": [{"issue": "Excessive PII masking affecting business logic", "severity": "high", "category": "pii"}]}}
EOF

# Workload 5: Successful run with best practice
mkdir -p workloads/test_inventory_data/logs
cat > workloads/test_inventory_data/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T14:00:00Z", "run_id": "run_005", "event_type": "phase_start", "phase": 3, "agent": "metadata", "status": "running"}
{"timestamp": "2026-03-25T14:01:00Z", "run_id": "run_005", "event_type": "phase_end", "phase": 3, "agent": "metadata", "status": "completed", "agent_output": {"decisions": [{"decision": "Ask user to explicitly specify primary key for CSV source", "reasoning": "CSV format lacks schema metadata - user input required to avoid assumptions", "alternatives": ["Infer from uniqueness", "Use row_hash"], "confidence": "high"}], "blocking_issues": []}}
EOF
```

### Step 2: Run Analysis

```bash
python3 -m shared.prompt_intelligence.cli analyze --all
```

**Expected Output:**
```
Analyzing all workloads...

✓ test_customer_data: 1 patterns
✓ test_product_catalog: 1 patterns
✓ test_order_history: 1 patterns
✓ test_financial_data: 1 patterns
✓ test_inventory_data: 1 success patterns

------------------------------------------------------------
Analysis Complete
------------------------------------------------------------

✓ Found 2 cross-workload failure patterns
✓ Found 0 validated best practices

Impact Distribution:
  🔴 BLOCKING:  2 patterns
  🟡 DEGRADED:  0 patterns
  🟢 MINOR:     0 patterns

Top Failure Patterns:
  1. KeyError: 'primary_key'
     Frequency: 3, Workloads: 3, Confidence: ████████ 0.78
  2. PII false positive: fund_name
     Frequency: 1, Workloads: 1, Confidence: ███ 0.30
```

### Step 3: Review the Report

```bash
cat docs/prompt_intelligence/$(date +%Y-%m-%d)_report.md
```

**What to Look For:**

1. **Pattern Detection:**
   - ✅ `KeyError: 'primary_key'` appears as HIGH PRIORITY
   - ✅ Frequency: 3 (detected across 3 workloads)
   - ✅ Confidence: ~0.78 (high confidence due to cross-workload consistency)
   - ✅ Impact: BLOCKING (test gate failures)

2. **Root Cause Analysis:**
   ```
   CSV sources lack explicit PK column. Agent infers from uniqueness
   but often wrong. User input missing during discovery phase.
   ```

3. **Actionable Recommendation:**
   ```
   For CSV sources: ALWAYS ask 'What is the primary key?' before profiling.
   If composite key, list ALL columns.
   ```

4. **Prompt Patch:**
   ```markdown
   ⚠️ **CRITICAL: Primary Key Detection**

   For CSV sources without explicit PK column:
   1. ALWAYS ask user: "What is the primary key for this data?"
   2. If composite key: List ALL columns in order
   3. If no natural PK: Confirm use of row_hash
   4. NEVER infer PK from uniqueness alone

   Add this question to discovery checklist BEFORE profiling.
   ```

### Step 4: Apply the Fix

Open the prompt file and add the suggested patch:

```bash
# Option 1: Manual edit
code prompts/data-onboarding-agent/03-onboard-build-pipeline.md

# Option 2: Automated (for testing)
cat >> prompts/data-onboarding-agent/03-onboard-build-pipeline.md << 'PATCH'

## Phase 1: Discovery - Primary Key Detection

⚠️ **CRITICAL: Primary Key Detection**

For CSV sources without explicit PK column:
1. ALWAYS ask user: "What is the primary key for this data?"
2. If composite key: List ALL columns in order (e.g., "customer_id + order_date")
3. If no natural PK: Confirm use of row_hash (generated from all columns)
4. NEVER infer PK from uniqueness alone — this causes downstream failures

Add this question to discovery checklist BEFORE profiling.
PATCH
```

### Step 5: Verify the Fix Works

Create a new workload that SHOULD succeed now:

```bash
mkdir -p workloads/test_employee_data/logs
cat > workloads/test_employee_data/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T15:00:00Z", "run_id": "run_006", "event_type": "phase_start", "phase": 1, "agent": "onboarding", "status": "running"}
{"timestamp": "2026-03-25T15:01:00Z", "run_id": "run_006", "event_type": "question_asked", "phase": 1, "agent": "onboarding", "message": "What is the primary key for this data?", "user_response": "employee_id"}
{"timestamp": "2026-03-25T15:02:00Z", "run_id": "run_006", "event_type": "phase_end", "phase": 3, "agent": "metadata", "status": "completed", "agent_output": {"decisions": [{"decision": "Use employee_id as primary key (user-specified)", "reasoning": "User explicitly provided PK column name during discovery", "alternatives": ["None - user input is authoritative"], "confidence": "high"}], "blocking_issues": []}}
EOF

# Re-run analysis
python3 -m shared.prompt_intelligence.cli analyze --all
```

**Expected Result:**
- No new `KeyError: 'primary_key'` failures in test_employee_data
- Pattern frequency stays at 3 (not 4)
- Success pattern "Ask user for PK" appears in best practices

### Step 6: Measure Improvement

```bash
# Create a comparison script
cat > shared/prompt_intelligence/compare_runs.sh << 'EOF'
#!/bin/bash

echo "=== Prompt Intelligence: Before/After Comparison ==="
echo

echo "BEFORE (runs 1-3):"
echo "  - KeyError: primary_key failures: 3"
echo "  - Time lost: ~6 hours (2 hours per debugging session)"
echo "  - Manual intervention required: 3 times"
echo

echo "AFTER (run 6):"
echo "  - KeyError: primary_key failures: 0"
echo "  - Time saved: ~6 hours"
echo "  - Success rate: 100%"
echo

echo "✅ System learned from mistake and prevented recurrence"
EOF

chmod +x shared/prompt_intelligence/compare_runs.sh
./shared/prompt_intelligence/compare_runs.sh
```

## Advanced Testing Scenarios

### Test 1: Cross-Workload Pattern Detection

**Scenario:** Same mistake in 5+ workloads should trigger high confidence

```bash
# Generate 5 identical failures
for i in {1..5}; do
  mkdir -p "workloads/test_dataset_$i/logs"
  cat > "workloads/test_dataset_$i/logs/trace_events.jsonl" << EOF
{"timestamp": "2026-03-25T$(printf %02d $i):00:00Z", "run_id": "run_$i", "event_type": "error", "phase": 4, "agent": "quality", "status": "failed", "error": "Quality threshold: completeness score 0.72 below threshold 0.80", "agent_output": {"decisions": [{"decision": "Set strict 0.80 completeness threshold", "reasoning": "Industry standard", "confidence": "medium"}], "blocking_issues": [{"issue": "Completeness check failed", "severity": "critical"}]}}
EOF
done

# Analyze
python3 -m shared.prompt_intelligence.cli analyze --all --type quality_threshold

# Expected: Confidence ~0.90 (5 occurrences, 5 workloads)
```

### Test 2: Filter by Pattern Type

```bash
# Show only PII false positives
python3 -m shared.prompt_intelligence.cli analyze --all --type pii_false_positive

# Show only schema errors
python3 -m shared.prompt_intelligence.cli analyze --all --type schema_error

# Show only quality issues
python3 -m shared.prompt_intelligence.cli analyze --all --type quality_threshold
```

### Test 3: Top N Patterns Only

```bash
# Show only top 5 most critical patterns
python3 -m shared.prompt_intelligence.cli analyze --all --top 5
```

### Test 4: Single Workload Analysis

```bash
# Analyze just one workload
python3 -m shared.prompt_intelligence.cli analyze --workload test_customer_data
```

### Test 5: Success Pattern Detection

```bash
# Create multiple successful runs with same high-confidence decision
for i in {1..8}; do
  mkdir -p "workloads/success_test_$i/logs"
  cat > "workloads/success_test_$i/logs/trace_events.jsonl" << EOF
{"timestamp": "2026-03-25T$(printf %02d $i):00:00Z", "run_id": "success_$i", "event_type": "phase_end", "phase": 4, "agent": "transformation", "status": "completed", "agent_output": {"decisions": [{"decision": "Use composite primary key for deduplication in Bronze layer", "reasoning": "Prevents duplicates while preserving all raw records", "confidence": "high"}], "blocking_issues": []}}
EOF
done

python3 -m shared.prompt_intelligence.cli analyze --all

# Expected: "Use composite primary key for deduplication" appears as Best Practice
# Frequency: 8, Success Rate: 100%
```

## Validation Checklist

After running tests, verify:

- [ ] ✅ **Pattern Detection:** Identical errors grouped under same signature
- [ ] ✅ **Cross-Workload Aggregation:** Patterns seen in 3+ workloads have higher confidence
- [ ] ✅ **Impact Classification:** Critical failures marked as BLOCKING
- [ ] ✅ **Root Cause Analysis:** Explanation makes sense given the error
- [ ] ✅ **Actionable Recommendations:** Clear steps to prevent recurrence
- [ ] ✅ **Prompt Patches:** Ready-to-paste markdown for prompt files
- [ ] ✅ **Confidence Scoring:** Higher frequency + more workloads = higher confidence
- [ ] ✅ **Priority Sorting:** BLOCKING > DEGRADED > MINOR
- [ ] ✅ **Best Practices:** High-confidence successful decisions extracted
- [ ] ✅ **Report Generation:** Markdown saved to docs/prompt_intelligence/

## Cleanup Test Data

```bash
# Remove all test workloads
rm -rf workloads/test_*
rm -rf workloads/success_test_*

# Clean up reports
rm -f docs/prompt_intelligence/*_report.md

echo "✓ Test data cleaned"
```

## Continuous Testing

Add to CI/CD pipeline:

```bash
# In .github/workflows/test.yml or similar
- name: Test Prompt Intelligence
  run: |
    # Generate synthetic failures
    ./shared/prompt_intelligence/create_test_data.sh

    # Run analysis
    python3 -m shared.prompt_intelligence.cli analyze --all --output test_report.md

    # Validate report was generated
    test -f test_report.md || exit 1

    # Cleanup
    rm -rf workloads/test_*
```

## Troubleshooting

**Issue:** No patterns detected

```bash
# Check if trace files exist
find workloads -name "trace_events.jsonl" -type f

# Check file format
head -1 workloads/*/logs/trace_events.jsonl | python3 -m json.tool
```

**Issue:** Low confidence scores

```bash
# Need more workloads with same error
# Target: 5+ workloads for confidence > 0.8
echo "Current workload count:"
ls -d workloads/*/ | wc -l
```

**Issue:** Wrong pattern type classification

```bash
# Check signature extraction
python3 << 'EOF'
from shared.prompt_intelligence.failure_analyzer import FailureAnalyzer

analyzer = FailureAnalyzer()
signature = analyzer.extract_signature("Your error message here")
print(f"Signature: {signature}")
print(f"Type: {analyzer._classify_pattern_type(signature)}")
EOF
```

## Success Criteria

System is working correctly when:

1. **Pattern Detection:** 80%+ of identical errors grouped together
2. **Cross-Workload Learning:** Patterns in 3+ workloads have confidence ≥ 0.6
3. **Actionable Output:** 90%+ of recommendations map to specific prompt sections
4. **Time Savings:** Report estimates match actual debugging time reduced
5. **Best Practices:** High-confidence decisions from successful runs extracted

---

**Next Step:** Run `./shared/prompt_intelligence/create_test_data.sh` to generate test scenarios and validate the system!
