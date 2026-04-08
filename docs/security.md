# Security & Sanitization

This repository has been sanitized for public GitHub release.

---

## What Was Removed/Sanitized

### ✅ Removed Files (156MB total)

| File/Directory | Size | Reason |
|----------------|------|--------|
| `mcp-main/` | 71 MB | Cloned AWS MCP repo (not part of this project) |
| `agent_run_logs/` | ~50 MB | Agent execution logs with local paths |
| `logs/` | ~30 MB | MCP server logs with local details |
| `.mcp.json` | 5 KB | Local MCP configuration with absolute paths |
| `pii_detection_test_results_*.json` | 3 KB | Test output files |
| `workloads/*/governance/pii_report_*.json` | 5 KB | PII detection reports |

### ✅ Sanitized Information (63 files)

| Sensitive Data | Replaced With | Occurrences |
|----------------|---------------|-------------|
| AWS Account ID `133661573128` | `123456789012` | 130 |
| S3 bucket `finsights-datalake` | `your-datalake-bucket` | 128 |
| Local paths `/Users/hcherian/...` | `/path/to/user/...` | 11 |
| AWS ARNs with real account | Example ARNs | ~50 |

### ✅ Protected in .gitignore

The following are now ignored by Git:

```
# Credentials & Secrets
.aws/
*.pem
*.key
credentials
secrets.yml
secrets.json
.env

# MCP Config (local paths)
.mcp.json

# Test Results & Logs
logs/
agent_run_logs/
pii_detection_test_results_*.json
*.log

# Output Data
**/output/bronze/
**/output/silver/
**/output/gold/
**/governance/pii_report_*.json
```

---

## What's Safe to Commit

### ✅ Safe Files

- **Documentation**: All `.md` files (sanitized)
- **Code**: Python, SQL, YAML (sanitized, no secrets)
- **Test Scripts**: Unit/integration tests (no real data)
- **Sample Data**: `sample_data/*.csv` (demo data only)
- **Configuration Templates**: `*.example`, `*_template.yaml`
- **Output Examples**: Small example CSVs with masked PII (email_hash, phone_masked)

### ⚠️ Use Placeholders

All AWS-specific values use placeholders:

```yaml
# Example from config files
aws_account_id: "123456789012"  # Replace with your account
s3_bucket: "your-datalake-bucket"  # Replace with your bucket
iam_role: "arn:aws:iam::123456789012:role/YourRole"  # Replace
```

---

## Configuration Files

### `.mcp.json`

The `.mcp.json` is committed to the repo and is portable (no local paths, no secrets). It uses `uvx` to auto-install MCP server packages and references relative paths only.

To customize for your account, edit `AWS_REGION` and `AWS_PROFILE`:
```bash
sed -i 's/us-east-1/your-region/g' .mcp.json
sed -i 's/"default"/"your-profile"/g' .mcp.json
```

See `mcp-setup.md` for full setup guide.

### AWS Credentials

**NEVER** commit:
- `~/.aws/credentials`
- `~/.aws/config`
- Any file with `AKIA` (AWS access key prefix)
- Any file with passwords, tokens, or secrets

Use:
- AWS Secrets Manager
- Environment variables
- Airflow Connections
- Parameter Store

---

## PII in Sample Data

Sample CSV files (`sample_data/*.csv`) contain:
- **Synthetic names**: Alice Smith, Bob Johnson, etc.
- **Fake emails**: `name@example.com` or `name@gmail.com` (not real)
- **Random phone numbers**: `(555) xxx-xxxx` (N11 codes = non-working)
- **Fake SSNs**: `123-45-6789` (invalid range)

Output CSV files in `workloads/*/output/` use:
- **Masked phone**: `******5471` (last 4 digits only)
- **Hashed email**: SHA-256 hash (irreversible)
- **No real PII**: All test data is synthetic

---

## Automated Security Hooks (pre-commit)

The repository uses the **pre-commit framework** to automatically scan every commit for security issues. Hooks run in under 5 seconds and catch vulnerabilities before code leaves your machine.

### Setup

```bash
# Install pre-commit and hook dependencies
pip install pre-commit

# Install hooks into your local .git/hooks/
pre-commit install

# Run all hooks manually against the full repo
pre-commit run --all-files
```

### What Gets Scanned

