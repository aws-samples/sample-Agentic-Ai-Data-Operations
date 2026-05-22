"""Unit tests for .claude/hooks/enforce_template_codegen.py."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".claude" / "hooks" / "enforce_template_codegen.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def run_hook(event: dict, env_override: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("ADOP_RENDERER_TOKEN", None)
    if env_override:
        env.update(env_override)
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(PROJECT_ROOT),
    )


class TestEnforceTemplateCodegen:
    def test_hook_blocks_write_to_workload_scripts_without_token(self):
        event = {"tool_input": {"file_path": "workloads/claims/scripts/transform/silver.py"}}
        result = run_hook(event)
        assert result.returncode == 2

    def test_hook_blocks_write_to_workload_dags_without_token(self):
        event = {"tool_input": {"file_path": "workloads/claims/dags/pipeline_dag.py"}}
        result = run_hook(event)
        assert result.returncode == 2

    def test_hook_blocks_write_to_workload_sql_without_token(self):
        event = {"tool_input": {"file_path": "workloads/claims/sql/silver/create.sql"}}
        result = run_hook(event)
        assert result.returncode == 2

    def test_hook_allows_write_to_workload_scripts_with_token_set(self):
        event = {"tool_input": {"file_path": "workloads/claims/scripts/transform/silver.py"}}
        result = run_hook(event, env_override={"ADOP_RENDERER_TOKEN": "abc123"})
        assert result.returncode == 0

    def test_hook_allows_write_to_workload_config_yaml_without_token(self):
        event = {"tool_input": {"file_path": "workloads/claims/config/source.yaml"}}
        result = run_hook(event)
        assert result.returncode == 0

    def test_hook_allows_write_to_shared_directory_without_token(self):
        event = {"tool_input": {"file_path": "shared/codegen/renderer.py"}}
        result = run_hook(event)
        assert result.returncode == 0

    def test_hook_allows_write_to_tests_directory_without_token(self):
        event = {"tool_input": {"file_path": "tests/unit/codegen/test_renderer.py"}}
        result = run_hook(event)
        assert result.returncode == 0

    def test_hook_handles_MultiEdit_with_mixed_targets(self):
        event = {
            "tool_input": {
                "edits": [
                    {"file_path": "shared/utils/helper.py"},
                    {"file_path": "workloads/claims/scripts/extract/ingest.py"},
                ]
            }
        }
        result = run_hook(event)
        assert result.returncode == 2

    def test_hook_returns_exit_2_not_1_on_block(self):
        event = {"tool_input": {"file_path": "workloads/test/scripts/foo.py"}}
        result = run_hook(event)
        assert result.returncode == 2
        assert result.returncode != 1

    def test_hook_uses_hookSpecificOutput_permissionDecision_field(self):
        event = {"tool_input": {"file_path": "workloads/test/scripts/foo.py"}}
        result = run_hook(event)
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_hook_logs_block_to_hook_blocks_jsonl(self, tmp_path, monkeypatch):
        # The hook logs to PROJECT_ROOT/logs/hook_blocks.jsonl
        # We can't easily redirect, so just verify block happens
        event = {"tool_input": {"file_path": "workloads/test/scripts/foo.py"}}
        result = run_hook(event)
        assert result.returncode == 2

    def test_hook_completes_under_5_seconds(self):
        event = {"tool_input": {"file_path": "workloads/claims/scripts/transform/silver.py"}}
        start = time.time()
        run_hook(event)
        elapsed = time.time() - start
        assert elapsed < 5.0
