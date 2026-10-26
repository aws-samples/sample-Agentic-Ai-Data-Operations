# Kiro adapter audit — `agent-integrations`

**Date:** 2026-10-26
**Scope:** `/Users/hcherian/agent-integrations/.kiro/` plus everything that wires it (`scripts/kiro_workflow.py`, `adapters/kiro/`, `core/tests/test_kiro_integration.py`, `manifest.yaml`, root docs)
**Mode:** read-only. Nothing in the repo was modified. Hook scripts were executed with synthetic stdin payloads only; no AWS calls, no writes to `workloads/`.

---

## 1. Verdict

**The Kiro adapter is substantially better engineered than a blind copy — and it is still not correct.** The hook *wiring* is genuinely Kiro-native: `.kiro/hooks/adop-gates.json` uses the real `{"version":"v1","hooks":[…]}` schema, correct PascalCase triggers, and `.kiro/hooks/adop-hook.sh` is a purpose-built launcher that translates the shared gates' `permissionDecision: deny` JSON into Kiro's exit-2 contract. I verified that translation end-to-end: every blocking gate returns rc=2 with a reason on stderr. That part works.

The headline problem is that **enforcement stops at the matcher and at the actor check.** Four of the five PreToolUse gates are bound to `matcher: "fs_write|write"`, which as a regex over Kiro tool names matches `fs_write` and nothing else — `str_replace`, `fs_append`, `delete_file`, and `execute_bash` all slip past, so the credential gate, the codegen gate, and the auditor scope gate are bypassable by using a different edit tool. Separately, `auditor_write_gate.py` keys off `ADOP_AGENT_NAME` / `payload.agent_name`, neither of which Kiro supplies, and the auditor agent has no shell tool to set the variable — I confirmed the gate returns **rc=0 (allow)** on a realistic Kiro payload, so `AGENTS.md`'s declared constraint that the `requirements-auditor` must not modify generated pipeline artifacts is **unenforced in Kiro**. Beyond that: all six non-auditor agent JSONs declare Claude tool names (`read`, `write`, `glob`, `grep`) and resources under a `skills/` directory that does not exist in this repo; the four conditional steering files use Claude's `paths:` front-matter instead of Kiro's `inclusion: fileMatch` + `fileMatchPattern`, so all 15 steering files load unconditionally (~31 KB every turn); the Phase 1 gate logic is duplicated between `phase_gate.py` and `scripts/kiro_workflow.py` and has **already drifted** — the hook blocks `workloads/customer_orders` while the driver passes it; and `.kiro/steering/01-human-gate-examples.md` describes a `config/` + `.discovery_complete` gate that the actual `enforce_template_codegen.py` does not implement.

Compounding all of this, the repo's own checks pass clean (`validate_integrations.py` → PASS, `sync_platforms.py check` → PASS, `pytest core/tests/test_kiro_integration.py` → 8 passed). They only assert file existence and JSON parseability, and the Kiro tests assert the *upstream* contract (`returncode == 0` + deny JSON on stdout) rather than Kiro's exit-2 contract — so `adop-hook.sh`, the single most load-bearing file in the adapter, has **zero test coverage**, and none of the defects below are detectable by CI.

---

## 2. Findings table

