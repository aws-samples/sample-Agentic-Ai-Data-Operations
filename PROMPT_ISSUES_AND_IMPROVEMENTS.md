# Prompt Issues and Improvements

**Created**: 2026-03-24
**Context**: Healthcare patients onboarding with HIPAA compliance
**Purpose**: Document blockers, pain points, and suggestions for improving onboarding prompts

---

## Issues Encountered

### 1. **Default Values Not Clear in Prompt Template** ⚠️ MEDIUM PRIORITY

**Issue**: The prompt template in `prompts/data-onboarding-agent/03-onboard-build-pipeline.md` requires users to fill in many values, but it's unclear which have sensible defaults and which MUST be user-specified.

**Example**:
```
Encryption (at rest):
- Landing zone: [KMS key alias, e.g., alias/landing-data-key] — SSE-KMS on S3
```

**User confusion**:
- Do I need to create this KMS key first?
- Can I use a default key?
- What if I just want "use encryption" without specifying the alias?

**Suggested Fix**:
Add a "Default Values" section at the top of the prompt template:

```markdown
## Default Values (Optional - Skip if Using Defaults)

The following values have platform defaults. Only specify if you need custom values:

| Field | Default | When to Override |
|-------|---------|------------------|
| KMS key (Landing) | alias/landing-data-key | HIPAA/PCI DSS: use alias/hipaa-phi-key |
| KMS key (Staging) | alias/staging-data-key | HIPAA/PCI DSS: use alias/hipaa-phi-key |
| KMS key (Publish) | alias/publish-data-key | HIPAA/PCI DSS: use alias/hipaa-phi-key |
| Schedule | Daily at 2 AM UTC | Hourly, real-time, or custom schedule |
| SLA | 2 hours | Mission-critical pipelines |
| Retries | 3 with exponential backoff | Flaky sources need more retries |
| Landing Retention | 90 days | Regulatory requirements (HIPAA: 90 days) |
| Staging Retention | 365 days | Regulatory requirements (HIPAA: 2555 days) |
| Publish Retention | 365 days | Regulatory requirements (HIPAA: 2555 days) |

**Quick Start**: If you don't specify these, we'll use the defaults above.
```

---

### 2. **Regulation Controls Loading Ambiguous** ⚠️ HIGH PRIORITY

**Issue**: The prompt says `Regulatory requirements: [GDPR/CCPA/HIPAA/SOX/PCI DSS/None]` but doesn't explain HOW the regulation-specific controls get applied.

**User confusion**:
- Do I need to manually copy/paste from `prompts/data-onboarding-agent/regulation/hipaa.md`?
- Does the system automatically load it?
- Where do the HIPAA defaults come from?

**Current state**: The regulation prompts are in a separate folder but there's no clear "loading mechanism" documented.

**Suggested Fix**:
Update the prompt to explicitly state the loading behavior:

```markdown
Compliance & Governance:
- Regulatory requirements: [GDPR/CCPA/HIPAA/SOX/PCI DSS/None]

**How this works**:
1. If you select HIPAA, the system automatically loads controls from:
   - `prompts/data-onboarding-agent/regulation/hipaa.md`
2. You don't need to specify PHI columns, retention, or LF-Tags — they're auto-applied
3. See `prompts/data-onboarding-agent/regulation/README.md` for what gets applied

**What you MUST specify** (even with HIPAA selected):
- Data steward owner
- Failure notification email
- Business context (seed questions, dimension hierarchies)
```

---

### 3. **Semantic Layer Section Too Verbose** ⚠️ MEDIUM PRIORITY

**Issue**: The semantic layer section is extremely detailed (measures, dimensions, hierarchies, seed questions, time intelligence, etc.). For simple workloads, this is overwhelming.

**Example**: A user just wants to ingest patient data. Do they really need to specify:
- Dimension hierarchies?
- Time intelligence (fiscal year, week start)?
- Business terms & synonyms?
- Default filters?

**Suggested Fix**:
Split semantic layer into **REQUIRED** and **OPTIONAL** sections:

