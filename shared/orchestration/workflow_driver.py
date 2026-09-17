"""External orchestration driver for ADOP on Amazon Q Developer CLI.

Replaces Claude Code's `Workflow`-tool DSL (phase/agent/parallel/pipeline).
It shells out to `q chat --agent <name> --no-interactive` per phase and enforces
three guarantees the DSL used to provide:

  1. Isolated sub-agent context   — each call is its own subprocess.
  2. Sequential + parallel phases  — plain calls vs. threaded fan-out + join.
  3. Test-gated progression        — pytest return code gates each phase.

CONTROL-FLOW CONTRACT (non-negotiable): success/failure is judged ONLY by a
sub-agent's schema-validated handoff artifact (its AgentOutput JSON written to
workloads/{wl}/.handoffs/{agent}.json) or by pytest's exit code. Chat stdout is
captured for logging only and is NEVER parsed to decide control flow.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from shared.templates.agent_output_schema import AgentOutput
from shared.utils.orchestrator_logger import OrchestratorLogger

# Regulations that warrant the strongest available model for build sub-agents.
REGULATIONS_REQUIRING_TOP_TIER = {"HIPAA", "SOX", "PCI"}

# Trust-tools passed to `q chat --trust-tools` per agent.
#
# IMPORTANT (verified against q CLI v1.19.7): trusting a tool via --trust-tools
# OVERRIDES its toolsSettings sandbox — `--trust-tools=fs_write` disables
# fs_write.allowedPaths, and likewise execute_bash.allowedCommands. So we trust
# ONLY fs_read here and let each agent's toolsSettings auto-approve its scoped
# fs_write (allowedPaths) and execute_bash (allowedCommands) without a prompt.
# Operations outside those allowlists get no auto-approval and, in --no-interactive
# mode, fail closed instead of running unsandboxed. Hooks (discovery/codegen/
# logging gates) fire regardless of trust, so they still enforce either way.
DEFAULT_TRUST_TOOLS: Dict[str, List[str]] = {
    "adop-build-metadata": ["fs_read"],
    "adop-build-transform": ["fs_read"],
    "adop-build-quality": ["fs_read"],
    "adop-build-dag": ["fs_read"],
    # Ontology's single MCP read tool is safe to pre-trust so it doesn't prompt.
    "adop-build-ontology": ["fs_read", "@glue-athena/get_table"],
    "adop-reviewer": ["fs_read"],
}


def build_model_for_regulation(
    regulation: Optional[Sequence[str]],
    model_map: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Return the model ID to use for build sub-agents given regulation(s).

    model_map maps the tiers "top" and "standard" to concrete Q CLI model IDs
    (e.g. {"top": "claude-opus-4", "standard": "claude-sonnet-4"}). Confirm real
    IDs with `q chat` `/model` before populating it. When model_map is empty (the
    default), returns None so no `--model` flag is passed and the agent uses the
    CLI default — see ADOP-to-AmazonQ-Migration-Design.md Appendix 7.2 on why the
    per-invocation --model flag is treated as unverified.
    """
    model_map = model_map or {}
    regs = list(regulation or [])
    tier = "top" if any(r in REGULATIONS_REQUIRING_TOP_TIER for r in regs) else "standard"
    return model_map.get(tier)


@dataclass
class AgentInvocation:
    """One sub-agent call. `task` is the workload-specific instruction."""

    agent: str
    task: str
    handoff_name: str
    trust_tools: Optional[List[str]] = None
    model: Optional[str] = None
    timeout_s: int = 1800

    def resolved_trust_tools(self) -> List[str]:
        return self.trust_tools or DEFAULT_TRUST_TOOLS.get(
            self.agent, ["fs_read", "fs_write", "execute_bash"]
        )