| # | Sev | File / Line | Issue | Why it is wrong | Suggested fix |
|---|---|---|---|---|---|
| F1 | **HIGH** | `.kiro/hooks/adop-gates.json:30,43,70,81,92` | All write-facing PreToolUse/PostToolUse hooks use `"matcher": "fs_write\|write"` | `matcher` is a regex over the **tool name**. It matches `fs_write` only. Kiro's `str_replace`, `fs_append`, `delete_file` are distinct tools and never match, so an agent editing via `str_replace` bypasses the credential gate, the codegen gate, the auditor gate, and artifact validation. The scripts already *handle* `new_str` (via the launcher's key normalisation) — only the matcher excludes them. | `"matcher": "fs_write\|str_replace\|fs_append\|delete_file"` |
| F2 | **HIGH** | `.kiro/hooks/auditor_write_gate.py:40-48` | Actor identified from `ADOP_AGENT_NAME` env var, `payload.agent_name`, or `tool_input.agent_name` | Kiro's PreToolUse payload is `{"tool_name":…,"tool_input":{…}}` — it carries no `agent_name`, and hook processes inherit Kiro's environment, not the agent's. `requirements-auditor.json:5` instructs the agent to "Set ADOP_AGENT_NAME=…", but its `tools` are `["fs_read","fs_write"]` — no shell. **Verified: rc=0 (allow) on a realistic payload.** `AGENTS.md:280` and `manifest.yaml:92-96` declare this constraint as mandatory. | Gate on the write path itself for any actor (deny non-auditor paths only when the run is in audit phase), or have Kiro's agent definition carry the scope. Do not rely on an env var the constrained party must set. |
| F3 | **HIGH** | `.kiro/agents/{dag,iac,metadata,ontology,quality,transformation}-agent.json` → `tools` | 6 of 7 agents declare `["read","write","glob","grep"]` (ontology adds `"shell"`) | These are **Claude Code** tool names. Kiro's are `fs_read`/`fs_write`/`grep_search`/`file_search`/`execute_bash` — as `requirements-auditor.json:9-12` correctly uses. An allowlist of non-existent tools cannot restrict anything, so `02-architecture.md:32` ("Sub-agents do NOT have MCP access — enforced by the `tools` list in `.kiro/agents/*.json`, not by convention") is false. `ontology-agent`'s `"shell"` also contradicts `02-architecture.md:33` ("file-only and has no MCP/AWS access"). | Rename to Kiro tool names; drop `shell` from `ontology-agent`. |
| F4 | **HIGH** | `.kiro/agents/*.json` → `resources` (6 files, 18 refs) | All reference `file://skills/pipeline-conventions/SKILL.md`, `file://skills/decision-engine/SKILL.md`, `file://skills/data-compliance/SKILL.md` | **No `skills/` directory exists at the repo root** (`ls -d skills` → No such file or directory). These skills live only at `.codex/skills/`. Every sub-agent loads zero of its three declared knowledge resources. Only `requirements-auditor.json` has resolving resources (`core/requirements-auditor.md`, `core/shared/requirements/auditor.py` — both verified present). | Point at `.codex/skills/…` if that is the canonical location, or vendor the three SKILL.md files under a path Kiro can read. |
| F5 | **HIGH** | `.kiro/hooks/phase_gate.py:103-112` vs `scripts/kiro_workflow.py:166-170` | Phase 1 gate logic duplicated and already drifted | `kiro_workflow.py` special-cases `ontology_opt_in` to accept any boolean; `phase_gate.py` still runs it through `_nonempty()`, which rejects `False`. **Verified on the real workload:** `phase_gate.py` → `rc=2 BLOCKED: … ontology_opt_in is missing`; `kiro_workflow.py gate --workload customer_orders` → `PHASE 1 PASS`. `git diff` confirms the fix landed in the driver only. An opted-out workload is permanently blocked by the hook. | Extract one gate implementation into `shared/` and have both call it. |
| F6 | **MEDIUM** | `.kiro/steering/{03,04,05,08}.md` front-matter | Uses `paths:` (e.g. `03-python-airflow.md:2-7`) | `paths:` is Claude's key, copied verbatim (`diff` confirms 03/04/05/08 are **byte-identical** to `.claude/rules/`). Kiro expects `inclusion: fileMatch` + `fileMatchPattern: '<glob>'`. Unrecognised front-matter means these fall back to always-included, so the intended conditional loading never happens. | Convert to Kiro front-matter, one `fileMatchPattern` per file. |
| F7 | **MEDIUM** | `.kiro/steering/` (all 15 files) | Every file loads on every interaction (~31 KB / ~630 lines) | 11 files have no front-matter (always-on by design) and the other 4 are always-on by accident (F6). Nothing uses `inclusion: manual` or `inclusion: auto`. Reference material — `09-glossary.md`, `10-ascii-stages.md`, `00-zone-questions.md` (196 lines), `14-strands-runtime.md` (optional runtime) — is paid for on every turn. | Keep the gate/architecture rules always-on; move glossary, ASCII blocks, and the Strands runtime to `inclusion: auto` with `name`+`description`. |
| F8 | **MEDIUM** | `.kiro/steering/01-human-gate-examples.md:28-31` | Describes a gate that does not exist | Claims `enforce_template_codegen.py` "denies any `fs_write` under `workloads/{name}/{config,scripts,dags,sql}/` for a workload that has neither `config/source.yaml` nor a `.discovery_complete` marker", and that its deny message ends with "create `workloads/{name}/.discovery_complete` to proceed". The actual script (`enforce_template_codegen.py:30`, `PROTECTED = re.compile(r"workloads/[^/]+/(scripts\|dags\|sql)/")`) covers **only** scripts/dags/sql, **unconditionally**, and its own docstring says "What is NOT blocked: config/". There is no marker logic and the deny message points at `render.sh`. | Rewrite the section against the current script, or restore the marker behaviour if that was the intent. |
| F9 | **MEDIUM** | `.kiro/hooks/adop-gates.json:81-100` | `adop-validate-artifacts-post` cannot do the job its own description claims | Description: covers "content that reached disk by a route with no `tool_input` (a bash heredoc, say)". A bash heredoc runs through `execute_bash`, which `matcher: "fs_write\|write"` never matches. The stated purpose is unreachable. | Add a second PostToolUse entry with `matcher: "execute_bash"`, or use `PostFileSave` (whose matcher is tested against the **file path**, e.g. `workloads/.*`). |
| F10 | **MEDIUM** | `.kiro/hooks/adop-hook.sh:48-55` | Hard dependency on `jq`; degrades to fail-open | Without `jq` the launcher prints a warning to stderr and skips key normalisation. `block_credentials.py:70-74` then reads `content`/`new_string` from a payload that only has `text`, finds nothing, and exits 0 — the file's own comment documents this exact failure ("it saw an empty body and allowed writes carrying AWS keys"). The warning goes to stderr on an exit-0 path, where Kiro discards it. | Do the normalisation in Python (already a hard dependency) instead of `jq`, or exit 2 when `jq` is absent so the gate fails closed. |
| F11 | **MEDIUM** | `.kiro/hooks/adop-hook.sh:76-96` | Advisory output is silently dropped | `validate_artifacts.py:206` emits `{"systemMessage": …}` for non-blocking findings (missing DAG `retries`, missing lineage flag). The launcher only forwards `additionalContext` or a deny reason; everything else is discarded and it exits 0 with no stdout. **Verified:** a DAG missing `retries` produced `rc=0` and zero output. All WARN-tier guidance is invisible. | Echo `$OUT`'s `systemMessage` on stdout before `exit 0` — Kiro forwards PreToolUse exit-0 stdout. |
| F12 | **MEDIUM** | `.kiro/hooks/adop-gates.json:52-67` | `matcher: "Agent\|agent\|spawn_agent"` on the Phase 1 gate | No tool by any of those names appears in Kiro's documented tool surface. The matcher is derived from `02-architecture.md:35` ("spawned by name via the `Agent` tool"), which is Claude's model. If no such tool exists, **the Phase 1 discovery gate never fires** — the single most important guardrail in ADOP. See *Not verified* §6: I could not confirm Kiro's agent-invocation tool name. | Confirm the real tool name against Kiro docs. If sub-agent invocation is not a tool call, move the gate to `PreTaskExec` (which supports exit-2 blocking) or depend on `kiro_workflow.py gate` as the enforcement point. |
| F13 | **MEDIUM** | `.kiro/hooks/` vs `.codex/hooks/`, `.claude/hooks/`, `.amazonq/hooks/` | No `log_conversation.py` | All three other harnesses wire a PostToolUse `AskUserQuestion` hook to log the human Q&A into the requirements ledger. Kiro has none, yet `00-zone-questions.md:3` and `01-human-gate-examples.md:37-38` tell the agent to use `AskUserQuestion`. Discovery Q&A is never captured, which is exactly the evidence `requirements-auditor` blocks promotion on. | Decide whether Kiro exposes an equivalent. If not, make `12-requirements-audit.md`'s `scripts/capture_user_turn.py` fallback the documented primary path, not the fallback. |
| F14 | **MEDIUM** | root docs | `AGENTS.md`, `SKILLS.md`, `TOOL_ROUTING.md`, `MCP_GUARDRAILS.md`, `ADOP_WORKFLOWS.md` contain **zero** occurrences of "Kiro" | `grep -i kiro` returns nothing in any of the five. These are the canonical rule sources — including the non-negotiable security rules at `AGENTS.md:69-72` and the mandatory-codegen rule at `AGENTS.md:164`. Kiro loads only `.kiro/steering/`, so unless a rule is restated there, Kiro never sees it. There is no `KIRO.md` to match `CLAUDE.md` / `AGENTS.md` / `AmazonQ.md`. | Add a steering file carrying the security + codegen invariants verbatim, and add Kiro rows to the harness tables in those five docs. |
| F15 | **MEDIUM** | `scripts/validate_integrations.py:40-52`, `core/tests/test_kiro_integration.py` | Validation cannot catch any of F1–F13 | The validator checks only existence + `json.loads`. The tests assert `returncode == 0` and deny-JSON-on-stdout — the *upstream* contract, not Kiro's exit-2 contract — and never invoke `adop-hook.sh`, the file that performs the translation. All checks pass today. | Add schema validation for trigger names and a matcher-vs-known-Kiro-tool-names check; add tests that pipe payloads through `adop-hook.sh` and assert `rc == 2`. |
| F16 | **LOW** | `.kiro/settings/mcp.optional.json` | Not a file Kiro reads | Kiro reads `.kiro/settings/mcp.json` only. The 16 optional servers (all 13 canonical ones present — verified against `tool-registry/servers.yaml`) are inert, and no `.kiro/` file or steering doc explains how to activate them. Equivalent to the other harnesses' optional profiles, so arguably by design — but undocumented for Kiro. | Add a note in `02-architecture.md` on merging entries into `mcp.json`, or ship a `scripts/` helper. |
| F17 | **LOW** | `.kiro/settings/mcp.optional.json` → `snowflake-native`, `databricks-native` | No `command`; use `{"type":"http","url":"${…}","headers":{…}}` | Kiro's documented server shape is `command`/`args`/`env`/`disabled`/`autoApprove`. Whether Kiro supports an HTTP transport with `${VAR}` interpolation in `url`/`headers` is unconfirmed (see §6). No hardcoded secret is present — all three third-party entries use `${VAR}` placeholders, which **passes** the `AGENTS.md:69-72` security rules. | Verify Kiro's HTTP-transport support; mark both `"disabled": true` explicitly rather than relying on absence. |
| F18 | **LOW** | `scripts/kiro_workflow.py:210` vs `.kiro/hooks/enforce_template_codegen.py:82` | Two different renderer paths | The driver shells out to `adapters/kiro/.kiro/adop/render.sh` (the portable snapshot); the deny message tells the agent to run `.kiro/adop/render.sh` (the live surface). `manifest.yaml:40` names the snapshot path. Both files exist and both work (`render.py --list` → rc=0), so this is confusing rather than broken. | Standardise on `.kiro/adop/render.sh` for in-repo use. |
| F19 | **LOW** | `adapters/kiro/workloads/unknown_workload/.requirements_pending/requirements.jsonl` | Committed test output that grows on every test run | 18 identical `"prompt": "hello"` records, written by `test_packaged_kiro_capture_is_standalone`. Tracked in git (commit `a9e622c`) and shows as ` M` after any test run, dirtying the tree. | Point the test at `tmp_path` and remove the file from version control. |
| F20 | **LOW** | `.kiro/hooks/auditor_write_gate.py:22-33` | Duplicate paths in the deny reason | `_paths()` appends both `file_path` and `path`; the launcher's normalisation sets `file_path` **from** `path`, so both are present and identical. Observed: `attempted: workloads/demo/config/source.yaml, workloads/demo/config/source.yaml`. | `break` after the first hit (as `enforce_template_codegen.py:_target_paths` already does), or de-duplicate. |
| F21 | **LOW** | `.kiro/steering/14-strands-runtime.md` | Untracked (`git status` → `??`) | Steering 14 and its `adapters/kiro/` twin are uncommitted, so a fresh clone gets 14 steering files, not 15. The two copies have also already diverged (3 trailing lines present in `.kiro/`, absent in the snapshot). | Commit both, or drop them until the Strands path is settled. |
| F22 | **INFO** | `.kiro/steering/02-architecture.md:35`, `13-workflow-orchestrator.md:24`, `00-zone-questions.md:3`, `01-human-gate-examples.md:37-38` | References to `Agent`, `SendMessage`, `AskUserQuestion` as Kiro tools | These are Claude Code tool names surviving the port. They are what produced F3, F12, and F13. No `.codex/…` or `.claude/…` *path* leaks exist in `.kiro/` — I grepped and the only hits are two comment lines in `validate_artifacts.py:59,66` listing vendoring locations, which is harmless. | Replace with Kiro's actual mechanisms once F12 is resolved. |

