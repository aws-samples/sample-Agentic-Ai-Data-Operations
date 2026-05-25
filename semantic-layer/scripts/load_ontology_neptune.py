#!/usr/bin/env python3
"""Load semantic-layer/ontology.ttl into Neptune via the loader Lambda.

The Lambda's `update` action takes raw SPARQL. We convert the local TTL into
a SPARQL `INSERT DATA` statement and dispatch it. Suitable for ontologies
that fit in one POST (small T-Box).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import boto3
from rdflib import Graph

REGION = os.environ.get("AWS_REGION", "us-west-2")
LOADER_FN = "adop-semantic-neptune-loader"
ONTOLOGY_PATH = Path(__file__).resolve().parents[1] / "ontology.ttl"


def main() -> int:
    g = Graph()
    g.parse(ONTOLOGY_PATH, format="turtle")
    print(f"Loaded {len(g)} triples from {ONTOLOGY_PATH.name}")

    # Serialize to N-Triples (each line = one triple, easy to fold into INSERT DATA)
    nt = g.serialize(format="nt").strip()
    sparql = f"INSERT DATA {{\n{nt}\n}}"

    lam = boto3.client("lambda", region_name=REGION)
    resp = lam.invoke(
        FunctionName=LOADER_FN,
        Payload=json.dumps({"action": "update", "sparql": sparql}).encode(),
    )
    body = json.loads(resp["Payload"].read().decode())
    print(json.dumps(body, indent=2)[:1000])
    if "error" in body:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
