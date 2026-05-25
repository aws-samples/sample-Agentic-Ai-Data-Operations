#!/usr/bin/env python3
"""Interactive prompt -> ADOP SPARQL agent -> answer.

Cross-platform (Windows / macOS / Linux). Bypasses the `agentcore invoke`
CLI to avoid Windows command-line argument quoting issues. Calls
boto3.invoke_agent_runtime directly and streams progress as the agent
emits each step.

Usage:
    python semantic-layer/scripts/ask_agent.py
    python semantic-layer/scripts/ask_agent.py "Your question here"

Agent ARN resolution order (first match wins):
    1. --agent-arn / -a CLI flag
    2. ADOP_AGENT_ARN environment variable
    3. semantic-layer/deployment_manifest.json -> endpoints.agent_runtime_arn
       (rejected if it contains the <ACCOUNT_ID> placeholder; deploy the
       semantic layer or set ADOP_AGENT_ARN explicitly)

Region resolution: AWS_REGION env var, falling back to us-west-2.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import boto3


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "semantic-layer" / "deployment_manifest.json"
PLACEHOLDER = "<ACCOUNT_ID>"


def resolve_agent_arn(cli_arg: str | None) -> str:
    if cli_arg:
        return cli_arg
    env = os.environ.get("ADOP_AGENT_ARN")
    if env:
        return env
    if not DEFAULT_MANIFEST.exists():
        sys.exit(
            f"deployment_manifest.json not found at {DEFAULT_MANIFEST}.\n"
            "Either deploy the semantic layer (Phase 7) or set $ADOP_AGENT_ARN."
        )
    manifest = json.loads(DEFAULT_MANIFEST.read_text())
    arn = manifest.get("endpoints", {}).get("agent_runtime_arn", "")
    if not arn or PLACEHOLDER in arn:
        sys.exit(
            f"agent_runtime_arn in {DEFAULT_MANIFEST} is missing or contains {PLACEHOLDER}.\n"
            "Set $ADOP_AGENT_ARN to your deployed runtime ARN, e.g.:\n"
            "  export ADOP_AGENT_ARN=arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/adop_sparql_agent-XXXXXXX"
        )
    return arn


def make_session_id() -> str:
    # AgentCore requires session id length >= 33
    return f"ask-agent-{int(time.time())}-{uuid.uuid4().hex[:12]}"


def render_step(step: dict, started_at: float) -> str:
    tool = step.get("tool", "?")
    elapsed = time.monotonic() - started_at
    line = f"  [{elapsed:5.1f}s] {tool}"
    if tool == "extract_terms":
        r = step.get("result", {})
        line += f": entities={r.get('entities', [])} metrics={r.get('metrics', [])}"
    elif tool == "get_ontology_slice":
        labels = [m.get("label") for m in step.get("result", []) if isinstance(m, dict)]
        line += f": matched {labels}"
    elif tool == "validate_sparql":
        res = step.get("result", {})
        if res.get("pass"):
            line += f" attempt={step.get('attempt', 0)} -> PASS"
        else:
            errs = [e.get("rule") for e in res.get("errors", [])]
            line += f" attempt={step.get('attempt', 0)} -> FAIL {errs}"
    elif tool == "generate_sparql":
        line += f": slice_count={step.get('slice_count', '?')}"
    elif tool == "execute_sparql":
        r = step.get("result", {})
        if "error" in r:
            line += f": ERROR {r['error']}"
        else:
            nrows = len(r.get("body", {}).get("results", {}).get("bindings", []))
            line += f": {nrows} rows returned"
    elif tool == "repair_sparql":
        line += f" attempt={step.get('attempt', 0)}"
    return line


def render_steps(trace: dict, already_shown: int, started_at: float) -> int:
    steps = trace.get("steps", [])
    for step in steps[already_shown:]:
        print(render_step(step, started_at), flush=True)
    return len(steps)


def spinner(stop: threading.Event, started_at: float) -> None:
    chars = "|/-\\"
    i = 0
    while not stop.is_set():
        sys.stdout.write(f"\r  thinking ... {chars[i % 4]} {time.monotonic() - started_at:.1f}s  ")
        sys.stdout.flush()
        i += 1
        time.sleep(0.2)
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()


def invoke(question: str, agent_arn: str, region: str) -> dict[str, Any]:
    client = boto3.client("bedrock-agentcore", region_name=region)
    started = time.monotonic()
    print(f"\n[asking] {question}\n", flush=True)

    stop_evt = threading.Event()
    spin = threading.Thread(target=spinner, args=(stop_evt, started), daemon=True)
    spin.start()

    resp = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=make_session_id(),
        payload=json.dumps({"question": question}).encode(),
    )

    buffer = b""
    seen_steps = 0
    spinner_stopped = False
    last_progress = time.monotonic()

    for chunk in resp["response"].iter_chunks(chunk_size=4096):
        if not chunk:
            continue
        if not spinner_stopped:
            stop_evt.set()
            spin.join(timeout=1)
            spinner_stopped = True
        buffer += chunk
        try:
            partial = json.loads(buffer)
            seen_steps = render_steps(partial, seen_steps, started)
        except json.JSONDecodeError:
            if time.monotonic() - last_progress > 1.5:
                print(f"  [{time.monotonic()-started:5.1f}s] receiving... ({len(buffer)} bytes)", flush=True)
                last_progress = time.monotonic()

    if not spinner_stopped:
        stop_evt.set()
        spin.join(timeout=1)

    try:
        trace = json.loads(buffer)
    except json.JSONDecodeError:
        print("\n[raw response could not be parsed as JSON]")
        print(buffer.decode(errors="replace")[:2000])
        return {}

    seen_steps = render_steps(trace, seen_steps, started)

    print()
    print("=" * 78)
    print(f"Status: {trace.get('status', 'unknown')}  ({time.monotonic() - started:.1f}s total)")
    print()

    bindings = trace.get("bindings") or []
    if not bindings:
        last_step = (trace.get("steps") or [{}])[-1]
        bindings = last_step.get("result", {}).get("body", {}).get("results", {}).get("bindings", [])

    if bindings:
        print("Answer:")
        for row in bindings:
            for k, v in row.items():
                print(f"  {k}: {v.get('value', '')}")
            print()
    else:
        print("No bindings returned. Final SPARQL:")
        print(trace.get("final_sparql", "(none)"))

    if trace.get("final_sparql") and bindings:
        print("=" * 78)
        print("SPARQL:")
        print(trace["final_sparql"])
    print("=" * 78)
    return trace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "question", nargs="?",
        help="Natural-language question. If omitted, prompt interactively.",
    )
    parser.add_argument(
        "--agent-arn", "-a",
        help="Agent runtime ARN (overrides ADOP_AGENT_ARN and deployment_manifest.json).",
    )
    parser.add_argument(
        "--region", "-r",
        default=os.environ.get("AWS_REGION", "us-west-2"),
        help="AWS region (default: $AWS_REGION or us-west-2).",
    )
    args = parser.parse_args()

    agent_arn = resolve_agent_arn(args.agent_arn)
    question = args.question or input("Question: ").strip()
    if not question:
        print("No question provided.", file=sys.stderr)
        return 1

    invoke(question, agent_arn, args.region)
    return 0


if __name__ == "__main__":
    sys.exit(main())