---

## 3. Per-area detail

### 3.1 Hook correctness

**Schema and triggers: correct.** All 8 entries in `.kiro/hooks/adop-gates.json` use valid PascalCase triggers (`UserPromptSubmit`, `SessionStart`, 5× `PreToolUse`, `PostToolUse`), `action.type: "command"`, and the `{"version":"v1","hooks":[…]}` envelope. `python3 -m json.tool` parses every JSON file under `.kiro/` without error. This is a real adaptation, not a copy — compare `.codex/hooks.json` (nested `{"hooks":{"PreToolUse":[{"hooks":[…],"matcher":…}]}}`, matcher `apply_patch`) and `.claude/settings.json` (same nesting, matchers `Edit|Write`, `Write|Edit|MultiEdit`). Neither shape appears in the Kiro file.

**Script paths and permissions.** Only the launcher is executable; the gates are invoked as `python3 "$HOOK"` so their mode bits do not matter:

```
-rw-r--r--  adop-gates.json
-rwxr-xr-x  adop-hook.sh
-rw-r--r--  auditor_write_gate.py  block_credentials.py  capture_user_turn.py
-rw-r--r--  enforce_template_codegen.py  inject_run_context.py  phase_gate.py  validate_artifacts.py
-rw-r--r--  .kiro/adop/render.py
-rwxr-xr-x  .kiro/adop/render.sh
```

All 8 referenced scripts exist. Commands are relative (`.kiro/hooks/adop-hook.sh <script>`), which depends on Kiro invoking hooks with the workspace root as cwd — the launcher defends against this by resolving `HOOK_DIR` from `${BASH_SOURCE[0]}` (`adop-hook.sh:28`), so the *gate* resolves correctly even if cwd differs; only the launcher's own relative invocation would fail.

**Exit-code contract: handled, by the launcher, not the scripts.** None of the five blocking gates calls `sys.exit(2)`. Every one prints `{"hookSpecificOutput":{"permissionDecision":"deny",…}}` (or `{"decision":"block",…}` for `validate_artifacts.py:208`) on stdout and exits 0 — which, raw, would fail open in Kiro. `adop-hook.sh:85-93` greps for either JSON form and converts it:

```bash
if printf '%s' "$OUT" | grep -qE '"(permissionDecision"[[:space:]]*:[[:space:]]*"deny|decision"[[:space:]]*:[[:space:]]*"block)"'; then
  REASON=$(… jq -r '.hookSpecificOutput.permissionDecisionReason // .reason // empty' …)
  printf '%s\n' "$REASON" >&2
  exit 2
fi
```

I verified all five through the launcher with Kiro-native payloads (`{"tool_name":…,"tool_input":{"path":…,"text":…}}`):

