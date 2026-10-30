import json
import shutil
from pathlib import Path

import pytest

from shared.codegen.contract_resolver import (
    ContractPolicyError,
    resolve_effective_policy,
    validate_zone_contract,
)
from shared.codegen.spec_loader import load_spec


ROOT = Path(__file__).resolve().parents[3]


def _policy_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "contracts" / "policies" / "organization").mkdir(parents=True)
    (root / "contracts" / "policies" / "domains").mkdir()
    (root / "contracts" / "policies" / "projects").mkdir()
    shutil.copy(
        ROOT / "contracts/policies/organization/default.yaml",
        root / "contracts/policies/organization/default.yaml",
    )
    shutil.copy(
        ROOT / "contracts/policies/zone_policy.schema.json",
        root / "contracts/policies/zone_policy.schema.json",
    )
    (root / "workloads" / "orders" / "run").mkdir(parents=True)
    return root


def test_default_policy_applies_to_all_workloads():
    policy = resolve_effective_policy(ROOT / "workloads/customer_orders")

    assert policy["zones"]["bronze"]["mutability"] == "immutable"
    assert policy["zones"]["silver"]["minimum_quality_threshold"] == 0.8
    assert policy["zones"]["gold"]["minimum_quality_threshold"] == 0.95
    assert len(policy["effective_hash"]) == 64


def test_domain_and_run_overrides_only_tighten(tmp_path: Path):
    root = _policy_root(tmp_path)
    (root / "contracts/policies/domains/sales.yaml").write_text(
        """
contract_id: adop.domain.sales
version: "1.0.0"
scope: domain
zones:
  silver:
    minimum_quality_threshold: 0.90
""",
        encoding="utf-8",
    )
    (root / "workloads/orders/run/context.json").write_text(
        json.dumps(
            {
                "scope": {"domain": "sales"},
                "human_answers": {
                    "contract_overrides": {
                        "zones": {"gold": {"minimum_quality_threshold": 0.98}}
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    policy = resolve_effective_policy(root / "workloads/orders")

    assert policy["zones"]["silver"]["minimum_quality_threshold"] == 0.9
    assert policy["zones"]["gold"]["minimum_quality_threshold"] == 0.98


def test_weaker_override_is_rejected(tmp_path: Path):
    root = _policy_root(tmp_path)
    (root / "workloads/orders/run/context.json").write_text(
        json.dumps(
            {
                "human_answers": {
                    "contract_overrides": {
                        "zones": {"gold": {"minimum_quality_threshold": 0.90}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractPolicyError, match="lowers"):
        resolve_effective_policy(root / "workloads/orders")


def test_zone_validation_enforces_organization_quality_floor():
    errors = validate_zone_contract(
        {
            "iceberg_database": "orders",
            "iceberg_table": "gold_orders",
            "quality_threshold": 0.90,
        },
        "gold",
        ROOT / "workloads/customer_orders",
    )

    assert any("at least 0.95" in error for error in errors)


def test_target_profile_is_a_separate_contract(tmp_path: Path):
    target = tmp_path / "target.yaml"
    target.write_text(
        """
dataset_name: orders
version: "1.0.0"
target:
  type: snowflake
  write_mode: merge
  database: ANALYTICS
  schema: PUBLIC
  table: ORDERS
""",
        encoding="utf-8",
    )

    spec, _ = load_spec(target, "target")

    assert spec["target"]["type"] == "snowflake"
