"""Command-line entry point for the ADOP Strands runtime."""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

from shared.orchestration.workflow_driver import WorkflowDriver, build_default_tasks

from .runner import StrandsRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adop_strands")
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the ADOP build through Strands")
    run.add_argument("--args", required=True, help="onboarding args JSON")
    run.add_argument("--run-id", default=None)
    run.add_argument("--region", default=None)
    run.add_argument("--model", default=None)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--ontology", action="store_true")
    run.add_argument("--no-review", action="store_true")

    profile = sub.add_parser("profile", help="Phase 3: read-only source profiling")
    profile.add_argument("--args", required=True, help="onboarding args JSON (needs workload_name, source)")
    profile.add_argument("--run-id", default=None)
    profile.add_argument("--region", default=None)
    profile.add_argument("--model", default=None)
    profile.add_argument("--athena-output", default=None,
                         help="human-provided s3:// location for Athena results")
    profile.add_argument("--athena-workgroup", default=None)
    profile.add_argument("--dry-run", action="store_true")

    status = sub.add_parser("status", help="list loadable Strands agent definitions")
    status.add_argument("--json", action="store_true")

    ns = parser.parse_args(argv)
    repo_root = Path(ns.repo_root).resolve()

    if ns.command == "status":
        from .definitions import DefinitionLoader
        names = DefinitionLoader(repo_root).names()
        if ns.json:
            print(json.dumps({"agents": names}, indent=2))
        else:
            print("\n".join(names))
        return 0

    args_obj = json.loads((repo_root / ns.args).read_text(encoding="utf-8"))
    if ns.command == "profile":
        return _profile(repo_root, ns, args_obj)
    workload = args_obj["workload_name"]
    run_id = ns.run_id or str(uuid.uuid4())
    runner = StrandsRunner(
        repo_root,
        region=ns.region,
        model_id=ns.model,
        dry_run=ns.dry_run,
        workload=workload,
        run_id=run_id,
    )
    driver = WorkflowDriver(
        workload,
        run_id,
        repo_root=repo_root,
        agent_backend=runner.invoke,
    )
    results = driver.run_build(
        build_default_tasks(args_obj),
        ontology=ns.ontology or bool(args_obj.get("ontology", {}).get("enabled")),
        review=not ns.no_review,
    )
    failed = [name for name, result in results.items() if not result.can_proceed]
    return 1 if failed else 0


def _profile(repo_root: Path, ns: argparse.Namespace, args_obj: dict) -> int:
    workload = str(args_obj.get("workload_name", ""))
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", workload):
        print("error: args.workload_name must match ^[a-z][a-z0-9_]{1,40}$")
        return 2
    if not (repo_root / "workloads" / workload).is_dir():
        print(f"error: workloads/{workload}/ does not exist; start the workload in the client first")
        return 2
    source = args_obj.get("source")
    if not source:
        print("error: args.source is required (the human-provided source details)")
        return 2
    runner = StrandsRunner(repo_root, region=ns.region, model_id=ns.model, dry_run=ns.dry_run,
                           workload=workload, run_id=ns.run_id or str(uuid.uuid4()))
    record = runner.profile(source, athena_output=ns.athena_output,
                            athena_workgroup=ns.athena_workgroup)
    print(json.dumps({"written": f"workloads/{workload}/run/source_profile.json",
                      "status": record["status"],
                      "columns": len(record["profile"].get("columns", []))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
