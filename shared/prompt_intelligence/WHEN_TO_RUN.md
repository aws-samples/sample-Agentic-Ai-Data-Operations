# When to Run Prompt Intelligence

The Prompt Intelligence system is **on-demand**, not automatic. Here's when and how to run it.

## Execution Timeline

```
Pipeline Lifecycle               Prompt Intelligence
─────────────────────           ───────────────────────

Phase 0-5: Onboard workload     (not running)
  ├── Discovery
  ├── Profiling
  ├── Build pipeline
  ├── Test gates
  └── Deploy to MWAA
      │
      ├── Pipeline runs          (not running)
      │   └── Creates trace_events.jsonl
      │
      └── After N workloads      ◄── RUN ANALYSIS HERE
          completed
          │
          ├── Weekly batch       python3 -m shared.prompt_intelligence.cli analyze --all
          ├── After failures     → Detects patterns
          └── Before deploy      → Generates recommendations
                                 → Saves report to docs/
```

## Recommended Schedule

### 1. Weekly Analysis (Proactive)

Run every Monday to catch accumulating patterns:

```bash
# Cron: Every Monday at 9 AM
0 9 * * 1 cd /path/to/repo && python3 -m shared.prompt_intelligence.cli analyze --all --output docs/prompt_intelligence/weekly_$(date +\%Y-\%m-\%d).md
```

**Why:** Patterns emerge gradually. 3-5 workloads with the same mistake = high confidence.

### 2. After Major Failures (Reactive)

Run immediately after test gate failures or deployment issues:

```bash
# Manual trigger after incident
python3 -m shared.prompt_intelligence.cli analyze --all

# Review BLOCKING patterns
grep -A 20 "BLOCKING" docs/prompt_intelligence/$(date +%Y-%m-%d)_report.md
```

**Why:** Understand root cause and apply fix before next onboarding.

### 3. Before Major Deployments (Preventive)

Run before deploying multiple workloads to production:

```bash
# Before prod deploy
python3 -m shared.prompt_intelligence.cli analyze --all --top 10
```

**Why:** Catch systemic issues that would affect multiple workloads.

### 4. After Onboarding Milestones (Batch)

Run after every 5-10 new workloads:

```bash
# Count workloads
WORKLOAD_COUNT=$(ls -d workloads/*/ | wc -l)

if [ $WORKLOAD_COUNT -ge 10 ]; then
    python3 -m shared.prompt_intelligence.cli analyze --all
fi
```

**Why:** Cross-workload patterns need multiple data points to emerge.

## What Triggers Analysis

### ✅ Good Triggers

- **N workloads completed** (N >= 3 for meaningful patterns)
- **Test gate failures** (pattern might be recurring)
- **Weekly routine** (proactive learning)
- **Before deployments** (catch issues early)
- **After regulation updates** (check compliance patterns)

### ❌ Bad Triggers

- **After every single workload** (not enough data for cross-workload patterns)
- **Real-time during onboarding** (analysis needs completed trace logs)
- **Before trace logs exist** (nothing to analyze)
- **Too frequently** (< 3 new workloads = no new patterns)

## Integration Patterns

### CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/prompt-intelligence.yml
name: Weekly Prompt Intelligence

on:
  schedule:
    - cron: '0 9 * * 1'  # Monday 9 AM
  workflow_dispatch:      # Manual trigger

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run analysis
        run: |
          python3 -m shared.prompt_intelligence.cli analyze --all \
            --output prompt_intelligence_$(date +%Y-%m-%d).md

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: prompt-intelligence-report
          path: prompt_intelligence_*.md

      - name: Create issue if BLOCKING patterns found
        run: |
          BLOCKING=$(grep -c "BLOCKING" prompt_intelligence_*.md || echo 0)
          if [ $BLOCKING -gt 0 ]; then
            gh issue create \
              --title "Prompt Intelligence: $BLOCKING BLOCKING patterns detected" \
              --body "See workflow artifacts for full report" \
              --label "prompt-intelligence,priority-high"
          fi
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Post-Onboarding Hook

```bash
# In workloads/{name}/deploy_to_aws.py

def post_deployment_hook():
    """Run after successful deployment."""
    # Count recent workloads
    recent_count = count_workloads_since_last_analysis()

    if recent_count >= 5:
        print("🧠 Running Prompt Intelligence (5+ new workloads)...")
        subprocess.run([
            "python3", "-m", "shared.prompt_intelligence.cli",
            "analyze", "--all", "--top", "10"
        ])
```

### Manual Ad-Hoc

```bash
# Investigate specific pattern type
python3 -m shared.prompt_intelligence.cli analyze --all --type schema_error

# Analyze single workload after failure
python3 -m shared.prompt_intelligence.cli analyze --workload customer_master

# Quick scan (top 5 patterns only)
python3 -m shared.prompt_intelligence.cli analyze --all --top 5
```

## Data Requirements

For analysis to work:

1. **Trace logs exist**: `workloads/*/logs/trace_events.jsonl` must be present
2. **Structured format**: Events follow AgentTracer schema (operational, cognitive, contextual)
3. **Decisions logged**: AgentOutput includes `decisions[]` array
4. **Minimum workloads**: ≥3 workloads for cross-workload patterns

If missing:
```bash
# Check for trace files
find workloads -name "trace_events.jsonl" -type f

# If none found
echo "No trace logs yet. Run some onboardings first."
```

## Feedback Loop (Manual)

1. **Run analysis** → Get report with recommendations
2. **Apply fix** → Add prompt patch to prompts/
3. **Monitor next runs** → Check if pattern stops appearing
4. **Re-run analysis** → Verify pattern frequency decreased
5. **Update confidence** → Document successful fix in CLAUDE.md

## Output Locations

```
docs/prompt_intelligence/
├── 2026-03-25_report.md      # Today's analysis
├── 2026-03-18_report.md      # Previous week
├── 2026-03-11_report.md      # Earlier
└── weekly_summary.md         # Aggregated trends (manual)
```

## When NOT to Run

- **No workloads yet** (nothing to analyze)
- **< 3 workloads** (not enough for cross-workload patterns)
- **No trace logs** (AgentTracer not enabled)
- **During active onboarding** (wait for completion)
- **Every minute** (waste of compute)

## Success Metrics

Track these over time:

- **Pattern frequency trend** (decreasing = system learning)
- **Time saved estimate** (from reports)
- **Test gate pass rate** (increasing = fewer recurring failures)
- **High-confidence patterns** (≥ 0.8 confidence = actionable)

---

**Quick Reference:**

```bash
# Standard weekly run
python3 -m shared.prompt_intelligence.cli analyze --all

# After incident
python3 -m shared.prompt_intelligence.cli analyze --all --type schema_error

# Before deploy
python3 -m shared.prompt_intelligence.cli analyze --all --top 10

# Test the system
./shared/prompt_intelligence/demo.sh
```
