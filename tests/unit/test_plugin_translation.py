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