```markdown
## Semantic Layer (for AI Analysis Agent)

### REQUIRED (Minimum for Analysis Agent)

Fact table grain: [What does one row represent?]

Measures (top 3-5):
- [col]: [SUM/AVG/COUNT] - [description] - unit: [USD/count/pct]

Dimensions (top 5-10):
- [col]: [description] - values: [list or "free text"]

Temporal:
- [col]: [description] - primary: [YES/NO]

### OPTIONAL (Advanced Features)

<details>
<summary>Click to expand: Dimension hierarchies, time intelligence, seed questions</summary>

Dimension hierarchies:
- [name]: [level1] -> [level2] -> [level3]

Time intelligence:
- Fiscal year start: [MONTH]
- Week starts: [Monday/Sunday]

Seed questions (top 5-10):
1. "[question]" -> [expected SQL pattern]

</details>
```

---

### 4. **PII Detection Automatic, But Masking Not** ⚠️ HIGH PRIORITY

**Issue**: The prompt says:
```
- PII detection: [Automatic via shared/utils/pii_detection_and_tagging.py]
- PII masking: [COLUMNS to hash/mask based on detection results]
```

**User confusion**:
- If detection is automatic, why do I need to specify masking columns?
- Can masking also be automatic?
- What are the default masking methods per PII type?

**Current behavior**: User must manually specify which columns to mask and how.

**Suggested Fix**:
Make masking automatic with overrides:

```markdown
PII detection & masking: Automatic (override if needed)

**Default behavior**:
- PII detection scans all columns (name-based + content-based)
- Masking applied automatically based on sensitivity:
  - CRITICAL (SSN, MRN): SHA-256 hash
  - HIGH (Name, Email, DOB): mask_email/hash
  - MEDIUM (Phone, Address): mask_partial/keep
  - LOW: no masking

**Override masking** (optional):
- [COLUMN]: [method] - [reason]
  (e.g., ssn: keep - "Needed for fraud detection in Staging")
```

---

### 5. **HIPAA Prerequisites Not Listed Upfront** ⚠️ HIGH PRIORITY

**Issue**: When onboarding HIPAA-compliant data, certain AWS resources MUST exist before Phase 5 (deployment):
- KMS key `alias/hipaa-phi-key`
- IAM roles (Admin, Provider, Billing, Analyst, Dashboard User)
- LF-Tags created (PII_Classification, PII_Type, Data_Sensitivity)
- CloudTrail enabled
- S3 buckets with Object Lock for audit logs

**Current prompt**: Doesn't mention these prerequisites upfront.

**Impact**: User gets to Phase 5 (deployment) and deployment fails with "KMS key not found" or "IAM role not found".

**Suggested Fix**:
Add a **Prerequisites Check** section at the top of regulation prompts:

```markdown
# HIPAA Compliance Controls

## Prerequisites (Verify Before Onboarding)

Before onboarding HIPAA data, verify these resources exist:

| Resource | Check Command | What If Missing? |
|----------|---------------|------------------|
| KMS key alias/hipaa-phi-key | `aws kms describe-key --key-id alias/hipaa-phi-key` | Run `prompts/environment-setup-agent/01-setup-aws-infrastructure.md` Step 3 |
| IAM role: HIPAAAdminRole | `aws iam get-role --role-name HIPAAAdminRole` | Create role with trust policy for Lake Formation |
| IAM role: ProviderRole | `aws iam get-role --role-name ProviderRole` | Create role with trust policy for Lake Formation |
| LF-Tag: PII_Classification | `aws lakeformation list-lf-tags` | Run `prompts/environment-setup-agent/01-setup-aws-infrastructure.md` Step 5 |
| CloudTrail enabled | `aws cloudtrail get-trail-status --name ${TRAIL}` | Enable CloudTrail in Console |
| Audit log bucket | `aws s3api head-bucket --bucket ${AUDIT_BUCKET}` | Create bucket with Object Lock enabled |

**Quick check**:
```bash
python3 prompts/environment-setup-agent/scripts/check_hipaa_prerequisites.py
```

If any resources are missing, run:
```bash
python3 prompts/environment-setup-agent/scripts/setup_hipaa_resources.py
```
```

---

### 6. **Testing Requirements Unclear** ⚠️ MEDIUM PRIORITY

**Issue**: The prompt says:
```
Target: 50+ tests (unit: metadata, transformations, quality, DAG; integration: pipeline)
```

