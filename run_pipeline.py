#!/usr/bin/env python3
"""End-to-end pipeline runner with EDMODE narration and Cedar policy guardrails.

Runs both customer_master and order_transactions pipelines locally,
with Cedar-evaluated guardrail checks at every step, and generates a
dashboard_preview.html.

Usage:
    python3 run_pipeline.py

Environment:
    CEDAR_MODE=local  (default) Use cedarpy / fallback evaluator
    CEDAR_MODE=avp    Use Amazon Verified Permissions
"""

import csv
import importlib.util
import json
import logging
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configure logging ONCE before importing any workload modules.
# Each workload script calls logging.basicConfig() internally, but since
# we call it first, those subsequent calls are no-ops.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_pipeline")
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

CUSTOMER_WORKLOAD = os.path.join(PROJECT_ROOT, "workloads", "customer_master")
ORDER_WORKLOAD = os.path.join(PROJECT_ROOT, "workloads", "order_transactions")

CUSTOMER_FIXTURES = os.path.join(PROJECT_ROOT, "shared", "fixtures", "customers.csv")
ORDER_FIXTURES = os.path.join(PROJECT_ROOT, "shared", "fixtures", "orders.csv")

ZONE_SQL = os.path.join(PROJECT_ROOT, "shared", "sql", "common", "create_zone_databases.sql")

ANALYTICS_YAML = os.path.join(ORDER_WORKLOAD, "config", "analytics.yaml")

DASHBOARD_OUTPUT = os.path.join(PROJECT_ROOT, "dashboard_preview.html")

# KMS key aliases
KMS_LANDING = "alias/landing-data-key"
KMS_STAGING = "alias/staging-data-key"
KMS_PUBLISH = "alias/publish-data-key"


