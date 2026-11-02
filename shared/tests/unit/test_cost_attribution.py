import json

import pytest

from shared.logging.agent_tracer import AgentTracer
from shared.requirements.capture import capture_event
from shared.requirements.auditor import append_user_turn
from shared.utils.cost_attribution import (
    CostAttribution,
    CostAttributionError,
    append_usage_event,
    summarize_events,
)


def _attribution() -> CostAttribution:
    return CostAttribution.from_dict(
        {
            "schema_version": "v1",
            "project": "orders_platform",
            "environment": "production",
            "cost_center": "data-platform",
            "owner": "analytics",
            "bedrock_inference_profile_arn": "arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/orders",
            "tags": {"team": "analytics"},
        }
    )


def test_requires_human_billing_dimensions():
    with pytest.raises(CostAttributionError, match="cost_center"):
        CostAttribution.from_dict(
            {
                "project": "orders_platform",
                "environment": "production",
                "owner": "analytics",
            }
        )


def test_emits_bedrock_tags_and_metadata_without_aws_reserved_keys():
    attribution = _attribution()

    tags = attribution.resource_tags(workload="customer_orders", agent="metadata")
    metadata = attribution.request_metadata(
        workload="customer_orders",
        run_id="run-1",
        agent="metadata",
        phase=4,
    )

    assert tags["adop:project"] == "orders_platform"
    assert tags["adop:workload"] == "customer_orders"
    assert tags["adop:agent"] == "metadata"
    assert all(not key.lower().startswith("aws:") for key in tags)
    assert metadata["adop_project"] == "orders_platform"
    assert metadata["adop_run_id"] == "run-1"


def test_records_and_aggregates_usage_by_project_workload_and_agent(tmp_path):
    attribution = _attribution()
    append_usage_event(
        tmp_path / "run",
        attribution=attribution,
        workload="customer_orders",
        run_id="run-1",
        agent="metadata",
        phase=4,
        usage={"inputTokens": 10, "outputTokens": 4},
        model_id="model-a",
    )
    append_usage_event(
        tmp_path / "run",
        attribution=attribution,
        workload="customer_orders",
        run_id="run-1",
        agent="quality",
        phase=4,
        usage={"input_tokens": 3, "output_tokens": 2},
        model_id="model-a",
        estimated_cost_usd=0.12,
    )

    records = [
        json.loads(line)
        for line in (tmp_path / "run" / "cost_events.jsonl").read_text().splitlines()
    ]
    summary = summarize_events(records)

    assert len(summary["groups"]) == 2
    assert summary["totals"]["total_tokens"] == 19
    quality = next(row for row in summary["groups"] if row["agent"] == "quality")
    assert quality["estimated_cost_usd"] == pytest.approx(0.12)


def test_trace_and_requirement_records_include_cost_dimensions(tmp_path):
    workload_dir = tmp_path / "workloads" / "customer_orders"
    (workload_dir / "config").mkdir(parents=True)
    (workload_dir / "run").mkdir()
    (workload_dir / "config" / "cost_attribution.yaml").write_text(
        "\n".join(
            [
                "schema_version: v1",
                "project: orders_platform",
                "environment: production",
                "cost_center: data-platform",
                "owner: analytics",
            ]
        )
        + "\n"
    )

    append_user_turn(
        workload_dir / "run",
        prompt="What is the primary key?",
        response="order_id",
        agent_name="orchestrator",
    )
    record = json.loads((workload_dir / "run" / "requirements.jsonl").read_text())
    assert record["project"] == "orders_platform"
    assert record["workload"] == "customer_orders"
    assert record["agent"] == "orchestrator"

    tracer = AgentTracer(
        "run-1",
        "customer_orders",
        output_path=str(workload_dir / "logs" / "trace.jsonl"),
        cost_attribution=_attribution(),
        cost_events_path=str(workload_dir / "run" / "cost_events.jsonl"),
    )
    tracer.operational_event("phase_start", agent_name="metadata", phase=4)
    event = tracer.events[-1]
    assert event["project"] == "orders_platform"
    assert event["workload_name"] == "customer_orders"
    assert event["agent_name"] == "metadata"


def test_client_hook_usage_is_recorded_for_the_active_workload(tmp_path):
    workload_dir = tmp_path / "workloads" / "customer_orders"
    (workload_dir / "config").mkdir(parents=True)
    (workload_dir / "run").mkdir()
    (workload_dir / "config" / "cost_attribution.yaml").write_text(
        "\n".join(
            [
                "schema_version: v1",
                "project: orders_platform",
                "environment: production",
                "cost_center: data-platform",
                "owner: analytics",
                "bedrock_inference_profile_arn: arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/orders",
            ]
        )
        + "\n"
    )
    (workload_dir / "run" / "context.json").write_text(
        json.dumps({"run_id": "run-hook-1"}) + "\n"
    )

    capture_event(
        {
            "workload_name": "customer_orders",
            "agent_name": "codex",
            "phase": 4,
            "modelId": "anthropic.claude",
            "usage": {"inputTokens": 7, "outputTokens": 5},
        },
        cwd=tmp_path,
    )

    event = json.loads(
        (workload_dir / "run" / "cost_events.jsonl").read_text().splitlines()[0]
    )
    assert event["project"] == "orders_platform"
    assert event["workload"] == "customer_orders"
    assert event["agent"] == "codex"
    assert event["total_tokens"] == 12