| Gate | Payload | Result |
|---|---|---|
| `block_credentials.py` | `workloads/demo/config/source.yaml` + `aws_secret_access_key: AKIA…` | **rc=2**, reason on stderr |
| `enforce_template_codegen.py` | `workloads/demo/dags/x.py` | **rc=2**, reason on stderr |
| `phase_gate.py` | `{"workload_name":"no_such"}` | **rc=2**, "run/context.json is missing" |
| `auditor_write_gate.py` | `{"agent_name":"requirements-auditor", …}` | **rc=2**, scope reason |
| `validate_artifacts.py` | `workloads/demo/scripts/x.py` + `def (` | **rc=2**, "Python syntax error" |

So the contract is satisfied *when the hook fires*. The defects are upstream of that: F1 (matcher excludes `str_replace`/`fs_append`/`execute_bash`), F2 (actor never identified), F10 (`jq` dependency), F11 (advisory output dropped), F12 (`Agent` matcher may not exist).

**F2, demonstrated.** With no `agent_name` in the payload — Kiro's actual shape — the auditor gate allows a write to a generated artifact:

```
$ printf '%s' '{"tool_name":"fs_write","tool_input":{"path":"workloads/demo/scripts/evil.py","text":"x=1"}}' \
    | ./.kiro/hooks/adop-hook.sh auditor_write_gate.py
rc=0 (ALLOWED)

$ ADOP_AGENT_NAME=requirements-auditor … same payload …
rc=2
BLOCKED: requirements-auditor may write only run/requirements_audit.json, …
```

`auditor_write_gate.py:40-48` is the cause:

```python
actor = (os.environ.get("ADOP_AGENT_NAME") or payload.get("agent_name")
         or tool_input.get("agent_name") or "")
if str(actor).lower().replace("_", "-") != "requirements-auditor":
    print("{}")   # allow
    return
```

`requirements-auditor.json:5` tries to compensate — *"Set ADOP_AGENT_NAME=requirements-auditor for every write operation"* — but `tools` is `["fs_read","fs_write"]`, so the agent has no way to set an environment variable, and a hook subprocess inherits Kiro's environment regardless. The constraint is advisory text, not a gate.

**F5, demonstrated.** Same workload, two verdicts:

```
$ printf '%s' '{"tool_name":"Agent","tool_input":{"workload_name":"customer_orders"}}' \
    | ./.kiro/hooks/adop-hook.sh phase_gate.py
rc=2
BLOCKED: Phase 1 human discovery gate is incomplete for workloads/customer_orders:
  human_answers.ontology_opt_in is missing

$ python3 scripts/kiro_workflow.py gate --workload customer_orders
PHASE 1 PASS: customer_orders
```

`workloads/customer_orders/run/context.json` has `human_answers.ontology_opt_in = False` — a legitimate opt-out. `git diff scripts/kiro_workflow.py` shows the fix, applied to the driver only:

```diff
     for field in COMMON:
-        if not _nonempty(answers.get(field)):
+        if field == "ontology_opt_in":
+            if not isinstance(answers.get(field), bool):
+                blockers.append("human_answers.ontology_opt_in is required and must be boolean")
+        elif not _nonempty(answers.get(field)):
             blockers.append(f"human_answers.{field} is required")
```

`git diff -- .kiro/hooks/phase_gate.py` is empty: the hook still carries the pre-fix logic, where `_nonempty(False)` → `False`. Two copies of a gate, one fix.

**Payload parsing: correct, thanks to the launcher.** The gates natively expect Claude's `file_path`/`content`/`new_string`. `adop-hook.sh:51-58` adds Kiro's `path`→`file_path`, `text`→`content`, `new_str`→`new_string` without renaming anything in the shared scripts. `validate_artifacts.py:230-231` additionally reads Kiro's keys directly (`("text","content","new_str","new_string")`). I confirmed a `str_replace`-shaped payload (`{"new_str": "password = \"hunter22\""}`) is inspected correctly and denied — the content handling is ready for `str_replace`; only the matcher excludes it. That is what makes F1 a one-line fix with a large blast radius.

**One divergence worth crediting:** `.kiro/hooks/` carries four gates that no other harness has — `block_credentials.py`, `validate_artifacts.py`, `phase_gate.py`, `auditor_write_gate.py`. `.codex/hooks/` has `discovery_gate`, `logging_gate`, `enforce_template_codegen`, `inject_run_context`, `log_conversation`, `patch_paths`. The Kiro set is a deliberate extension, and `enforce_template_codegen.py:12-21` documents a genuine security improvement over upstream (removing the `ADOP_RENDERER_TOKEN` bypass, on the reasoning that anything able to export the variable includes the agent being constrained). This adapter had real thought put into it. The gaps are in binding, not in intent.

### 3.2 Steering correctness

**Front-matter.** 11 files have none → always included, which is correct for gate and architecture rules. The 4 conditional files use `paths:`:

```
.kiro/steering/03-python-airflow.md:1-7
---
paths:
  - "workloads/**/*.py"
  - "shared/**/*.py"
  - "dags/**/*.py"
  - "scripts/**/*.py"
---
```

`diff` against `.claude/rules/03-python-airflow.md` is empty — byte-identical, including the front-matter. Same for 04, 05, 08. Kiro's keys are `inclusion` (`always`/`fileMatch`/`manual`/`auto`), `fileMatchPattern`, and `name`+`description` for `auto`. No file uses any of them. Net effect: all 15 load unconditionally (F6, F7). Nothing uses `inclusion: manual` or `inclusion: auto`, so the `#` context key and on-demand activation are both unavailable.

**`#[[file:…]]` references.** `grep -rn '#\[\[file:' .kiro/` returns nothing. No broken references, and no use of the mechanism either — which is a missed opportunity for `11-shared-run-context.md` to point at `contracts/v1/run_context.schema.json`.

**Cross-harness leaks.** No `.codex/` or `.claude/` *path* references in steering. The leaks are tool names (F22):

- `02-architecture.md:34-35` — *"sub-agents defined in `.kiro/agents/` and spawned by name via the `Agent` tool. Sub-agents cannot spawn peers (no `Agent`/`SendMessage` in their toolset)."*
- `13-workflow-orchestrator.md:24` — *"The phase hook denies `Agent` calls until the context and completion marker pass the same checks as the driver."*
- `00-zone-questions.md:3` — *"Use `AskUserQuestion` tool when possible."*
- `01-human-gate-examples.md:37-38` — *"the only party holding `AskUserQuestion` … Every sub-agent is launched without `AskUserQuestion` (the harness strips it regardless of frontmatter)"*

The parenthetical in the last one ("the harness strips it regardless of frontmatter") is a statement about Claude Code's behaviour, carried into Kiro steering unexamined.

