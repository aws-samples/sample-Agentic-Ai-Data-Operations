# 06 — GOVERN: Trace Data Lineage
> Documentation, impact analysis, and compliance.

## Purpose

Generate comprehensive data lineage documentation for a workload, covering source-to-target flow, transformations, quality scores, FK relationships, and compliance controls. Useful for audits, impact analysis, and data governance.

## When to Use

- For compliance audits (GDPR, CCPA, SOX)
- Before making breaking changes to understand downstream impact
- To document data products for a data catalog
- When onboarding new team members who need to understand the pipeline

## Prompt Template

```
Analyze data lineage for [WORKLOAD_NAME]:

Provide:
1. Source -> Bronze -> Silver -> Gold flow
2. FK relationships
3. DAG dependencies
4. Column-level transformations
5. Quality scores
6. Usage (dashboards, APIs)

Generate data_product_catalog.yaml and lineage diagram.
```

## Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `WORKLOAD_NAME` | Workload to analyze | `customer_master` |

## Expected Output

1. `data_product_catalog.yaml` -- structured lineage metadata
2. Lineage diagram (ASCII or Mermaid) showing data flow
3. Column-level transformation mapping (source column -> target column + transformation)
4. FK relationship documentation
5. DAG dependency graph
6. Quality score summary per zone
7. Downstream usage list (dashboards, APIs, other workloads)

## Extended Prompt for Compliance Audits

For PII/compliance-focused lineage, use this extended version:

```
Analyze data lineage for [WORKLOAD_NAME] with focus on PII handling:

Scope: [WORKLOAD_LIST], with emphasis on data privacy compliance

Analysis:
1. Source-to-target lineage:
   - Trace PII columns: [COLUMNS] from source through all zones
   - Document transformations: Where is PII masked? Encrypted? Dropped?
   - Identify retention: How long is raw PII kept in each zone?

2. PII classifications:
   - List all columns classified as PII/PHI/PCI
   - Document masking methods used (hash, redact, drop)
   - Show which zones contain unmasked PII (Bronze only?)

3. Access controls:
   - Which IAM roles can access Bronze (raw PII)?
   - Which roles can access Silver (masked)?
   - Which roles can access Gold (aggregated, no PII)?

4. Compliance checkpoints:
   - Encryption: KMS keys used per zone
   - Audit logs: What operations are logged?
   - Data retention: [RETENTION_PER_ZONE]
   - Right to deletion: How to purge customer data?

5. Data flow diagram:
   - ASCII or Mermaid diagram showing PII flow
   - Annotate with encryption, masking, access control points
   - Highlight compliance controls

Output:
1. pii_lineage_report.md (detailed analysis)
2. pii_flow_diagram.md (visual with annotations)
3. compliance_controls.yaml (structured compliance metadata)
4. data_retention_policy.md (retention rules per zone)
5. access_control_matrix.md (who can access what)

Format for compliance team review (non-technical audience).
```
