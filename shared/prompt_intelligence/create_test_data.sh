#!/bin/bash
# Create Test Data for Prompt Intelligence System
# Generates synthetic trace logs to demonstrate pattern detection

set -e

echo "========================================="
echo "Creating Test Workloads"
echo "========================================="
echo

# Clean up any existing test workloads
echo "Cleaning up old test data..."
rm -rf workloads/test_* 2>/dev/null || true
echo "✓ Cleanup complete"
echo

# Test Scenario 1: Same mistake (missing PK) across 3 workloads
echo "Scenario 1: Missing Primary Key (3 workloads)"
echo "----------------------------------------------"

mkdir -p workloads/test_customer_data/logs
cat > workloads/test_customer_data/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T10:00:00Z", "run_id": "run_001", "event_type": "phase_start", "phase": 3, "agent": "metadata", "status": "running", "operation": "profile_schema"}
{"timestamp": "2026-03-25T10:01:30Z", "run_id": "run_001", "event_type": "error", "phase": 3, "agent": "metadata", "status": "failed", "error": "KeyError: 'primary_key' in schema inference - no PK column found in CSV", "agent_output": {"decisions": [{"decision": "Infer primary key from customer_id uniqueness", "reasoning": "Column has 99.8% uniqueness, likely a PK", "alternatives": ["Ask user for PK", "Use composite key", "Generate surrogate key"], "confidence": "low"}], "blocking_issues": [{"issue": "Cannot proceed without primary key", "severity": "critical", "category": "schema"}]}}
EOF
echo "✓ Created test_customer_data"

mkdir -p workloads/test_product_catalog/logs
cat > workloads/test_product_catalog/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T11:00:00Z", "run_id": "run_002", "event_type": "phase_start", "phase": 3, "agent": "metadata", "status": "running", "operation": "profile_schema"}
{"timestamp": "2026-03-25T11:02:15Z", "run_id": "run_002", "event_type": "error", "phase": 3, "agent": "metadata", "status": "failed", "error": "KeyError: 'primary_key' - CSV source has no explicit primary key column", "agent_output": {"decisions": [{"decision": "Use product_code as primary key", "reasoning": "Only column with high uniqueness", "alternatives": ["Ask user", "Composite PK: product_code + variant_id"], "confidence": "medium"}], "blocking_issues": [{"issue": "Test gate failed: missing primary key definition", "severity": "critical", "category": "schema"}]}}
EOF
echo "✓ Created test_product_catalog"

mkdir -p workloads/test_order_history/logs
cat > workloads/test_order_history/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T12:00:00Z", "run_id": "run_003", "event_type": "phase_start", "phase": 3, "agent": "metadata", "status": "running", "operation": "profile_schema"}
{"timestamp": "2026-03-25T12:01:45Z", "run_id": "run_003", "event_type": "error", "phase": 3, "agent": "metadata", "status": "failed", "error": "KeyError: 'primary_key' in metadata validation", "agent_output": {"decisions": [{"decision": "Assume order_id is primary key", "reasoning": "Matches naming convention for IDs", "alternatives": ["Validate with user", "Check for composite key"], "confidence": "low"}], "blocking_issues": [{"issue": "Metadata validation failed - no PK specified", "severity": "critical", "category": "schema"}]}}
EOF
echo "✓ Created test_order_history"

echo

# Test Scenario 2: PII false positive
echo "Scenario 2: PII False Positive (1 workload)"
echo "----------------------------------------------"

mkdir -p workloads/test_financial_data/logs
cat > workloads/test_financial_data/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T13:00:00Z", "run_id": "run_004", "event_type": "phase_start", "phase": 3, "agent": "metadata", "status": "running", "operation": "detect_pii"}
{"timestamp": "2026-03-25T13:01:20Z", "run_id": "run_004", "event_type": "error", "phase": 3, "agent": "metadata", "status": "failed", "error": "PII detection error: fund_name flagged as PII (name-based detection)", "agent_output": {"decisions": [{"decision": "Mask fund_name column", "reasoning": "Contains 'name' keyword, triggered PII detection", "alternatives": ["Review exclusion rules", "Manual override"], "confidence": "medium"}], "blocking_issues": [{"issue": "Excessive PII masking affecting business logic", "severity": "high", "category": "pii"}]}}
{"timestamp": "2026-03-25T13:02:00Z", "run_id": "run_004", "event_type": "error", "phase": 3, "agent": "metadata", "status": "failed", "error": "PII detection error: product_name flagged as PII", "agent_output": {"decisions": [{"decision": "Apply PII masking to product_name", "reasoning": "Name-based heuristic triggered", "alternatives": ["Check business context", "Add to exclusion list"], "confidence": "low"}], "blocking_issues": []}}
EOF
echo "✓ Created test_financial_data"

