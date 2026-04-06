"""
Post-run memory extractor.

Runs after every complete pipeline phase to extract durable facts
and write them to the workload's memory directory.

Two modes:
- Direct call: distill_run_insights() for local/development use
- Lambda handler: lambda_handler() triggered by EventBridge after run completes
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.memory.workload_memory import WorkloadMemory, EXCLUSION_GUIDANCE

logger = logging.getLogger(__name__)


# Minimum number of agent decisions before LLM extraction is worthwhile.
MIN_DECISIONS_FOR_DISTILLATION = 3


# Extraction prompt — instructs LLM to identify reusable learnings from a run
DISTILLATION_PROMPT = """You are reviewing a completed data pipeline run.

WORKLOAD: {workload_name}
AGENT: {agent_name}
STATUS: {status}

Review the agent decisions below. Extract durable facts worth
remembering for FUTURE runs of this workload.

Follow the 4-type taxonomy:
- type: user       -> operator preferences, tolerance settings, preferred output formats
- type: feedback   -> explicit corrections, patterns that were wrong
- type: project    -> schema facts, PK choices, known data quirks, zone configs
- type: reference  -> S3 paths, Glue DB names, LakeFormation tags, MWAA env names

{exclusion_guidance}

For each memory worth saving, call the distill_memories tool.

Agent decisions from this run:
{decisions_json}
"""


# Tool schema for forced structured output from the extraction call
DISTILLATION_TOOL = {
    "toolSpec": {
        "name": "distill_memories",
        "description": "Save extracted memories from this pipeline run.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "memories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": ["user", "feedback", "project", "reference"],
                                },
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["filename", "type", "name", "description", "content"],
                        },
                    }
                },
                "required": ["memories"],
            }
        },
    }
}


DEFAULT_MODEL_ID = "anthropic.claude-haiku-4-5-20251001"


def distill_run_insights(
    workload_name: str,
    agent_output: Dict[str, Any],
    bedrock_client,
    model_id: str = DEFAULT_MODEL_ID,
    base_dir: Optional[Path] = None,
) -> int:
    """
    Extract and save memories from a completed pipeline run.

    Processes two sources:
    1. memory_hints from AgentOutput — saved directly (no LLM needed)
    2. decisions from AgentOutput — distilled via cheap Bedrock call

    Args:
        workload_name: e.g. "financial_portfolios"
        agent_output: Serialized AgentOutput dict (or AgentOutput.to_dict() output)
        bedrock_client: boto3 bedrock-runtime client
        model_id: cheap model for extraction
        base_dir: override workloads/ base directory (for testing)

    Returns:
        Number of memories saved (0 if skipped due to MIN_DECISIONS check)
    """
    memory = WorkloadMemory(workload_name, base_dir=base_dir)
    saved_count = 0

    # Step 1: Process memory_hints directly (no LLM call)
    hints = agent_output.get("memory_hints", [])
    for hint in hints:
        mem_type = hint.get("type", "project")
        content = hint.get("content", "")
        if not content:
            continue
        if mem_type not in {"user", "feedback", "project", "reference"}:
            continue

        slug = _slugify(content[:60])
        filename = f"hint_{slug}.md"
        try:
            memory.inscribe(
                filename=filename,
                memory_type=mem_type,
                name=content[:60].strip(),
                description=content[:150].replace("\n", " ").strip(),
                content=content,
            )
            saved_count += 1
        except (ValueError, OSError) as exc:
            logger.warning("Failed to save memory hint: %s", exc)

    # Step 2: Check if enough decisions for LLM extraction
    decisions = agent_output.get("decisions", [])
    if len(decisions) < MIN_DECISIONS_FOR_DISTILLATION:
        logger.info(
            "Only %d decisions (need %d) — skipping LLM extraction",
            len(decisions),
            MIN_DECISIONS_FOR_DISTILLATION,
        )
        return saved_count

    # Step 3: Bedrock call to distill durable insights from decisions
    prompt = DISTILLATION_PROMPT.format(
        workload_name=workload_name,
        agent_name=agent_output.get("agent_name", "unknown"),
        status=agent_output.get("status", "unknown"),
        exclusion_guidance=EXCLUSION_GUIDANCE,
        decisions_json=json.dumps(decisions, indent=2, default=str),
    )

    try:
        response = bedrock_client.converse(
            modelId=model_id,
            system=[{"text": "You are a memory extraction agent."}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            toolConfig={
                "tools": [DISTILLATION_TOOL],
                "toolChoice": {"tool": {"name": "distill_memories"}},
            },
        )
    except Exception as exc:
        logger.warning("Bedrock extraction call failed: %s", exc)
        return saved_count

    # Step 4: Parse and save extracted memories
    extracted = _parse_distilled_memories(response)
    for mem in extracted:
        mem_type = mem.get("type", "project")
        if mem_type not in {"user", "feedback", "project", "reference"}:
            logger.warning("Invalid memory type from LLM: %s — skipping", mem_type)
            continue
        try:
            memory.inscribe(
                filename=mem.get("filename", "extracted.md"),
                memory_type=mem_type,
                name=mem.get("name", "Extracted insight"),
                description=mem.get("description", "No description"),
                content=mem.get("content", ""),
            )
            saved_count += 1
        except (ValueError, OSError) as exc:
            logger.warning("Failed to save extracted memory: %s", exc)

    return saved_count


def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda handler — triggered by EventBridge after pipeline run completes.

    Event format:
    {
        "workload_name": "financial_portfolios",
        "run_id": "run-2026-04-06-abc123",
        "agent_outputs": [...]  // list of serialized AgentOutput dicts
    }
    """
    import boto3

    workload_name = event.get("workload_name")
    if not workload_name:
        return {"statusCode": 400, "error": "Missing workload_name"}

    agent_outputs = event.get("agent_outputs", [])
    if not agent_outputs:
        return {"statusCode": 200, "memories_saved": 0, "message": "No agent outputs"}

    bedrock_client = boto3.client("bedrock-runtime")
    total_saved = 0

    for output in agent_outputs:
        count = distill_run_insights(
            workload_name=workload_name,
            agent_output=output,
            bedrock_client=bedrock_client,
        )
        total_saved += count

    return {
        "statusCode": 200,
        "memories_saved": total_saved,
        "workloads_processed": 1,
    }


def _parse_distilled_memories(response: dict) -> List[Dict[str, str]]:
    """Extract memories from a Bedrock converse() response with tool_use."""
    try:
        content_blocks = response["output"]["message"]["content"]
        for block in content_blocks:
            if "toolUse" in block:
                tool_input = block["toolUse"].get("input", {})
                return tool_input.get("memories", [])
    except (KeyError, TypeError, IndexError):
        logger.warning("Could not parse extraction response")
    return []


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s_-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text[:50].rstrip("_")
