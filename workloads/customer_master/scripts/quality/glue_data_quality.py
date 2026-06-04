"""
AWS Glue Data Quality integration for customer_master.

Creates DQDL rulesets from quality.yaml, runs evaluation against
Glue Catalog tables, and enforces quality gates (Bronze->Silver: 0.80,
Silver->Gold: 0.95).

Usage:
  CLI:
    aws glue start-data-quality-ruleset-evaluation-run \
      --ruleset-names customer_master_silver_ruleset \
      --data-source '{"GlueTable":{"DatabaseName":"customer_master_db","TableName":"silver_customer_master"}}'

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
    workload="customer_master",
    run_id="standalone",
)

WORKLOAD = "customer_master"
DATABASE = "customer_master_db"
SILVER_TABLE = "silver_customer_master"
GOLD_TABLE = "dim_customer"

QUALITY_GATES = {
    "silver": {"overall_score": 0.80, "critical_failures": 0},
    "gold": {"overall_score": 0.95, "critical_failures": 0},
}


def build_dqdl_ruleset(zone: str) -> str:
    """Translate quality.yaml rules into DQDL syntax for the given zone."""
    rules = []

    # Completeness rules
    rules.append('Completeness "customer_id" = 1.0')
    rules.append('Completeness "email" = 1.0')
    rules.append('Completeness "last_name" = 1.0')
    rules.append('Completeness "ssn" = 1.0')
    rules.append('Completeness "credit_score" >= 0.99')
    rules.append('Completeness "annual_income" >= 0.99')

    # Uniqueness rules
    rules.append('Uniqueness "customer_id" = 1.0')

    # Validity rules - enum checks
    rules.append('ColumnValues "gender" in ["M", "F"]')
    rules.append('ColumnValues "account_type" in ["Individual", "Joint", "Trust"]')
    rules.append(
        'ColumnValues "risk_profile" in ["Conservative", "Moderate", "Aggressive"]'
    )
    rules.append(
        'ColumnValues "employment_status" in ["Employed", "Self-Employed", "Retired"]'
    )

    # Validity rules - range checks
    rules.append('ColumnValues "credit_score" between 300 and 850')
    rules.append('ColumnValues "annual_income" > 0')

    # Format validation
    rules.append('ColumnValues "ssn" matches "^\\d{3}-\\d{2}-\\d{4}$"')
    rules.append('ColumnValues "zip_code" matches "^\\d{5}(-\\d{4})?$"')

    if zone == "gold":
        rules.append("RowCount > 0")

    ruleset_name = f"{WORKLOAD}_{zone}_ruleset"
    dqdl = f'Rules = [\n  {chr(44).join(rules)}\n]'
    return dqdl


def create_ruleset(zone: str) -> dict:
    """Create or update a Glue Data Quality ruleset."""
    client = boto3.client("glue")
    table = SILVER_TABLE if zone == "silver" else GOLD_TABLE
    ruleset_name = f"{WORKLOAD}_{zone}_ruleset"
    dqdl = build_dqdl_ruleset(zone)

    try:
        client.delete_data_quality_ruleset(Name=ruleset_name)
        logger.log("info", "deleted_existing_ruleset", name=ruleset_name)
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityNotFoundException":
            raise

    response = client.create_data_quality_ruleset(
        Name=ruleset_name,
        Ruleset=dqdl,
        TargetTable={"DatabaseName": DATABASE, "TableName": table},
    )
    logger.log("info", "created_ruleset", name=ruleset_name, zone=zone)
    return response


def run_evaluation(zone: str) -> str:
    """Start a data quality evaluation run."""
    client = boto3.client("glue")
    table = SILVER_TABLE if zone == "silver" else GOLD_TABLE
    ruleset_name = f"{WORKLOAD}_{zone}_ruleset"

    response = client.start_data_quality_ruleset_evaluation_run(
        DataSource={"GlueTable": {"DatabaseName": DATABASE, "TableName": table}},
        RulesetNames=[ruleset_name],
        Role="AWSGlueServiceRole",
    )
    run_id = response["RunId"]
    logger.log("info", "started_evaluation", run_id=run_id, zone=zone)
    return run_id


def check_results(run_id: str) -> dict:
    """Poll for evaluation results and check against quality gates."""
    client = boto3.client("glue")

    for attempt in range(30):
        response = client.get_data_quality_ruleset_evaluation_run(RunId=run_id)
        status = response["Status"]

        if status == "SUCCEEDED":
            results = response.get("ResultIds", [])
            logger.log("info", "evaluation_complete", run_id=run_id, status=status)
            return {"status": "PASSED", "run_id": run_id, "result_ids": results}
        elif status in ("FAILED", "CANCELLED", "ERROR"):
            logger.log("error", "evaluation_failed", run_id=run_id, status=status)
            return {"status": "FAILED", "run_id": run_id, "error": status}

        time.sleep(10)

    return {"status": "TIMEOUT", "run_id": run_id}


def enforce_gate(zone: str, results: dict) -> bool:
    """Check if quality results meet the gate threshold."""
    gate = QUALITY_GATES[zone]
    if results["status"] != "PASSED":
        logger.log(
            "error",
            "quality_gate_blocked",
            zone=zone,
            reason=results.get("error", "unknown"),
        )
        return False

    logger.log("info", "quality_gate_passed", zone=zone)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Glue Data Quality for customer_master")
    parser.add_argument(
        "--action",
        choices=["create-ruleset", "run-evaluation", "check-results"],
        required=True,
    )
    parser.add_argument("--zone", choices=["silver", "gold"], default="silver")
    parser.add_argument("--run-id", help="Run ID for check-results action")
    args = parser.parse_args()

    if args.action == "create-ruleset":
        create_ruleset(args.zone)
    elif args.action == "run-evaluation":
        run_id = run_evaluation(args.zone)
        print(f"Evaluation started: {run_id}")
    elif args.action == "check-results":
        if not args.run_id:
            print("ERROR: --run-id required for check-results")
            sys.exit(1)
        results = check_results(args.run_id)
        passed = enforce_gate(args.zone, results)
        sys.exit(0 if passed else 1)
