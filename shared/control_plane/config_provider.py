"""Approved configuration snapshots for future ADOP runs.

The orchestrator can use this provider without knowing whether configuration
comes from Git files or the control-plane store. The current run context stays
immutable; callers select a snapshot before a new run begins.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from .store import _from_dynamo


@dataclass(frozen=True)
class ConfigSnapshot:
    workload_name: str
    version: str
    effective_hash: str
    contracts: dict[str, Any]
    source: str


class ConfigProvider(Protocol):
    def get_current(self, workload_name: str) -> ConfigSnapshot: ...

    def get_version(self, workload_name: str, version: str) -> ConfigSnapshot: ...


class FileConfigProvider:
    """Reads the existing workload config files without changing behavior."""

    CONFIG_FILES = (
        "source.yaml",
        "target.yaml",
        "bronze.yaml",
        "silver.yaml",
        "gold.yaml",
        "quality_rules.yaml",
        "schedule.yaml",
    )

    def __init__(self, repository_root: str | Path):
        self.root = Path(repository_root)

    def get_current(self, workload_name: str) -> ConfigSnapshot:
        workload_dir = self.root / "workloads" / workload_name
        if not workload_dir.is_dir():
            raise KeyError(workload_name)
        contracts: dict[str, Any] = {}
        for filename in self.CONFIG_FILES:
            path = workload_dir / "config" / filename
            if path.exists():
                contracts[path.stem] = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not contracts:
            raise KeyError(f"No config files for workload {workload_name}")
        canonical = json.dumps(contracts, sort_keys=True, separators=(",", ":"))
        return ConfigSnapshot(
            workload_name=workload_name,
            version="git-working-tree",
            effective_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            contracts=contracts,
            source="git",
        )

    def get_version(self, workload_name: str, version: str) -> ConfigSnapshot:
        if version != "git-working-tree":
            raise KeyError(f"File provider has no version {version}")
        return self.get_current(workload_name)


class DynamoConfigProvider:
    """Reads immutable approved snapshots from the control-plane table.

    This is intentionally separate from proposal storage. A deployment should
    provision the CURRENT pointer and snapshot records before enabling this
    provider for a workload.
    """

    def __init__(self, table_name: str, region_name: str | None = None):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("DynamoConfigProvider requires boto3") from exc
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def get_current(self, workload_name: str) -> ConfigSnapshot:
        response = self.table.get_item(
            Key={"PK": f"WORKLOAD#{workload_name}", "SK": "CURRENT"}
        )
        pointer = response.get("Item")
        if not pointer:
            raise KeyError(workload_name)
        return self.get_version(workload_name, str(pointer["version"]))

    def get_version(self, workload_name: str, version: str) -> ConfigSnapshot:
        response = self.table.get_item(
            Key={"PK": f"WORKLOAD#{workload_name}", "SK": f"CONFIG#{version}"}
        )
        item = response.get("Item")
        if not item:
            raise KeyError(f"{workload_name}:{version}")
        return ConfigSnapshot(
            workload_name=workload_name,
            version=version,
            effective_hash=str(item["effective_hash"]),
            contracts=_from_dynamo(dict(item.get("contracts", {}))),
            source="dynamodb",
        )