@dataclass
class AgentResult:
    """Outcome of a sub-agent call, judged by handoff artifact (never stdout)."""

    agent: str
    ok: bool
    reason: str = ""
    output: Optional[AgentOutput] = None
    returncode: Optional[int] = None
    handoff_path: Optional[str] = None
    stdout_tail: str = ""  # captured for logging/debugging ONLY

    @property
    def can_proceed(self) -> bool:
        return self.ok and self.output is not None and self.output.can_proceed


# A runner takes (argv, timeout_s) and returns (returncode, stdout, stderr).
# Injectable so the driver can be unit-tested / dry-run without the real q CLI.
RunnerFn = Callable[[List[str], int], "tuple[int, str, str]"]


def _subprocess_runner(argv: List[str], timeout_s: int) -> "tuple[int, str, str]":
    proc = subprocess.run(  # noqa: S603 - argv list, no shell, prompt not interpolated
        argv, capture_output=True, text=True, timeout=timeout_s
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


class WorkflowDriver:
    """Sequences ADOP sub-agents as `q chat` subprocesses with test gates."""

    def __init__(
        self,
        workload: str,
        run_id: str,
        *,
        repo_root: Optional[Path] = None,
        q_bin: str = "q",
        model_map: Optional[Dict[str, str]] = None,
        runner: RunnerFn = _subprocess_runner,
        logger: Optional[OrchestratorLogger] = None,
        max_attempts: int = 3,
    ):
        self.workload = workload
        self.run_id = run_id
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()
        self.q_bin = q_bin
        self.model_map = model_map or {}
        self.runner = runner
        self.max_attempts = max_attempts
        self.logger = logger or OrchestratorLogger(workload, run_id)
        self.handoff_dir = self.repo_root / "workloads" / workload / ".handoffs"

    # ── command construction ────────────────────────────────────────────

    def _handoff_path(self, handoff_name: str) -> Path:
        return self.handoff_dir / f"{handoff_name}.json"

    def _augment_task(self, task: str, handoff_path: Path) -> str:
        rel = handoff_path.relative_to(self.repo_root) if handoff_path.is_absolute() else handoff_path
        return (
            f"{task}\n\n"
            f"--- HANDOFF CONTRACT ---\n"
            f"When finished, write your complete AgentOutput as JSON to "
            f"'{rel}' using fs_write. That file is your ONLY success signal; "
            f"the orchestrator ignores chat output. Set status='success' with an "
            f"empty blocking_issues array only if all your tests pass, and always "
            f"include a populated decisions array."
        )

    def build_command(self, inv: AgentInvocation,
                      handoff_path: Optional[Path]) -> List[str]:
        argv = [self.q_bin, "chat", "--agent", inv.agent, "--no-interactive"]
        model = inv.model or build_model_for_regulation(None, self.model_map)
        if model:
            argv += ["--model", model]
        argv += ["--trust-tools", ",".join(inv.resolved_trust_tools())]
        # handoff_path is None for file-judged agents (e.g. the reviewer, whose
        # fs_write is scoped away from .handoffs/) — pass the task unaugmented.
        task = self._augment_task(inv.task, handoff_path) if handoff_path else inv.task
        argv.append(task)
        return argv


    # ── low-level: run one agent, judge by handoff artifact only ─────────

    def run_agent(self, inv: AgentInvocation) -> AgentResult:
        """Invoke one sub-agent and judge success by its handoff file."""
        handoff_path = self._handoff_path(inv.handoff_name)
        self.handoff_dir.mkdir(parents=True, exist_ok=True)
        # Remove any stale handoff so we never read a previous run's result.
        if handoff_path.exists():
            handoff_path.unlink()

        argv = self.build_command(inv, handoff_path)
        try:
            returncode, stdout, stderr = self.runner(argv, inv.timeout_s)
        except subprocess.TimeoutExpired:
            return AgentResult(
                agent=inv.agent, ok=False, reason="timeout",
                handoff_path=str(handoff_path),
            )

        stdout_tail = (stdout or "")[-2000:]

        # Success is determined ONLY by the handoff artifact, never by stdout.
        if not handoff_path.exists():
            return AgentResult(
                agent=inv.agent, ok=False,
                reason=f"no handoff artifact written (rc={returncode}); stderr: {(stderr or '')[-300:]}",
                returncode=returncode, handoff_path=str(handoff_path),
                stdout_tail=stdout_tail,
            )
        try:
            output = AgentOutput.from_json(handoff_path.read_text())
        except (ValueError, KeyError, OSError) as exc:
            return AgentResult(
                agent=inv.agent, ok=False,
                reason=f"invalid handoff artifact: {exc}",
                returncode=returncode, handoff_path=str(handoff_path),
                stdout_tail=stdout_tail,
            )

        ok = output.status != "failed"
        reason = "" if ok else f"agent status={output.status}, blocking={output.blocking_issues}"
        return AgentResult(
            agent=inv.agent, ok=ok, reason=reason, output=output,
            returncode=returncode, handoff_path=str(handoff_path),
            stdout_tail=stdout_tail,
        )


    # ── test gate: pytest return code is the gate (not text parsing) ─────

    def run_tests(self, test_selector: str) -> "tuple[bool, Dict[str, int]]":
        """Run pytest on a selector. Gate on the RETURN CODE, not stdout text.

        Returns (passed, {"passed": n, "total": n}). Counts are best-effort for
        reporting only; the pass/fail decision is pytest's exit code (0 == pass).
        """
        argv = [sys.executable, "-m", "pytest", test_selector, "-q"]
        try:
            returncode, stdout, _ = self.runner(argv, 900)
        except subprocess.TimeoutExpired:
            return False, {"passed": 0, "total": 0}
        counts = _parse_pytest_counts(stdout)
        return returncode == 0, counts

    # ── mid-level: run one agent with retries + a test gate ──────────────

    def run_gated(
        self,
        inv: AgentInvocation,
        phase: int,
        *,
        test_selector: Optional[str] = None,
        retry_hint: str = "Previous attempt failed. Fix the issue and try again.",
    ) -> AgentResult:
        """Run an agent, then its test gate, retrying up to max_attempts."""
        self.logger.phase_start(phase, inv.agent)
        last: Optional[AgentResult] = None
        base_task = inv.task

        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1:
                inv = AgentInvocation(
                    agent=inv.agent,
                    task=f"{base_task}\n\n[RETRY {attempt}] {retry_hint} {last.reason if last else ''}".strip(),
                    handoff_name=inv.handoff_name,
                    trust_tools=inv.trust_tools,
                    model=inv.model,
                    timeout_s=inv.timeout_s,
                )
            result = self.run_agent(inv)
            last = result

            if not result.can_proceed:
                self.logger.phase_retry(phase, attempt, result.reason or "handoff not ok")
                continue

            # Handoff OK — link its decisions into the trace, then gate on tests.
            if result.output is not None:
                self.logger.link_sub_agent_trace(
                    result.output.to_dict(), agent_name=inv.agent, phase=phase
                )
            if test_selector is None:
                self.logger.phase_complete(phase, "success",
                                           artifacts=_artifact_paths(result))
                return result

            passed, counts = self.run_tests(test_selector)
            self.logger.test_gate(phase, inv.agent, passed, counts)
            if passed:
                self.logger.phase_complete(phase, "success",
                                           artifacts=_artifact_paths(result),
                                           test_results=counts)
                return result
            last = AgentResult(agent=inv.agent, ok=False,
                               reason=f"test gate failed ({counts.get('passed',0)}/{counts.get('total',0)})",
                               output=result.output, handoff_path=result.handoff_path)
            self.logger.phase_retry(phase, attempt, last.reason)

        self.logger.phase_escalate(phase, last.reason if last else "unknown failure")
        return last or AgentResult(agent=inv.agent, ok=False, reason="no attempts run")

    # ── file-judged agent (reviewer): success = the artifact it wrote ────

    def run_file_judged(
        self,
        inv: AgentInvocation,
        success_file: str,
        *,
        reject_if_contains: Optional[Sequence[str]] = None,
    ) -> AgentResult:
        """Run an agent whose success is a written file, not a handoff.

        ok when success_file exists after the run and (if reject_if_contains is
        given) contains none of those markers. This still judges by an artifact
        the agent wrote — never by chat stdout.
        """
        target = (self.repo_root / success_file) if not Path(success_file).is_absolute() else Path(success_file)
        if target.exists():
            target.unlink()
        argv = self.build_command(inv, None)
        try:
            returncode, stdout, stderr = self.runner(argv, inv.timeout_s)
        except subprocess.TimeoutExpired:
            return AgentResult(agent=inv.agent, ok=False, reason="timeout")
        if not target.exists():
            return AgentResult(agent=inv.agent, ok=False,
                               reason=f"expected artifact '{success_file}' not written",
                               returncode=returncode, stdout_tail=(stdout or "")[-2000:])
        ok, reason = True, ""
        if reject_if_contains:
            content = target.read_text(errors="replace")
            hit = [m for m in reject_if_contains if m in content]
            if hit:
                ok, reason = False, f"artifact contains blocking markers: {hit}"
        return AgentResult(agent=inv.agent, ok=ok, reason=reason,
                           returncode=returncode, handoff_path=str(target),
                           stdout_tail=(stdout or "")[-2000:])

    # ── parallel fan-out (today's parallel([...])) ───────────────────────

    def run_parallel(self, invocations: Sequence[AgentInvocation]) -> List[AgentResult]:
        """Run several agents concurrently; join and return all results."""
        with ThreadPoolExecutor(max_workers=max(1, len(invocations))) as pool:
            return list(pool.map(self.run_agent, invocations))


    # ── high-level: the Phase 4 build sequence with named agents ─────────

    def run_build(self, tasks: Dict[str, str], *, ontology: bool = False,
                  review: bool = True) -> Dict[str, AgentResult]:
        """Run the build phase: metadata+quality (parallel), transform, dag,
        optional ontology, then optional adversarial review.

        `tasks` maps agent name -> its workload-specific instruction. Returns a
        map of agent name -> AgentResult. Stops and returns early if a gate
        escalates (a returned result with can_proceed False).
        """
        results: Dict[str, AgentResult] = {}
        wl_unit = f"workloads/{self.workload}/tests/unit"

        # Stage 1 — metadata + quality in parallel, then a shared test gate.
        stage1 = [
            AgentInvocation("adop-build-metadata", tasks["adop-build-metadata"], "metadata"),
            AgentInvocation("adop-build-quality", tasks["adop-build-quality"], "quality"),
        ]
        self.logger.phase_start(4, "Build: metadata + quality (parallel)")
        par = {r.agent: r for r in self.run_parallel(stage1)}
        results.update(par)
        for r in par.values():
            if r.output is not None:
                self.logger.link_sub_agent_trace(r.output.to_dict(), agent_name=r.agent, phase=4)
        if not all(r.can_proceed for r in par.values()):
            bad = [r.agent for r in par.values() if not r.can_proceed]
            self.logger.phase_escalate(4, f"stage-1 handoff failed: {bad}")
            return results
        passed, counts = self.run_tests(wl_unit)
        self.logger.test_gate(4, "metadata+quality", passed, counts)
        if not passed:
            self.logger.phase_escalate(4, f"stage-1 test gate failed {counts}")
            return results
        self.logger.phase_complete(4, "success", test_results=counts)

        # Stage 2 — transform (sequential, own gate).
        results["adop-build-transform"] = self.run_gated(
            AgentInvocation("adop-build-transform", tasks["adop-build-transform"], "transform"),
            phase=5, test_selector=f"{wl_unit}/test_transformations.py",
        )
        if not results["adop-build-transform"].can_proceed:
            return results

        # Stage 3 — DAG (sequential, own gate).
        results["adop-build-dag"] = self.run_gated(
            AgentInvocation("adop-build-dag", tasks["adop-build-dag"], "dag"),
            phase=6, test_selector=f"{wl_unit}/test_dag.py",
        )
        if not results["adop-build-dag"].can_proceed:
            return results

        # Stage 4 — ontology (optional).
        if ontology and "adop-build-ontology" in tasks:
            results["adop-build-ontology"] = self.run_gated(
                AgentInvocation("adop-build-ontology", tasks["adop-build-ontology"], "ontology"),
                phase=7, test_selector=wl_unit,
            )
            if not results["adop-build-ontology"].can_proceed:
                return results

        # Stage 5 — adversarial review. Judged by the findings file it writes
        # (its fs_write is scoped to reviews/, not .handoffs/). A HIGH finding
        # blocks; the workflow surfaces it to the human.
        if review and "adop-reviewer" in tasks:
            self.logger.phase_start(8, "adop-reviewer")
            rev = self.run_file_judged(
                AgentInvocation("adop-reviewer", tasks["adop-reviewer"], "review"),
                success_file="reviews/security-findings.md",
                reject_if_contains=["Severity: High", "Severity: HIGH"],
            )
            results["adop-reviewer"] = rev
            self.logger.phase_complete(8, "success" if rev.ok else "failed")

        return results


# ── module-level helpers ────────────────────────────────────────────────

def _parse_pytest_counts(stdout: str) -> Dict[str, int]:
    """Best-effort parse of pytest's summary line for REPORTING only.

    The pass/fail gate is pytest's exit code (see run_tests); these counts are
    cosmetic. Handles lines like '5 passed', '3 passed, 1 failed', '2 failed'.
    """
    import re

    passed = failed = 0
    m = re.search(r"(\d+) passed", stdout)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) failed", stdout)
    if m:
        failed = int(m.group(1))
    return {"passed": passed, "total": passed + failed}


