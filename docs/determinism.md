# Deterministic Code Generation

All pipeline artifacts (scripts, DAGs, SQL) are produced via a **spec → template → artifact** chain that guarantees bit-for-bit reproducibility. Given identical spec inputs and the same `run_started_at` timestamp, the renderer always produces byte-identical output.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Spec YAML  (workloads/{name}/config/*.yaml)         │
│      │                                               │
│      ▼                                               │
│  spec_loader.load_spec(path, spec_type)              │
│      • validates against contracts/v1/*.schema.json  │
│      • returns (spec_dict, spec_hash: SHA-256)       │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  renderer.render(spec, spec_hash, template_id, ...)  │
│      • loads shared/templates/{template_id}.*.j2     │
│      • validates slots via slot_extractor            │
│      • renders with Jinja2 StrictUndefined           │
│      • prepends 5-line deterministic header          │
│      • writes atomically (tempfile + os.replace)     │
│      • sets ADOP_RENDERER_TOKEN during write         │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  drift_validator.verify_artifact(path)               │
│      • re-parses header (spec_hash, template_id)     │
│      • re-renders from current spec                  │
│      • compares SHA-256 of actual vs expected        │
│      • returns DriftReport(ok, expected, actual)     │
└──────────────────────────────────────────────────────┘
```

## Spec Contracts (`contracts/v1/`)

JSON Schema Draft 2020-12 files define the shape of every config:

| Schema | Validates |
|--------|-----------|
| `source_profile.schema.json` | Source connection, schema, compliance |
| `bronze_spec.schema.json` | Bronze ingestion parameters |
| `silver_spec.schema.json` | Silver transform (PK, dedup, quality) |
| `gold_spec.schema.json` | Gold aggregation (measures, grain) |
| `quality_spec.schema.json` | Quality rules + thresholds |
| `dag_spec.schema.json` | Airflow scheduling + tasks |
| `workload_manifest.schema.json` | Top-level hash registry |

Schemas are immutable once published. Breaking changes require `contracts/v2/`.

## Spec Hash

```
spec_hash = sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")))
```

Canonical JSON ensures key ordering doesn't affect the hash. The same YAML loaded in any order produces the same hash.

## Artifact Header

Every generated file starts with a 5-line deterministic header:

```python
# spec_hash: a1b2c3d4e5f6...
# template_id: silver_transform
# template_hash: 7890abcdef...
# schema_version: v1
# rendered_at: 2026-05-21T10:00:00Z
```

SQL files use `--` prefix instead of `#`.

## Templates (`shared/templates/*.j2`)

- Pure Jinja2: only `{{ var }}`, `{% for %}`, `{% if %}`
- `StrictUndefined`: missing slots cause immediate error
- Each template declares required slots in header comments
- Template version changes require a semver bump

## Hook Enforcement

`.claude/hooks/enforce_template_codegen.py` runs as a PreToolUse hook on Write/Edit/MultiEdit:

- If target path matches `workloads/*/(scripts|dags|sql)/**` AND `ADOP_RENDERER_TOKEN` env var is NOT set → **exit 2** (block)
- Otherwise → exit 0 (allow)

The renderer is the only code that sets `ADOP_RENDERER_TOKEN` during its atomic write.

## Drift Detection

**Pre-commit**: `drift-validator` hook re-renders any changed artifact and compares checksums.

**CI**: `python -m shared.codegen.drift_validator workloads/{name}/`

**Orchestrator**: Step 4.5.2 runs drift validation after sub-agent builds.

## Replay Test

`tests/integration/test_determinism_replay.py` proves the core claim:
1. Load frozen fixtures from `tests/fixtures/replay_workload/`
2. Render twice with same `run_started_at`
3. Assert byte-identical output (same hashes)
4. Change one spec byte → hash changes
5. Hand-edit artifact → drift validator catches it

## Key Files

```
shared/codegen/
├── __init__.py
├── exceptions.py          # Typed exceptions
├── spec_loader.py         # Load + validate + hash
├── slot_extractor.py      # Jinja2 AST → required vars
├── renderer.py            # Render + atomic write
└── drift_validator.py     # Re-render + compare

shared/templates/
├── silver_transform.py.j2
├── bronze_ingestion.py.j2
├── gold_aggregate.py.j2
├── quality_check.py.j2
├── airflow_dag.py.j2
├── glue_job_config.yaml.j2
└── iceberg_ddl.sql.j2

contracts/v1/              # JSON Schema contracts (7 files)
.claude/hooks/enforce_template_codegen.py  # PreToolUse enforcement
```
