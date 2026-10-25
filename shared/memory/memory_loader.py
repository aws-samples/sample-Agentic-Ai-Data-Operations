"""
MemoryLoader — orchestrator-level memory management per pipeline run.

Called by the orchestrator before spawning each sub-agent.

Responsibilities:
1. Load relevant memory for each phase (via cheap Haiku side call)
2. Collect memory hints from sub-agent outputs
3. Flush accumulated hints to disk after all phases complete
"""

import re
from typing import Dict, List, Optional, Set

from shared.memory.workload_memory import WorkloadMemory
from shared.memory.find_relevant_memories import curate_relevant_memories


class MemoryLoader:
    """
    Per-run memory manager. Create one at pipeline start,
    use it across all phases, flush at the end.
    """

    def __init__(
        self,
        workload_name: str,
        bedrock_client=None,
        base_dir=None,
        region: str = "us-east-1",
    ):
        """
        Args:
            workload_name: e.g. "financial_portfolios"
            bedrock_client: boto3 bedrock-runtime client (lazy-init if None)
            base_dir: override workloads/ base directory (for testing)
            region: AWS region for lazy bedrock client init
        """
        self.workload_name = workload_name
        self._bedrock_client = bedrock_client
        self._region = region
        self.memory = WorkloadMemory(workload_name, base_dir=base_dir)
        self._surfaced_this_run: Set[str] = set()
        self._pending_hints: List[Dict[str, str]] = []

    @property
    def bedrock_client(self):
        """Lazy-initialize bedrock-runtime client."""
        if self._bedrock_client is None:
            import boto3
            self._bedrock_client = boto3.client(
                "bedrock-runtime", region_name=self._region
            )
        return self._bedrock_client

    def load_for_phase(self, phase_query: str) -> str:
        """
        Load relevant memory for a specific pipeline phase.

        Args:
            phase_query: Describes what this phase is doing, e.g.
                "Generate Bronze->Silver transformation scripts for financial_portfolios.
                 Source: CSV with columns ticker, pe_ratio, dividend_yield, market_cap."

        Returns:
            Formatted memory injection string ready to prepend to sub-agent prompt.
            Empty string if no relevant memory found.

        Side effects:
            Updates self._surfaced_this_run so the same files aren't re-loaded.
        """
        # Get relevant memory contents via cheap side call
        contents = curate_relevant_memories(
            query=phase_query,
            workload_memory=self.memory,
            bedrock_client=self.bedrock_client,
            already_surfaced=self._surfaced_this_run,
        )

        if not contents:
            # Fall back to just the ledger index (always useful)
            ledger = self.memory.read_ledger()
            if ledger:
                return f"## Memory for {self.workload_name}\n\n{ledger}"
            return ""

        # Track which files were surfaced (extract filenames from frontmatter)
        for content in contents:
            # Parse filename from content if possible
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    import yaml
                    try:
                        fm = yaml.safe_load(content[3:end])
                        if fm and "name" in fm:
                            # We track by the query that surfaced them
                            pass
                    except yaml.YAMLError:
                        pass

        # Build the full injection with ledger + selected content
        # Delegate to compose_injection for consistent formatting
        # But we need filenames — survey to find matches
        manifest = self.memory.survey()
        selected_names = []
        for m in manifest:
            if m["filename"] not in self._surfaced_this_run:
                try:
                    file_content = self.memory.recall(m["filename"])
                    if file_content in contents:
                        selected_names.append(m["filename"])
                        self._surfaced_this_run.add(m["filename"])
                except FileNotFoundError:
                    continue

        return self.memory.compose_injection(selected_names)

    def collect_hint(self, hint: Dict[str, str]) -> None:
        """
        Queue a memory hint from sub-agent output for later persistence.

        Called by orchestrator after parsing AgentOutput.memory_hints.

        Args:
            hint: {"type": "project|user|feedback|reference", "content": "..."}
        """
        if isinstance(hint, dict) and "type" in hint and "content" in hint:
            self._pending_hints.append(hint)

    def flush_hints_to_disk(self) -> int:
        """
        Write all queued memory hints to the workload memory directory.
        Called by orchestrator after all phases complete.

        Returns:
            Number of hints written.
        """
        if not self._pending_hints:
            return 0

        written = 0
        for i, hint in enumerate(self._pending_hints):
            mem_type = hint.get("type", "project")
            content = hint.get("content", "")
            if not content:
                continue

            # Generate a filename from the content
            slug = _slugify(content[:60])
            filename = f"hint_{slug}.md"
            name = content[:60].strip()
            description = content[:150].replace("\n", " ").strip()

            try:
                self.memory.inscribe(
                    filename=filename,
                    memory_type=mem_type,
                    name=name,
                    description=description,
                    content=content,
                )
                written += 1
            except ValueError:
                # Invalid memory type — skip silently
                continue

        self._pending_hints.clear()
        return written


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s_-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text[:50].rstrip("_")
