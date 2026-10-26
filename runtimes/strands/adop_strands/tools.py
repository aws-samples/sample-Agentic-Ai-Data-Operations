"""Restricted purpose-built tools exposed to Strands agents."""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from shared.codegen.renderer import render
from shared.codegen.spec_loader import load_spec


PROTECTED = ("scripts", "dags", "sql")


def _relative(root: Path, raw: str) -> tuple[Path, str]:
    path = Path(raw)
    if path.is_absolute():
        raise ValueError("absolute paths are not allowed")
    resolved = (root / path).resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("path escapes the repository root") from exc
    return resolved, relative.as_posix()


def _allowed(relative: str, patterns: tuple[str, ...]) -> bool:
    return any(
        fnmatch.fnmatch(relative, pattern)
        or Path(relative).match(pattern)
        for pattern in patterns
    )


# Run state only the orchestrator may write: it records human answers and the
# discovery gate, which no sub-agent can have collected.
ORCHESTRATOR_OWNED = (
    "workloads/*/run/context.json",
    "workloads/*/run/requirements.jsonl",
    "workloads/*/run/*discovery_complete*",
    "workloads/*/.discovery_complete",
)


def check_write(relative: str, patterns: tuple[str, ...]) -> None:
    """Raise PermissionError unless a sub-agent may write this repo-relative path."""
    if not _allowed(relative, patterns):
        raise PermissionError(f"path is outside the agent allowlist: {relative}")
    if any(fnmatch.fnmatch(relative, owned) for owned in ORCHESTRATOR_OWNED):
        raise PermissionError(f"orchestrator-owned run state is read-only: {relative}")
    if relative.startswith("workloads/") and any(
        f"/{zone}/" in f"/{relative}" for zone in PROTECTED
    ):
        raise PermissionError(
            f"direct writes to renderer-owned artifacts are blocked: {relative}"
        )
    if relative.endswith(".py") and not fnmatch.fnmatch(relative, "workloads/*/tests/*"):
        raise PermissionError(
            f"executable code must come from render_artifact, not fs_write: {relative}"
        )


def make_tools(
    repo_root: Path,
    allowed_paths: tuple[str, ...],
    allowed_tools: tuple[str, ...] = ("fs_read", "fs_write", "run_pytest_gate", "render_artifact"),
) -> list[Any]:
    """Create tools bound to one agent's repository scope."""

    try:
        from strands import tool
    except ImportError as exc:  # pragma: no cover - exercised by CLI guard
        raise RuntimeError(
            "Strands is not installed. Install the optional 'strands' extra."
        ) from exc

    root = repo_root.resolve()
    patterns = allowed_paths or ("workloads/**", "logs/**")

    @tool(name="fs_read")
    def fs_read(path: str) -> str:
        """Read a UTF-8 text file within the repository."""
        resolved, _ = _relative(root, path)
        if not resolved.is_file():
            raise FileNotFoundError(path)
        return resolved.read_text(encoding="utf-8")

    @tool(name="fs_write")
    def fs_write(path: str, file_text: str) -> str:
        """Write a scoped text file, excluding renderer-owned artifacts."""
        resolved, relative = _relative(root, path)
        check_write(relative, patterns)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(file_text, encoding="utf-8")
        return relative

    @tool(name="run_pytest_gate")
    def run_pytest_gate(selector: str) -> dict[str, Any]:
        """Run pytest for a repository-relative selector; the exit code is authoritative."""
        _, relative = _relative(root, selector)
        if not (relative.startswith("workloads/") or relative.startswith("shared/")):
            raise PermissionError("pytest selector must target workloads/ or shared/")
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", relative, "-q"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "output_tail": (completed.stdout + completed.stderr)[-2000:],
        }

    @tool(name="render_artifact")
    def render_artifact(
        spec_path: str,
        spec_type: str,
        template_id: str,
        output_path: str,
        template_version: str = "1.0.0",
        run_started_at: str = "",
    ) -> dict[str, str]:
        """Validate and render one artifact through ADOP's deterministic renderer."""
        spec_file, _ = _relative(root, spec_path)
        output_file, output_relative = _relative(root, output_path)
        if not output_relative.startswith("workloads/"):
            raise PermissionError("render output must be under workloads/")
        if not (
            output_relative.startswith("workloads/")
            and any(f"/{zone}/" in f"/{output_relative}" for zone in PROTECTED)
        ):
            raise PermissionError("render output must target scripts/, dags/, or sql/")
        spec, spec_hash = load_spec(spec_file, spec_type)
        _, artifact_hash = render(
            spec=spec,
            spec_hash=spec_hash,
            template_id=template_id,
            template_version=template_version,
            output_path=output_file,
            run_started_at=run_started_at or "1970-01-01T00:00:00+00:00",
        )
        return {"path": output_relative, "spec_hash": spec_hash, "artifact_hash": artifact_hash}

    available = {
        "fs_read": fs_read,
        "fs_write": fs_write,
        "run_pytest_gate": run_pytest_gate,
        "render_artifact": render_artifact,
    }
    return [available[name] for name in allowed_tools if name in available]
