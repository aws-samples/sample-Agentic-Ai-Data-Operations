"""ADOP SPARQL/NL Query Agent — Bedrock AgentCore Runtime.

Self-contained 5-tool agent that translates natural language to SPARQL,
validates against the OWL ontology via OBQC, and executes against Ontop VKG.

Tools:
  - extract_terms       — Parse NL question -> entity / metric / class terms
  - get_ontology_slice  — Fetch relevant OWL slice from OpenSearch (kNN over Titan v2)
  - validate_sparql     — Call OBQC Lambda to check OWL semantics
  - execute_sparql      — Call ontop-via-VPC Lambda to run against Ontop VKG
  - repair_sparql       — Re-prompt model with errors to produce corrected SPARQL

Targets ADOP infrastructure deployed via the Phase 7 CDK stack. Endpoints
and Lambda function names come from runtime env vars (set on the AgentCore
runtime by the deploy script).
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Any

import boto3
import requests
from requests_aws4auth import AWS4Auth

from bedrock_agentcore.runtime import BedrockAgentCoreApp

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# -----------------------------------------------------------------------------
# Configuration (env vars override SSM)
# -----------------------------------------------------------------------------
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))
OBQC_FN = os.environ.get("OBQC_FUNCTION_NAME", "adop-semantic-obqc")
EXEC_FN = os.environ.get("EXEC_SPARQL_FUNCTION_NAME", "adop-semantic-smoke")
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")
OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "ontology-slices")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "amazon.titan-embed-text-v2:0")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
LLM_MODEL = os.environ.get(
    "LLM_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
NAMESPACE = os.environ.get("NAMESPACE", "http://adop.example.org/ontology#")
PREFIX = os.environ.get("PREFIX", "adop")
MAX_REPAIR_ATTEMPTS = int(os.environ.get("MAX_REPAIR_ATTEMPTS", "3"))

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)


def _ssm_lookup_endpoint() -> None:
    """Resolve OPENSEARCH_ENDPOINT from SSM if not already set."""
    global OPENSEARCH_ENDPOINT
    if not OPENSEARCH_ENDPOINT:
        try:
            OPENSEARCH_ENDPOINT = ssm.get_parameter(
                Name="/adop-semantic/opensearch-endpoint"
            )["Parameter"]["Value"]
        except Exception:
            # Optional — falls back to env var; if empty, slice retrieval will fail loudly
            pass


_ssm_lookup_endpoint()


# -----------------------------------------------------------------------------
# Tool 1: extract_terms — model-driven term extraction
# -----------------------------------------------------------------------------
def extract_terms(question: str) -> dict:
    """Use Claude to extract salient terms from the NL question."""
    prompt = (
        "Extract the salient terms from this natural-language question for "
        "ontology lookup. Return JSON with keys: classes (concept types like "
        "'company', 'sector'), entities (specific names like 'Apple', "
        "'Technology'), metrics (numeric attributes), temporal (time refs). "
        "Be terse, JSON only.\n\nQuestion: " + question
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = bedrock.invoke_model(modelId=LLM_MODEL, body=json.dumps(body))
    text = json.loads(resp["body"].read())["content"][0]["text"]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {"classes": [], "entities": [], "metrics": [], "temporal": [], "raw": text}


# -----------------------------------------------------------------------------
# Tool 2: get_ontology_slice — OpenSearch kNN against ontology-slices
# -----------------------------------------------------------------------------
def _embed(text: str) -> list[float]:
    body = json.dumps(
        {"inputText": text, "dimensions": EMBED_DIM, "normalize": True}
    )
    resp = bedrock.invoke_model(modelId=EMBED_MODEL, body=body)
    return json.loads(resp["body"].read())["embedding"]


def _aoss_auth() -> AWS4Auth:
    creds = boto3.Session().get_credentials().get_frozen_credentials()
    return AWS4Auth(
        creds.access_key, creds.secret_key, REGION, "aoss",
        session_token=creds.token,
    )


def _aoss_request(method: str, path: str, body: dict | None = None) -> dict:
    if not OPENSEARCH_ENDPOINT:
        raise RuntimeError("OPENSEARCH_ENDPOINT not configured")
    url = OPENSEARCH_ENDPOINT.rstrip("/") + path
    r = requests.request(
        method,
        url,
        auth=_aoss_auth(),
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_ontology_slice(question: str, top_k: int = 5) -> dict:
    """Retrieve the top-K most relevant ontology classes for the NL question."""
    qvec = _embed(question)
    body = {
        "size": top_k,
        "_source": ["iri", "label", "text"],
        "query": {"knn": {"embedding": {"vector": qvec, "k": top_k}}},
    }
    res = _aoss_request("POST", f"/{OPENSEARCH_INDEX}/_search", body)
    hits = res.get("hits", {}).get("hits", [])
    return {
        "matches": [
            {
                "label": h["_source"]["label"],
                "iri": h["_source"]["iri"],
                "score": h.get("_score"),
                "slice": h["_source"]["text"],
            }
            for h in hits
        ]
    }


# -----------------------------------------------------------------------------
# Tool 3: validate_sparql — call OBQC Lambda
# -----------------------------------------------------------------------------
def validate_sparql(sparql: str) -> dict:
    resp = lam.invoke(
        FunctionName=OBQC_FN,
        Payload=json.dumps({"sparql_query": sparql}).encode(),
    )
    return json.loads(resp["Payload"].read())


# -----------------------------------------------------------------------------
# Tool 4: execute_sparql — proxy through smoke Lambda (inside VPC -> Ontop ALB)
# -----------------------------------------------------------------------------
def execute_sparql(sparql: str) -> dict:
    resp = lam.invoke(
        FunctionName=EXEC_FN,
        Payload=json.dumps({"sparql": sparql}).encode(),
    )
    return json.loads(resp["Payload"].read())


# -----------------------------------------------------------------------------
# Tool 5: repair_sparql
# -----------------------------------------------------------------------------
def repair_sparql(question: str, sparql: str, errors: list[dict], slice_text: str) -> str:
    err_summary = "\n".join(
        f"- {e.get('rule', '?')}: {e.get('message', '?')}" for e in errors
    )
    prompt = (
        f"You wrote this SPARQL for the question, but OBQC found errors. "
        f"Produce a corrected SPARQL query.\n\n"
        f"Question: {question}\n\n"
        f"Original SPARQL:\n{sparql}\n\n"
        f"OBQC errors:\n{err_summary}\n\n"
        f"Relevant ontology:\n{slice_text}\n\n"
        f"Return only the corrected SPARQL, no markdown fences or commentary."
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = bedrock.invoke_model(modelId=LLM_MODEL, body=json.dumps(body))
    text = json.loads(resp["body"].read())["content"][0]["text"]
    return _strip_md(text)


_SLICE_TOOL_SPEC = {
    "toolSpec": {
        "name": "get_ontology_slice",
        "description": (
            "Fetch ontology slices via vector search. Each slice describes "
            "one class: its datatype properties and its outgoing/incoming "
            "object relationships. Call this multiple times to traverse the "
            "navigation graph until you have every property and link the "
            "query needs."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 4},
                },
                "required": ["query"],
            }
        },
    }
}


def generate_sparql(question: str, initial_slices: list[dict], max_slice_calls: int = 4) -> tuple[str, list[dict]]:
    """Generate SPARQL via a tool-calling loop. The model retrieves more slices
    as it discovers links it doesn't have full information on. Returns the
    SPARQL string and the cumulative list of slices fetched.
    """
    initial_slice_text = "\n\n".join(s["slice"] for s in initial_slices)
    slice_history: list[dict] = list(initial_slices)

    system = [
        {
            "text": (
                f"You translate natural-language questions into SPARQL 1.1 "
                f"queries. The ontology uses namespace {NAMESPACE} with prefix "
                f"`{PREFIX}:`.\n\n"
                "Use only class IRIs and property IRIs that appeared verbatim "
                "in the slices you have seen. Do not invent or paraphrase "
                "names. Each slice shows the class's own datatype properties "
                "plus a navigation graph of outgoing and incoming object "
                "relationships. If the navigation graph references a linked "
                "class whose properties you also need, call "
                "get_ontology_slice with that class name to retrieve them. "
                "Repeat as needed.\n\n"
                "Once you have every property and relationship the query "
                "requires, output ONLY the SPARQL — no markdown fences, no "
                "commentary, no explanation."
            )
        }
    ]

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "text": (
                        f"Question: {question}\n\n"
                        f"Initial slices:\n{initial_slice_text}\n\n"
                        "Call get_ontology_slice if you need more context. "
                        "Otherwise produce the SPARQL."
                    )
                }
            ],
        }
    ]

    calls_made = 0
    for _ in range(max_slice_calls + 3):
        resp = bedrock.converse(
            modelId=LLM_MODEL,
            messages=messages,
            system=system,
            toolConfig={"tools": [_SLICE_TOOL_SPEC]},
            inferenceConfig={"maxTokens": 1500, "temperature": 0.0},
        )
        out = resp["output"]["message"]
        messages.append(out)
        if resp.get("stopReason") != "tool_use":
            text = "\n".join(c.get("text", "") for c in out["content"] if "text" in c)
            return _strip_md(text), slice_history

        tool_results = []
        for c in out["content"]:
            tu = c.get("toolUse")
            if not tu or tu["name"] != "get_ontology_slice":
                continue
            calls_made += 1
            if calls_made > max_slice_calls:
                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tu["toolUseId"],
                            "content": [{"text": "Slice budget exhausted. Produce the SPARQL with what you have."}],
                        }
                    }
                )
                continue
            new_slices = get_ontology_slice(
                tu["input"]["query"], top_k=tu["input"].get("top_k", 4)
            ).get("matches", [])
            slice_history.extend(new_slices)
            new_text = "\n\n".join(s["slice"] for s in new_slices) or "(no matches)"
            tool_results.append(
                {
                    "toolResult": {
                        "toolUseId": tu["toolUseId"],
                        "content": [{"text": new_text}],
                    }
                }
            )
        messages.append({"role": "user", "content": tool_results})

    last_text = ""
    for m in reversed(messages):
        if m.get("role") == "assistant":
            for c in m.get("content", []):
                if "text" in c:
                    last_text = c["text"]
                    break
            break
    return _strip_md(last_text), slice_history


def _strip_md(text: str) -> str:
    """Extract only the SPARQL query from a model response.

    Strategy:
    1. If a fenced code block is present, take its contents.
    2. Find the latest occurrence of a query-form keyword (SELECT, ASK,
       CONSTRUCT, DESCRIBE) at the start of a line. Walk backwards through
       any preceding PREFIX/BASE declarations to find the true start.
    3. Ensure the configured PREFIX declaration is present at the top — the
       model sometimes omits it. We always need it for Ontop to resolve
       prefixed names.
    """
    s = text.strip()

    fence = re.search(r"```(?:sparql)?\s*\n?(.*?)```", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()

    pattern = re.compile(
        r"(?:^|\n)\s*(PREFIX|BASE|SELECT|ASK|CONSTRUCT|DESCRIBE)\b"
    )
    matches = list(pattern.finditer(s))
    if matches:
        last = matches[-1]
        start = last.start()
        while True:
            preceding = s[:start].rstrip()
            m_prev = re.search(
                r"(?:^|\n)\s*(PREFIX|BASE)\b[^\n]*$", preceding
            )
            if not m_prev:
                break
            start = m_prev.start()
        s = s[start:]

    s = s.strip()

    # Ensure the configured PREFIX is declared. If the SPARQL uses prefixed
    # names with our PREFIX but no PREFIX line, prepend one.
    prefix_decl = f"PREFIX {PREFIX}: <{NAMESPACE}>"
    if (
        f"{PREFIX}:" in s
        and not re.search(rf"^\s*PREFIX\s+{re.escape(PREFIX)}:\s*<", s, re.MULTILINE)
    ):
        s = f"{prefix_decl}\n{s}"

    return s


# -----------------------------------------------------------------------------
# AgentCore HTTP entrypoint
# -----------------------------------------------------------------------------
app = BedrockAgentCoreApp()


@app.entrypoint
def handler(event: dict, context: Any | None = None) -> dict:
    """AgentCore runtime entry. event is the request body parsed as JSON."""
    question = (
        event.get("question")
        or event.get("prompt")
        or event.get("input", {}).get("question")
        if isinstance(event.get("input"), dict)
        else None
    )
    question = question or event.get("question")
    if not question:
        return {"error": "event.question is required"}

    trace: dict[str, Any] = {"question": question, "steps": []}

    try:
        terms = extract_terms(question)
        trace["steps"].append({"tool": "extract_terms", "result": terms})

        slices = get_ontology_slice(question, top_k=4).get("matches", [])
        trace["steps"].append(
            {
                "tool": "get_ontology_slice",
                "result": [{"label": s["label"], "score": s["score"]} for s in slices],
            }
        )

        sparql, slices = generate_sparql(question, slices)
        trace["steps"].append({"tool": "generate_sparql", "result": sparql, "slice_count": len(slices)})

        for attempt in range(MAX_REPAIR_ATTEMPTS):
            v = validate_sparql(sparql)
            trace["steps"].append(
                {"tool": "validate_sparql", "attempt": attempt, "result": v}
            )
            if v.get("pass"):
                break
            if attempt + 1 >= MAX_REPAIR_ATTEMPTS:
                trace["status"] = "validation_failed"
                trace["final_sparql"] = sparql
                return trace
            slice_text = "\n\n".join(s["slice"] for s in slices)
            sparql = repair_sparql(
                question, sparql, v.get("errors", []), slice_text
            )
            trace["steps"].append(
                {"tool": "repair_sparql", "attempt": attempt, "result": sparql}
            )

        result = execute_sparql(sparql)
        trace["steps"].append({"tool": "execute_sparql", "result": result})
        trace["status"] = "success"
        trace["final_sparql"] = sparql
        trace["bindings"] = (
            result.get("body", {}).get("results", {}).get("bindings", [])
        )
        return trace
    except Exception as e:
        logger.error("Agent error: %s", e, exc_info=True)
        trace["status"] = "error"
        trace["error"] = str(e)
        return trace


if __name__ == "__main__":
    app.run()
