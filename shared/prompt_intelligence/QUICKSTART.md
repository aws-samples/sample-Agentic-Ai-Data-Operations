# Quick Start: Self-Healing Prompt Architecture

Get started in 3 minutes.

## Option 1: Interactive Demo (Recommended)

See the full learning cycle in action:

```bash
./shared/prompt_intelligence/demo.sh
```

This will:
1. Generate 6 test workloads with realistic failures
2. Run pattern analysis across all workloads
3. Show you the detected patterns and recommendations
4. Display the full report
5. Summarize what the system learned

## Option 2: Manual Testing

### Step 1: Generate Test Data

```bash
./shared/prompt_intelligence/create_test_data.sh
```

Creates 6 test workloads:
- 3 with missing primary key errors (same mistake)
- 1 with PII false positives
- 2 with quality threshold issues
- 1 successful run with best practices

### Step 2: Run Analysis

```bash
python3 -m shared.prompt_intelligence.cli analyze --all
```

Output shows:
- Number of patterns detected
- Impact distribution (BLOCKING/DEGRADED/MINOR)
- Top failure patterns with confidence scores

### Step 3: Review the Report

```bash
cat docs/prompt_intelligence/$(date +%Y-%m-%d)_report.md
```

The report includes:
- **Executive Summary**: Top blockers, estimated time savings
- **Failure Patterns**: Grouped by impact with root cause analysis
- **Recommendations**: Actionable fixes with prompt patches
- **Best Practices**: Successful patterns to adopt
- **Implementation Guide**: How to apply the fixes

### Step 4: Apply a Fix

Example: Fix the "missing primary key" pattern

```bash
# 1. Read the recommendation from the report
grep -A 10 "KeyError: 'primary_key'" docs/prompt_intelligence/$(date +%Y-%m-%d)_report.md

# 2. Copy the suggested prompt patch

# 3. Add to the appropriate prompt file
code prompts/data-onboarding-agent/03-onboard-build-pipeline.md
```

### Step 5: Verify the Fix

Create a new workload (simulating the fix):

```bash
mkdir -p workloads/test_new_success/logs
cat > workloads/test_new_success/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T17:00:00Z", "run_id": "new_run", "event_type": "phase_end", "phase": 3, "agent": "metadata", "status": "completed", "agent_output": {"decisions": [{"decision": "Ask user for primary key (prompt-based)", "reasoning": "Following updated discovery checklist", "confidence": "high"}], "blocking_issues": []}}
EOF

# Re-run analysis
python3 -m shared.prompt_intelligence.cli analyze --all
```

Expected: No new primary key failures, pattern frequency stays at 3 (not 4).

### Step 6: Cleanup

```bash
rm -rf workloads/test_*
```

## Option 3: Real Usage

Once you have real workloads with trace logs:

```bash
# Analyze all workloads
python3 -m shared.prompt_intelligence.cli analyze --all

# Show only top 10 patterns
python3 -m shared.prompt_intelligence.cli analyze --all --top 10

# Filter by pattern type
python3 -m shared.prompt_intelligence.cli analyze --all --type schema_error

# Analyze specific workload
python3 -m shared.prompt_intelligence.cli analyze --workload customer_master
```

## What Success Looks Like

After running the analysis, you should see:

```
✓ Found 2 cross-workload failure patterns
✓ Found 0 validated best practices

Impact Distribution:
  🔴 BLOCKING:  1 patterns
  🟡 DEGRADED:  0 patterns
  🟢 MINOR:     1 patterns

Top Failure Patterns:
  1. KeyError: 'primary_key'
     Frequency: 3, Workloads: 3, Confidence: ████████ 0.78
```

The report will include:
- **Root cause**: Why the pattern occurs
- **Recommendation**: How to prevent it
- **Prompt patch**: Ready-to-paste markdown for prompt files
- **Examples**: Concrete error messages from affected workloads

## Next Steps

1. **Apply high-priority fixes** from the report
2. **Monitor future runs** to verify fixes work
3. **Run analysis periodically** to catch new patterns
4. **Share successful patterns** as best practices in CLAUDE.md

## Troubleshooting

**No patterns detected?**
```bash
# Check if trace files exist
find workloads -name "trace_events.jsonl" -type f

# Verify JSON format
head -1 workloads/*/logs/trace_events.jsonl | python3 -m json.tool
```

**Want more details?**
```bash
# See full testing guide
cat shared/prompt_intelligence/TESTING.md

# See implementation README
cat shared/prompt_intelligence/README.md
```

---

**Ready to test?** Run `./shared/prompt_intelligence/demo.sh` to see it in action!
