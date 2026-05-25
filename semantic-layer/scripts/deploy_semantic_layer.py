#!/usr/bin/env python3
"""Deploy the ADOP semantic layer end-to-end.

Order of operations:
  1. Deploy Storage + OpenSearch in parallel (no Docker needed)
  2. Zip ontop_config -> S3 -> trigger CodeBuild to build + push Ontop image
  3. Deploy SparqlVirtualization stack (uses ECR image from step 2)
  4. Push ontology + R2RML to S3 config bucket
  5. Trigger Ontop ECS rolling restart so it picks up new TTL files
  6. Invoke Neptune Loader Lambda to load ontology into Neptune
  7. Index ontology slices into OpenSearch

Usage: python deploy_semantic_layer.py
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_REGION", "us-west-2")
ACCOUNT = boto3.client("sts").get_caller_identity()["Account"]

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_LAYER_DIR = REPO_ROOT / "semantic-layer"
INFRA_DIR = SEMANTIC_LAYER_DIR / "infra"
ONTOP_CONFIG_DIR = SEMANTIC_LAYER_DIR / "ontop_config"

STORAGE_STACK = "AdopSemanticLayerStorage"
OPENSEARCH_STACK = "AdopSemanticLayerOpenSearch"
SPARQL_STACK = "AdopSemanticLayerSparql"


def run(cmd: list[str], cwd: Path | None = None, **kw) -> subprocess.CompletedProcess:
    print(f"+ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=True, **kw)


def cdk_deploy(stacks: list[str], concurrency: int = 1) -> None:
    # Pick the right binary for the host OS (Windows uses cdk.cmd, Unix uses cdk)
    if os.name == "nt":
        cdk_bin = INFRA_DIR / "node_modules" / ".bin" / "cdk.cmd"
    else:
        cdk_bin = INFRA_DIR / "node_modules" / ".bin" / "cdk"
    cmd = [
        str(cdk_bin),
        "deploy",
        *stacks,
        "--concurrency",
        str(concurrency),
        "--require-approval",
        "never",
        "--no-rollback",
    ]
    env = os.environ.copy()
    env["CDK_DEFAULT_ACCOUNT"] = ACCOUNT
    env["CDK_DEFAULT_REGION"] = REGION
    env["AWS_REGION"] = REGION
    subprocess.run(cmd, cwd=INFRA_DIR, env=env, check=True, shell=(os.name == "nt"))


def stack_outputs(stack_name: str) -> dict[str, str]:
    cf = boto3.client("cloudformation", region_name=REGION)
    desc = cf.describe_stacks(StackName=stack_name)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in desc.get("Outputs", [])}


def zip_ontop_source(config_bucket: str) -> str:
    """Zip ontop_config and upload to S3 for CodeBuild."""
    print(f"\n=== Zipping ontop_config -> s3://{config_bucket}/codebuild/ontop-source.zip ===")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in ONTOP_CONFIG_DIR.iterdir():
            if p.is_file():
                zf.write(p, arcname=f"ontop_config/{p.name}")
    buf.seek(0)
    s3 = boto3.client("s3", region_name=REGION)
    s3.put_object(
        Bucket=config_bucket,
        Key="codebuild/ontop-source.zip",
        Body=buf.read(),
    )
    return "codebuild/ontop-source.zip"


def trigger_codebuild(project_name: str) -> str:
    """Start CodeBuild and wait for completion."""
    print(f"\n=== Triggering CodeBuild project {project_name} ===")
    cb = boto3.client("codebuild", region_name=REGION)
    build_id = cb.start_build(projectName=project_name)["build"]["id"]
    print(f"build_id = {build_id}")

    while True:
        time.sleep(15)
        b = cb.batch_get_builds(ids=[build_id])["builds"][0]
        status = b["buildStatus"]
        phase = b.get("currentPhase")
        print(f"  status={status}, phase={phase}")
        if status == "SUCCEEDED":
            return build_id
        if status in ("FAILED", "FAULT", "TIMED_OUT", "STOPPED"):
            log = b.get("logs", {})
            print(f"BUILD FAILED. Logs: {log.get('deepLink')}")
            raise SystemExit(1)


def upload_artifacts(config_bucket: str) -> None:
    """Push ontology.ttl + r2rml-mappings.ttl to S3 config bucket."""
    print(f"\n=== Uploading ontology + R2RML to s3://{config_bucket}/ontology/ ===")
    s3 = boto3.client("s3", region_name=REGION)
    for fname in ("ontology.ttl", "r2rml-mappings.ttl"):
        src = SEMANTIC_LAYER_DIR / fname
        s3.put_object(
            Bucket=config_bucket,
            Key=f"ontology/{fname}",
            Body=src.read_bytes(),
        )
        print(f"  uploaded ontology/{fname} ({src.stat().st_size} bytes)")


def restart_ontop_service() -> None:
    """Force ECS to redeploy Ontop so it picks up the new S3 TTL files."""
    print("\n=== Triggering Ontop ECS rolling restart ===")
    ecs = boto3.client("ecs", region_name=REGION)
    # Find the cluster + service
    clusters = ecs.list_clusters()["clusterArns"]
    target_cluster = None
    target_service = None
    for c in clusters:
        services = ecs.list_services(cluster=c)["serviceArns"]
        for s in services:
            if "OntopService" in s:
                target_cluster = c
                target_service = s
                break
        if target_service:
            break
    if not target_service:
        print("  No OntopService found; skipping restart.")
        return
    ecs.update_service(
        cluster=target_cluster,
        service=target_service,
        forceNewDeployment=True,
    )
    print(f"  forceNewDeployment requested on {target_service}")


def invoke_neptune_loader(loader_fn_name: str, config_bucket: str) -> None:
    """Trigger ontology load into Neptune via the loader Lambda."""
    print(f"\n=== Invoking Neptune Loader Lambda {loader_fn_name} ===")
    lam = boto3.client("lambda", region_name=REGION)
    payload = {
        "action": "load",
        "source": f"s3://{config_bucket}/ontology/ontology.ttl",
    }
    resp = lam.invoke(
        FunctionName=loader_fn_name,
        Payload=json.dumps(payload).encode(),
    )
    body = resp["Payload"].read().decode()
    print(f"  loader response: {body[:500]}")


def main() -> int:
    print(f"Account={ACCOUNT} Region={REGION}")
    print(f"Repo root: {REPO_ROOT}")

    # Step 1: Deploy Storage + OpenSearch in parallel (CDK dependency-free)
    print("\n=== STEP 1: Deploy Storage + OpenSearch (parallel) ===")
    cdk_deploy([STORAGE_STACK, OPENSEARCH_STACK], concurrency=2)

    storage_out = stack_outputs(STORAGE_STACK)
    config_bucket = storage_out["ConfigBucketName"]
    build_project = storage_out["OntopBuildProjectName"]

    # Step 2: Zip ontop source -> S3 -> trigger CodeBuild
    print("\n=== STEP 2: Build Ontop image via CodeBuild ===")
    zip_ontop_source(config_bucket)
    trigger_codebuild(build_project)

    # Step 3: Deploy SparqlVirtualization (consumes ECR image)
    print("\n=== STEP 3: Deploy SparqlVirtualization ===")
    cdk_deploy([SPARQL_STACK], concurrency=1)

    sparql_out = stack_outputs(SPARQL_STACK)
    loader_fn = sparql_out["LoaderFunctionName"]

    # Step 4: Push ontology + R2RML to S3
    upload_artifacts(config_bucket)

    # Step 5: Force Ontop restart so it picks up new TTL
    restart_ontop_service()

    # Step 6: Load ontology into Neptune
    invoke_neptune_loader(loader_fn, config_bucket)

    print("\n=== DEPLOY COMPLETE ===")
    print(f"Neptune endpoint: {sparql_out['NeptuneSparqlEndpoint']}")
    print(f"Ontop endpoint: {sparql_out['OntopSparqlEndpoint']}")
    print(f"OBQC ARN: {sparql_out['ObqcFunctionArn']}")
    print(f"Loader Fn: {loader_fn}")
    print(f"OpenSearch: {stack_outputs(OPENSEARCH_STACK).get('CollectionEndpoint')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