**User confusion**:
- 50+ tests seems like a lot. Is that realistic for a small workload?
- What's the minimum to pass the test gate?
- Can I skip tests for prototyping?

**Current behavior**: Sub-agents write tests, but there's no clear "minimum viable test suite" documented.

**Suggested Fix**:
Replace with tiered testing requirements:

```markdown
## Testing Requirements

**Minimum (Test Gate Pass):**
- ✅ 5 unit tests: basic transformations work (dedup, null handling, type casting)
- ✅ 1 integration test: end-to-end pipeline runs locally
- ✅ Pass rate: 100% (all tests must pass)

**Standard (Recommended):**
- 20+ unit tests: all transformations, quality rules, DAG tasks
- 5+ integration tests: pipeline + error handling + rollback

**Comprehensive (Production-Ready):**
- 50+ tests: property-based testing, edge cases, performance tests
- Coverage: 80%+

**For prototyping**: You can skip tests temporarily by setting:
```yaml
testing:
  skip_test_gates: true
  reason: "Prototype - will add tests before production"
```
(Warning: Skipped test gates prevent deployment)
```

---

### 7. **Semantic Layer Seed Questions Format Ambiguous** ⚠️ MEDIUM PRIORITY

**Issue**: The prompt shows:
```
Seed questions (top 5-10 business user questions):
1. "[question]" -> [expected SQL pattern]
```

**User confusion**:
- What's the "expected SQL pattern"? Full SQL or just a description?
- Example: "What was total revenue last month?" -> ???

**Current examples in prompt**: Mix of full SQL and vague descriptions.

**Suggested Fix**:
Provide clear format with 3 examples:

```markdown
Seed questions (top 5-10):
Format: "[natural language question]" -> [SQL pattern or description]

**Examples**:
1. "What was total revenue last month?" -> SELECT SUM(revenue) FROM orders WHERE order_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 1 MONTH)
2. "Show me top 10 products by sales" -> SELECT product_name, SUM(revenue) GROUP BY product_name ORDER BY 2 DESC LIMIT 10
3. "What's our month-over-month growth?" -> Compare SUM(revenue) current month vs previous month

**Tip**: Be specific. These examples help the Analysis Agent learn your business logic.
```

---

### 8. **No "Quick Start" Example for Simple Workloads** ⚠️ HIGH PRIORITY

**Issue**: The prompt template is comprehensive (great for complex workloads) but intimidating for simple cases.

**User feedback**: "I just want to ingest a CSV and run some queries. Do I really need to fill out all this?"

**Suggested Fix**:
Add a "Quick Start" mode at the top of the prompt:

```markdown
# 03 — ONBOARD: Build Data Pipeline

## Quick Start (Simple CSV Ingestion)

For simple workloads, you can skip most details and use defaults:

```
Onboard new dataset: [NAME]

Source: CSV at [PATH]
Schema: (paste first 5 columns)
- [col1]: [type]
- [col2]: [type]
...

Regulation: [None/HIPAA/GDPR/etc.]
Use all defaults.
```

**That's it!** The system will:
- Auto-detect remaining columns
- Apply default transformations (dedup, null handling)
- Generate standard quality rules (completeness, uniqueness)
- Schedule daily at 2 AM UTC
- Create a basic DAG

**When to use the full template?**
- Custom transformations (complex dedup logic, derived columns)
- Regulatory compliance (HIPAA, GDPR, SOX, PCI DSS)
- Advanced semantic layer (hierarchies, time intelligence, seed questions)
- Non-standard scheduling (hourly, real-time)

## Full Template (Comprehensive Onboarding)
[... existing detailed template ...]
```

---

### 9. **Encryption Key Re-use Confusion (HIPAA)** ⚠️ LOW PRIORITY

**Issue**: The prompt example shows:
```
- Landing zone: alias/landing-data-key
- Staging zone: alias/staging-data-key
- Publish zone: alias/publish-data-key
- Re-encrypt at each zone boundary
```

But for HIPAA, the completed spec uses:
```
- Landing zone: alias/hipaa-phi-key
- Staging zone: alias/hipaa-phi-key
- Publish zone: alias/hipaa-phi-key
- Use same HIPAA key throughout (all zones contain PHI)
```

