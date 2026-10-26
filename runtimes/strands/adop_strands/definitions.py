"""Load the existing Amazon Q agent definitions as the Strands source format."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    prompt: str
    tools: tuple[str, ...] = ()
    allowed_paths: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class DefinitionLoader:
    """Resolve Q-compatible definitions relative to the repository root."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.directory = self.repo_root / ".amazonq" / "cli-agents"

    def load(self, name: str) -> AgentDefinition:
        path = self.directory / f"{name}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Strands agent definition not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        settings = data.get("toolsSettings", {}).get("fs_write", {})
        return AgentDefinition(
            name=str(data.get("name", name)),
            description=str(data.get("description", "")),
            prompt=str(data.get("prompt", "")),
            tools=tuple(str(item) for item in data.get("tools", [])),
            allowed_paths=tuple(str(item) for item in settings.get("allowedPaths", [])),
            resources=tuple(str(item) for item in data.get("resources", [])),
            metadata=data,
        )

    def names(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        return sorted(path.stem for path in self.directory.glob("adop-*.json"))

    def system_prompt(self, definition: AgentDefinition) -> str:
        parts = [definition.prompt.strip()]
        for resource in definition.resources:
            for path in self._resource_paths(resource):
                parts.append(
                    f"\n--- RESOURCE: {path.relative_to(self.repo_root)} ---\n"
                    f"{path.read_text(encoding='utf-8')}"
                )
        parts.append(
            "\n--- STRANDS RUNTIME CONTRACT ---\n"
            "You are running under the ADOP Strands runtime. Use only the supplied "
            "purpose-built tools. There is no generic shell tool. Use fs_read and "
            "fs_write for scoped files, run_pytest_gate for tests, and "
            "render_artifact for renderer-owned files. Return a complete AgentOutput "
            "with at least one populated decisions entry."
        )
        return "\n".join(part for part in parts if part)

    def _resource_paths(self, resource: str) -> Iterable[Path]:
        raw = resource.removeprefix("file://")
        candidate = self.repo_root / raw
        if any(char in raw for char in "*?["):
            yield from sorted(self.repo_root.glob(raw))
        elif candidate.is_file():
            yield candidate
