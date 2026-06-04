"""
AWS Glue Data Quality integration for claims_v2.

Creates DQDL rulesets from quality.yaml, runs evaluation against
Glue Catalog tables, and enforces quality gates (Bronze→Silver: 0.80,
Silver→Gold: 0.95).

Usage:
  CLI:
    aws glue start-data-quality-ruleset-evaluation-run \
      --ruleset-names claims_v2_silver_ruleset \
      --data-source '{"GlueTable":{"DatabaseName":"claims_v2_db","TableName":"silver_claims_v2"}}'

  Airflow (GlueDataQualityOperator):
    See claims_v2_pipeline.py for DAG integration.

  Standalone:
    python glue_data_quality.py --action create-ruleset --zone silver
    python glue_data_quality.py --action run-evaluation --zone silver
    python glue_data_quality.py --action check-results --run-id <run-id>
"""
import argparse
import json
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.structured_logger import StructuredLogger

logger = StructuredLogger(
    agent="glue_data_quality",
    workload="claims_v2",
    run_id="standalone",
)

WORKLOAD = "claims_v2"
DATABASE = "claims_v2_db"
SILVER_TABLE = "silver_claims_v2"
GOLD_TABLE = "gold_claims_v2"

QUALITY_GATES = {
    "silver": {"overall_score": 0.80, "critical_failures": 0},
    "gold": {"overall_score": 0.95, "critical_failures": 0},
}


def build_dqdl_ruleset(zone: str) -> str:
    """Translate quality.yaml rules into DQDL syntax for the given zone."""
    rules = []

    # Completeness rules
    rules.append('Completeness "claim_id" = 1.0')
    rules.append('Completeness "member_id" = 1.0')
    rules.append('Completeness "billed_amount" >= 0.99')
    rules.append('Completeness "service_date" = 1.0')

    # Uniqueness rules
    rules.append('Uniqueness "claim_id" = 1.0')

    # Validity rules - enum checks via ColumnValues
    rules.append(
        'ColumnValues "claim_type" in ["medical", "dental", "vision", "pharmacy"]'
    )
    rules.append(
        'ColumnValues "claim_status" in ["paid", "denied", "pending", "appealed"]'
    )

    # Validity rules - range checks
    rules.append('ColumnValues "billed_amount" between 0 and 10000000')

    if zone == "gold":
        # Gold has stricter thresholds — add row count check
        rules.append("RowCount > 0")

    rules_block = ",\n    ".join(rules)
    return f"Rules = [\n    {rules_block}\n]"


def get_glue_client():
    return boto3.client("glue")


def create_ruleset(zone: str) -> str:
    """Create or update DQDL ruleset in Glue Data Catalog."""
    client = get_glue_client()
    table_name = SILVER_TABLE if zone == "silver" else GOLD_TABLE
    ruleset_name = f"{WORKLOAD}_{zone}_ruleset"
    dqdl = build_dqdl_ruleset(zone)

    logger.log("info", "create_ruleset_start", zone=zone, ruleset_name=ruleset_name)

    try:
        client.delete_data_quality_ruleset(Name=ruleset_name)
        logger.log("info", "deleted_existing_ruleset", ruleset_name=ruleset_name)
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityNotFoundException":
            raise

    client.create_data_quality_ruleset(
        Name=ruleset_name,
        Ruleset=dqdl,
        Description=f"Data quality rules for {WORKLOAD} {zone} zone",
        TargetTable={
            "TableName": table_name,
            "DatabaseName": DATABASE,
        },
    )

    logger.log("info", "create_ruleset_complete", ruleset_name=ruleset_name)
    print(f"Created ruleset: {ruleset_name}")
    print(f"DQDL:\n{dqdl}")
    return ruleset_name


def run_evaluation(zone: str) -> str:
    """Start a Glue Data Quality evaluation run."""
    client = get_glue_client()
    table_name = SILVER_TABLE if zone == "silver" else GOLD_TABLE
    ruleset_name = f"{WORKLOAD}_{zone}_ruleset"

    logger.log("info", "evaluation_start", zone=zone, ruleset_name=ruleset_name)

    response = client.start_data_quality_ruleset_evaluation_run(
        DataSource={
            "GlueTable": {
                "DatabaseName": DATABASE,
                "TableName": table_name,
            }
        },
        RulesetNames=[ruleset_name],
        Role=Variable_get_safe("glue_iam_role", "AWSGlueServiceRole"),
    )

    run_id = response["RunId"]
    logger.log("info", "evaluation_started", run_id=run_id)
    print(f"Started evaluation run: {run_id}")
    return run_id