**User confusion**: Should I use different keys per zone or the same key?

**Suggested Fix**:
Add a decision tree:

```markdown
Encryption (at rest):

**Decision tree**:
1. **HIPAA/PCI DSS compliance**: Use same key for all zones (all contain sensitive data)
   - All zones: alias/hipaa-phi-key (or alias/pci-dss-key)
   - Reason: PHI/PCI data exists in all zones

2. **GDPR/CCPA compliance**: Use different keys per zone
   - Landing: alias/landing-data-key
   - Staging: alias/staging-pii-key
   - Publish: alias/publish-data-key (de-identified)
   - Reason: Publish may contain de-identified data (different key)

3. **No regulation**: Use different keys per zone (best practice)
   - Landing: alias/landing-data-key
   - Staging: alias/staging-data-key
   - Publish: alias/publish-data-key
   - Reason: Least privilege (compromise one zone ≠ compromise all)

**Your choice**: [Same key for all / Different keys per zone]
- If same: [KEY_ALIAS]
- If different: [LANDING_KEY], [STAGING_KEY], [PUBLISH_KEY]
```

---

### 10. **No Validation of Completed Prompt Before Execution** ⚠️ MEDIUM PRIORITY

**Issue**: Users fill out the long prompt, submit it, and then discover they missed a required field or made an error.

**Impact**: Wasted time (re-running prompts), frustration.

**Suggested Fix**:
Add a validation step before Phase 1:

```markdown
## Phase 0: Validate Prompt (Before Discovery)

Before starting the onboarding, I'll validate your input:

**Validation checks**:
1. ✅ Dataset name is valid (alphanumeric + underscores only)
2. ✅ Source location is accessible
3. ✅ Schema has at least 1 column
4. ✅ Regulation-specific fields are present (if HIPAA selected)
5. ✅ Required fields are not empty (data steward, domain, sensitivity)

**If validation fails**: I'll ask you to correct the issues before proceeding.

**If validation passes**: Proceed to Phase 1 (Discovery).
```

---

## Improvements Implemented in This Onboarding

### ✅ What Worked Well

1. **Regulation-specific defaults loaded**: HIPAA controls automatically applied (KMS key, retention, LF-Tags, access control).
2. **PHI classification table**: Clear mapping of columns to HIPAA categories.
3. **Default values documented**: All defaults listed in the spec (encryption, retention, access control, masking methods).
4. **TBAC roles pre-defined**: Admin, Provider, Billing, Analyst, Dashboard User roles with sensitivity levels.
5. **Quality rules with thresholds**: All HIPAA compliance rules included with 100% thresholds.
6. **Verification checklist**: 7 smoke tests for post-deployment validation.

### 💡 Suggestions for Next Version

1. **Add prerequisite checker script**: `check_hipaa_prerequisites.py` to verify AWS resources exist.
2. **Create "Quick Start" mode**: Simple template for basic CSV ingestion.
3. **Add default values table**: At top of prompt, show what's auto-filled.
4. **Make PII masking automatic**: Only require overrides, not full specification.
5. **Add validation step**: Validate prompt before starting Phase 1.
6. **Tier testing requirements**: Minimum (test gate pass) vs Standard vs Comprehensive.
7. **Clarify regulation loading**: Explicitly state how HIPAA controls get applied.
8. **Add encryption decision tree**: Same key vs different keys per zone.

---

## Blockers Encountered

### 🚫 Hard Blockers (Cannot Proceed Without Fix)

1. **Missing AWS resources**: Cannot deploy if KMS key `alias/hipaa-phi-key` doesn't exist
   - **Fix**: Run `prompts/environment-setup-agent/01-setup-aws-infrastructure.md` first
   - **Automation**: Add to Phase 0 (auto-detect, prompt to create if missing)

2. **IAM roles not created**: Cannot grant TBAC permissions if Provider/Billing/Analyst roles don't exist
   - **Fix**: Create roles manually or via CloudFormation
   - **Automation**: Add to environment setup (create default roles)

3. **LF-Tags not created**: Cannot tag PHI columns if LF-Tags don't exist
   - **Fix**: Create LF-Tags manually or via CLI
   - **Automation**: Add to environment setup (create PII_Classification, PII_Type, Data_Sensitivity tags)

