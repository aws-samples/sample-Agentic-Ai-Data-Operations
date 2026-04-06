---
name: Quality thresholds
description: 95% completeness, 0 critical failures, 7-year SOX retention
type: project
---

## Quality Dimension Thresholds

| Dimension | Threshold | Notes |
|---|---|---|
| Completeness | 95% | Core identifiers and financial metrics are 100% (critical) |
| Uniqueness | 100% | All PKs must be unique — no exceptions |
| Validity | 98% | Prices positive, dates not future, PE ratio -100 to 1000 |
| Consistency | 100% | FK integrity, calculation cross-checks |

## Zone Promotion Gates

- **Bronze -> Silver**: overall score >= 0.80, zero critical failures
- **Silver -> Gold**: overall score >= 0.95, zero critical failures

## SOX-Specific Rules

- **Retention**: 7 years for all data and audit logs
- **KMS encryption**: alias/sox-compliance-key (AES-256 at rest, TLS 1.3 in transit)
- **Audit alerts**: SOX audit channel emails compliance@company.com and audit@company.com with full quality report
- **Quarantine**: 90-day retention in quarantine zone, notification required

## Anomaly Detection

- Stock prices and portfolio values: z-score threshold 3.0
- Trading volume: IQR threshold 1.5
- Row count deviation: alert on >20% change from 30-day baseline
- Null percentage deviation: alert on >10% change from baseline