**Factual drift against the code (F8).** `01-human-gate-examples.md:28-31` describes `enforce_template_codegen.py` as covering `{config,scripts,dags,sql}` conditional on a `config/source.yaml` or `.discovery_complete` marker. The script's own docstring contradicts this: *"What is NOT blocked: config/ (specs live there and must be writable)"*, and `PROTECTED = re.compile(r"workloads/[^/]+/(scripts|dags|sql)/")` with no marker check anywhere. The paragraph was adapted from Claude's `check-discovery-gate.sh` — `diff` against `.claude/rules/01-human-gate-examples.md` shows exactly one changed line (the script name and `Write`/`Edit`→`fs_write`), while the behavioural description underneath was left describing the old script.

**Divergence from `.claude/rules/` and `.amazonq/rules/`.** 11 of 13 numbered files are byte-identical between `.kiro/steering/` and `.claude/rules/`; only 01, 02, and 12 were edited for Kiro, and all three edits are substantive and correct in direction (02 swaps `.claude/agents/*.md` → `.kiro/agents/*.json` and documents the ontology agent as file-only; 12 replaces the Claude-hook narrative with the `scripts/capture_user_turn.py` fallback). Drift direction on `.amazonq/rules/`: it is the laggard — 11 files, missing 10, 11, 12-era updates in 8 others; `.kiro/steering/` is the most complete rule set in the repo at 15 files. Kiro is ahead, not behind, on steering *content*. It is behind on steering *mechanics*.

### 3.3 Feature parity gaps

**Agents: name parity is complete.** `{dag, iac, metadata, ontology, quality, requirements-auditor, transformation}` — all 7 present as `.codex/agents/*.toml`, `.claude/agents/*.md`, and `.kiro/agents/*.json`. `.amazonq/cli-agents/` restructures into 10 differently-named profiles. No agent is missing from Kiro.

**Content parity: prompts preserved, metadata broken.** `iac-agent.json`'s prompt is 14,103 characters and retains the full hard-won deploy knowledge (KMS principal ordering, the Bronze-table-over-Parquet-not-CSV section, the `glue:GetDatabase on default` Spark bootstrap probe, the `DenyUnEncryptedObjectUploads` null-condition trap). Nothing was lost in translation. What broke is everything around the prompt — `tools` (F3) and `resources` (F4). `.codex/agents/references/*-domain.md` has no Kiro counterpart; that content is inlined into the prompts instead, which is a reasonable adaptation.

**`requirements-auditor` constraints: partially enforced.** `AGENTS.md:280` and `manifest.yaml:92-96` require: no AWS, no MCP, no network, no modification of generated pipeline artifacts.

| Constraint | Kiro status |
|---|---|
| No AWS / MCP / network | **Satisfied** — `tools: ["fs_read","fs_write"]`, no `mcpServers` key, no shell |
| No modification of generated artifacts | **NOT enforced** — see F2; the only mechanism is `auditor_write_gate.py`, which cannot identify the actor |
| Resources resolve | **Satisfied** — the one agent whose `resources` are correct |
| Tool names correct | **Satisfied** — the one agent using `fs_read`/`fs_write` |

**Workflow / command entry points: thinner than the brief assumed, but not absent.** There is no `.kiro/workflows/` and no `.kiro/specs/`, so Kiro's two native orchestration features are both unused. The onboarding entry point is `scripts/kiro_workflow.py` (`init` / `gate` / `audit` / `status` / `render`), which exists, works, and is what `13-workflow-orchestrator.md` documents — so that steering file is **not** describing something nonexistent, it is describing a shell driver rather than a workflow definition. The gap is at the edges:

| Capability | `.claude/commands/` | `.codex/skills/` | `.kiro/` |
|---|---|---|---|
| Onboarding | `onboard-workflow.md` | `command-onboard-workflow/` | `scripts/kiro_workflow.py` + steering 13 |
| DevOps / production readiness | `devops-workflow.md` | `command-devops-workflow/` | **none** — `iac-agent` exists, no driver |
| Security review | `security-review.md` | `command-security-review/` | **missing entirely** |
| Strands runtime | `strands-run.md` | `strands-runtime/` | steering 14 only (doc, untracked — F21) |

`README.md:230` claims Kiro's production-readiness path is *"Kiro DevOps agent after workload gates"* — the agent exists but has no invocation path comparable to `/devops-workflow`; and `README.md:233` says the native definitions live under "`.claude/commands/`, `.codex/skills/`, `.amazonq/cli-agents/`, and `.kiro/`", which overstates what `.kiro/` contains. Security review has no Kiro surface at all.

**Hooks parity.** Kiro has four gates the others lack (§3.1) and lacks one they all have: `log_conversation.py` (F13), present at `.codex/hooks/`, `.claude/hooks/`, `.amazonq/hooks/`.

### 3.4 `.kiro/adop/render.py` and `render.sh`

**Not dead code, and not a duplicate.** `render.py` is a 150-line argparse CLI that imports the shared engine:

```python
from shared.codegen.renderer import render
from shared.codegen.spec_loader import load_spec
```

`_bundle_root()` (`render.py:14-26`) walks up for `shared/codegen/renderer.py`, falling back to the vendored `plugins/claude-code/lib/` copy. It contributes a `TEMPLATES` map (template_id → spec stem, contract name, VERSION key) and reads versions from `shared/templates/VERSION`. No rendering logic is reimplemented, so `AGENTS.md:164`'s mandatory-deterministic-codegen rule is respected rather than bypassed. Verified working:

```
$ python3 .kiro/adop/render.py --list
ADOP Kiro renderer:
  airflow_dag          config/dag.yaml  dag      DAG_TEMPLATE_VERSION=1.4.0
  bronze_ingestion     config/bronze.yaml  bronze   TRANSFORMATION_TEMPLATE_VERSION=1.6.0
  glue_job_config      config/dag.yaml  dag      TEMPLATE_VERSION=1.3.0
  gold_aggregate       config/gold.yaml  gold     TRANSFORMATION_TEMPLATE_VERSION=1.6.0
  iceberg_ddl          config/silver.yaml  silver   TEMPLATE_VERSION=1.3.0
  quality_check        config/quality.yaml  quality  QUALITY_RULES_TEMPLATE_VERSION=1.4.0
  silver_transform     config/silver.yaml  silver   TRANSFORMATION_TEMPLATE_VERSION=1.6.0
rc=0
```

`render.sh` is a 4-line `exec python3` wrapper that resolves its own directory — correct and cwd-independent.