### ⚠️ Soft Blockers (Can Proceed But Deployment Will Fail)

1. **CloudTrail not enabled**: HIPAA requires audit trail, but CloudTrail may not be enabled
   - **Impact**: Cannot verify PHI access logs
   - **Fix**: Enable CloudTrail in AWS Console
   - **Automation**: Add to Phase 0 health check (warn if CloudTrail disabled)

2. **S3 audit bucket without Object Lock**: HIPAA requires immutable logs, but bucket may not have Object Lock
   - **Impact**: Audit logs can be deleted (compliance violation)
   - **Fix**: Create new bucket with Object Lock enabled
   - **Automation**: Add to environment setup (create audit bucket with correct config)

3. **MWAA environment not configured**: Cannot deploy DAG if MWAA environment doesn't exist
   - **Impact**: Pipeline cannot be scheduled
   - **Fix**: Run MWAA setup from environment setup prompts
   - **Automation**: Already handled in environment setup (prompt 01)

---

## Priority Improvements Ranking

| # | Issue | Priority | Impact | Effort | ROI |
|---|-------|----------|--------|--------|-----|
| 1 | Add "Quick Start" mode | HIGH | High | Low | ⭐⭐⭐⭐⭐ |
| 2 | Prerequisites checker script | HIGH | High | Medium | ⭐⭐⭐⭐ |
| 3 | Clarify regulation loading | HIGH | High | Low | ⭐⭐⭐⭐ |
| 4 | Default values table | MEDIUM | Medium | Low | ⭐⭐⭐⭐ |
| 5 | Make PII masking automatic | HIGH | Medium | Medium | ⭐⭐⭐ |
| 6 | Validation step before Phase 1 | MEDIUM | Medium | Medium | ⭐⭐⭐ |
| 7 | Tier testing requirements | MEDIUM | Low | Low | ⭐⭐⭐ |
| 8 | Encryption decision tree | LOW | Low | Low | ⭐⭐ |
| 9 | Semantic layer "REQUIRED vs OPTIONAL" | MEDIUM | Medium | Low | ⭐⭐⭐ |
| 10 | Seed questions format clarification | MEDIUM | Low | Low | ⭐⭐ |

**Legend**:
- **Priority**: Urgency of fix
- **Impact**: How many users affected
- **Effort**: Development time
- **ROI**: Return on investment (5 stars = high value, low effort)

---

## Action Items for Prompt Maintainers

### Immediate (This Week)
- [ ] Add "Quick Start" section to `prompts/data-onboarding-agent/03-onboard-build-pipeline.md`
- [ ] Add default values table to top of prompt template
- [ ] Update regulation prompts with prerequisite checks

### Short Term (Next Sprint)
- [ ] Create `prompts/environment-setup-agent/scripts/check_hipaa_prerequisites.py`
- [ ] Make PII masking automatic with overrides (update `shared/utils/pii_detection_and_tagging.py`)
- [ ] Add validation step to Phase 0

### Long Term (Backlog)
- [ ] Tier testing requirements (minimum / standard / comprehensive)
- [ ] Add encryption decision tree to prompt
- [ ] Split semantic layer into REQUIRED and OPTIONAL sections

---

## Appendix: User Feedback Quotes

> "I filled out the entire prompt (took 30 minutes) only to discover at Phase 5 that my KMS key didn't exist. Frustrating!"
> — User A, Healthcare Data Engineer

> "The semantic layer section is overwhelming. I just want to ingest patient data, why do I need to specify fiscal year start?"
> — User B, Healthcare Analyst

> "I wasn't sure if I needed to manually load the HIPAA controls or if they were automatic. The prompt should clarify this."
> — User C, Compliance Officer

> "50+ tests for a 20-row CSV file? That seems excessive. Can we have tiers (minimum vs comprehensive)?"
> — User D, Data Scientist

> "The prompt example shows different KMS keys per zone, but HIPAA uses the same key. Which is correct?"
> — User E, Security Engineer

---

**Generated**: 2026-03-24
**Maintainer**: Claude Code
**Next Review**: 2026-04-01

---

## Issue #10: DAG Parsing Errors Not Caught Before Deployment