def wait_for_evaluation(run_id: str, timeout_seconds: int = 600) -> dict:
    """Poll until the evaluation run completes."""
    client = get_glue_client()
    start_time = time.time()

    while True:
        response = client.get_data_quality_ruleset_evaluation_run(RunId=run_id)
        status = response["Status"]

        if status in ("SUCCEEDED", "FAILED", "TIMEOUT", "STOPPED"):
            logger.log("info", "evaluation_complete", run_id=run_id, status=status)
            return response

        if time.time() - start_time > timeout_seconds:
            raise TimeoutError(
                f"Evaluation run {run_id} did not complete within {timeout_seconds}s"
            )

        time.sleep(15)


def check_results(run_id: str, zone: str) -> dict:
    """Check evaluation results and enforce quality gate."""
    client = get_glue_client()

    response = client.get_data_quality_result(ResultId=run_id)

    total_rules = len(response.get("RuleResults", []))
    passed_rules = sum(
        1 for r in response.get("RuleResults", []) if r["Result"] == "PASS"
    )
    failed_rules = total_rules - passed_rules
    overall_score = response.get("Score", passed_rules / total_rules if total_rules > 0 else 0.0)

    gate = QUALITY_GATES[zone]
    gate_passed = overall_score >= gate["overall_score"] and failed_rules <= gate["critical_failures"]

    result = {
        "workload": WORKLOAD,
        "zone": zone,
        "run_id": run_id,
        "total_rules": total_rules,
        "passed_rules": passed_rules,
        "failed_rules": failed_rules,
        "overall_score": overall_score,
        "gate_threshold": gate["overall_score"],
        "gate_passed": gate_passed,
        "rule_results": [
            {
                "name": r["Name"],
                "description": r.get("Description", ""),
                "result": r["Result"],
                "evaluation_message": r.get("EvaluationMessage", ""),
            }
            for r in response.get("RuleResults", [])
        ],
    }

    logger.log(
        "info",
        "quality_gate_evaluation",
        zone=zone,
        overall_score=overall_score,
        passed=passed_rules,
        failed=failed_rules,
        gate_passed=gate_passed,
    )

    print(f"\n{'='*60}")
    print(f"  GLUE DATA QUALITY RESULTS — {zone.upper()} ZONE")
    print(f"{'='*60}")
    print(f"  Score:    {overall_score:.2%}")
    print(f"  Rules:    {passed_rules}/{total_rules} passed")
    print(f"  Gate:     {'PASSED' if gate_passed else 'FAILED'} (threshold: {gate['overall_score']:.0%})")
    print(f"{'='*60}")

    if not gate_passed:
        print("\n  FAILED RULES:")
        for r in result["rule_results"]:
            if r["result"] == "FAIL":
                print(f"    ✗ {r['name']}: {r['evaluation_message']}")

    return result


def run_full_evaluation(zone: str) -> dict:
    """End-to-end: create ruleset, run evaluation, check results."""
    create_ruleset(zone)
    run_id = run_evaluation(zone)
    wait_for_evaluation(run_id)
    result = check_results(run_id, zone)

    if not result["gate_passed"]:
        raise RuntimeError(
            f"Quality gate FAILED for {zone}: score={result['overall_score']:.3f}, "
            f"failed_rules={result['failed_rules']}"
        )

    return result


def Variable_get_safe(key: str, default: str) -> str:
    """Get Airflow Variable if available, else use default."""
    try:
        from airflow.models import Variable
        return Variable.get(key, default_var=default)
    except (ImportError, Exception):
        return default


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AWS Glue Data Quality for claims_v2")
    parser.add_argument(
        "--action",
        choices=["create-ruleset", "run-evaluation", "check-results", "full"],
        required=True,
        help="Action to perform",
    )
    parser.add_argument("--zone", choices=["silver", "gold"], default="silver")
    parser.add_argument("--run-id", help="Run ID (for check-results action)")

    args = parser.parse_args()

    if args.action == "create-ruleset":
        create_ruleset(args.zone)
    elif args.action == "run-evaluation":
        run_evaluation(args.zone)
    elif args.action == "check-results":
        if not args.run_id:
            parser.error("--run-id required for check-results action")
        check_results(args.run_id, args.zone)
    elif args.action == "full":
        run_full_evaluation(args.zone)
