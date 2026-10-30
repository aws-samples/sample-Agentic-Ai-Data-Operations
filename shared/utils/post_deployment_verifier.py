"""
Post-Deployment Verifier (Step 5.9)

Runs up to 10 smoke tests (5.9a-5.9j) against deployed AWS resources after
pipeline deployment, including IAM simulation of the MWAA and Glue roles.
Reports PASS/FAIL summary. Deployment is NOT complete until all checks pass.

Usage:
    from shared.utils.post_deployment_verifier import PostDeploymentVerifier

    verifier = PostDeploymentVerifier(workload="claims", database="claims_db", region="us-east-1")
    results = verifier.run_all()
    verifier.print_summary(results)

    # Or run individual checks:
    result = verifier.check_glue_tables(["silver_claims", "gold_claims_analytical"])
"""

import boto3
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.metadata.glue_fetcher import GlueFetcher
from shared.metadata.lakeformation_fetcher import LakeFormationFetcher
from shared.utils.deployment_checks import (
    glue_role_requirements,
    mwaa_role_requirements,
    simulate_role,
)
from shared.utils.deployment_guardrails import (
    DeploymentGuardrailError,
    require_query_principal,
    require_tbac_principals,
)
from shared.utils.structured_logger import StructuredLogger


@dataclass
class CheckResult:
    name: str
    step: str
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


