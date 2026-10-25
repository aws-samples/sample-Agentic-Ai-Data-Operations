"""
Find memories relevant to a given agent query.

Uses a cheap side Bedrock call (Haiku) to select up to 5 relevant
memory files from the manifest — does NOT load full file contents
for the selection step, only frontmatter (filename + description).
"""

import logging
from typing import List, Optional, Set

from shared.memory.workload_memory import WorkloadMemory

logger = logging.getLogger(__name__)


# System prompt for the side selection call
CURATOR_SYSTEM_PROMPT = (
    "You are selecting memories that will be useful to the Data Onboarding Agent "
    "as it processes a pipeline phase for a specific workload. You will be given "
    "the current phase query and a list of available memory files with their "
    "filenames and descriptions.\n\n"
    "Return a list of filenames for the memories that will clearly be useful to "
    "the agent as it processes the current query (up to 5). Only include memories "
    "that you are certain will be helpful based on their name and description.\n"
    "- If you are unsure if a memory will be useful, do not include it. "
    "Be selective and discerning.\n"
    "- If no memories would clearly be useful, return an empty list.\n"
    "- Do NOT select memories that are generic boilerplate — only select "
    "workload-specific facts."
)


# Tool schema forcing structured output from the side call
CURATOR_TOOL = {
    "toolSpec": {
        "name": "curate_memory_files",
        "description": "Select the memory files relevant to the current query.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "selected_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of memory filenames to load (up to 5)",
                    }
                },
                "required": ["selected_files"],
            }
        },
    }
}


DEFAULT_MODEL_ID = "anthropic.claude-haiku-4-5-20251001"
MAX_CURATED = 5


def curate_relevant_memories(
    query: str,
    workload_memory: WorkloadMemory,
    bedrock_client,
    model_id: str = DEFAULT_MODEL_ID,
    max_memories: int = MAX_CURATED,
    already_surfaced: Optional[Set[str]] = None,
) -> List[str]:
    """
    Select and load memory files relevant to the current agent query.

    Args:
        query: The current phase prompt, e.g. "Generate quality rules for
               financial_portfolios. Source: CSV with columns ticker, pe_ratio..."
        workload_memory: WorkloadMemory instance for this workload
        bedrock_client: boto3 bedrock-runtime client
        model_id: cheap model for side call (Haiku default)
        max_memories: max files to return
        already_surfaced: set of filenames already loaded this session

    Returns:
        List of full memory file contents (ready to inject into prompt).
        Empty list if no relevant memories or no memory exists.
    """
    if already_surfaced is None:
        already_surfaced = set()

    # Step 1: Get manifest (frontmatter only, no content)
    manifest = workload_memory.survey()
    if not manifest:
        return []

    # Step 2: Filter out already-surfaced files
    candidates = [m for m in manifest if m["filename"] not in already_surfaced]
    if not candidates:
        return []

    # Step 3: Build the manifest string for the side call
    manifest_text = "Available memory files:\n"
    for m in candidates:
        manifest_text += f"- {m['filename']} — {m.get('description', 'no description')}\n"

    user_message = (
        f"Current task: {query}\n\n"
        f"Workload: {workload_memory.workload_name}\n\n"
        f"{manifest_text}\n"
        f"Select up to {max_memories} files that are relevant to this task."
    )

    # Step 4: Side Bedrock call with forced tool_choice
    try:
        response = bedrock_client.converse(
            modelId=model_id,
            system=[{"text": CURATOR_SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            toolConfig={
                "tools": [CURATOR_TOOL],
                "toolChoice": {"tool": {"name": "curate_memory_files"}},
            },
        )
    except Exception as exc:
        logger.warning("Bedrock side call failed for memory selection: %s", exc)
        return []

    # Step 5: Parse selected filenames from tool_use response
    selected_filenames = _extract_filenames_from_response(response)

    # Step 6: Filter to valid filenames and enforce limit
    valid_names = {m["filename"] for m in candidates}
    selected_filenames = [f for f in selected_filenames if f in valid_names]
    selected_filenames = selected_filenames[:max_memories]

    # Step 7: Load and return file contents
    contents = []
    for fname in selected_filenames:
        try:
            contents.append(workload_memory.recall(fname))
        except FileNotFoundError:
            continue

    return contents


def _extract_filenames_from_response(response: dict) -> List[str]:
    """Extract selected_files from a Bedrock converse() response with tool_use."""
    try:
        content_blocks = response["output"]["message"]["content"]
        for block in content_blocks:
            if "toolUse" in block:
                tool_input = block["toolUse"].get("input", {})
                return tool_input.get("selected_files", [])
    except (KeyError, TypeError, IndexError):
        logger.warning("Could not parse memory selection response")
    return []
