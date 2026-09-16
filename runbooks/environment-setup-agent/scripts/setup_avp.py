#!/usr/bin/env python3
"""Setup Amazon Verified Permissions policy store and sync Cedar policies.

Creates a policy store, uploads the Cedar schema, and syncs all .cedar policy
files from shared/policies/ into AVP.

Usage:
    python3 shared/scripts/setup_avp.py [--dry-run]

Environment:
    AWS_REGION      (default: us-east-1)
    AWS_PROFILE     (optional)
"""

import argparse
import json
import sys
from pathlib import Path

POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"
GUARDRAILS_DIR = POLICIES_DIR / "guardrails"
AGENT_AUTH_DIR = POLICIES_DIR / "agent_authorization"
SCHEMA_FILE = POLICIES_DIR / "schema.cedarschema"


def get_client():
    import boto3
    return boto3.client("verifiedpermissions")


def create_policy_store(client, dry_run: bool) -> str:
    """Create a new AVP policy store or return existing one."""
    if dry_run:
        print("[DRY-RUN] Would create policy store: DataOnboardingPolicies")
        return "dry-run-policy-store-id"

    response = client.create_policy_store(
        validationSettings={"mode": "STRICT"},
        description="Agentic Data Onboarding Platform - Cedar policies",
    )
    store_id = response["policyStoreId"]
    print(f"Created policy store: {store_id}")
    return store_id


def upload_schema(client, store_id: str, dry_run: bool):
    """Upload the Cedar schema to the policy store."""
    if not SCHEMA_FILE.is_file():
        print(f"ERROR: Schema file not found: {SCHEMA_FILE}")
        sys.exit(1)

    schema_text = SCHEMA_FILE.read_text()

    if dry_run:
        print(f"[DRY-RUN] Would upload schema ({len(schema_text)} chars) to {store_id}")
        return

    client.put_schema(
        policyStoreId=store_id,
        definition={"cedarJson": schema_text},
    )
    print(f"Uploaded schema to {store_id} ({len(schema_text)} chars)")


def sync_policies(client, store_id: str, dry_run: bool):
    """Upload all .cedar policy files to AVP."""
    policy_files = []
    for policy_dir in [GUARDRAILS_DIR, AGENT_AUTH_DIR]:
        if policy_dir.is_dir():
            policy_files.extend(sorted(policy_dir.glob("*.cedar")))

    print(f"Found {len(policy_files)} policy files to sync")

    for cedar_file in policy_files:
        policy_text = cedar_file.read_text()
        description = cedar_file.stem.replace("_", " ").title()

        if dry_run:
            print(f"  [DRY-RUN] Would create policy: {cedar_file.name} ({len(policy_text)} chars)")
            continue

        try:
            response = client.create_policy(
                policyStoreId=store_id,
                definition={
                    "static": {
                        "description": description,
                        "statement": policy_text,
                    }
                },
            )
            policy_id = response["policyId"]
            print(f"  Created policy: {cedar_file.name} -> {policy_id}")
        except Exception as exc:
            print(f"  ERROR creating policy {cedar_file.name}: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Setup AVP policy store")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY-RUN MODE ===\n")
        client = None
    else:
        client = get_client()

    store_id = create_policy_store(client, args.dry_run)
    upload_schema(client, store_id, args.dry_run)
    sync_policies(client, store_id, args.dry_run)

    print(f"\nPolicy store ID: {store_id}")
    print("Set AVP_POLICY_STORE_ID environment variable to use AVP mode:")
    print(f"  export AVP_POLICY_STORE_ID={store_id}")
    print(f"  export CEDAR_MODE=avp")


if __name__ == "__main__":
    main()
