---
name: Source facts
description: CSV source, 52 rows (2 duplicates for testing), PK=customer_id, 3 PII columns
type: project
---

## Source Overview

- **Type**: CSV file on S3
- **Format**: CSV, comma-delimited, UTF-8, header row
- **Expected rows**: 52 (includes 2 duplicate pairs for dedup testing)
- **Primary key**: customer_id (format: CUST-NNN)
- **Owner**: CRM Team / Sales

## Schema

| Column | Type | Nullable | PII | Notes |
|---|---|---|---|---|
| customer_id | string | no | no | PK, format CUST-NNN |
| name | string | no | yes | Keep for reporting (do not hash) |
| email | string | yes | yes | SHA-256 hash in Silver |
| phone | string | yes | yes | Mask last 4 digits in Silver |
| segment | string | no | no | Enterprise, SMB, Individual |
| industry | string | yes | no | Industry vertical |
| country | string | no | no | US, UK, CA, DE |
| status | string | no | no | Active, Inactive, Churned |
| join_date | date | no | no | Format YYYY-MM-DD |
| annual_value | decimal | no | no | Annual contract value USD |
| credit_limit | decimal | no | no | Assigned credit limit USD |

## PII Handling Strategy

- **name**: Keep readable for reporting — do NOT mask or hash
- **email**: SHA-256 hash in Silver zone (irreversible)
- **phone**: Mask to show last 4 digits only (e.g., ***-***-1234)

## Segments

Three customer segments with different analysis patterns:
- **Enterprise**: High annual_value, complex reporting needs
- **SMB**: Mid-range, standard dashboards
- **Individual**: Lower value, volume-based analysis
