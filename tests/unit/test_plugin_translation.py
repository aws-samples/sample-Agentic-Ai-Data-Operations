"""The repository is normative; plugins/claude-code/ is derived from it.

A plugin is copied into ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/
at install time and cannot see this repository, so it has to *contain* the
capability rather than reference it. That means copies, and copies drift silently:
the predecessor of this plugin shipped three skills that were condensations of
.claude/rules/ files which were later rewritten, and nothing noticed for weeks
because the plugin lived in a separate repository with no access to the originals.

These tests exist because the plugin now lives beside its sources. Every file under
plugins/claude-code/ must be accounted for in TRANSLATION.yaml, and each category
is checked as strictly as that category permits:

    copy       byte-identical to its source
    rewrite    source exists, and named anchors survive into the derived file
    transform  every source is claimed by some target
    plugin-only / untranslatable   declared, with a stated reason

The `status: pending` marker means "declared but not yet translated" — Phases B-D
convert those. Pending entries are reported, not failed, so the harness is useful
during the port instead of only after it.
"""
import pathlib
import sys

import pytest

yaml = pytest.importorskip("yaml")

REPO = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "claude-code"
MANIFEST = PLUGIN / "TRANSLATION.yaml"

# Files inside the plugin that are build/runtime noise rather than content.
IGNORED = ("__pycache__", ".pytest_cache", ".venv", ".DS_Store")


def _load():
    return yaml.safe_load(MANIFEST.read_text())


@pytest.fixture(scope="module")
def manifest():
    assert MANIFEST.is_file(), f"missing translation manifest: {MANIFEST}"
    return _load()


def _entries(manifest, section):
    return manifest.get(section) or []


def _declared_targets(manifest):
    out = set()
    for section in ("copy", "rewrite", "transform", "plugin-only"):
        for e in _entries(manifest, section):
            out.add(e["target"])
    return out


def _plugin_files():
    return sorted(
        p.relative_to(PLUGIN).as_posix()
        for p in PLUGIN.rglob("*")
        if p.is_file() and not any(part in IGNORED for part in p.parts)
    )


# --------------------------------------------------------------------------
# Accounting: nothing in the plugin without a declared origin
# --------------------------------------------------------------------------

def test_every_plugin_file_is_declared(manifest):
    """An undeclared file is content invented in the plugin instead of derived.

    This is the guard that keeps the repo normative. Adding a file to the plugin
    now requires saying where it came from, which is the whole contract.
    """
    undeclared = sorted(set(_plugin_files()) - _declared_targets(manifest))
    assert not undeclared, (
        "these plugin files are not in TRANSLATION.yaml:\n  "
        + "\n  ".join(undeclared)
        + "\nAdd an entry naming the repo source, or declare it plugin-only with a reason."
    )


def test_no_declared_target_is_missing(manifest):
    """A manifest entry whose target does not exist is a stale declaration.

    `status: planned` is exempt: it means the target is intentionally not written
    yet. That is how a not-yet-created skill can still claim its rule sources, so
    the coverage check below has something to match against.
    """
    missing = sorted(
        e["target"]
        for section in ("copy", "rewrite", "transform", "plugin-only")
        for e in _entries(manifest, section)
        if e.get("status") != "planned" and not (PLUGIN / e["target"]).is_file()
    )
    assert not missing, "declared but absent from the plugin:\n  " + "\n  ".join(missing)


# --------------------------------------------------------------------------
# Sources must exist — catches a repo file being renamed out from under us
# --------------------------------------------------------------------------

def _all_sources(manifest):
    for section in ("copy", "rewrite", "transform"):
        for e in _entries(manifest, section):
            for s in ([e["source"]] if "source" in e else e.get("sources", [])):
                yield e["target"], s
    for e in _entries(manifest, "untranslatable"):
        yield "(untranslatable)", e["source"]


def test_every_declared_source_exists(manifest):
    """The repo moved `prompts/` to `runbooks/` once already; this catches the next one."""
    broken = [f"{t}  <-  {s}" for t, s in _all_sources(manifest) if not (REPO / s).exists()]
    assert not broken, (
        "manifest names repo sources that do not exist:\n  " + "\n  ".join(sorted(broken))
    )


# --------------------------------------------------------------------------
# copy: byte-identical
# --------------------------------------------------------------------------