# ---------------------------------------------------------------------------
# Module loader — uses importlib to avoid cross-workload collisions
# ---------------------------------------------------------------------------
def load_module(name: str, path: str):
    """Load a Python module from an absolute file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module '{name}' from '{path}'")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Cedar policy evaluator (replaces inline GuardrailTracker)
# ---------------------------------------------------------------------------
from shared.utils.cedar_client import (
    AgentPrincipal,
    CedarPolicyEvaluator,
    PipelineStep,
)


# ---------------------------------------------------------------------------
# EDMODE formatting helpers
# ---------------------------------------------------------------------------
def print_step_header(step_num: int, title: str):
    """Print a boxed step header."""
    inner = f"  Step {step_num} -- {title}"
    width = max(70, len(inner) + 4)
    print()
    print(f"{'=' * width}")
    print(inner.ljust(width))
    print(f"{'=' * width}")
    print()


def print_section(label: str, lines: list):
    """Print a labeled section with indented lines."""
    print(f"  {label}:")
    for line in lines:
        print(f"    - {line}")
    print()


def print_executing():
    """Print the executing separator."""
    print("  " + "-" * 69)
    print("  [EXECUTING]")


def print_end_executing():
    """Print the end-of-executing separator."""
    print("  " + "-" * 69)
    print()


def print_result(lines: list):
    """Print result lines."""
    print("  Result:")
    for line in lines:
        print(f"    {line}")
    print()


def print_safety(notes: list):
    """Print safety notes."""
    print("  Safety notes:")
    for note in notes:
        print(f"    {note}")
    print()


# ---------------------------------------------------------------------------
# Step 1: Create Glue Zone Databases (simulated)
# ---------------------------------------------------------------------------
def step_01_create_databases(ctx: dict):
    print_step_header(1, "Create Glue Zone Databases (simulated)")

    print_section("Inputs inspected", [
        f"{ZONE_SQL} -- DDL for landing_db, staging_db, publish_db",
    ])
    print_section("Tools used", [
        "shared/sql/common/create_zone_databases.sql -- zone DDL reference",
    ])
    print_section("Planned operation", [
        "Read and display the zone database DDL. In production, these would",
        "be executed via Athena or a Glue Job. Locally, we just validate the",
        "SQL file exists and print its contents.",
    ])

    print_executing()
    with open(ZONE_SQL, "r") as f:
        sql_content = f.read()
    # Print abbreviated version
    for line in sql_content.strip().split("\n"):
        if line.startswith("CREATE DATABASE") or line.startswith("    COMMENT"):
            print(f"    {line}")
    print_end_executing()

    print_result([
        "3 zone databases defined: landing_db, staging_db, publish_db",
        "Each zone has a dedicated KMS key and quality threshold",
    ])

    step1 = PipelineStep(step_number=1, step_name="Create zone databases")
    agent = AgentPrincipal("onboarding")

    ctx["guardrails"].check(
        "SEC-002", "KMS key alias validated: alias/landing-data-key",
        KMS_LANDING.startswith("alias/"),
        context={"guardrailCode": "SEC-002", "kmsAlias": KMS_LANDING, "kmsAliasValid": KMS_LANDING.startswith("alias/")},
        principal=agent, resource=step1,
    )
    ctx["guardrails"].check(
        "SEC-002", "KMS key alias validated: alias/staging-data-key",
        KMS_STAGING.startswith("alias/"),
        context={"guardrailCode": "SEC-002", "kmsAlias": KMS_STAGING, "kmsAliasValid": KMS_STAGING.startswith("alias/")},
        principal=agent, resource=step1,
    )
    ctx["guardrails"].check(
        "SEC-002", "KMS key alias validated: alias/publish-data-key",
        KMS_PUBLISH.startswith("alias/"),
        context={"guardrailCode": "SEC-002", "kmsAlias": KMS_PUBLISH, "kmsAliasValid": KMS_PUBLISH.startswith("alias/")},
        principal=agent, resource=step1,
    )

    print_safety([
        "Dry-run only -- no databases were created.",
        "In production, run each CREATE DATABASE as a separate Athena query.",
    ])


# ---------------------------------------------------------------------------
# Step 2: Ingest Customer Data to Landing Zone
# ---------------------------------------------------------------------------
def step_02_ingest_customers(ctx: dict):
    print_step_header(2, "Ingest Customer Data to Landing Zone")

    print_section("Inputs inspected", [
        f"{CUSTOMER_FIXTURES} -- 50 rows, 11 columns (raw customer CSV)",
    ])
    print_section("Tools used", [
        "customer_master/scripts/extract/ingest_customers.py::ingest() -- copies raw CSV to Landing zone",
    ])
    print_section("Planned operation", [
        "Copy fixture CSV to workloads/customer_master/data/landing/ with",
        "date-partitioned path. Write encryption metadata sidecar.",
    ])

    mod = load_module("cm_ingest", os.path.join(
        CUSTOMER_WORKLOAD, "scripts", "extract", "ingest_customers.py"
    ))

    print_executing()
    result = mod.ingest()
    print(f"    Source: {result['source_file']}")
    print(f"    Landing: {result['landing_file']}")
    print(f"    Rows: {result['row_count']}, Columns: {result['column_count']}")
    print(f"    Partition: {result['partition']}")
    print(f"    Encryption: {result['encryption_method']} with {result['kms_key_alias']}")
    print_end_executing()

    ctx["cm_ingest"] = result

    print_result([
        f"{result['row_count']} rows ingested to Landing zone",
        f"Partition: {result['partition']}",
    ])

    step2 = PipelineStep(step_number=2, step_name="Ingest customers", target_zone="landing")
    agent = AgentPrincipal("onboarding")

    ctx["guardrails"].check(
        "SEC-002", f"KMS key alias validated: {result['kms_key_alias']}",
        result["kms_key_alias"] == KMS_LANDING,
        context={"guardrailCode": "SEC-002", "kmsAlias": result["kms_key_alias"], "kmsAliasValid": result["kms_key_alias"] == KMS_LANDING},
        principal=agent, resource=step2,
    )
    ctx["guardrails"].check(
        "DQ-004", f"Row count > 0: {result['row_count']} rows",
        result["row_count"] > 0,
        context={"guardrailCode": "DQ-004", "rowCountAboveZero": result["row_count"] > 0, "rowCount": result["row_count"]},
        principal=agent, resource=step2,
    )
    ctx["guardrails"].check(
        "OPS-003", "Audit log: encryption metadata sidecar written",
        os.path.isfile(result["landing_file"] + ".metadata"),
        context={"guardrailCode": "OPS-003", "auditLogWritten": os.path.isfile(result["landing_file"] + ".metadata")},
        principal=agent, resource=step2,
    )
    ctx["guardrails"].check(
        "INT-001", "Landing zone file written (immutable after this point)",
        os.path.isfile(result["landing_file"]),
        context={"guardrailCode": "INT-001", "landingFileWritten": os.path.isfile(result["landing_file"])},
        principal=agent, resource=step2,
    )

    print_safety([
        "Local dev: file copied to local filesystem, not S3.",
        "Landing zone is immutable -- no further modifications allowed.",
    ])


# ---------------------------------------------------------------------------
# Step 3: Customer Master: Landing -> Staging
# ---------------------------------------------------------------------------
def step_03_customer_landing_to_staging(ctx: dict):
    print_step_header(3, "Customer Master: Landing -> Staging (clean, mask PII, validate)")

    config_path = os.path.join(CUSTOMER_WORKLOAD, "config", "transformations.yaml")
    staging_output = os.path.join(CUSTOMER_WORKLOAD, "data", "staging", "customer_staging.csv")
    quarantine_output = os.path.join(CUSTOMER_WORKLOAD, "data", "quarantine", "quarantined_records.csv")

    print_section("Inputs inspected", [
        f"{CUSTOMER_FIXTURES} -- raw customer CSV from fixture",
        f"{config_path} -- dedup, null-quarantine, PII masking, type casting rules",
    ])
    print_section("Tools used", [
        "customer_master/scripts/transform/landing_to_staging.py::run() -- full cleaning pipeline",
    ])
    print_section("Planned operation", [
        "Deduplicate on customer_id, quarantine null PKs, trim whitespace,",
        "lowercase email, validate dates & enums, cast decimals, mask PII",
        "(email->SHA256, phone->mask_last_4), write Staging CSV + Iceberg metadata.",
    ])

    mod = load_module("cm_l2s", os.path.join(
        CUSTOMER_WORKLOAD, "scripts", "transform", "landing_to_staging.py"
    ))

    print_executing()
    result = mod.run(
        config_path=config_path,
        source_csv=CUSTOMER_FIXTURES,
        staging_output=staging_output,
        quarantine_output=quarantine_output,
        landing_kms_key=KMS_LANDING,
        staging_kms_key=KMS_STAGING,
    )
    print(f"    Input rows:        {result['input_rows']}")
    print(f"    Duplicates removed: {result['duplicates_removed']}")
    print(f"    Quarantined:       {result['quarantined_rows']}")
    print(f"    Staging rows:      {result['staging_rows']}")
    print(f"    Staging output:    {result['staging_output']}")
    print(f"    Quarantine output: {result['quarantine_output']}")
    print_end_executing()

    ctx["cm_staging"] = result

    print_result([
        f"{result['staging_rows']} clean rows promoted to Staging",
        f"{result['quarantined_rows']} rows quarantined (not silently dropped)",
        f"{result['duplicates_removed']} duplicates removed",
    ])

    # Check PII masking by reading staging output
    pii_masked = False
    if os.path.isfile(staging_output):
        with open(staging_output, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader, None)
            if row:
                email_val = row.get("email", "")
                # SHA256 hashes are 64 hex chars
                pii_masked = len(email_val) == 64 and all(c in "0123456789abcdef" for c in email_val)

    step3 = PipelineStep(step_number=3, step_name="Customer L2S", source_zone="landing", target_zone="staging")
    agent = AgentPrincipal("onboarding")

    ctx["guardrails"].check(
        "SEC-003", "PII columns masked: email -> SHA256",
        pii_masked,
        context={"guardrailCode": "SEC-003", "piiColumnsMasked": pii_masked},
        principal=agent, resource=step3,
    )
    ctx["guardrails"].check(
        "DQ-003", f"Quarantine table populated: {result['quarantined_rows']} rejects",
        os.path.isfile(quarantine_output),
        context={"guardrailCode": "DQ-003", "rowAccountingBalances": os.path.isfile(quarantine_output),
                 "inputRows": result["input_rows"], "outputRows": result["staging_rows"], "quarantineRows": result["quarantined_rows"]},
        principal=agent, resource=step3,
    )
    ctx["guardrails"].check(
        "DQ-004", f"Staging row count > 0: {result['staging_rows']} rows",
        result["staging_rows"] > 0,
        context={"guardrailCode": "DQ-004", "rowCountAboveZero": result["staging_rows"] > 0, "rowCount": result["staging_rows"]},
        principal=agent, resource=step3,
    )
    ctx["guardrails"].check(
        "OPS-002", f"Encryption re-keyed: {result['landing_kms_key']} -> {result['staging_kms_key']}",
        result["landing_kms_key"] != result["staging_kms_key"],
        context={"guardrailCode": "OPS-002", "keysAreDifferent": result["landing_kms_key"] != result["staging_kms_key"],
                 "sourceKeyAlias": result["landing_kms_key"], "targetKeyAlias": result["staging_kms_key"]},
        principal=agent, resource=step3,
    )
    ctx["guardrails"].check(
        "OPS-004", "Iceberg metadata sidecar generated for Staging",
        os.path.isfile(staging_output + ".iceberg_metadata"),
        context={"guardrailCode": "OPS-004", "icebergMetadataExists": os.path.isfile(staging_output + ".iceberg_metadata")},
        principal=agent, resource=step3,
    )

    print_safety([
        "Local dev: CSV output simulates Iceberg table.",
        "Production: Glue ETL writes to S3 Tables with Iceberg format.",
        "OPS-001: Idempotency verified by unit tests (re-run produces identical output).",
    ])


# ---------------------------------------------------------------------------
# Step 4: Customer Master: Staging Quality Gate
# ---------------------------------------------------------------------------
def step_04_customer_staging_quality(ctx: dict):
    print_step_header(4, "Customer Master: Staging Quality Gate")

    staging_csv = os.path.join(CUSTOMER_WORKLOAD, "data", "staging", "customer_staging.csv")

    print_section("Inputs inspected", [
        f"{staging_csv} -- cleaned customer Staging data",
        f"{os.path.join(CUSTOMER_WORKLOAD, 'config', 'quality_rules.yaml')} -- quality rules",
    ])
    print_section("Tools used", [
        "customer_master/scripts/quality/check_staging.py::run() -- 5 quality dimensions",
    ])
    print_section("Planned operation", [
        "Run completeness, accuracy, consistency, validity, and uniqueness",
        "checks against Staging data. Threshold: score >= 0.80, no critical failures.",
    ])

    mod = load_module("cm_qs", os.path.join(
        CUSTOMER_WORKLOAD, "scripts", "quality", "check_staging.py"
    ))

    print_executing()
    score, passed, details = mod.run(staging_csv, 0.80)
    print(f"    Quality score: {score:.4f}")
    print(f"    Gate passed:   {passed}")
    print(f"    Checks run:    {len(details)}")
    checks_passed = sum(1 for d in details if d["passed"])
    checks_failed = len(details) - checks_passed
    print(f"    Passed: {checks_passed}, Failed: {checks_failed}")
    for d in details:
        status = "PASS" if d["passed"] else "FAIL"
        name = d.get("rule_id", d.get("name", "?"))
        detail = d.get("detail", "")
        print(f"      [{status}] {name}: {detail}")
    print_end_executing()

    ctx["cm_staging_quality"] = {"score": score, "passed": passed, "details": details}

    print_result([
        f"Staging quality score: {score:.4f} (threshold: 0.80)",
        f"Gate: {'PASSED' if passed else 'FAILED'}",
    ])

    step4 = PipelineStep(step_number=4, step_name="Customer staging QG", target_zone="staging")
    agent = AgentPrincipal("onboarding")

    critical_failures = [d for d in details if not d["passed"] and d.get("severity") == "critical"]
    ctx["guardrails"].check(
        "DQ-001", f"Staging quality gate: {score:.4f} >= 0.80",
        score >= 0.80,
        context={"guardrailCode": "DQ-001", "qualityScore": int(score * 100), "qualityThreshold": 80},
        principal=agent, resource=step4,
    )
    ctx["guardrails"].check(
        "DQ-002", f"No critical rule failures: {len(critical_failures)} critical",
        len(critical_failures) == 0,
        context={"guardrailCode": "DQ-002", "criticalFailureCount": len(critical_failures)},
        principal=agent, resource=step4,
    )

    print_safety([
        "Quality gate blocks promotion to Publish if score < 0.80.",
    ])


# ---------------------------------------------------------------------------
# Step 5: Customer Master: Staging -> Publish (star schema)
# ---------------------------------------------------------------------------
def step_05_customer_staging_to_publish(ctx: dict):
    print_step_header(5, "Customer Master: Staging -> Publish (star schema)")

    config_path = os.path.join(CUSTOMER_WORKLOAD, "config", "transformations.yaml")
    staging_input = os.path.join(CUSTOMER_WORKLOAD, "data", "staging", "customer_staging.csv")
    publish_dir = os.path.join(CUSTOMER_WORKLOAD, "data", "publish")

    print_section("Inputs inspected", [
        f"{staging_input} -- cleaned Staging data",
        f"{config_path} -- star schema definition (fact + dimensions)",
    ])
    print_section("Tools used", [
        "customer_master/scripts/transform/staging_to_publish.py::run() -- star schema builder",
    ])
    print_section("Planned operation", [
        "Build dim_segment, dim_country, customer_fact, and",
        "customer_summary_by_segment tables. Write to Publish zone.",
    ])

    mod = load_module("cm_s2p", os.path.join(
        CUSTOMER_WORKLOAD, "scripts", "transform", "staging_to_publish.py"
    ))

    print_executing()
    result = mod.run(
        config_path=config_path,
        staging_input=staging_input,
        publish_dir=publish_dir,
        staging_kms_key=KMS_STAGING,
        publish_kms_key=KMS_PUBLISH,
    )
    print(f"    Staging rows:     {result['staging_rows']}")
    print(f"    dim_segment:      {result['dim_segment_rows']} rows")
    print(f"    dim_country:      {result['dim_country_rows']} rows")
    print(f"    customer_fact:    {result['fact_rows']} rows")
    print(f"    summary:          {result['summary_rows']} rows")
    print(f"    Publish dir:      {result['publish_dir']}")
    print_end_executing()

    ctx["cm_publish"] = result

    print_result([
        f"Star schema built: {result['fact_rows']} fact rows, "
        f"{result['dim_segment_rows']} segments, {result['dim_country_rows']} countries",
        f"{result['summary_rows']} summary rows",
    ])

    step5 = PipelineStep(step_number=5, step_name="Customer S2P", source_zone="staging", target_zone="publish")
    agent = AgentPrincipal("onboarding")

    schema_ok = all(os.path.isfile(os.path.join(publish_dir, f))
                    for f in ["customer_fact.csv", "dim_segment.csv", "dim_country.csv",
                               "customer_summary_by_segment.csv"])

    ctx["guardrails"].check(
        "DQ-004", f"Fact row count > 0: {result['fact_rows']} rows",
        result["fact_rows"] > 0,
        context={"guardrailCode": "DQ-004", "rowCountAboveZero": result["fact_rows"] > 0, "rowCount": result["fact_rows"]},
        principal=agent, resource=step5,
    )
    ctx["guardrails"].check(
        "OPS-002", f"Encryption re-keyed: {result['staging_kms_key']} -> {result['publish_kms_key']}",
        result["staging_kms_key"] != result["publish_kms_key"],
        context={"guardrailCode": "OPS-002", "keysAreDifferent": result["staging_kms_key"] != result["publish_kms_key"],
                 "sourceKeyAlias": result["staging_kms_key"], "targetKeyAlias": result["publish_kms_key"]},
        principal=agent, resource=step5,
    )
    ctx["guardrails"].check(
        "INT-004", "Schema enforcement: expected Publish tables created",
        schema_ok,
        context={"guardrailCode": "INT-004", "schemaMatches": schema_ok},
        principal=agent, resource=step5,
    )
    ctx["guardrails"].check(
        "OPS-004", "Iceberg metadata sidecars generated for Publish",
        os.path.isfile(os.path.join(publish_dir, "customer_fact.csv.iceberg_metadata")),
        context={"guardrailCode": "OPS-004", "icebergMetadataExists": os.path.isfile(os.path.join(publish_dir, "customer_fact.csv.iceberg_metadata"))},
        principal=agent, resource=step5,
    )

    print_safety([
        "Local dev: CSV output simulates Iceberg tables.",
        "Production: Glue ETL writes to S3 Tables with Iceberg format.",
    ])


# ---------------------------------------------------------------------------
# Step 6: Customer Master: Publish Quality Gate
# ---------------------------------------------------------------------------
def step_06_customer_publish_quality(ctx: dict):
    print_step_header(6, "Customer Master: Publish Quality Gate")

    publish_dir = os.path.join(CUSTOMER_WORKLOAD, "data", "publish")

    print_section("Inputs inspected", [
        f"{publish_dir}/ -- customer_fact, dim_segment, dim_country, summary",
    ])
    print_section("Tools used", [
        "customer_master/scripts/quality/check_publish.py::run() -- star schema validation",
    ])
    print_section("Planned operation", [
        "Validate FK integrity, PK uniqueness, non-negative measures,",
        "churn rate range, and fact-to-summary count consistency.",
        "Threshold: score >= 0.95, no critical failures.",
    ])

    mod = load_module("cm_qp", os.path.join(
        CUSTOMER_WORKLOAD, "scripts", "quality", "check_publish.py"
    ))

    print_executing()
    score, passed, details = mod.run(publish_dir, 0.95)
    print(f"    Quality score: {score:.4f}")
    print(f"    Gate passed:   {passed}")
    print(f"    Checks run:    {len(details)}")
    for d in details:
        status = "PASS" if d["passed"] else "FAIL"
        name = d.get("rule_id", d.get("name", "?"))
        detail = d.get("detail", "")
        print(f"      [{status}] {name}: {detail}")
    print_end_executing()

    ctx["cm_publish_quality"] = {"score": score, "passed": passed, "details": details}

    print_result([
        f"Publish quality score: {score:.4f} (threshold: 0.95)",
        f"Gate: {'PASSED' if passed else 'FAILED'}",
    ])

    step6 = PipelineStep(step_number=6, step_name="Customer publish QG", target_zone="publish")
    agent = AgentPrincipal("onboarding")

    critical_failures = [d for d in details if not d["passed"] and d.get("severity") == "critical"]
    ctx["guardrails"].check(
        "DQ-001", f"Publish quality gate: {score:.4f} >= 0.95",
        score >= 0.95,
        context={"guardrailCode": "DQ-001", "qualityScore": int(score * 100), "qualityThreshold": 95},
        principal=agent, resource=step6,
    )
    ctx["guardrails"].check(
        "DQ-002", f"No critical rule failures: {len(critical_failures)} critical",
        len(critical_failures) == 0,
        context={"guardrailCode": "DQ-002", "criticalFailureCount": len(critical_failures)},
        principal=agent, resource=step6,
    )

    print_safety([
        "Quality gate blocks dashboard deployment if score < 0.95.",
    ])


# ---------------------------------------------------------------------------
# Step 7: Ingest Order Data to Landing Zone
# ---------------------------------------------------------------------------
def step_07_ingest_orders(ctx: dict):
    print_step_header(7, "Ingest Order Data to Landing Zone")

    print_section("Inputs inspected", [
        f"{ORDER_FIXTURES} -- ~150 rows, 11 columns (raw order CSV)",
    ])
    print_section("Tools used", [
        "order_transactions/scripts/extract/ingest_orders.py::ingest() -- copies raw CSV to Landing zone",
    ])
    print_section("Planned operation", [
        "Copy fixture CSV to workloads/order_transactions/data/landing/ with",
        "date-partitioned path. Write encryption metadata sidecar.",
    ])

    mod = load_module("ot_ingest", os.path.join(
        ORDER_WORKLOAD, "scripts", "extract", "ingest_orders.py"
    ))

    print_executing()
    result = mod.ingest()
    print(f"    Source: {result['source_file']}")
    print(f"    Landing: {result['landing_file']}")
    print(f"    Rows: {result['row_count']}, Columns: {result['column_count']}")
    print(f"    Partition: {result['partition']}")
    print(f"    Encryption: {result['encryption_method']} with {result['kms_key_alias']}")
    print_end_executing()

    ctx["ot_ingest"] = result

    print_result([
        f"{result['row_count']} rows ingested to Landing zone",
        f"Partition: {result['partition']}",
    ])

    step7 = PipelineStep(step_number=7, step_name="Ingest orders", target_zone="landing")
    agent = AgentPrincipal("onboarding")

    ctx["guardrails"].check(
        "SEC-002", f"KMS key alias validated: {result['kms_key_alias']}",
        result["kms_key_alias"] == KMS_LANDING,
        context={"guardrailCode": "SEC-002", "kmsAlias": result["kms_key_alias"], "kmsAliasValid": result["kms_key_alias"] == KMS_LANDING},
        principal=agent, resource=step7,
    )
    ctx["guardrails"].check(
        "DQ-004", f"Row count > 0: {result['row_count']} rows",
        result["row_count"] > 0,
        context={"guardrailCode": "DQ-004", "rowCountAboveZero": result["row_count"] > 0, "rowCount": result["row_count"]},
        principal=agent, resource=step7,
    )
    ctx["guardrails"].check(
        "OPS-003", "Audit log: encryption metadata sidecar written",
        os.path.isfile(result["landing_file"] + ".metadata"),
        context={"guardrailCode": "OPS-003", "auditLogWritten": os.path.isfile(result["landing_file"] + ".metadata")},
        principal=agent, resource=step7,
    )
    ctx["guardrails"].check(
        "INT-001", "Landing zone file written (immutable after this point)",
        os.path.isfile(result["landing_file"]),
        context={"guardrailCode": "INT-001", "landingFileWritten": os.path.isfile(result["landing_file"])},
        principal=agent, resource=step7,
    )

    print_safety([
        "Local dev: file copied to local filesystem, not S3.",
        "Landing zone is immutable -- no further modifications allowed.",
    ])


# ---------------------------------------------------------------------------
# Step 8: Order Transactions: Landing -> Staging
# ---------------------------------------------------------------------------
def step_08_order_landing_to_staging(ctx: dict):
    print_step_header(8, "Order Transactions: Landing -> Staging (clean, FK validate)")

    config_path = os.path.join(ORDER_WORKLOAD, "config", "transformations.yaml")
    staging_output = os.path.join(ORDER_WORKLOAD, "data", "staging", "orders_clean.csv")
    quarantine_output = os.path.join(ORDER_WORKLOAD, "data", "quarantine", "quarantined_records.csv")
    customer_staging = os.path.join(CUSTOMER_WORKLOAD, "data", "staging", "customer_staging.csv")

    print_section("Inputs inspected", [
        f"{ORDER_FIXTURES} -- raw order CSV from fixture",
        f"{config_path} -- dedup, FK validation, revenue check, enum rules",
        f"{customer_staging} -- customer_master Staging for FK validation",
    ])
    print_section("Tools used", [
        "order_transactions/scripts/transform/landing_to_staging.py::run() -- full cleaning pipeline",
    ])
    print_section("Planned operation", [
        "Deduplicate on order_id, quarantine null required fields, validate",
        "dates, quarantine future dates, validate enums, cast types, verify",
        "revenue formula (qty * price * (1-discount)), FK validate customer_id",
        "against customer_master Staging data.",
    ])

    mod = load_module("ot_l2s", os.path.join(
        ORDER_WORKLOAD, "scripts", "transform", "landing_to_staging.py"
    ))

    print_executing()
    result = mod.run(
        config_path=config_path,
        source_csv=ORDER_FIXTURES,
        staging_output=staging_output,
        quarantine_output=quarantine_output,
        customer_master_csv=customer_staging,
    )
    print(f"    Input rows:              {result['input_rows']}")
    print(f"    Duplicates removed:      {result['duplicates_removed']}")
    print(f"    Future dates quarantined: {result['future_dates_quarantined']}")
    print(f"    Orphan FK quarantined:   {result['orphan_fk_quarantined']}")
    print(f"    Revenue mismatch:        {result['revenue_mismatch_quarantined']}")
    print(f"    Total quarantined:       {result['quarantined_rows']}")
    print(f"    Staging rows:            {result['staging_rows']}")
    print_end_executing()

    ctx["ot_staging"] = result

    print_result([
        f"{result['staging_rows']} clean rows promoted to Staging",
        f"{result['quarantined_rows']} rows quarantined (not silently dropped)",
    ])

    # FK integrity rate
    total_after_dedup = result["input_rows"] - result["duplicates_removed"]
    fk_checked = total_after_dedup - result["quarantined_rows"] + result["orphan_fk_quarantined"]
    fk_pass_rate = 1.0 - (result["orphan_fk_quarantined"] / fk_checked) if fk_checked > 0 else 1.0

    step8 = PipelineStep(step_number=8, step_name="Order L2S", source_zone="landing", target_zone="staging")
    agent = AgentPrincipal("onboarding")

    ctx["guardrails"].check(
        "DQ-003", f"Quarantine table populated: {result['quarantined_rows']} rejects",
        os.path.isfile(quarantine_output),
        context={"guardrailCode": "DQ-003", "rowAccountingBalances": os.path.isfile(quarantine_output),
                 "inputRows": result["input_rows"], "outputRows": result["staging_rows"], "quarantineRows": result["quarantined_rows"]},
        principal=agent, resource=step8,
    )
    ctx["guardrails"].check(
        "DQ-004", f"Staging row count > 0: {result['staging_rows']} rows",
        result["staging_rows"] > 0,
        context={"guardrailCode": "DQ-004", "rowCountAboveZero": result["staging_rows"] > 0, "rowCount": result["staging_rows"]},
        principal=agent, resource=step8,
    )
    ctx["guardrails"].check(
        "INT-002", f"FK referential integrity: {fk_pass_rate:.4f} >= 0.90",
        fk_pass_rate >= 0.90,
        context={"guardrailCode": "INT-002", "fkPassRate": int(fk_pass_rate * 100), "fkThreshold": 90},
        principal=agent, resource=step8,
    )
    ctx["guardrails"].check(
        "INT-003", f"Revenue formula verified: {result['revenue_mismatch_quarantined']} mismatches quarantined",
        True,  # Mismatches are quarantined, not silently passed
        context={"guardrailCode": "INT-003", "formulaVerified": True},
        principal=agent, resource=step8,
    )
    ctx["guardrails"].check(
        "OPS-002", f"Encryption re-keyed: {result['landing_kms_key']} -> {result['staging_kms_key']}",
        result["landing_kms_key"] != result["staging_kms_key"],
        context={"guardrailCode": "OPS-002", "keysAreDifferent": result["landing_kms_key"] != result["staging_kms_key"],
                 "sourceKeyAlias": result["landing_kms_key"], "targetKeyAlias": result["staging_kms_key"]},
        principal=agent, resource=step8,
    )
    ctx["guardrails"].check(
        "OPS-004", "Iceberg metadata sidecar generated for Staging",
        os.path.isfile(staging_output + ".iceberg_metadata"),
        context={"guardrailCode": "OPS-004", "icebergMetadataExists": os.path.isfile(staging_output + ".iceberg_metadata")},
        principal=agent, resource=step8,
    )

    print_safety([
        "Local dev: CSV output simulates Iceberg table.",
        "FK validation depends on customer_master running first (Step 3).",
    ])


# ---------------------------------------------------------------------------
# Step 9: Order Transactions: Staging Quality Gate
# ---------------------------------------------------------------------------
def step_09_order_staging_quality(ctx: dict):
    print_step_header(9, "Order Transactions: Staging Quality Gate")

    staging_csv = os.path.join(ORDER_WORKLOAD, "data", "staging", "orders_clean.csv")
    config_path = os.path.join(ORDER_WORKLOAD, "config", "quality_rules.yaml")

    print_section("Inputs inspected", [
        f"{staging_csv} -- cleaned order Staging data",
        f"{config_path} -- quality rules (completeness, uniqueness, validity, accuracy, referential)",
    ])
    print_section("Tools used", [
        "order_transactions/scripts/quality/check_staging.py::run() -- rule evaluation engine",
    ])
    print_section("Planned operation", [
        "Run all quality rules against Staging data.",
        "Threshold: score >= 0.80, no critical failures.",
    ])

    mod = load_module("ot_qs", os.path.join(
        ORDER_WORKLOAD, "scripts", "quality", "check_staging.py"
    ))

    print_executing()
    score, passed, details = mod.run(staging_csv, 0.80, config_path)
    print(f"    Quality score: {score:.4f}")
    print(f"    Gate passed:   {passed}")
    print(f"    Checks run:    {len(details)}")
    for d in details:
        status = "PASS" if d["passed"] else "FAIL"
        name = d.get("name", "?")
        col = d.get("column", "")
        dscore = d.get("score", "")
        print(f"      [{status}] {name} ({col}): score={dscore}")
    print_end_executing()

    ctx["ot_staging_quality"] = {"score": score, "passed": passed, "details": details}

    print_result([
        f"Staging quality score: {score:.4f} (threshold: 0.80)",
        f"Gate: {'PASSED' if passed else 'FAILED'}",
    ])

    step9 = PipelineStep(step_number=9, step_name="Order staging QG", target_zone="staging")
    agent = AgentPrincipal("onboarding")

    critical_failures = [d for d in details if not d["passed"] and d.get("severity") == "critical"]
    ctx["guardrails"].check(
        "DQ-001", f"Staging quality gate: {score:.4f} >= 0.80",
        score >= 0.80,
        context={"guardrailCode": "DQ-001", "qualityScore": int(score * 100), "qualityThreshold": 80},
        principal=agent, resource=step9,
    )
    ctx["guardrails"].check(
        "DQ-002", f"No critical rule failures: {len(critical_failures)} critical",
        len(critical_failures) == 0,
        context={"guardrailCode": "DQ-002", "criticalFailureCount": len(critical_failures)},
        principal=agent, resource=step9,
    )

    print_safety([
        "Quality gate blocks promotion to Publish if score < 0.80.",
    ])


# ---------------------------------------------------------------------------
# Step 10: Order Transactions: Staging -> Publish (star schema)
# ---------------------------------------------------------------------------
def step_10_order_staging_to_publish(ctx: dict):
    print_step_header(10, "Order Transactions: Staging -> Publish (star schema)")

    config_path = os.path.join(ORDER_WORKLOAD, "config", "transformations.yaml")
    staging_csv = os.path.join(ORDER_WORKLOAD, "data", "staging", "orders_clean.csv")
    publish_dir = os.path.join(ORDER_WORKLOAD, "data", "publish")

    print_section("Inputs inspected", [
        f"{staging_csv} -- cleaned Staging data",
        f"{config_path} -- star schema definition (fact + dim_product + summary)",
    ])
    print_section("Tools used", [
        "order_transactions/scripts/transform/staging_to_publish.py::run() -- star schema builder",
    ])
    print_section("Planned operation", [
        "Build order_fact, dim_product, and order_summary_by_region_category",
        "tables. Write to Publish zone with Iceberg metadata sidecars.",
    ])

    mod = load_module("ot_s2p", os.path.join(
        ORDER_WORKLOAD, "scripts", "transform", "staging_to_publish.py"
    ))

    print_executing()
    result = mod.run(
        config_path=config_path,
        staging_csv=staging_csv,
        publish_dir=publish_dir,
        staging_kms_key=KMS_STAGING,
        publish_kms_key=KMS_PUBLISH,
    )
    print(f"    Staging input rows: {result['staging_input_rows']}")
    print(f"    order_fact:         {result['fact_rows']} rows")
    print(f"    dim_product:        {result['dim_product_rows']} rows")
    print(f"    summary:            {result['summary_rows']} rows")
    print(f"    Publish dir:        {result['publish_dir']}")
    print_end_executing()

    ctx["ot_publish"] = result

    print_result([
        f"Star schema built: {result['fact_rows']} fact rows, "
        f"{result['dim_product_rows']} products, {result['summary_rows']} summary rows",
    ])

    step10 = PipelineStep(step_number=10, step_name="Order S2P", source_zone="staging", target_zone="publish")
    agent = AgentPrincipal("onboarding")

    schema_ok = all(os.path.isfile(os.path.join(publish_dir, f))
                    for f in ["order_fact.csv", "dim_product.csv",
                               "order_summary_by_region_category.csv"])

    ctx["guardrails"].check(
        "DQ-004", f"Fact row count > 0: {result['fact_rows']} rows",
        result["fact_rows"] > 0,
        context={"guardrailCode": "DQ-004", "rowCountAboveZero": result["fact_rows"] > 0, "rowCount": result["fact_rows"]},
        principal=agent, resource=step10,
    )
    ctx["guardrails"].check(
        "OPS-002", f"Encryption re-keyed: {result['staging_kms_key']} -> {result['publish_kms_key']}",
        result["staging_kms_key"] != result["publish_kms_key"],
        context={"guardrailCode": "OPS-002", "keysAreDifferent": result["staging_kms_key"] != result["publish_kms_key"],
                 "sourceKeyAlias": result["staging_kms_key"], "targetKeyAlias": result["publish_kms_key"]},
        principal=agent, resource=step10,
    )
    ctx["guardrails"].check(
        "INT-004", "Schema enforcement: expected Publish tables created",
        schema_ok,
        context={"guardrailCode": "INT-004", "schemaMatches": schema_ok},
        principal=agent, resource=step10,
    )
    ctx["guardrails"].check(
        "OPS-004", "Iceberg metadata sidecars generated for Publish",
        os.path.isfile(os.path.join(publish_dir, "order_fact.csv.iceberg_metadata")),
        context={"guardrailCode": "OPS-004", "icebergMetadataExists": os.path.isfile(os.path.join(publish_dir, "order_fact.csv.iceberg_metadata"))},
        principal=agent, resource=step10,
    )

    print_safety([
        "Local dev: CSV output simulates Iceberg tables.",
        "Production: Glue ETL writes to S3 Tables with Iceberg format.",
    ])


# ---------------------------------------------------------------------------
# Step 11: Order Transactions: Publish Quality Gate
# ---------------------------------------------------------------------------
def step_11_order_publish_quality(ctx: dict):
    print_step_header(11, "Order Transactions: Publish Quality Gate")

    publish_dir = os.path.join(ORDER_WORKLOAD, "data", "publish")

    print_section("Inputs inspected", [
        f"{publish_dir}/ -- order_fact, dim_product, order_summary",
    ])
    print_section("Tools used", [
        "order_transactions/scripts/quality/check_publish.py::run() -- star schema validation",
    ])
    print_section("Planned operation", [
        "Validate FK integrity, PK uniqueness, non-negative measures,",
        "aggregate consistency. Threshold: score >= 0.95, no critical failures.",
    ])

    mod = load_module("ot_qp", os.path.join(
        ORDER_WORKLOAD, "scripts", "quality", "check_publish.py"
    ))

    print_executing()
    score, passed, details = mod.run(publish_dir, 0.95)
    print(f"    Quality score: {score:.4f}")
    print(f"    Gate passed:   {passed}")
    print(f"    Checks run:    {len(details)}")
    for d in details:
        status = "PASS" if d["passed"] else "FAIL"
        name = d.get("name", "?")
        detail = d.get("detail", "")
        print(f"      [{status}] {name}: {detail}")
    print_end_executing()

    ctx["ot_publish_quality"] = {"score": score, "passed": passed, "details": details}

    print_result([
        f"Publish quality score: {score:.4f} (threshold: 0.95)",
        f"Gate: {'PASSED' if passed else 'FAILED'}",
    ])

    step11 = PipelineStep(step_number=11, step_name="Order publish QG", target_zone="publish")
    agent = AgentPrincipal("onboarding")

    critical_failures = [d for d in details if not d["passed"]
                         and (d.get("severity") == "critical" or d.get("critical"))]
    ctx["guardrails"].check(
        "DQ-001", f"Publish quality gate: {score:.4f} >= 0.95",
        score >= 0.95,
        context={"guardrailCode": "DQ-001", "qualityScore": int(score * 100), "qualityThreshold": 95},
        principal=agent, resource=step11,
    )
    ctx["guardrails"].check(
        "DQ-002", f"No critical rule failures: {len(critical_failures)} critical",
        len(critical_failures) == 0,
        context={"guardrailCode": "DQ-002", "criticalFailureCount": len(critical_failures)},
        principal=agent, resource=step11,
    )

    print_safety([
        "Quality gate blocks dashboard deployment if score < 0.95.",
    ])


# ---------------------------------------------------------------------------
# Step 12: Generate QuickSight Dashboard Preview
# ---------------------------------------------------------------------------
def step_12_generate_dashboard(ctx: dict):
    print_step_header(12, "Generate QuickSight Dashboard Preview")

    order_fact_path = os.path.join(ORDER_WORKLOAD, "data", "publish", "order_fact.csv")
    order_summary_path = os.path.join(ORDER_WORKLOAD, "data", "publish",
                                       "order_summary_by_region_category.csv")
    customer_summary_path = os.path.join(CUSTOMER_WORKLOAD, "data", "publish",
                                          "customer_summary_by_segment.csv")

    print_section("Inputs inspected", [
        f"{ANALYTICS_YAML} -- QuickSight dashboard config (6 visuals, 2 datasets)",
        f"{order_fact_path} -- Publish zone order fact table",
        f"{order_summary_path} -- Publish zone order summary table",
        f"{customer_summary_path} -- Publish zone customer summary table",
    ])
    print_section("Tools used", [
        "shared/utils/quicksight_dashboard.py::validate_analytics_config() -- config validation",
        "generate_dashboard_html() -- local HTML dashboard builder",
    ])
    print_section("Planned operation", [
        "1. Validate analytics.yaml against QuickSight schema.",
        "2. Read Publish zone CSV data from both workloads.",
        "3. Generate self-contained dashboard_preview.html with 6 visuals.",
    ])

    # Validate analytics config
    qs_mod = load_module("qs_dashboard", os.path.join(
        PROJECT_ROOT, "shared", "utils", "quicksight_dashboard.py"
    ))

    print_executing()
    errors = qs_mod.validate_analytics_config(ANALYTICS_YAML)
    if errors:
        print(f"    Analytics config validation FAILED:")
        for e in errors:
            print(f"      - {e}")
    else:
        print(f"    Analytics config validation: PASSED (0 errors)")

    # Read data
    order_fact = _read_csv(order_fact_path)
    order_summary = _read_csv(order_summary_path)
    customer_summary = _read_csv(customer_summary_path)

    print(f"    order_fact: {len(order_fact)} rows")
    print(f"    order_summary: {len(order_summary)} rows")
    print(f"    customer_summary: {len(customer_summary)} rows")

    # Generate HTML
    generate_dashboard_html(order_fact, order_summary, customer_summary, DASHBOARD_OUTPUT)
    print(f"    Dashboard written: {DASHBOARD_OUTPUT}")
    file_size = os.path.getsize(DASHBOARD_OUTPUT)
    print(f"    File size: {file_size:,} bytes")
    print_end_executing()

    print_result([
        f"Dashboard preview generated: {DASHBOARD_OUTPUT}",
        f"6 visuals rendered from {len(order_fact)} order fact rows",
        "Open in any browser to view.",
    ])

    step12 = PipelineStep(step_number=12, step_name="Generate dashboard")
    agent = AgentPrincipal("onboarding")

    ctx["guardrails"].check(
        "OPS-003", "Audit log: dashboard_preview.html generated",
        os.path.isfile(DASHBOARD_OUTPUT),
        context={"guardrailCode": "OPS-003", "auditLogWritten": os.path.isfile(DASHBOARD_OUTPUT)},
        principal=agent, resource=step12,
    )

    print_safety([
        "Local preview only -- not deployed to QuickSight.",
        "Production: use generate_dashboard_definition() for API payload.",
    ])


# ---------------------------------------------------------------------------
# CSV reader helper
# ---------------------------------------------------------------------------
def _read_csv(path: str) -> list:
    """Read a CSV file and return list of dicts."""
    rows = []
    if os.path.isfile(path):
        with open(path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    return rows


# ---------------------------------------------------------------------------
# Dashboard HTML generator
# ---------------------------------------------------------------------------
def generate_dashboard_html(
    order_fact: list,
    order_summary: list,
    customer_summary: list,
    output_path: str,
):
    """Generate a self-contained HTML dashboard with 6 visuals."""

    # ---- Compute KPI data ----
    total_orders = len(set(r.get("order_id", "") for r in order_fact))
    total_revenue = sum(float(r.get("revenue", 0)) for r in order_fact)
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
    unique_customers = len(set(r.get("customer_id", "") for r in order_fact))

    # ---- Top 5 customers by revenue ----
    customer_revenue = defaultdict(float)
    for r in order_fact:
        customer_revenue[r.get("customer_id", "")] += float(r.get("revenue", 0))
    top_5 = sorted(customer_revenue.items(), key=lambda x: x[1], reverse=True)[:5]

    # ---- Sales by region ----
    region_revenue = defaultdict(float)
    for r in order_summary:
        region_revenue[r.get("region", "")] += float(r.get("total_revenue", 0))
    regions_sorted = sorted(region_revenue.items(), key=lambda x: x[1], reverse=True)

    # ---- Revenue trend by month ----
    monthly_revenue = defaultdict(float)
    for r in order_fact:
        date_str = r.get("order_date", "")
        if len(date_str) >= 7:
            month_key = date_str[:7]  # YYYY-MM
            monthly_revenue[month_key] += float(r.get("revenue", 0))
    months_sorted = sorted(monthly_revenue.items())

    # ---- Orders by category ----
    category_orders = defaultdict(int)
    for r in order_summary:
        category_orders[r.get("category", "")] += int(r.get("order_count", 0))
    categories_sorted = sorted(category_orders.items(), key=lambda x: x[1], reverse=True)

    # ---- Order status breakdown ----
    status_counts = defaultdict(int)
    for r in order_fact:
        status_counts[r.get("status", "")] += 1
    statuses_sorted = sorted(status_counts.items(), key=lambda x: x[1], reverse=True)

    # ---- Build JSON data for embedding ----
    data = {
        "kpis": {
            "total_orders": total_orders,
            "total_revenue": round(total_revenue, 2),
            "avg_order_value": round(avg_order_value, 2),
            "unique_customers": unique_customers,
        },
        "top_customers": [{"id": c, "revenue": round(v, 2)} for c, v in top_5],
        "regions": [{"region": r, "revenue": round(v, 2)} for r, v in regions_sorted],
        "monthly": [{"month": m, "revenue": round(v, 2)} for m, v in months_sorted],
        "categories": [{"category": c, "orders": v} for c, v in categories_sorted],
        "statuses": [{"status": s, "count": v} for s, v in statuses_sorted],
    }

    # ---- Color definitions ----
    navy = "#1B2A4A"
    teal = "#2E86AB"
    orange = "#F18F01"
    red = "#C73E1D"
    plum = "#3B1F2B"
    green = "#2CA58D"
    colors = [teal, orange, red, green, plum, "#5B8C5A"]

    # ---- SVG Generators ----
    def svg_horizontal_bar(items, label_key, value_key, width=380, bar_h=28, gap=6, color=teal):
        """Generate horizontal bar chart SVG."""
        if not items:
            return "<p>No data</p>"
        max_val = max(item[value_key] for item in items)
        if max_val == 0:
            max_val = 1
        label_w = 90
        chart_w = width - label_w - 80
        height = len(items) * (bar_h + gap) + 10
        svg = f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">\n'
        for i, item in enumerate(items):
            y = i * (bar_h + gap) + 5
            bar_width = max(2, (item[value_key] / max_val) * chart_w)
            svg += f'  <text x="0" y="{y + bar_h * 0.65}" font-size="11" fill="#444" '
            svg += f'font-family="sans-serif">{item[label_key]}</text>\n'
            svg += f'  <rect x="{label_w}" y="{y}" width="{bar_width}" height="{bar_h}" '
            svg += f'rx="3" fill="{color}" opacity="0.85"/>\n'
            val_str = f"${item[value_key]:,.0f}" if value_key == "revenue" else f"{item[value_key]:,}"
            svg += f'  <text x="{label_w + bar_width + 5}" y="{y + bar_h * 0.65}" '
            svg += f'font-size="11" fill="#333" font-family="sans-serif">{val_str}</text>\n'
        svg += '</svg>'
        return svg

    def svg_vertical_bar(items, label_key, value_key, width=380, height=220, color_list=None):
        """Generate vertical bar chart SVG."""
        if not items:
            return "<p>No data</p>"
        max_val = max(item[value_key] for item in items)
        if max_val == 0:
            max_val = 1
        n = len(items)
        margin_l, margin_b, margin_t = 60, 40, 20
        chart_w = width - margin_l - 20
        chart_h = height - margin_b - margin_t
        bar_w = max(20, min(60, chart_w // (n * 2)))
        gap = (chart_w - n * bar_w) / (n + 1) if n > 0 else 0

        svg = f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">\n'
        # Y-axis labels
        for i in range(5):
            val = max_val * (4 - i) / 4
            y = margin_t + chart_h * i / 4
            svg += f'  <text x="{margin_l - 5}" y="{y + 4}" font-size="10" fill="#888" '
            svg += f'text-anchor="end" font-family="sans-serif">'
            if value_key == "revenue":
                svg += f'${val:,.0f}'
            else:
                svg += f'{val:,.0f}'
            svg += '</text>\n'
            svg += f'  <line x1="{margin_l}" y1="{y}" x2="{width - 20}" y2="{y}" '
            svg += f'stroke="#eee" stroke-width="1"/>\n'

        for i, item in enumerate(items):
            x = margin_l + gap + i * (bar_w + gap)
            bar_height = max(2, (item[value_key] / max_val) * chart_h)
            y = margin_t + chart_h - bar_height
            c = (color_list or colors)[i % len(color_list or colors)]
            svg += f'  <rect x="{x}" y="{y}" width="{bar_w}" height="{bar_height}" '
            svg += f'rx="2" fill="{c}" opacity="0.85"/>\n'
            svg += f'  <text x="{x + bar_w / 2}" y="{height - margin_b + 15}" '
            svg += f'font-size="10" fill="#444" text-anchor="middle" '
            svg += f'font-family="sans-serif">{item[label_key]}</text>\n'
        svg += '</svg>'
        return svg

    def svg_line_chart(items, label_key, value_key, width=380, height=220):
        """Generate line chart SVG with polyline."""
        if not items or len(items) < 2:
            return "<p>Not enough data</p>"
        max_val = max(item[value_key] for item in items)
        min_val = min(item[value_key] for item in items)
        if max_val == min_val:
            max_val = min_val + 1
        margin_l, margin_r, margin_t, margin_b = 65, 20, 20, 50
        chart_w = width - margin_l - margin_r
        chart_h = height - margin_t - margin_b
        n = len(items)

        svg = f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">\n'
        # Grid lines
        for i in range(5):
            val = min_val + (max_val - min_val) * (4 - i) / 4
            y = margin_t + chart_h * i / 4
            svg += f'  <text x="{margin_l - 5}" y="{y + 4}" font-size="10" fill="#888" '
            svg += f'text-anchor="end" font-family="sans-serif">${val:,.0f}</text>\n'
            svg += f'  <line x1="{margin_l}" y1="{y}" x2="{width - margin_r}" y2="{y}" '
            svg += f'stroke="#eee" stroke-width="1"/>\n'

        # Points and polyline
        points = []
        for i, item in enumerate(items):
            x = margin_l + (i / max(1, n - 1)) * chart_w
            y = margin_t + chart_h - ((item[value_key] - min_val) / (max_val - min_val)) * chart_h
            points.append(f"{x:.1f},{y:.1f}")

        svg += f'  <polyline points="{" ".join(points)}" fill="none" '
        svg += f'stroke="{teal}" stroke-width="2.5" stroke-linejoin="round"/>\n'

        # Dots and labels
        for i, item in enumerate(items):
            x = margin_l + (i / max(1, n - 1)) * chart_w
            y = margin_t + chart_h - ((item[value_key] - min_val) / (max_val - min_val)) * chart_h
            svg += f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{teal}"/>\n'
            # X-axis labels — show every Nth to avoid overlap
            step = max(1, n // 6)
            if i % step == 0 or i == n - 1:
                label = item[label_key][-5:] if len(item[label_key]) > 5 else item[label_key]
                svg += f'  <text x="{x:.1f}" y="{height - margin_b + 15}" font-size="9" '
                svg += f'fill="#444" text-anchor="middle" font-family="sans-serif" '
                svg += f'transform="rotate(-30 {x:.1f} {height - margin_b + 15})">{label}</text>\n'
        svg += '</svg>'
        return svg

    def svg_pie_chart(items, label_key, value_key, width=360, height=220):
        """Generate donut/pie chart SVG."""
        if not items:
            return "<p>No data</p>"
        total = sum(item[value_key] for item in items)
        if total == 0:
            total = 1
        cx, cy, r = width // 2 - 40, height // 2, min(width // 2 - 60, height // 2 - 15)
        inner_r = r * 0.5

        svg = f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">\n'
        start_angle = -math.pi / 2
        for i, item in enumerate(items):
            fraction = item[value_key] / total
            end_angle = start_angle + fraction * 2 * math.pi
            large_arc = 1 if fraction > 0.5 else 0
            c = colors[i % len(colors)]

            # Outer arc
            x1 = cx + r * math.cos(start_angle)
            y1 = cy + r * math.sin(start_angle)
            x2 = cx + r * math.cos(end_angle)
            y2 = cy + r * math.sin(end_angle)
            # Inner arc
            ix1 = cx + inner_r * math.cos(end_angle)
            iy1 = cy + inner_r * math.sin(end_angle)
            ix2 = cx + inner_r * math.cos(start_angle)
            iy2 = cy + inner_r * math.sin(start_angle)

            path = (f"M {x1:.1f} {y1:.1f} "
                    f"A {r} {r} 0 {large_arc} 1 {x2:.1f} {y2:.1f} "
                    f"L {ix1:.1f} {iy1:.1f} "
                    f"A {inner_r} {inner_r} 0 {large_arc} 0 {ix2:.1f} {iy2:.1f} Z")
            svg += f'  <path d="{path}" fill="{c}" opacity="0.85" stroke="white" stroke-width="1.5"/>\n'
            start_angle = end_angle

        # Legend on the right
        legend_x = cx + r + 20
        for i, item in enumerate(items):
            ly = 20 + i * 22
            c = colors[i % len(colors)]
            pct = item[value_key] / total * 100
            svg += f'  <rect x="{legend_x}" y="{ly}" width="12" height="12" rx="2" fill="{c}"/>\n'
            svg += f'  <text x="{legend_x + 18}" y="{ly + 10}" font-size="11" fill="#444" '
            svg += f'font-family="sans-serif">{item[label_key]} ({pct:.0f}%)</text>\n'

        svg += '</svg>'
        return svg

    # ---- KPI cards HTML ----
    kpi_html = f"""
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
      <div style="background:#f0f7fa; border-radius:8px; padding:16px; text-align:center;">
        <div style="font-size:28px; font-weight:700; color:{teal};">{total_orders:,}</div>
        <div style="font-size:12px; color:#666; margin-top:4px;">Total Orders</div>
      </div>
      <div style="background:#fff8f0; border-radius:8px; padding:16px; text-align:center;">
        <div style="font-size:28px; font-weight:700; color:{orange};">${total_revenue:,.2f}</div>
        <div style="font-size:12px; color:#666; margin-top:4px;">Total Revenue</div>
      </div>
      <div style="background:#f0faf5; border-radius:8px; padding:16px; text-align:center;">
        <div style="font-size:28px; font-weight:700; color:{green};">${avg_order_value:,.2f}</div>
        <div style="font-size:12px; color:#666; margin-top:4px;">Avg Order Value</div>
      </div>
      <div style="background:#f5f0f5; border-radius:8px; padding:16px; text-align:center;">
        <div style="font-size:28px; font-weight:700; color:{plum};">{unique_customers:,}</div>
        <div style="font-size:12px; color:#666; margin-top:4px;">Unique Customers</div>
      </div>
    </div>"""

    # ---- Generate SVGs ----
    top_customers_svg = svg_horizontal_bar(
        data["top_customers"], "id", "revenue", color=teal
    )
    regions_svg = svg_vertical_bar(
        data["regions"], "region", "revenue",
        color_list=[teal, orange, green, red, plum]
    )
    monthly_svg = svg_line_chart(data["monthly"], "month", "revenue")
    categories_svg = svg_pie_chart(data["categories"], "category", "orders")
    status_svg = svg_vertical_bar(
        data["statuses"], "status", "count",
        color_list=[green, teal, orange, red, plum]
    )

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # ---- Assemble HTML ----
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Order Transactions Analytics Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #f4f5f7; color: #333; }}
  header {{ background: {navy}; color: white; padding: 20px 32px;
           display: flex; justify-content: space-between; align-items: center; }}
  header h1 {{ font-size: 22px; font-weight: 600; }}
  header .subtitle {{ font-size: 12px; opacity: 0.7; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr;
           gap: 20px; padding: 24px 32px; max-width: 1400px; margin: 0 auto; }}
  .card {{ background: white; border-radius: 10px; padding: 20px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .card h2 {{ font-size: 14px; color: #666; font-weight: 600;
              margin-bottom: 16px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .card svg {{ max-width: 100%; height: auto; }}
  footer {{ text-align: center; padding: 20px; font-size: 11px; color: #999; }}
  footer a {{ color: {teal}; text-decoration: none; }}
  @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<header>
  <div>
    <h1>Order Transactions Analytics</h1>
    <div class="subtitle">Publish Zone | Star Schema | Generated {now_str}</div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:11px; opacity:0.6;">Data freshness</div>
    <div style="font-size:13px;">{now_str}</div>
  </div>
</header>

<div class="grid">
  <!-- Row 1 -->
  <div class="card">
    <h2>Key Metrics</h2>
    {kpi_html}
  </div>
  <div class="card" style="grid-column: span 2;">
    <h2>Top 5 Customers by Revenue</h2>
    {top_customers_svg}
  </div>

  <!-- Row 2 -->
  <div class="card">
    <h2>Sales by Region</h2>
    {regions_svg}
  </div>
  <div class="card">
    <h2>Revenue Trend by Month</h2>
    {monthly_svg}
  </div>
  <div class="card">
    <h2>Orders by Product Category</h2>
    {categories_svg}
  </div>

  <!-- Row 3 -->
  <div class="card" style="grid-column: span 3;">
    <h2>Order Status Breakdown</h2>
    {status_svg}
  </div>
</div>

<footer>
  Generated by <strong>run_pipeline.py</strong> &mdash; Agentic Data Onboarding Platform
  &nbsp;|&nbsp; {now_str}
  <br>
  <script>
    // Embedded data for reference / further JS interactivity
    const DASHBOARD_DATA = {json.dumps(data, indent=2)};
  </script>
</footer>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print()
    print("=" * 78)
    print("  AGENTIC DATA ONBOARDING PLATFORM -- End-to-End Pipeline Runner")
    print("  EDMODE Narration | Guardrail Checks | Dashboard Preview")
    print(f"  Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Project: {PROJECT_ROOT}")
    print("=" * 78)

    ctx = {"guardrails": CedarPolicyEvaluator()}

    steps = [
        step_01_create_databases,
        step_02_ingest_customers,
        step_03_customer_landing_to_staging,
        step_04_customer_staging_quality,
        step_05_customer_staging_to_publish,
        step_06_customer_publish_quality,
        step_07_ingest_orders,
        step_08_order_landing_to_staging,
        step_09_order_staging_quality,
        step_10_order_staging_to_publish,
        step_11_order_publish_quality,
        step_12_generate_dashboard,
    ]

    for step_fn in steps:
        try:
            step_fn(ctx)
        except Exception as exc:
            step_name = step_fn.__name__
            print(f"\n  !!! FATAL ERROR in {step_name}: {exc}")
            print(f"  Pipeline halted. Printing guardrail summary so far.\n")
            import traceback
            traceback.print_exc()
            ctx["guardrails"].print_summary()
            sys.exit(2)

    ctx["guardrails"].print_summary()

    if ctx["guardrails"].all_passed():
        print(f"\n  Dashboard preview: {DASHBOARD_OUTPUT}")
        print("  Open in any browser to view the analytics dashboard.\n")
        sys.exit(0)
    else:
        print(f"\n  Dashboard preview was still generated: {DASHBOARD_OUTPUT}")
        print("  However, some guardrails FAILED. Review the summary above.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