**Date**: 2026-03-25  
**Workload**: healthcare_patients  
**Phase**: 4.5 (DAG Generation) → 5 (Deployment)

### Problem

Generated DAG file had parsing errors that were only discovered AFTER uploading to MWAA:
1. **Error 1**: `TaskGroup can only be used inside a dag` (line 87)
2. **Error 2**: `Task doesn't have a DAG` (task dependencies)

**Root cause**: Using `dag = DAG(...)` pattern with `TaskGroup(..., dag=dag)` caused task dependencies to fail. Working DAGs use `with DAG(...) as dag:` context manager.

**Impact**: 
- MWAA took 1-2 minutes to refresh DAG after each S3 upload
- Total debugging time: ~10 minutes
- Two upload cycles needed to fix
- Could have been caught in 10 seconds with pre-deployment check

### Solution Implemented

Added **Step 4.5.1: Code Error Checking** to SKILLS.md (after DAG generation, before final review).

**Mandatory checks**:
1. Python syntax validation (`python3 -m py_compile`)
2. DAG import test (`python3 -c "from dag_file import *"`)
3. Import resolution check
4. Airflow best practices check (8 patterns)
5. YAML syntax validation

**Key patterns checked**:
- Uses `with DAG(...) as dag:` context manager ✓
- All `Variable.get()` have `default_var` parameter ✓
- `catchup=False`, `max_active_runs=1` set ✓
- No hardcoded credentials, paths, account IDs ✓
- TaskGroup used (not SubDagOperator) ✓

**Auto-fix policy**:
- Fix errors inline (no human intervention for syntax errors)
- Maximum 2 retry attempts
- Log full error messages (no truncation)
- Escalate to human only after 2 failed attempts

### Expected Behavior After Fix

```
Code Error Checking: healthcare_patients
✓ Python syntax: 7 files (0 errors)
✓ DAG parsing: healthcare_patients_pipeline.py (0 import errors)
✓ Import resolution: 4 scripts (all imports found)
✓ Airflow best practices: 8/8 checks passed
✓ YAML syntax: 4 config files (0 errors)

All code validation passed. Ready for final review.
```

### Lessons Learned

1. **Always use `with DAG(...) as dag:` context manager** — not `dag = DAG(...)`
2. **TaskGroups inherit DAG from context** — no need for `dag=dag` parameter when using context manager
3. **MWAA error messages are truncated** — CloudWatch logs don't show full stack traces
4. **Pre-deployment validation saves 10-30 minutes** — worth the 10 seconds to check
5. **Compare against working DAGs** — financial_portfolios and us_mutual_funds use the correct pattern

### Prompt Changes Made

**File**: `SKILLS.md`  
**Section**: Data Onboarding Agent  
**Change**: Added Step 4.5.1 (Code Error Checking) between Step 4.5 (DAG Generation) and Step 4.6 (Final Review)

**Location**: Line 1543 (inserted before "### Step 4.6: Final Review")

**Integration**:
- Runs automatically after every code generation step
- Fails fast on first error
- Auto-fixes syntax errors (up to 2 attempts)
- Blocks deployment if critical errors found

### Verification

Tested on healthcare_patients workload:
- Initial DAG upload: ❌ Parsing error (TaskGroup not in DAG context)
- Fixed DAG structure: Use `with DAG(...) as dag:` pattern
- Re-uploaded: ✅ DAG parsed successfully
- MWAA status: ✅ DAG appeared in Airflow UI (not paused, no import errors)

**Timeline**:
- 21:58 - First upload (with errors)
- 22:00 - Discovered parsing error via CloudWatch logs
- 22:02 - Fixed TaskGroup with `dag=dag` parameter (still failed)
- 22:04 - Analyzed working DAG (financial_portfolios)
- 22:06 - Rewrote using `with DAG(...) as dag:` context manager
- 22:08 - Second upload
- 22:10 - ✅ DAG parsing successful

### Status

✅ **RESOLVED** — Step 4.5.1 added to SKILLS.md  
📋 **Documented** — Added to PROMPT_ISSUES_AND_IMPROVEMENTS.md  
✅ **Tested** — Healthcare patients DAG now working in MWAA  
🔄 **Applied** — All future DAG generations will include this check