def test_copy_entries_are_byte_identical(manifest):
    drifted = []
    for e in _entries(manifest, "copy"):
        if e.get("status") in ("pending", "planned"):
            continue
        src, dst = REPO / e["source"], PLUGIN / e["target"]
        if src.read_bytes() != dst.read_bytes():
            drifted.append(f"{e['target']}  !=  {e['source']}")
    assert not drifted, (
        "vendored copies have drifted from their sources:\n  "
        + "\n  ".join(drifted)
        + "\nRe-vendor from the repo; do not edit the plugin copy."
    )


# --------------------------------------------------------------------------
# rewrite: anchors survive the retargeting
# --------------------------------------------------------------------------

def test_declared_anchors_exist_in_the_source(manifest):
    """An anchor must be a real string in the source, even for a pending entry.

    Added after recording "Intent-to-Tool" as a TOOL_ROUTING.md anchor when the
    heading is "Tool Selection for Agentic Data Onboarding". The anchor check below
    skips pending and planned entries, so a typo in one of those sits undetected
    until the translation happens and then fails for a reason that looks like the
    translation's fault. Checking against the source catches it at declaration.

    An anchor already retargeted for the plugin (a plugin-namespaced agent name,
    a ${CLAUDE_PLUGIN_ROOT} path) legitimately will not appear in the source, so
    presence in either file is enough.
    """
    bogus = []
    for e in _entries(manifest, "rewrite"):
        for a in e.get("anchors") or []:
            src = REPO / e["source"]
            tgt = PLUGIN / e["target"]
            in_src = src.is_file() and a in src.read_text()
            in_tgt = tgt.is_file() and a in tgt.read_text()
            if not (in_src or in_tgt):
                bogus.append(f"{e['target']}: anchor {a!r} appears in neither source nor target")
    assert not bogus, "\n  ".join(["anchors that match nothing:"] + bogus)


def test_rewrite_entries_keep_their_anchors(manifest):
    """A rewrite may retarget paths but must not drop the mechanisms it names.

    Anchors are the load-bearing strings — step headings, tool names, the
    discovery marker. Retargeting `shared.codegen` to the vendored CLI is
    expected; losing `AskUserQuestion` is not.
    """
    lost = []
    for e in _entries(manifest, "rewrite"):
        if e.get("status") in ("pending", "planned") or not e.get("anchors"):
            continue
        text = (PLUGIN / e["target"]).read_text()
        for a in e["anchors"]:
            if a not in text:
                lost.append(f"{e['target']}: missing anchor {a!r}")
    assert not lost, "\n  ".join(["rewrites dropped required anchors:"] + lost)


# --------------------------------------------------------------------------
# transform: no source left behind
# --------------------------------------------------------------------------

def test_every_rule_file_is_claimed_by_some_target(manifest):
    """Adding .claude/rules/13-*.md must not silently skip the plugin.

    Always-on rules become on-demand skills, which is already a fidelity loss;
    an unclaimed rule would be a total one.
    """
    claimed = {s for _, s in _all_sources(manifest)}
    rules = sorted(
        p.relative_to(REPO).as_posix() for p in (REPO / ".claude" / "rules").glob("*.md")
    )
    orphans = [r for r in rules if r not in claimed]
    assert not orphans, (
        "these .claude/rules/ files are not carried into the plugin:\n  "
        + "\n  ".join(orphans)
        + "\nMap each to a skill in TRANSLATION.yaml, or list it as untranslatable."
    )


def test_untranslatable_entries_state_a_reason(manifest):
    """An undocumented gap is indistinguishable from an oversight."""
    thin = [
        e.get("source", "?")
        for e in _entries(manifest, "untranslatable")
        if len((e.get("reason") or "").split()) < 10
    ]
    assert not thin, "untranslatable entries need a real explanation: " + ", ".join(thin)


def test_plugin_only_entries_state_a_reason(manifest):
    thin = [
        e.get("target", "?")
        for e in _entries(manifest, "plugin-only")
        if len((e.get("reason") or "").split()) < 5
    ]
    assert not thin, "plugin-only entries need a reason: " + ", ".join(thin)


# --------------------------------------------------------------------------
# The vendored library must actually work from its vendored location
# --------------------------------------------------------------------------

