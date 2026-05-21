# claims_v2 — Healthcare Claims Pipeline

HIPAA-compliant Bronze → Silver → Gold pipeline for insurance claims data, generated via template-driven codegen.

## Source

- **File**: `demo/sample_data/claims.csv` (50 rows, 31 columns)
- **Format**: CSV
- **Frequency**: Daily
- **Compliance**: HIPAA

## Pipeline

| Stage | Script | Template | Target |
|-------|--------|----------|--------|
| Bronze | `scripts/extract/ingest_claims.py` | `bronze_ingestion.py.j2` | `s3://data-lake/claims_v2/bronze/` |
| Silver | `scripts/transform/bronze_to_silver.py` | `silver_transform.py.j2` | `glue_catalog.claims_v2_db.silver_claims_v2` |
| Quality | `scripts/quality/check_quality.py` | `quality_check.py.j2` | Gate: 0.80 (Silver), 0.95 (Gold) |
| Gold | `scripts/transform/silver_to_gold.py` | `gold_aggregate.py.j2` | `glue_catalog.claims_v2_db.gold_claims_v2` |
| DAG | `dags/claims_v2_pipeline.py` | `airflow_dag.py.j2` | Daily 6am ET |

## Key Decisions

- **PK**: `claim_id`, dedup `keep_latest` by `submission_date`
- **PHI masking**: `member_ssn`, `member_dob`, `member_email` (SHA-256 hash)
- **Gold schema**: Flat Iceberg — KPIs by `claim_type` + `payer_name` (monthly grain)
- **Ontology**: Yes — 4 classes (Claim, Member, Provider, Payer), 21 properties

## Codegen

All scripts are rendered via `shared.codegen.renderer` — do NOT edit directly. To modify behavior:

1. Edit the relevant spec in `config/` (e.g., `silver.yaml`)
2. Re-render: `python3 -c "from shared.codegen.renderer import render; ..."`
3. Verify: `python -m shared.codegen.drift_validator workloads/claims_v2/`

## Config Files

| File | Contract |
|------|----------|
| `config/source.yaml` | `contracts/v1/source_profile.schema.json` |
| `config/bronze.yaml` | `contracts/v1/bronze_spec.schema.json` |
| `config/silver.yaml` | `contracts/v1/silver_spec.schema.json` |
| `config/gold.yaml` | `contracts/v1/gold_spec.schema.json` |
| `config/quality.yaml` | `contracts/v1/quality_spec.schema.json` |
| `config/dag.yaml` | `contracts/v1/dag_spec.schema.json` |
| `config/semantic.yaml` | Ontology Agent input |
| `config/ontology.ttl` | OWL2 ontology (4 classes) |
| `config/mappings.ttl` | R2RML triple maps (4 maps) |