def _artifact_paths(result: AgentResult) -> List[str]:
    if result.output is None:
        return []
    out: List[str] = []
    for a in result.output.artifacts:
        if isinstance(a, dict) and "path" in a:
            out.append(str(a["path"]))
    return out


def build_default_tasks(args: Dict, *, model: Optional[str] = None) -> Dict[str, str]:
    """Produce per-agent task prompts from an onboard-workflow args object.

    args follows the shape in .claude/commands/onboard-workflow.md Step 4
    (workload_name, source, primary_key, pii_columns, transformations, quality,
    schedule, gold_format, ontology, ...). These are concise instructions; the
    agents load full role/rules context via their `resources` field.
    """
    import json

    wl = args["workload_name"]
    ctx = json.dumps(args, indent=2, sort_keys=True, default=str)
    tasks = {
        "adop-build-metadata":
            f"Generate metadata for workload '{wl}'. Produce config/source.yaml and "
            f"config/semantic.yaml plus tests. Workload args:\n{ctx}",
        "adop-build-quality":
            f"Generate config/quality.yaml and the quality check for workload '{wl}', "
            f"plus tests, honoring the thresholds in the args. Args:\n{ctx}",
        "adop-build-transform":
            f"Produce silver_spec/gold_spec and render the Glue ETL scripts for "
            f"workload '{wl}' via the renderer, plus tests. Args:\n{ctx}",
        "adop-build-dag":
            f"Generate the Airflow DAG for workload '{wl}' plus tests. Args:\n{ctx}",
        "adop-build-ontology":
            f"Stage OWL2 + R2RML for workload '{wl}' from config/semantic.yaml and the "
            f"Gold Glue schema. Args:\n{ctx}",
        "adop-reviewer":
            f"Perform an adversarial security review of the generated artifacts for "
            f"workload '{wl}' and write reviews/security-findings.md.",
    }
    return tasks


