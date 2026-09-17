# Quality Standards & Testing Strategy

## Quality Dimensions

- **5 dimensions**: Completeness, Accuracy, Consistency, Validity, Uniqueness
- Quality checks are deterministic — same data always produces same score
- Critical rule failures block zone promotion regardless of overall score
- Anomaly detection: outliers (>3 std dev), distribution shifts, volume anomalies (>20% deviation), null spikes
- Historical comparison: always compare current run against baseline

## PII Detection (automatic)

- AI-driven scanning after profiling via `shared/utils/pii_detection_and_tagging.py`
- Lake Formation LF-Tags for column-level security
- 12 PII types, 4 sensitivity levels (CRITICAL/HIGH/MEDIUM/LOW)
- MCP server at `mcp-servers/pii-detection-server/`

## Testing Strategy

- **Unit tests**: Jest + fast-check for every agent method. Mock external dependencies.
- **Property-based tests**: Transformation idempotency, lineage completeness, quality monotonicity, schema preservation, Bronze immutability.
- **Integration tests**: End-to-end Bronze→Silver→Gold pipeline, agent coordination, auth flows.
- **Coverage target**: 80% minimum.
- Place in `workloads/{name}/tests/` (workload-specific) or `tests/` (shared infrastructure).

## Data Zone Quality Gates

| Zone | Quality Gate | Format |
|---|---|---|
| Bronze | None (raw ingestion) | Raw source format |
| Silver | Score >= 0.80, no critical failures | Apache Iceberg (always) |
| Gold | Score >= 0.95, no critical failures | Iceberg (schema per use case) |