# Modules a sub-agent can reach. These must import with nothing beyond the three
# codegen dependencies (jinja2, jsonschema, pyyaml), because a user installing the
# plugin to render a pipeline should not also need the AWS SDK.
SUBAGENT_SAFE = [
    "shared.codegen.renderer",
    "shared.codegen.spec_loader",
    "shared.codegen.slot_extractor",
    "shared.codegen.drift_validator",
    "shared.logging.agent_tracer",
    "shared.logging.trace_viewer",
    "shared.metadata.semantic_reader",
    "shared.templates.agent_output_schema",
    "shared.utils.ascii_display",
    "shared.utils.deterministic_yaml",
    "shared.utils.orchestrator_logger",
    "shared.utils.script_tracer",
    "shared.utils.structured_logger",
]

# Modules that call AWS and therefore need boto3, which pyproject.toml keeps
# optional. All four are orchestrator work — profiling a source, tagging PII,
# verifying a deployment. Listed so the boundary is explicit: if one of these ever
# becomes importable without boto3, or a SUBAGENT_SAFE module starts needing it,
# the split has moved and somebody should notice.
NEEDS_AWS_SDK = [
    "shared.metadata.glue_fetcher",
    "shared.metadata.lakeformation_fetcher",
    "shared.utils.pii_detection_and_tagging",
    "shared.utils.post_deployment_verifier",
]


def _import_in_subprocess(module: str) -> tuple[int, str]:
    """Import in a clean interpreter so sys.modules from this session cannot mask a failure."""
    import subprocess

    r = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(PLUGIN / 'lib')!r}); import {module}"],
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""


@pytest.mark.parametrize("module", SUBAGENT_SAFE)
def test_subagent_safe_modules_import_from_the_vendored_tree(module):
    """Byte-identity is not enough — the copy has to be importable where it sits.

    This is what proves the lib/shared/... layout works: renderer.py resolves its
    template directory by walking three parents up from __file__, so a flattened
    vendoring would import fine here and then fail to find a template at render
    time.
    """
    code, err = _import_in_subprocess(module)
    assert code == 0, f"{module} does not import from plugins/claude-code/lib: {err}"


@pytest.mark.parametrize("module", NEEDS_AWS_SDK)
def test_aws_modules_are_confined_to_the_named_four(module):
    """Documents rather than forbids: these need boto3, and that is expected.

    Skips when boto3 is installed, since then there is nothing to observe. The
    value is in the list itself — it names the AWS surface the plugin carries, so
    growth in it is visible in review.
    """
    try:
        import boto3  # noqa: F401

        pytest.skip("boto3 present; the boundary is only observable without it")
    except ImportError:
        pass
    code, _ = _import_in_subprocess(module)
    assert code != 0, (
        f"{module} imported without boto3 — it was expected to need the AWS SDK. "
        "If it no longer does, move it to SUBAGENT_SAFE."
    )


# --------------------------------------------------------------------------
# The README must keep describing the plugin that exists
# --------------------------------------------------------------------------