echo

# Test Scenario 3: Quality threshold too strict (2 workloads)
echo "Scenario 3: Quality Threshold Issues (2 workloads)"
echo "----------------------------------------------"

mkdir -p workloads/test_sales_data/logs
cat > workloads/test_sales_data/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T14:00:00Z", "run_id": "run_005", "event_type": "phase_start", "phase": 4, "agent": "quality", "status": "running", "operation": "validate_quality"}
{"timestamp": "2026-03-25T14:01:30Z", "run_id": "run_005", "event_type": "error", "phase": 4, "agent": "quality", "status": "failed", "error": "Quality threshold: completeness score 0.72 below threshold 0.80 for commission_rate column", "agent_output": {"decisions": [{"decision": "Set strict 0.80 completeness threshold for all columns", "reasoning": "Industry standard threshold", "alternatives": ["Adjust per-column thresholds", "Mark commission_rate as nullable"], "confidence": "medium"}], "blocking_issues": [{"issue": "Completeness check failed for commission_rate", "severity": "critical", "category": "quality"}]}}
EOF
echo "✓ Created test_sales_data"

mkdir -p workloads/test_marketing_data/logs
cat > workloads/test_marketing_data/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T15:00:00Z", "run_id": "run_006", "event_type": "phase_start", "phase": 4, "agent": "quality", "status": "running", "operation": "validate_quality"}
{"timestamp": "2026-03-25T15:01:45Z", "run_id": "run_006", "event_type": "error", "phase": 4, "agent": "quality", "status": "failed", "error": "Quality threshold: completeness score 0.76 below threshold 0.80 for campaign_notes column", "agent_output": {"decisions": [{"decision": "Apply 0.80 completeness to all text fields", "reasoning": "Consistent quality standards", "alternatives": ["Exclude optional fields", "Lower threshold for text fields"], "confidence": "medium"}], "blocking_issues": [{"issue": "Quality gate blocked due to completeness", "severity": "critical", "category": "quality"}]}}
EOF
echo "✓ Created test_marketing_data"

echo

# Test Scenario 4: Successful run with best practice
echo "Scenario 4: Best Practice Example (1 workload)"
echo "----------------------------------------------"

mkdir -p workloads/test_inventory_data/logs
cat > workloads/test_inventory_data/logs/trace_events.jsonl << 'EOF'
{"timestamp": "2026-03-25T16:00:00Z", "run_id": "run_007", "event_type": "phase_start", "phase": 1, "agent": "onboarding", "status": "running", "operation": "discovery"}
{"timestamp": "2026-03-25T16:01:00Z", "run_id": "run_007", "event_type": "question_asked", "phase": 1, "agent": "onboarding", "message": "What is the primary key for this CSV data?", "user_response": "sku + location_id"}
{"timestamp": "2026-03-25T16:02:00Z", "run_id": "run_007", "event_type": "phase_end", "phase": 3, "agent": "metadata", "status": "completed", "agent_output": {"decisions": [{"decision": "Ask user to explicitly specify primary key for CSV source before profiling", "reasoning": "CSV format lacks schema metadata - user input required to avoid incorrect assumptions", "alternatives": ["Infer from uniqueness (unreliable)", "Use row_hash as fallback"], "confidence": "high"}], "blocking_issues": []}}
{"timestamp": "2026-03-25T16:05:00Z", "run_id": "run_007", "event_type": "phase_end", "phase": 5, "agent": "orchestrator", "status": "completed", "agent_output": {"decisions": [{"decision": "Use composite primary key (sku + location_id) for deduplication", "reasoning": "User-specified composite key ensures correct dedup logic", "alternatives": [], "confidence": "high"}], "blocking_issues": []}}
EOF
echo "✓ Created test_inventory_data"

echo

# Summary
echo "========================================="
echo "Test Data Created Successfully"
echo "========================================="
echo
echo "Created 6 test workloads:"
echo "  3 with KeyError: 'primary_key' (BLOCKING)"
echo "  1 with PII false positives (DEGRADED)"
echo "  2 with quality threshold issues (BLOCKING)"
echo "  1 successful run with best practices"
echo
echo "Next steps:"
echo "  1. Run analysis:"
echo "     python3 -m shared.prompt_intelligence.cli analyze --all"
echo
echo "  2. View report:"
echo "     cat docs/prompt_intelligence/\$(date +%Y-%m-%d)_report.md"
echo
echo "  3. Clean up when done:"
echo "     rm -rf workloads/test_*"
echo
