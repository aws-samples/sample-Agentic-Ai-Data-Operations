# PII Detection - Quick Reference Card

**TL;DR**: AI-powered PII detection with Lake Formation tagging

---

## 🚀 Quick Start

### Test Locally (Python Script)
```bash
python3 test_pii_detection.py
```

### Via Claude Code (MCP Server)
```
"Scan the customer_data table for PII"
```

---

## 📊 What Gets Detected

| Sensitivity | PII Types | Example |
|-------------|-----------|---------|
| **CRITICAL** | SSN, Credit Card, Bank Account | 123-45-6789 |
| **HIGH** | Email, Name, Date of Birth | alice@email.com |
| **MEDIUM** | Phone, Address, IP | (555) 123-4567 |
| **LOW** | ZIP Code | 02101 |

---

## 🔧 MCP Tools (6 total)

```
detect_pii_in_table        → Scan one table
scan_database_for_pii      → Scan all tables
create_lf_tags             → Setup LF tags
get_pii_columns            → List PII columns
apply_column_security      → Grant access by sensitivity
get_pii_report             → Compliance report
```

---

## 📝 Common Commands

### Scan a table
```
"Detect PII in finsights_silver.customer_data"
```

### Apply tags
```
"Detect PII and apply Lake Formation tags"
```

### Grant access
```
"Grant analyst role access to LOW and MEDIUM PII"
```

### Report
```
"Generate PII report for production database"
```

---

## 📁 Test Files

- `test_pii_detection.py` → Standalone test script
- `sample_data/customer_pii_test.csv` → Test data with all PII types
- `PII_DETECTION_TEST_REPORT.md` → Full test results
- `MCP_PII_USAGE_EXAMPLES.md` → Usage examples

---

## ✅ Test Results

**Accuracy**: 96.6% (28/29 detections correct)
**Coverage**: 12 PII types × 4 sensitivity levels
**Methods**: Name-based + Content-based (regex)

---

## 🔐 Security Best Practices

| Sensitivity | Access Control | Masking | Audit |
|-------------|----------------|---------|-------|
| CRITICAL | Executive approval | Always | All access |
| HIGH | RBAC + LF tags | Prod only | Access |
| MEDIUM | LF tags | Optional | Changes |
| LOW | Standard RBAC | No | No |

---

**Status**: ✅ Production-ready
**Last Tested**: March 17, 2026