**Wired from three places, two of which disagree (F18):** `enforce_template_codegen.py:82` deny message → `.kiro/adop/render.sh`; `scripts/kiro_workflow.py:210` `render()` → `adapters/kiro/.kiro/adop/render.sh`; `manifest.yaml:40` `kiro_renderer` → the snapshot path. Both files exist, so nothing is broken. Notably, Kiro is the **only** harness with a dedicated renderer CLI — a parity advantage, not a duplication problem.

### 3.5 MCP config

**Syntax and schema: valid.** Both files parse. `.kiro/settings/mcp.json` uses the correct Kiro shape and is content-identical to `.mcp.json` and `.amazonq/mcp.json`:

```json
{"mcpServers":{"aws-mcp":{"command":"uvx","args":["mcp-proxy-for-aws==1.6.0",
  "https://aws-mcp.us-east-1.api.aws/mcp","--metadata","AWS_REGION=us-east-1"]}}}
```

Pinned version, no secrets, no account IDs. `scripts/validate_integrations.py:check_default_mcp_profiles` enforces exactly this and passes.

**Canonical coverage: complete.** `tool-registry/servers.yaml` lists 13 servers (3 REQUIRED: glue-athena, lakeformation, iam; 5 WARN; 5 OPTIONAL). Set difference against `mcp.json` ∪ `mcp.optional.json`: **registry-minus-Kiro is empty**. Kiro adds 4 beyond the registry — `aws-mcp` (the default proxy) and the three third-party providers, matching every other harness's optional profile.

**Binaries / packages.** The 8 PyPI servers use `uvx --from awslabs-<x>-mcp-server`; the 4 custom ones use `uv run … mcp-servers/<x>-server/server.py` — I confirmed `mcp-servers/` exists with those server directories. I did not attempt to resolve the PyPI names (no network use in a read-only audit).

**Secrets: clean.** `grep -rnE 'AKIA[0-9A-Z]{16}|\b[0-9]{12}\b|vpc-[0-9a-f]{8}|s3://…'` over `.kiro/` returns **no hits**. The only `env` values are `FASTMCP_LOG_LEVEL: ERROR` and `${TERADATA_DATABASE_URI}`; the two HTTP providers use `${SNOWFLAKE_MCP_URL}` / `Bearer ${SNOWFLAKE_MCP_TOKEN}` and the Databricks equivalents. Fully compliant with `AGENTS.md:69-72`. See F17 on whether Kiro expands `${VAR}` and supports `type: "http"`.

**The inert-file problem (F16).** Kiro reads `.kiro/settings/mcp.json` only. Nothing in `.kiro/` tells a user how to promote entries from `mcp.optional.json`, and `02-architecture.md:4-13`'s diagram shows a DEFAULT/DEMO/OPTIONAL tiering whose activation path is `scripts/mcp_demo.py` — a Claude/Codex-era helper.

### 3.6 Docs accuracy

**`grep -i kiro` across the root docs:**

| Doc | Kiro mentions |
|---|---|
| `README.md` | 7 (lines 15, 24, 56-57, 72, 230, 233, 266) |
| `docs/platform-integration.md` | 3 (lines 7, 19, 39) |
| `manifest.yaml` | 6 entries |
| `AGENTS.md` | **0** |
| `SKILLS.md` | **0** |
| `TOOL_ROUTING.md` | **0** |
| `MCP_GUARDRAILS.md` | **0** |
| `ADOP_WORKFLOWS.md` | **0** |

That table is F14. The five silent docs are where the invariants live, and Kiro cannot read any of them (it loads `.kiro/steering/` only — unlike Codex, which reads `AGENTS.md` natively). The non-negotiable security rules at `AGENTS.md:69-72` and the mandatory-codegen rule at `AGENTS.md:164` reach Codex and, via `CLAUDE.md`, Claude. They do not reach Kiro.

**Accurate claims.** `README.md:24,56-57` (`python3 scripts/kiro_workflow.py init --workload <name>`) — verified, the script exists and `init`/`gate`/`audit`/`status`/`render` all resolve. `docs/platform-integration.md:19,39` (`.kiro/` as the Kiro entry point) — accurate.

**Overstated claims.** `README.md:230` (devops path = "Kiro DevOps agent after workload gates") — the agent exists, the invocation path does not. `README.md:233` ("native definitions are under … `.kiro/`") — there is no Kiro workflow or command definition, only steering 13 describing a CLI.

**`manifest.yaml`.** The `kiro` adapter block (lines 26-31) lists 3 entrypoints: `mcp.json`, `requirements-auditor.json`, `adop-gates.json`. It never mentions `.kiro/steering/` — 15 files and the largest part of the adapter — nor the other 6 agents or 7 hook scripts. The `shared:` block (lines 33-45) does cover `kiro_workflow`, `kiro_renderer`, `kiro_phase_gate`. `clone_ready` (line 54) lists `CLAUDE.md`, `AGENTS.md`, `AmazonQ.md` and the four config dirs — correctly noting there is no `KIRO.md`, which is consistent with Kiro's conventions but means the asymmetry in F14 is baked into the manifest.

**Files no doc mentions:** `.kiro/steering/*` (all 15), `.kiro/hooks/adop-hook.sh` (the critical translation layer), `block_credentials.py`, `validate_artifacts.py`, `enforce_template_codegen.py`, `inject_run_context.py`, `capture_user_turn.py`, `.kiro/settings/mcp.optional.json`, and 6 of the 7 agent JSONs.

### 3.7 Security rules compliance

Against `AGENTS.md:69-72`:

1. **No hardcoded secrets** — compliant. No hits across `.kiro/`.
2. **No infrastructure details in code** — compliant. No account IDs, VPC/subnet IDs, or bucket names. `iac-agent.json`'s prompt uses `${AWS::AccountId}` / `!Sub` / `!Ref` throughout; the one literal-looking S3 path is the illustrative `s3://.../raw/<dataset>/`.
3. **Least-privilege IAM** — the `iac-agent` prompt is unusually strong here: it explains *why* `glue:CreateDatabase` cannot be scoped to a database name, instructs the agent not to present it as least-privilege if granted, and documents the `database/default` Spark bootstrap probe as a metadata-only grant with a comment so a later tightening pass does not remove it.

