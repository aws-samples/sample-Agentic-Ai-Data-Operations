"""
Neptune Loader Lambda.

Runs inside the VPC to load ontology triples into Neptune DB and proxy
SPARQL queries/constructs from the agent. Uses SigV4 signing for IAM auth.

Actions:
  - update: Execute a SPARQL UPDATE (INSERT DATA, DELETE WHERE, etc.)
  - query:  Execute a SPARQL SELECT and return bindings
  - construct: Execute a SPARQL CONSTRUCT and return Turtle
"""

import json
import os
import urllib.request
import urllib.parse
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session

NEPTUNE_ENDPOINT = os.environ.get("NEPTUNE_SPARQL_ENDPOINT", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")


def _signed_request(method, url, data=None, headers=None):
    """Send a SigV4-signed HTTP request to Neptune."""
    if not NEPTUNE_ENDPOINT:
        raise RuntimeError("NEPTUNE_SPARQL_ENDPOINT environment variable is not set")
    session = Session()
    creds = session.get_credentials()
    if creds is None:
        raise RuntimeError("AWS credentials not available — check Lambda execution role")
    credentials = creds.get_frozen_credentials()
    req = AWSRequest(method=method, url=url, data=data, headers=headers or {})
    SigV4Auth(credentials, "neptune-db", REGION).add_auth(req)
    body = req.body.encode() if isinstance(req.body, str) else req.body
    http_req = urllib.request.Request(url, data=body, headers=dict(req.headers), method=method)
    return urllib.request.urlopen(http_req, timeout=120)


def handler(event, context):
    """Lambda handler supporting update, query, and construct actions."""
    action = event.get("action", "update")
    sparql = event.get("sparql", "")

    if action == "update":
        data = urllib.parse.urlencode({"update": sparql})
        try:
            resp = _signed_request(
                "POST", NEPTUNE_ENDPOINT, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            return {"status": resp.status, "message": resp.read().decode()[:500]}
        except Exception as e:
            return {"error": str(e)}

    elif action == "query":
        data = urllib.parse.urlencode({"query": sparql})
        try:
            resp = _signed_request(
                "POST", NEPTUNE_ENDPOINT, data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/sparql-results+json",
                },
            )
            result = json.loads(resp.read())
            bindings = result.get("results", {}).get("bindings", [])
            return {"count": len(bindings), "bindings": bindings[:50]}
        except Exception as e:
            return {"error": str(e)}

    elif action == "construct":
        data = urllib.parse.urlencode({"query": sparql})
        try:
            resp = _signed_request(
                "POST", NEPTUNE_ENDPOINT, data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "text/turtle",
                },
            )
            return {"turtle": resp.read().decode()}
        except Exception as e:
            return {"error": str(e)}

    else:
        return {"error": f"Unknown action: {action}. Use 'update', 'query', or 'construct'."}