| Hook | What It Catches | Severity |
|------|----------------|----------|
| **git-secrets** (existing) | AWS access keys, secret keys, account IDs | BLOCK |
| **detect-secrets** | API keys, tokens, passwords, private keys (broader than git-secrets) | BLOCK |
| **bandit** | SQL injection, hardcoded passwords, exec/eval, unsafe deserialization | BLOCK (medium+) |
| **pii-code-scanner** | SSN, credit card, email, phone, DOB patterns in source code | BLOCK (CRITICAL), WARN (HIGH) |
| **cedar-policy-validator** | Cedar policy syntax errors (broken guardrails) | BLOCK |
| **yaml-config-validator** | Missing required keys in workload configs, hardcoded secrets in YAML | BLOCK |
| **sensitive-info-scanner** | Hardcoded passwords/tokens, private keys, connection strings with creds, real S3 buckets | BLOCK (CRITICAL), WARN (HIGH) |
| **check-yaml** | YAML syntax errors | BLOCK |
| **check-added-large-files** | Files > 5MB | BLOCK |
| **no-commit-to-branch** | Direct commits to main | BLOCK |

### Custom Hook Validators

Located in `shared/utils/hook_validators/`:

- **`pii_code_scanner.py`** — Reuses PII regex patterns from `shared/utils/pii_detection_and_tagging.py`. Skips regex definitions and comments (false positives). Blocks on CRITICAL (SSN, credit card), warns on HIGH (email, DOB).
- **`cedar_validator.py`** — Validates `.cedar` and `.cedarschema` files. Uses cedarpy if available, falls back to structural checks (balanced braces, forbid/permit keywords, required fields).
- **`yaml_config_validator.py`** — Validates `workloads/*/config/*.yaml` against expected schemas (source.yaml, quality_rules.yaml, schedule.yaml, semantic.yaml). Also scans for hardcoded secrets in YAML values.
- **`sensitive_info_scanner.py`** — Catches hardcoded passwords, tokens, private keys, connection strings with credentials, and real AWS infrastructure details. Complements git-secrets with broader pattern coverage.

### Bypass (Emergency Only)

```bash
# Skip a specific hook
SKIP=pii-code-scanner git commit -m "reason for bypass"

# Skip all pre-commit hooks (use sparingly)
git commit --no-verify -m "EMERGENCY: reason"

# Skip pre-push hooks
git push --no-verify
```

All bypasses are logged. Use `.gitallowed` to permanently allow false-positive patterns.

### CI/CD Integration

GitHub Actions workflow (`.github/workflows/security-scan.yml`) runs on every PR to main:
1. All pre-commit hooks on full repo
2. Dependency vulnerability scan (pip-audit)
3. Cedar policy + hook validator tests
4. Bandit security analysis with report

### Adding New Patterns

- **PII patterns**: Add to `PII_PATTERNS` in `shared/utils/hook_validators/pii_code_scanner.py`
- **Secret patterns**: Add to `SENSITIVE_PATTERNS` in `shared/utils/hook_validators/sensitive_info_scanner.py`
- **Allowed values**: Add to `.gitallowed` (one pattern per line, `#` for comments)
- **Config schemas**: Add to `CONFIG_SCHEMAS` in `shared/utils/hook_validators/yaml_config_validator.py`

---

## Pre-Commit Checklist (Manual)

For additional verification before pushing to GitHub:

```bash
# 1. Run all automated hooks
pre-commit run --all-files

# 2. Check for sensitive data (should return 0)
grep -r "AKIA" . --exclude-dir=.git
grep -r "aws_secret" . --exclude-dir=.git

# 3. Check for real account IDs (should return 0)
grep -r "133661573128" . --exclude-dir=.git

# 4. Check for local paths (should return 0)
grep -r "/Users/hcherian" . --exclude-dir=.git --exclude="*.md"

# 5. Verify .gitignore is working
git status --ignored

# 6. Review what's being committed
git diff --staged
```

All checks should return **0 matches** for sensitive data.

---

## Reporting Security Issues

If you find sensitive information that was missed:

1. **DO NOT** create a public GitHub issue
2. Email the repository owner directly
3. Use GitHub's private vulnerability reporting (if enabled)

---

## License

This project is released under the MIT License. See `LICENSE` file.

---

**Last Sanitized**: March 17, 2026
**Files Sanitized**: 63
**Data Removed**: 156 MB
**Status**: ✅ Safe for public release