# ── dry-run runner (exercise the flow without the real q CLI) ────────────

def make_dry_run_runner(repo_root: Path) -> RunnerFn:
    """A runner that fakes `q chat` and `pytest` so the driver can be exercised
    end-to-end offline. For a q-chat argv it writes a valid AgentOutput to the
    handoff path embedded in the prompt (or the reviewer's findings file); for a
    pytest argv it returns success. Never used in production."""
    import json
    import re
    from datetime import datetime, timezone

    handoff_type = {
        "adop-build-metadata": "metadata",
        "adop-build-quality": "quality",
        "adop-build-transform": "transformation",
        "adop-build-dag": "dag",
        "adop-build-ontology": "analysis",
        "adop-reviewer": "analysis",
    }

    def runner(argv: List[str], timeout_s: int) -> "tuple[int, str, str]":
        if "pytest" in argv:
            return 0, "1 passed", ""
        if len(argv) >= 3 and argv[1] == "chat" and argv[2] == "--agent":
            agent = argv[3]
            prompt = argv[-1]
            # Reviewer writes a findings file, not a handoff.
            if agent == "adop-reviewer":
                fp = repo_root / "reviews" / "security-findings.md"
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text("# Security Review\n\nNo high-confidence findings.\n")
                return 0, "review written", ""
            m = re.search(r"to '([^']+\.json)'", prompt)
            if not m:
                return 0, "no handoff path found in prompt", ""
            hp = repo_root / m.group(1)
            hp.parent.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc).isoformat()
            out = AgentOutput(
                agent_name=agent, agent_type=handoff_type.get(agent, "analysis"),
                workload_name="dryrun", run_id="dry", started_at=now, completed_at=now,
                status="success", artifacts=[{"path": f"config/{agent}.yaml", "type": "config", "checksum": "0"}],
                tests={"unit": {"passed": 1, "failed": 0, "total": 1}},
                blocking_issues=[], decisions=[{"decision_id": "d-001", "category": "dryrun"}],
            )
            hp.write_text(out.to_json())
            return 0, "handoff written", ""
        return 0, "", ""

    return runner


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    import uuid

    p = argparse.ArgumentParser(description="ADOP orchestration driver (Amazon Q Developer CLI).")
    p.add_argument("--args", required=True, help="Path to the onboard-workflow args JSON.")
    p.add_argument("--repo-root", default=".", help="Repo root (default: cwd).")
    p.add_argument("--run-id", default=None, help="Run id (default: random UUID).")
    p.add_argument("--q-bin", default="q", help="q CLI binary (default: q).")
    p.add_argument("--ontology", action="store_true", help="Run the ontology stage.")
    p.add_argument("--no-review", action="store_true", help="Skip the adversarial review stage.")
    p.add_argument("--model-top", default=None, help="Model ID for HIPAA/SOX/PCI builds.")
    p.add_argument("--model-standard", default=None, help="Model ID for standard builds.")
    p.add_argument("--dry-run", action="store_true", help="Fake q/pytest; exercise the flow offline.")
    ns = p.parse_args(argv)

    repo_root = Path(ns.repo_root).resolve()
    args_obj = json.loads(Path(ns.args).read_text())
    workload = args_obj["workload_name"]
    run_id = ns.run_id or str(uuid.uuid4())

    model_map: Dict[str, str] = {}
    if ns.model_top:
        model_map["top"] = ns.model_top
    if ns.model_standard:
        model_map["standard"] = ns.model_standard

    model = build_model_for_regulation(args_obj.get("regulation"), model_map)
    tasks = build_default_tasks(args_obj, model=model)
    runner = make_dry_run_runner(repo_root) if ns.dry_run else _subprocess_runner

    driver = WorkflowDriver(
        workload, run_id, repo_root=repo_root, q_bin=ns.q_bin,
        model_map=model_map, runner=runner,
    )
    results = driver.run_build(
        tasks,
        ontology=ns.ontology or bool(args_obj.get("ontology", {}).get("enabled")),
        review=not ns.no_review,
    )
    driver.logger.pipeline_summary()

    failed = [name for name, r in results.items()
              if not (r.can_proceed or (r.output is None and r.ok))]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