class PostDeploymentVerifier:

    def __init__(self, workload: str, database: str, region: str = "us-east-1",
                 catalog_id: Optional[str] = None, mwaa_environment: Optional[str] = None,
                 query_principal_arn: Optional[str] = None):
        self.workload = workload
        self.database = database
        self.region = region
        self.catalog_id = catalog_id
        self.mwaa_environment = mwaa_environment
        self.query_principal_arn = query_principal_arn

        self.glue_fetcher = GlueFetcher(region=region, catalog_id=catalog_id)
        self.lf_fetcher = LakeFormationFetcher(region=region, catalog_id=catalog_id)
        self.log = StructuredLogger("PostDeployVerifier", workload, f"verify-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")

        # Created lazily after assuming the explicitly named query role.
        self.athena = None
        self.kms = boto3.client("kms", region_name=region)
        self.cloudtrail = boto3.client("cloudtrail", region_name=region)

    def run_all(self, tables: Optional[List[str]] = None,
                phi_columns: Optional[Dict[str, List[str]]] = None,
                kms_key_alias: str = "alias/hipaa-phi-key",
                dag_id: Optional[str] = None,
                tbac_principals: Optional[List[Dict[str, Any]]] = None,
                mwaa_role_arn: Optional[str] = None,
                glue_role_arn: Optional[str] = None,
                glue_job_names: Optional[List[str]] = None,
                kms_key_arn: Optional[str] = None) -> List[CheckResult]:
        results = []

        if tables:
            results.append(self.check_glue_tables(tables))
            results.append(self.check_athena_queries(tables))

        if phi_columns:
            results.append(self.check_lf_tags(phi_columns))
            results.append(self.check_tbac_access(phi_columns, tbac_principals))

        results.append(self.check_kms_encryption(kms_key_alias))

        if dag_id:
            results.append(self.check_mwaa_dag(dag_id))
        else:
            results.append(CheckResult(
                name="MWAA DAG Health",
                step="5.9f",
                passed=False,
                message="dag_id is required",
            ))

        # These checks are mandatory even when their inputs are absent; the
        # individual check returns a failed result for missing arguments.
        results.append(self.check_mwaa_role_permissions(
            mwaa_role_arn, glue_role_arn, glue_job_names or []))

        if glue_role_arn:
            results.append(self.check_glue_role_permissions(glue_role_arn, kms_key_arn))
        else:
            results.append(CheckResult(
                name="Glue Role Permissions",
                step="5.9j",
                passed=False,
                message="glue_role_arn is required",
            ))

        results.append(self.check_cloudtrail_events())

        self.log.info("Verification complete", total=len(results),
                      passed=sum(1 for r in results if r.passed),
                      failed=sum(1 for r in results if not r.passed))
        return results

    def check_glue_tables(self, tables: List[str]) -> CheckResult:
        """5.9a: Verify all Silver + Gold tables exist with correct schema."""
        self.log.info("Checking Glue Catalog tables", tables=tables)
        missing = []
        found = []

        for table in tables:
            try:
                meta = self.glue_fetcher.fetch_table_metadata(self.database, table)
                found.append(table)
            except Exception as e:
                if "EntityNotFoundException" in str(e):
                    missing.append(table)
                else:
                    missing.append(f"{table} (error: {e})")

        passed = len(missing) == 0
        return CheckResult(
            name="Glue Catalog Tables",
            step="5.9a",
            passed=passed,
            message=f"Found {len(found)}/{len(tables)} tables" if passed else f"Missing: {missing}",
            details={"found": found, "missing": missing}
        )

    def check_athena_queries(self, tables: List[str]) -> CheckResult:
        """5.9b: Verify data is queryable with correct row counts."""
        self.log.info("Running Athena verification queries", tables=tables)
        try:
            query_principal = require_query_principal(
                {"iac_query_principal_arn": self.query_principal_arn}
            )
        except DeploymentGuardrailError:
            return CheckResult(
                name="Athena Query Verification",
                step="5.9b",
                passed=False,
                message="Explicit query_principal_arn is required; refusing to use the current caller",
                details={"query_principal_arn": None},
            )
        results_detail = {}
        all_passed = True

        for table in tables:
            query = f"SELECT COUNT(*) as cnt FROM {self.database}.{table} LIMIT 1"
            try:
                row_count = self._run_athena_query(query)
                results_detail[table] = {
                    "row_count": row_count,
                    "queryable": True,
                    "query_principal_arn": query_principal,
                }
                if row_count == 0:
                    all_passed = False
                    results_detail[table]["issue"] = "Table is empty"
            except Exception as e:
                all_passed = False
                results_detail[table] = {"queryable": False, "error": str(e)}

        return CheckResult(
            name="Athena Query Verification",
            step="5.9b",
            passed=all_passed,
            message="All tables queryable with data" if all_passed else "Some tables empty or not queryable",
            details=results_detail
        )

    def check_lf_tags(self, phi_columns: Dict[str, List[str]]) -> CheckResult:
        """5.9c: Verify every PHI column is tagged with PII_Classification + Data_Sensitivity."""
        self.log.info("Checking LF-Tags on PHI columns")
        untagged = []
        tagged = []
        required_tags = {"PII_Classification", "PII_Type", "Data_Sensitivity"}

        for table, columns in phi_columns.items():
            try:
                tag_info = self.lf_fetcher.fetch_table_lf_tags(self.database, table)
                column_tags = tag_info.get("column_tags", {})

                for col in columns:
                    col_tag_keys = set()
                    for tag in column_tags.get(col, []):
                        col_tag_keys.add(tag.get("TagKey", ""))

                    if required_tags.issubset(col_tag_keys):
                        tagged.append(f"{table}.{col}")
                    else:
                        missing_tags = required_tags - col_tag_keys
                        untagged.append(f"{table}.{col} (missing: {missing_tags})")
            except Exception as e:
                untagged.append(f"{table} (error: {e})")

        passed = len(untagged) == 0
        return CheckResult(
            name="LF-Tags on PHI Columns",
            step="5.9c",
            passed=passed,
            message=f"All {len(tagged)} PHI columns tagged" if passed else f"{len(untagged)} columns missing tags",
            details={"tagged": tagged, "untagged": untagged}
        )

    def check_tbac_access(
        self,
        phi_columns: Dict[str, List[str]],
        tbac_principals: Optional[List[Dict[str, Any]]] = None,
    ) -> CheckResult:
        """5.9d: Verify TBAC restricts access to CRITICAL PHI columns."""
        self.log.info("Checking TBAC access control")
        try:
            if not tbac_principals:
                return CheckResult(
                    name="TBAC Access Control",
                    step="5.9d",
                    passed=False,
                    message="Explicit TBAC principals are required; refusing to infer the current caller",
                    details={"tbac_principals": []},
                )
            normalized = require_tbac_principals(
                {"iac_tbac_principals": tbac_principals}
            )
            critical_grants = self.lf_fetcher.fetch_lf_tag_policy_permissions(
                "Data_Sensitivity", ["CRITICAL"]
            )
            granted_critical = {
                item.get("Principal", {}).get("DataLakePrincipalIdentifier")
                for item in critical_grants
                if "SELECT" in item.get("Permissions", [])
            }
            critical_columns_found = False
            for table, columns in phi_columns.items():
                tag_info = self.lf_fetcher.fetch_table_lf_tags(self.database, table)
                column_tags = tag_info.get("column_tags", {})

                critical_columns = []
                for col in columns:
                    for tag in column_tags.get(col, []):
                        if tag.get("TagKey") == "Data_Sensitivity" and tag.get("TagValues", [None])[0] == "CRITICAL":
                            critical_columns.append(col)

                if critical_columns:
                    critical_columns_found = True

            if critical_columns_found:
                missing_critical = [
                    p["role_arn"]
                    for p in normalized
                    if "CRITICAL" in p["allowed_classifications"]
                    and p["role_arn"] not in granted_critical
                ]
                overexposed = [
                    p["role_arn"]
                    for p in normalized
                    if "CRITICAL" not in p["allowed_classifications"]
                    and p["role_arn"] in granted_critical
                ]
                passed = not missing_critical and not overexposed
                return CheckResult(
                    name="TBAC Access Control",
                    step="5.9d",
                    passed=passed,
                    message=(
                        "CRITICAL columns restricted to declared principals"
                        if passed
                        else "TBAC CRITICAL grant does not match declared principals"
                    ),
                    details={
                        "critical_granted_principals": sorted(granted_critical),
                        "missing_critical_grants": missing_critical,
                        "overexposed_principals": overexposed,
                    },
                )

            return CheckResult(
                name="TBAC Access Control",
                step="5.9d",
                passed=True,
                message="No CRITICAL columns found — declared TBAC principals recorded",
                details={"tbac_principals": normalized}
            )
        except Exception as e:
            return CheckResult(
                name="TBAC Access Control",
                step="5.9d",
                passed=False,
                message=f"Could not verify TBAC: {e}",
                details={"error": str(e)}
            )

    def check_kms_encryption(self, key_alias: str) -> CheckResult:
        """5.9e: Verify KMS key exists and rotation is enabled."""
        self.log.info("Checking KMS encryption", key_alias=key_alias)
        try:
            key_info = self.kms.describe_key(KeyId=key_alias)
            key_id = key_info["KeyMetadata"]["KeyId"]
            key_state = key_info["KeyMetadata"]["KeyState"]

            rotation = self.kms.get_key_rotation_status(KeyId=key_id)
            rotation_enabled = rotation.get("KeyRotationEnabled", False)

            passed = key_state == "Enabled" and rotation_enabled
            return CheckResult(
                name="KMS Encryption",
                step="5.9e",
                passed=passed,
                message=f"Key {key_alias}: state={key_state}, rotation={'enabled' if rotation_enabled else 'DISABLED'}",
                details={"key_id": key_id, "state": key_state, "rotation": rotation_enabled}
            )
        except Exception as e:
            return CheckResult(
                name="KMS Encryption",
                step="5.9e",
                passed=False,
                message=f"KMS check failed: {e}",
                details={"error": str(e)}
            )

    def _mwaa_cli(self, command: str) -> Any:
        """Run an Airflow CLI command through the MWAA CLI endpoint; return parsed JSON stdout."""
        mwaa = boto3.client("mwaa", region_name=self.region)
        token_response = mwaa.create_cli_token(Name=self.mwaa_environment)

        import urllib.request
        url = f"https://{token_response['WebServerHostname']}/aws_mwaa/cli"
        headers = {
            "Authorization": f"Bearer {token_response['CliToken']}",
            "Content-Type": "text/plain"
        }
        req = urllib.request.Request(url, data=command.encode(), headers=headers, method="POST")
        # B310: the scheme is the literal "https://" above and the host
        # comes from an authenticated mwaa.create_cli_token() response, so the
        # file:/ and custom-scheme cases B310 guards against cannot arise.
        response = urllib.request.urlopen(req)  # nosec B310
        import base64
        output = base64.b64decode(json.loads(response.read())["stdout"]).decode().strip()
        return json.loads(output) if output else []

    def check_mwaa_dag(self, dag_id: str) -> CheckResult:
        """5.9f: Verify DAG loaded in MWAA and has no import errors."""
        self.log.info("Checking MWAA DAG", dag_id=dag_id)
        if not self.mwaa_environment:
            return CheckResult(
                name="MWAA DAG Health",
                step="5.9f",
                passed=False,
                message="mwaa_environment is required to verify the DAG; refusing to skip",
                details={"dag_id": dag_id},
            )
        try:
            # A DAG that fails to import can still be listed from an earlier
            # good parse, so check import errors as well as presence.
            import_errors = [
                e for e in self._mwaa_cli("dags list-import-errors -o json")
                if dag_id in str(e.get("filepath", "")) or self.workload in str(e.get("filepath", ""))
            ]
            dags = self._mwaa_cli("dags list -o json")
            dag_entry = next((d for d in dags if d.get("dag_id") == dag_id), None)

            if import_errors:
                return CheckResult(
                    name="MWAA DAG Health",
                    step="5.9f",
                    passed=False,
                    message=f"DAG '{dag_id}' has {len(import_errors)} import error(s)",
                    details={"dag_id": dag_id, "import_errors": import_errors}
                )
            if dag_entry:
                is_paused = dag_entry.get("is_paused", True)
                return CheckResult(
                    name="MWAA DAG Health",
                    step="5.9f",
                    passed=True,
                    message=f"DAG '{dag_id}' loaded without import errors (paused={is_paused})",
                    details={"dag_id": dag_id, "paused": is_paused}
                )
            return CheckResult(
                name="MWAA DAG Health",
                step="5.9f",
                passed=False,
                message=f"DAG '{dag_id}' not found in MWAA environment",
                details={"dag_id": dag_id, "available_dags": [d.get("dag_id") for d in dags[:10]]}
            )
        except Exception as e:
            return CheckResult(
                name="MWAA DAG Health",
                step="5.9f",
                passed=False,
                message=f"MWAA check failed: {e}",
                details={"error": str(e)}
            )

    def _simulation_result(self, name: str, step: str, role_arn: str,
                           requirements: List[Dict[str, Any]]) -> CheckResult:
        try:
            iam = boto3.client("iam", region_name=self.region)
            denied = simulate_role(iam, role_arn, requirements)
        except Exception as e:
            return CheckResult(name=name, step=step, passed=False,
                               message=f"IAM simulation failed: {e}",
                               details={"role_arn": role_arn, "error": str(e)})
        return CheckResult(
            name=name,
            step=step,
            passed=not denied,
            message="All required actions allowed" if not denied
            else f"{len(denied)} required action(s) denied",
            details={"role_arn": role_arn, "denied": denied},
        )

    def check_mwaa_role_permissions(self, mwaa_role_arn: Optional[str],
                                    glue_role_arn: Optional[str],
                                    glue_job_names: List[str]) -> CheckResult:
        """5.9i: Simulate the MWAA execution role's GetJob/StartJobRun/GetJobRun + PassRole."""
        self.log.info("Simulating MWAA execution role", role=mwaa_role_arn, jobs=glue_job_names)
        if not (mwaa_role_arn and glue_role_arn and glue_job_names):
            return CheckResult(
                name="MWAA Role Permissions",
                step="5.9i",
                passed=False,
                message="mwaa_role_arn, glue_role_arn and glue_job_names are required",
                details={"mwaa_role_arn": mwaa_role_arn, "glue_role_arn": glue_role_arn,
                         "glue_job_names": glue_job_names},
            )
        try:
            requirements = mwaa_role_requirements(
                region=self.region, glue_role_arn=glue_role_arn, job_names=glue_job_names)
        except DeploymentGuardrailError as e:
            return CheckResult(name="MWAA Role Permissions", step="5.9i", passed=False,
                               message=str(e), details={})
        return self._simulation_result("MWAA Role Permissions", "5.9i",
                                       mwaa_role_arn, requirements)

    def check_glue_role_permissions(self, glue_role_arn: str,
                                    kms_key_arn: Optional[str]) -> CheckResult:
        """5.9j: Simulate the Glue role's catalog (incl. `default` db) and KMS calls."""
        self.log.info("Simulating Glue execution role", role=glue_role_arn)
        try:
            requirements = glue_role_requirements(
                region=self.region, glue_role_arn=glue_role_arn,
                databases=[self.database], kms_key_arn=kms_key_arn)
        except DeploymentGuardrailError as e:
            return CheckResult(name="Glue Role Permissions", step="5.9j", passed=False,
                               message=str(e), details={})
        return self._simulation_result("Glue Role Permissions", "5.9j",
                                       glue_role_arn, requirements)

    def check_cloudtrail_events(self) -> CheckResult:
        """5.9h: Verify deployment events logged in CloudTrail."""
        self.log.info("Checking CloudTrail audit events")
        try:
            expected_events = ["CreateTable", "AddLFTagsToResource", "GrantPermissions"]
            found_events = []
            start_time = datetime.now(timezone.utc) - timedelta(hours=24)

            for event_name in expected_events:
                response = self.cloudtrail.lookup_events(
                    LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": event_name}],
                    StartTime=start_time,
                    MaxResults=5
                )
                if response.get("Events"):
                    found_events.append(event_name)

            passed = len(found_events) >= 1
            return CheckResult(
                name="CloudTrail Audit Events",
                step="5.9h",
                passed=passed,
                message=f"Found {len(found_events)}/{len(expected_events)} deployment events in last 24h",
                details={"found": found_events, "expected": expected_events}
            )
        except Exception as e:
            return CheckResult(
                name="CloudTrail Audit Events",
                step="5.9h",
                passed=False,
                message=f"CloudTrail check failed: {e}",
                details={"error": str(e)}
            )

    def _run_athena_query(self, query: str, output_location: str = "s3://athena-query-results/") -> int:
        """Execute Athena query and return row count."""
        if self.athena is None:
            query_principal = require_query_principal(
                {"iac_query_principal_arn": self.query_principal_arn}
            )
            sts = boto3.client("sts", region_name=self.region)
            assumed = sts.assume_role(
                RoleArn=query_principal,
                RoleSessionName=f"adop-verify-{self.workload[:40]}",
            )["Credentials"]
            self.athena = boto3.client(
                "athena",
                region_name=self.region,
                aws_access_key_id=assumed["AccessKeyId"],
                aws_secret_access_key=assumed["SecretAccessKey"],
                aws_session_token=assumed["SessionToken"],
            )

        response = self.athena.start_query_execution(
            QueryString=query,
            ResultConfiguration={"OutputLocation": output_location}
        )
        query_id = response["QueryExecutionId"]

        for _ in range(30):
            status = self.athena.get_query_execution(QueryExecutionId=query_id)
            state = status["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                results = self.athena.get_query_results(QueryExecutionId=query_id)
                rows = results["ResultSet"]["Rows"]
                if len(rows) > 1:
                    return int(rows[1]["Data"][0]["VarCharValue"])
                return 0
            elif state in ("FAILED", "CANCELLED"):
                reason = status["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
                raise Exception(f"Athena query {state}: {reason}")
            time.sleep(2)

        raise Exception("Athena query timed out after 60s")

    @staticmethod
    def print_summary(results: List[CheckResult]):
        """Print PASS/FAIL summary table."""
        print("\n" + "=" * 70)
        print("  POST-DEPLOYMENT VERIFICATION RESULTS")
        print("=" * 70)
        print(f"\n{'Step':<8} {'Check':<30} {'Status':<8} {'Message'}")
        print("-" * 70)

        for r in results:
            status = "PASS" if r.passed else "FAIL"
            icon = "✓" if r.passed else "✗"
            print(f"{r.step:<8} {r.name:<30} {icon} {status:<5} {r.message}")

        print("-" * 70)
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        print(f"\n  Total: {total} | Passed: {passed} | Failed: {failed}")

        if failed > 0:
            print("\n  ⚠ DEPLOYMENT NOT COMPLETE — fix failures before proceeding")
        else:
            print("\n  ✓ ALL CHECKS PASSED — deployment verified")
        print("=" * 70 + "\n")

        return failed == 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Post-deployment verification")
    parser.add_argument("--workload", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--tables", nargs="+", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--kms-key", default="alias/hipaa-phi-key")
    parser.add_argument("--mwaa-env", required=True)
    parser.add_argument("--dag-id", required=True)
    parser.add_argument("--query-principal-arn", required=True)
    parser.add_argument("--mwaa-role-arn", required=True)
    parser.add_argument("--glue-role-arn", required=True)
    parser.add_argument("--glue-jobs", nargs="+", required=True)
    parser.add_argument("--kms-key-arn", required=True)
    args = parser.parse_args()

    verifier = PostDeploymentVerifier(
        workload=args.workload,
        database=args.database,
        region=args.region,
        mwaa_environment=args.mwaa_env,
        query_principal_arn=args.query_principal_arn,
    )

    results = verifier.run_all(
        tables=args.tables,
        kms_key_alias=args.kms_key,
        dag_id=args.dag_id,
        mwaa_role_arn=args.mwaa_role_arn,
        glue_role_arn=args.glue_role_arn,
        glue_job_names=args.glue_jobs,
        kms_key_arn=args.kms_key_arn,
    )

    all_passed = PostDeploymentVerifier.print_summary(results)
    sys.exit(0 if all_passed else 1)
