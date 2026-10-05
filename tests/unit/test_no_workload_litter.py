"""The test suite must not create directories under the repository's workloads/.

Running the suite used to leave three directories behind — `workloads/unknown/`,
`workloads/env_workload/` and `workloads/sales_transactions/` — all empty. The last is named
after a path `test_script_tracer.py` invents (`/project/workloads/sales_transactions/...`) and
which has never existed as a workload.

They were invisible to git, because git cannot track an empty directory, so `git status` stayed
clean and nothing ever flagged them. But every tool that globs `workloads/*` counted them: the
drift validator iterated six "workloads" and reported three of them as "no artifacts under
scripts/, dags/ or sql/". A phantom workload is worse than clutter — it dilutes exactly the
check that is supposed to notice a workload with no generated code.

Cause: `_default_trace_path()` in both script_tracer.py and orchestrator_logger.py called
`log_dir.mkdir(parents=True, exist_ok=True)` while merely COMPUTING a path. Constructing a
tracer created a directory tree even when nothing was ever written. `AgentTracer._emit` already
mkdirs immediately before opening the file, so the eager call was redundant.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKLOADS = PROJECT_ROOT / "workloads"

# Directories that legitimately exist in the repository. Anything else appearing under
# workloads/ after a test run was created by the tests.
REAL_WORKLOADS = {"claims", "claims_v2", "customer_master"}


def test_computing_a_default_trace_path_creates_nothing(tmp_path, monkeypatch):
    """The property directly. Compute a path for a workload that does not exist."""
    from shared.utils.script_tracer import _default_trace_path

    monkeypatch.chdir(tmp_path)
    path = _default_trace_path("a_workload_that_does_not_exist")
    assert "a_workload_that_does_not_exist" in path
    assert not (tmp_path / "workloads").exists(), (
        "computing a trace path created a directory tree; it must only build a string, and "
        "AgentTracer._emit already mkdirs before it writes"
    )


def test_orchestrator_default_trace_path_creates_nothing(tmp_path, monkeypatch):
    from shared.utils.orchestrator_logger import _default_trace_path

    monkeypatch.chdir(tmp_path)
    _default_trace_path("another_nonexistent_workload")
    assert not (tmp_path / "workloads").exists()


def test_constructing_a_script_tracer_creates_nothing(tmp_path, monkeypatch):
    """Construction alone must not touch the filesystem."""
    from shared.utils.script_tracer import ScriptTracer

    monkeypatch.chdir(tmp_path)
    ScriptTracer.for_script("/nowhere/workloads/phantom/scripts/transform/x.py")
    assert not (tmp_path / "workloads").exists(), (
        "merely constructing a ScriptTracer created workloads/phantom/logs/"
    )


def test_the_default_path_stays_relative_to_cwd(tmp_path, monkeypatch):
    """Deliberate, and the reason an earlier fix of mine was wrong.

    Anchoring this to the project root looks tidier and breaks isolation:
    `test_agent_tracer.test_default_trace_path` isolates itself with
    `monkeypatch.chdir(tmp_path)`, which only works while the path is relative. Making it
    absolute caused a correctly-written test to start writing into the real repository.
    """
    from shared.utils.script_tracer import _default_trace_path

    monkeypatch.chdir(tmp_path)
    assert not Path(_default_trace_path("w")).is_absolute(), (
        "the trace path became absolute, so a test that chdir's to isolate itself can no "
        "longer do so"
    )


def test_the_repository_has_no_phantom_workloads():
    """Guards the observable symptom, so a different cause is still caught.

    Deliberately checks the real tree rather than a fixture: the point is that running the
    suite leaves it unchanged. pytest runs from the project root, which is what made the
    relative path resolve here in the first place.
    """
    if not WORKLOADS.is_dir():
        pytest.skip("no workloads/ directory")
    found = {p.name for p in WORKLOADS.iterdir() if p.is_dir()}
    phantom = sorted(found - REAL_WORKLOADS)
    assert not phantom, (
        "these appeared under workloads/ and are not real workloads:\n  "
        + "\n  ".join(phantom)
        + "\n\nSomething computed a default trace path with the repo root as cwd. Tests that "
          "build a tracer without an explicit output_path must monkeypatch.chdir(tmp_path)."
    )
