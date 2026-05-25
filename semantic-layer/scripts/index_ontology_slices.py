#!/usr/bin/env python3
"""Chunk semantic-layer/ontology.ttl into per-class slices,
embed each via Bedrock Titan v2, and bulk-index into OpenSearch Serverless.

One slice per OWL class. Slice text:
  Class label, comment.
  Datatype properties (name, range, comment) where this class is rdfs:domain.
  Object properties (name, range, comment) to neighbor classes.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import boto3
from rdflib import Graph, OWL, RDF, RDFS, URIRef
from rdflib.namespace import XSD
from requests_aws4auth import AWS4Auth
import requests

REGION = os.environ.get("AWS_REGION", "us-west-2")
COLLECTION_NAME = "adop-semantic-slices"
INDEX_NAME = "ontology-slices"
EMBED_MODEL = "amazon.titan-embed-text-v2:0"
EMBED_DIM = 1024

ONTOLOGY_PATH = Path(__file__).resolve().parents[1] / "ontology.ttl"


def get_collection_endpoint() -> str:
    aoss = boto3.client("opensearchserverless", region_name=REGION)
    cols = aoss.batch_get_collection(names=[COLLECTION_NAME])["collectionDetails"]
    if not cols:
        raise SystemExit(f"Collection {COLLECTION_NAME} not found")
    return cols[0]["collectionEndpoint"]


def aws_auth() -> AWS4Auth:
    creds = boto3.Session().get_credentials().get_frozen_credentials()
    return AWS4Auth(
        creds.access_key, creds.secret_key, REGION, "aoss",
        session_token=creds.token,
    )


def _local(uri) -> str:
    s = str(uri)
    if "#" in s:
        return s.rsplit("#", 1)[1]
    return s.rsplit("/", 1)[-1]


def slice_class(g: Graph, cls: URIRef) -> dict:
    """Per-class slice with own properties + the navigation graph.

    Generic: walks the ontology with rdflib, no domain knowledge embedded.
    Includes:
      - own datatype properties (where rdfs:domain == this class)
      - outgoing object properties (this class -> target class)
      - incoming object properties (other class -> this class)
    The model can use the navigation graph to decide which neighboring
    classes to fetch next via additional get_ontology_slice calls.
    """
    label = next(iter(g.objects(cls, RDFS.label)), None) or _local(cls)
    comment = next(iter(g.objects(cls, RDFS.comment)), None)
    iri = str(cls)

    dt_props = []
    outgoing = []  # (predicate_local, target_class_local)
    incoming = []  # (source_class_local, predicate_local)

    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        if (prop, RDFS.domain, cls) in g:
            pname = _local(prop)
            prng = next(iter(g.objects(prop, RDFS.range)), XSD.string)
            pcom = next(iter(g.objects(prop, RDFS.comment)), "")
            dt_props.append(f"  - {pname} ({_local(prng)}): {pcom}")

    for prop in g.subjects(RDF.type, OWL.ObjectProperty):
        domains = set(g.objects(prop, RDFS.domain))
        ranges = set(g.objects(prop, RDFS.range))
        pname = _local(prop)
        if cls in domains:
            for rng in ranges:
                outgoing.append((pname, _local(rng)))
        if cls in ranges:
            for dom in domains:
                if dom != cls:
                    incoming.append((_local(dom), pname))

    parts = [f"Class: {label}", f"IRI: {iri}"]
    if comment:
        parts.append(f"Description: {comment}")
    if dt_props:
        parts.append("Datatype properties (use as predicate with subject of this class):")
        parts.extend(dt_props)
    if outgoing:
        parts.append("Outgoing relationships (this class is the subject):")
        for p, t in outgoing:
            parts.append(f"  - {p} -> {t}")
    if incoming:
        parts.append("Incoming relationships (this class is the object):")
        for s, p in incoming:
            parts.append(f"  - {s} {p} -> this class")
    if outgoing or incoming:
        parts.append(
            "Use get_ontology_slice again on the linked class names above "
            "if you need their datatype properties."
        )

    return {
        "iri": iri,
        "label": str(label),
        "text": "\n".join(parts) + "\n",
    }


def embed(text: str) -> list[float]:
    bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({"inputText": text, "dimensions": EMBED_DIM, "normalize": True}),
    )
    return json.loads(resp["body"].read())["embedding"]


def ensure_index(endpoint: str, auth: AWS4Auth) -> None:
    url = f"{endpoint}/{INDEX_NAME}"
    r = requests.head(url, auth=auth, timeout=20)
    if r.status_code == 200:
        print(f"Index {INDEX_NAME} exists; deleting + recreating for clean re-index")
        requests.delete(url, auth=auth, timeout=20)
        time.sleep(3)
    body = {
        "settings": {"index.knn": True},
        "mappings": {
            "properties": {
                "iri": {"type": "keyword"},
                "label": {"type": "keyword"},
                "text": {"type": "text"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": EMBED_DIM,
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss",
                        "space_type": "cosinesimil",
                    },
                },
            }
        },
    }
    r = requests.put(url, auth=auth, json=body, timeout=30)
    print(f"create index status={r.status_code}, body={r.text[:200]}")
    r.raise_for_status()


def index_slice(endpoint: str, auth: AWS4Auth, doc: dict) -> None:
    # AOSS allows POST /<index>/_doc only (no _bulk in serverless dataplane for some types)
    url = f"{endpoint}/{INDEX_NAME}/_doc"
    r = requests.post(url, auth=auth, json=doc, timeout=30)
    if r.status_code not in (200, 201):
        print(f"  WARN status={r.status_code}: {r.text[:200]}")
    r.raise_for_status()


def main() -> int:
    g = Graph()
    g.parse(ONTOLOGY_PATH, format="turtle")
    print(f"Parsed {len(g)} triples")

    classes = list(g.subjects(RDF.type, OWL.Class))
    print(f"Found {len(classes)} OWL classes")

    endpoint = get_collection_endpoint()
    print(f"OpenSearch endpoint: {endpoint}")
    auth = aws_auth()

    ensure_index(endpoint, auth)

    indexed = 0
    for cls in classes:
        slc = slice_class(g, cls)
        emb = embed(slc["text"])
        doc = {**slc, "embedding": emb}
        index_slice(endpoint, auth, doc)
        print(f"  + indexed {slc['label']} ({len(slc['text'])} chars)")
        indexed += 1

    print(f"\nIndexed {indexed} slices into {INDEX_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