**`block_credentials.py` assessment.** The detection logic is good — four patterns including a YAML-assignment pattern the file documents as a deliberate divergence from upstream (upstream's three `key = "value"` patterns miss `key: value`, and every ADOP spec is YAML). It correctly excludes `${…}`, `$VAR`, `arn:aws:`, `<…>`, `{{…}}`, `CHANGE_ME`, `TODO`, `null`, `~`, `[]`. Verified blocking: rc=2 on `aws_secret_access_key: AKIAIOSFODNN7EXAMPLE`.

**But it does block only what it sees, and three things narrow that:**

- **F1** — `matcher: "fs_write|write"` misses `str_replace` and `fs_append`. A credential introduced by editing an existing file is never inspected. (I confirmed the script *handles* a `str_replace` payload correctly; only the matcher excludes it.)
- **F10** — no `jq` → no normalisation → `_pending_content()` reads `content`/`new_string` from a payload carrying only `text`, gets `""`, and returns allow at `block_credentials.py:88-90`. The file's own comment describes this having happened.
- **Scope** — `block_credentials.py:84-86` returns allow for any path without `workloads/` in it. Documented and defensible (a PreToolUse deny on `.env.example` would be disruptive), but it means a secret written to `shared/`, `contracts/`, or `.kiro/` is not gated.

With `jq` present and a `fs_write` call, the gate works. Those are both conditions, not guarantees.

---

## 4. Parity matrix

| Capability | `.codex` | `.claude` | `.amazonq` | `.kiro` |
|---|---|---|---|---|
| **Agents** | present (7 toml + 7 domain refs) | present (7 md) | present (10 json, restructured) | **partial** — 7 json, names and prompts complete; `tools` use Claude names (F3), 18 of 21 `resources` unresolvable (F4) |
| **Hooks — wiring** | present (`hooks.json`) | present (`settings.json`) | partial (shell, no manifest) | **present** — correct Kiro v1 schema, valid triggers, exit-2 translated by `adop-hook.sh` |
| **Hooks — binding** | present | present | partial | **partial** — matchers miss `str_replace`/`fs_append`/`execute_bash` (F1); `Agent` matcher unverifiable (F12) |
| **Hooks — conversation logging** | present | present | present | **missing** (F13) |
| **Steering / rules** | via `AGENTS.md` + skills | present (13) | partial (11; missing 10, 11) | **partial** — 15 files, the most complete content in the repo; mechanics wrong (`paths:` not `inclusion`, F6; all always-on, F7; one section factually stale, F8) |
| **Workflows — onboarding** | present (skill) | present (command) | present (orchestrator agent) | **partial** — `scripts/kiro_workflow.py` + steering 13; no `.kiro/workflows/`, no `.kiro/specs/` |
| **Workflows — devops** | present | present | present | **partial** — agent exists, no driver |
| **Workflows — security review** | present | present | partial (`adop-reviewer`) | **missing** |
| **Workflows — strands** | present (skill) | present (command) | missing | **partial** — steering 14 only, untracked (F21) |
| **Skills** | present (10) | n/a (inlined) | n/a (inlined) | **missing** — and 6 agents reference `file://skills/…` anyway (F4) |
| **MCP — default** | present (TOML) | present | present | **present**, valid, pinned, no secrets |
| **MCP — optional** | present | present | present | **present but inert** — Kiro reads only `mcp.json` (F16); 2 entries use an unverified HTTP shape (F17) |
| **Codegen** | shared engine | shared engine + vendored copy | shared engine | **present** — only harness with a dedicated CLI (`render.py`/`render.sh`), correctly delegating to `shared/codegen/` |
| **Validation / CI** | structural | structural | structural | **inadequate** — existence + JSON parse only; `adop-hook.sh` untested (F15) |

---

## 5. Conclusions and recommendations

The Kiro adapter is not a blind copy. Someone understood Kiro's exit-code contract, wrote a launcher to bridge it, documented why (`adop-hook.sh:16-24`), removed a real security bypass from the upstream codegen gate, and added four gates no other harness has. Judged on intent and on the hard part — the hook schema and the block contract — it is the most carefully built adapter in the repo.

Judged on whether the guardrails actually hold, it has three failures that each independently defeat a stated invariant:

1. **The matchers** (F1). One regex, five hooks, four tools unguarded. Lowest-effort, highest-value fix in the audit.
2. **The auditor actor check** (F2). `AGENTS.md`'s "must not modify generated pipeline artifacts" is text, not a gate, in Kiro.
3. **The agent `tools` lists** (F3). `02-architecture.md` claims MCP denial is "enforced by the `tools` list … not by convention." It is convention.

And one structural failure that will keep producing new defects: **the Phase 1 gate exists twice** (F5), the copies have already diverged in the one commit of history this repo has, and `validate_integrations.py` cannot see it.

### Recommended order

**Fix first (correctness, small diffs):**
1. F1 — widen the matchers to `fs_write|str_replace|fs_append|delete_file`.
2. F5 — extract one Phase 1 gate into `shared/` and call it from both `phase_gate.py` and `kiro_workflow.py`.
3. F3 / F4 — Kiro tool names in all 7 agent JSONs; repoint or vendor the three SKILL.md resources; drop `shell` from `ontology-agent`.
4. F2 — re-found the auditor scope on something Kiro actually supplies. If Kiro cannot attribute a tool call to a sub-agent, say so in the steering rather than shipping a gate that always allows.

**Then (resilience and honesty):**
5. F10 — move normalisation into Python; fail closed if it cannot run.
6. F11 — forward `systemMessage` on stdout so WARN findings are visible.
7. F15 — test through `adop-hook.sh` asserting `rc == 2`; add a schema check for trigger names and a matcher-vs-known-tool-names check.
8. F8 — rewrite `01-human-gate-examples.md:28-31` against the current script.
9. F12 — resolve the `Agent` matcher question. If there is no such tool, the Phase 1 hook is decorative and `kiro_workflow.py gate` is the only real gate — which should be stated plainly in steering 13.

**Then (parity and context budget):**
10. F6 / F7 — convert the 4 `paths:` files to `inclusion: fileMatch` + `fileMatchPattern`; move glossary, ASCII blocks, and Strands to `inclusion: auto`.
11. F14 — add a steering file carrying `AGENTS.md`'s security and codegen invariants verbatim; add Kiro rows to the five silent docs.
12. F13 — decide Kiro's discovery-Q&A capture story and make `12-requirements-audit.md` reflect it.
13. Security review and devops entry points — or document their absence.
14. F16–F21 — housekeeping: MCP activation docs, the two HTTP entries, renderer path, the committed test ledger, commit steering 14.

One broader note: the three substantive Kiro edits to steering (01, 02, 12) are all correct in direction, and the 11 untouched files are byte-identical to `.claude/rules/`. The port was done file-by-file and stopped at the files whose *prose* mentioned Claude, missing the files whose *front-matter* did. A mechanical check — "does any `.kiro/` file contain a token from another harness's vocabulary" — would have caught F3, F6, and F22 in one pass, and is worth adding to `validate_integrations.py` as a standing guard.

---

## 6. Not verified

Stated explicitly rather than guessed:

1. **Whether Kiro exposes an agent-invocation tool named `Agent`, `agent`, or `spawn_agent`** (F12). The platform facts I was given list `fs_write`, `str_replace`, `fs_append`, `read_file`, `execute_bash`, `delete_file`, `grep_search`, `file_search`, `list_directory` — no agent-spawn tool. I did not consult live Kiro documentation. If no such tool exists, the Phase 1 gate never fires, which would upgrade F12 to HIGH. **This is the single most important open question in the audit.**
2. **Whether `str_replace` and `fs_append` are distinct tool names in the Kiro build in use, or modes of a single `fs_write` tool.** F1 assumes distinct, per the facts given. If they are modes of `fs_write`, F1 narrows to `execute_bash` and `delete_file` only. I verified the *payload handling* works for `str_replace`-shaped input; I could not verify the tool-name surface.
3. **Whether Kiro's `UserPromptSubmit` payload uses `prompt` / `user_prompt` (snake) or `userPrompt` (camel).** `shared/requirements/capture.py:135-141` tries `user_prompt`, `prompt`, `message`, `text`, `content` — not camelCase. If Kiro sends `userPrompt`, capture silently records nothing. Related and also unverified: `detect_workload` (`capture.py:30-52`) falls back to cwd-path inspection, so in a repo-root session with no `ADOP_WORKLOAD` exported it resolves to `"unknown"` and `capture_turn` returns `None` — no record. The hook's own description in `adop-gates.json:14` hedges on `SessionStart` not firing during testing, so this surface was evidently already shaky.
4. **Whether Kiro supports `"type": "http"` MCP servers and expands `${VAR}` in `url` / `headers` / `env`** (F17). Affects `snowflake-native`, `databricks-native`, `teradata`.
5. **Whether Kiro honours `timeout`, `enabled`, and `description` in a hook entry.** `.kiro/hooks/adop-gates.json` sets all three on every entry. They are plausible but not in the schema I was given. Harmless if ignored; `enabled: false` silently not honoured would matter.
6. **Whether a PostToolUse hook exiting 2 surfaces its stderr.** `adop-validate-artifacts-post` will exit 2 via the launcher when `validate_artifacts.py` hard-blocks. Per the contract, exit 2 is meaningful only for PreToolUse / UserPromptSubmit / PreTaskExec, so the advisory message is probably dropped. Did not confirm.
7. **Runtime behaviour inside Kiro IDE.** Everything here comes from reading the files and from executing the hook scripts with synthetic stdin. No hook was observed firing in a live Kiro session, so claims about *whether* a hook fires rest on the platform facts, not on observation. Claims about *what a hook does when it fires* are empirically verified.
8. **PyPI package existence** for the 8 `uvx --from awslabs-*-mcp-server` servers. No network calls were made.
9. **`adapters/kiro/` snapshot staleness beyond the two files I diffed.** `diff -rq .kiro adapters/kiro/.kiro` reports only `02-architecture.md` and `14-strands-runtime.md` differing; I read both diffs. The `02` divergence is substantive — the snapshot has a REQUIRED/WARN/OPTIONAL MCP tiering and no demo-profile paragraph, the live copy has DEFAULT/DEMO/OPTIONAL and a `scripts/mcp_demo.py` instruction — but which is intended, I cannot determine.

---

## 7. Addendum — open questions resolved by the orchestrator (2026-10-26)

The investigator could not confirm Kiro's live tool surface. The orchestrating session runs *inside* Kiro, so its own available tool list is direct evidence. Three items from §6 are now closed.

**§6.1 — is there an `Agent` / `spawn_agent` tool? NO. F12 upgrades to HIGH.**
The Kiro session tool surface contains no agent-invocation tool by any of the names `Agent`, `agent`, or `spawn_agent`. Sub-agent dispatch in Kiro happens through `run_workflow` (workflow steps naming a registered agent), and that tool is available **only to the top-level orchestrator session** — it is explicitly refused inside workflow step sessions. Consequences:

- `adop-gates.json:52-67` `matcher: "Agent|agent|spawn_agent"` matches no tool name, so **the Phase 1 discovery gate never fires in Kiro**. Per the investigator's own criterion ("If no such tool exists, the Phase 1 gate never fires, which would upgrade F12 to HIGH"), this is now HIGH — and it is the most important guardrail in ADOP.
- `scripts/kiro_workflow.py gate` is therefore the *only* real Phase 1 enforcement point. Steering 13 should say so plainly.
- If hook-based enforcement is wanted, the trigger to use is `PreTaskExec` (spec-task execution, supports exit-2 blocking) or `PreToolUse` with `matcher: "run_workflow"`. Note the latter only covers orchestrator-initiated dispatch.
- The Kiro-native mechanism for sub-agent constraints is the workflow definition plus the registered agent's own config, not a tool allowlist intercepted at dispatch time.

**§6.2 — are `str_replace` and `fs_append` distinct tools? YES. F1 stands at full scope.**
`fs_write`, `str_replace`, `fs_append`, and `delete_file` are four separate tools, not modes of one. F1 does not narrow: `matcher: "fs_write|write"` leaves edits via `str_replace` and appends via `fs_append` completely ungated, and the recommended widening to `fs_write|str_replace|fs_append|delete_file` is correct as written. (`execute_bash` is also distinct, confirming F9.)

**§6 related — `AskUserQuestion` does not exist in Kiro. F13 confirmed, and F22's steering references are dead.**
There is no `AskUserQuestion` tool. In Kiro the orchestrator asks the user by emitting a normal message and waiting for the reply. So:
- `00-zone-questions.md:3` ("Use `AskUserQuestion` tool when possible") instructs the agent to call a nonexistent tool.
- `01-human-gate-examples.md:37-38` ("the only party holding `AskUserQuestion`", "the harness strips it regardless of frontmatter") describes Claude Code mechanics that have no Kiro analogue.
- A PostToolUse hook matching `AskUserQuestion` could never fire, so F13's gap cannot be closed by porting the other harnesses' `log_conversation.py` as-is. The `scripts/capture_user_turn.py` + `UserPromptSubmit` path is the only viable capture route in Kiro and should be documented as primary, not fallback.

**§6.5 — partially resolved.** `timeout` (seconds, default 60) and `description` are both supported on a command hook entry. `enabled` remains unverified; treat `enabled: false` as not reliably honoured and remove entries instead of disabling them.

**Still open:** §6.3 (`UserPromptSubmit` payload key casing), §6.4 (MCP `type: "http"` and `${VAR}` expansion), §6.6 (PostToolUse exit-2 stderr surfacing), §6.7 (live in-IDE hook firing), §6.8 (PyPI package existence), §6.9 (`adapters/kiro/` snapshot intent).
