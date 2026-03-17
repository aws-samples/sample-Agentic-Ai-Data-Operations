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
| Local paths `>/path/to/user/...` | `/path/to/user/...` | 11 |
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

### `.mcp.json` → `.mcp.json.example`

The real `.mcp.json` contains local paths and is **gitignored**.

Use the template:
```bash
cp .mcp.json.example ~/.mcp.json
# Edit with your actual paths
```

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

## Pre-Commit Checklist

Before pushing to GitHub:

```bash
# 1. Check for sensitive data
grep -r "AKIA" . --exclude-dir=.git
grep -r "aws_secret" . --exclude-dir=.git
grep -r "password" . --exclude-dir=.git --exclude="*.md"

# 2. Check for real account IDs (should return 0)
grep -r "133661573128" . --exclude-dir=.git

# 3. Check for local paths (should return 0)
grep -r "/Users/hcherian" . --exclude-dir=.git --exclude="*.md"

# 4. Verify .gitignore is working
git status --ignored

# 5. Review what's being committed
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