def test_readme_names_every_skill_and_agent():
    """The README went stale during this port and nothing caught it.

    By the end of Phase D it still listed 2 skills where 7 shipped, and named three
    agents — data-quality-agent, orchestration-agent, devops-agent — that had been
    renamed out of existence. A reader following it would have invoked agents that do
    not exist. Adding or renaming a component now fails here.
    """
    readme = (PLUGIN / "README.md").read_text()
    components = [p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md")]
    components += [p.stem for p in (PLUGIN / "agents").glob("*.md")]
    missing = sorted(c for c in components if c not in readme)
    assert not missing, (
        "README does not mention these components:\n  " + "\n  ".join(missing)
    )


def test_readme_does_not_name_components_that_were_removed():
    """Catches the other half: a name left behind after a rename."""
    readme = (PLUGIN / "README.md").read_text()
    live = {p.stem for p in (PLUGIN / "agents").glob("*.md")}
    # Names the plugin used before Phase C1 adopted the repository's.
    retired = {"data-quality-agent", "orchestration-agent", "devops-agent"}
    stale = sorted(n for n in retired - live if n in readme)
    assert not stale, (
        "README still names agents that no longer exist: " + ", ".join(stale)
    )


def test_readme_states_both_fidelity_gaps():
    """Two limitations are structural, and a user who hits them unwarned is owed better.

    Skill bodies load on demand where .claude/rules/ is always in context, and a plugin
    cannot install the commit-time gate. Both must stay documented.
    """
    readme = (PLUGIN / "README.md").read_text().lower()
    for phrase, what in (
        ("on-demand", "always-on rules becoming on-demand skills"),
        ("pre-commit", "commit-time gating being opt-in"),
    ):
        assert phrase in readme, f"README no longer states the limitation: {what}"


# --------------------------------------------------------------------------
# Port progress — visible, not enforced
# --------------------------------------------------------------------------

def test_report_pending_translations(manifest, capsys):
    """Always passes. Prints what Phases B-D still owe, with -s."""
    pending = [
        (section, e.get("status"), e["target"], e.get("note", ""))
        for section in ("copy", "rewrite", "transform")
        for e in _entries(manifest, section)
        if e.get("status") in ("pending", "planned")
    ]
    with capsys.disabled():
        print(f"\n  translation pending: {len(pending)}")
        for section, status, target, note in pending:
            print(f"    [{status:<7}] {target}" + (f"  — {note.strip()}" if note else ""))


# --------------------------------------------------------------------------
# Every template must be renderable from the contract the CLI maps it to
# --------------------------------------------------------------------------

def test_render_cli_maps_each_template_to_a_contract_that_has_its_slots():
    """A template whose required slots are absent from its contract can never render.

    Found by an end-to-end run rather than by unit tests: 2 of 7 templates failed with
    MissingSlotError. One was a mapping error of mine — glue_job_config needs `tasks`,
    which only dag_spec defines, and it was mapped to silver. The other, iceberg_ddl,
    needs `tables`, which no v1 contract defines at all, so it is unrenderable upstream
    too and is xfailed here rather than silently skipped.
    """
    import json
    import re

    cli = (PLUGIN / "scripts" / "adop_render.py").read_text()
    table = re.search(r"TEMPLATES = \{(.*?)\n\}", cli, re.S).group(1)
    mapping = dict(re.findall(r'"([a-z_]+)": \("[a-z]+", "([a-z_]+)"', table))
    assert mapping, "could not parse the TEMPLATES table"

    tmpl_dir = PLUGIN / "lib" / "shared" / "templates"
    unrenderable = []
    for template_id, contract in mapping.items():
        candidates = list(tmpl_dir.glob(f"{template_id}.*.j2"))
        assert candidates, f"no template file for {template_id}"
        # required_slots is line 2 of the header block, not line 0 — reading only the
        # first line made this test find nothing and pass vacuously on its first run.
        head = "\n".join(candidates[0].read_text().splitlines()[:6])
        m = re.search(r"required_slots:\s*(.+?)\s*#\}", head)
        if not m:
            continue
        needed = {s.strip() for s in m.group(1).split(",") if s.strip()}
        schema = json.loads(
            (PLUGIN / "lib" / "contracts" / "v1" / f"{contract}_spec.schema.json").read_text()
        )
        missing = sorted(needed - set(schema.get("properties", {})))
        if missing:
            unrenderable.append(f"{template_id} -> {contract}_spec is missing {missing}")

    # iceberg_ddl is a known upstream gap: `tables` is in no v1 contract. Asserting the
    # exact set means this test starts failing the moment it is fixed upstream, which is
    # the reminder to remove the exemption.
    known = ["iceberg_ddl -> silver_spec is missing ['tables']"]
    assert unrenderable == known, (
        "template/contract mapping problems:\n  " + "\n  ".join(unrenderable)
        + f"\n\nExpected only the known upstream gap:\n  {known[0]}"
    )


def test_plugin_contains_no_broken_or_escaping_symlinks():
    """A symlink is fragile in a distributed plugin and this one shipped broken.

    mcp-servers/pii-detection-server/pii_detection_and_tagging.py is a symlink in the
    repo, pointing at ../../shared/utils/. That resolves from mcp-servers/, but the
    vendored copy lives under lib/shared/utils/, so copying it verbatim produced a
    dangling link — invisible to `ls`, and only caught by comparing the installed cache
    against the repo.

    Regular files are the right answer here: a plugin is copied into a cache at install
    time, and a relative link that leaves the plugin root cannot be relied on to survive.
    """
    offenders = []
    for p in PLUGIN.rglob("*"):
        if not p.is_symlink():
            continue
        target = p.resolve()
        rel = p.relative_to(PLUGIN).as_posix()
        if not target.exists():
            offenders.append(f"{rel} -> {p.readlink()} (BROKEN)")
        elif PLUGIN.resolve() not in target.parents:
            offenders.append(f"{rel} -> {p.readlink()} (escapes the plugin root)")
    assert not offenders, (
        "symlinks that will not survive an install:\n  " + "\n  ".join(offenders)
        + "\nReplace with a real file copy."
    )
