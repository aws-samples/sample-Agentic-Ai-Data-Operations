"""
OBQC (Ontology-Based Query Check) Lambda handler.

Deterministic SPARQL validation against OWL semantics stored in Neptune DB.
No LLM calls — purely rule-based validation using regex-based SPARQL parsing
and SPARQL queries against the ontology in Neptune DB.
"""

import json
import logging
import os
import re
import urllib.request
import urllib.parse
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session

logger = logging.getLogger()
logger.setLevel(logging.INFO)

NEPTUNE_SPARQL_ENDPOINT = os.environ.get("NEPTUNE_SPARQL_ENDPOINT", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")

ADOP_PREFIX = "http://adop.example.org/ontology#"

# Standard prefixes exempt from property existence checks
STANDARD_PREFIXES = {"rdf", "rdfs", "xsd", "owl", "skos"}

# Label predicates that resolve IRI output warnings
LABEL_PREDICATES = {"rdfs:label", "adop:entityName", "adop:ticker"}


# ---------------------------------------------------------------------------
# Neptune DB helpers (SigV4 signed)
# ---------------------------------------------------------------------------

def _sparql_query(query: str) -> dict:
    """Execute a SPARQL query against Neptune DB with SigV4 signing."""
    if not NEPTUNE_SPARQL_ENDPOINT:
        raise RuntimeError("NEPTUNE_SPARQL_ENDPOINT environment variable is not set")
    data = urllib.parse.urlencode({"query": query})
    headers = {"Content-Type": "application/x-www-form-urlencoded",
               "Accept": "application/sparql-results+json"}
    session = Session()
    creds = session.get_credentials()
    if creds is None:
        raise RuntimeError("AWS credentials not available — check Lambda execution role")
    credentials = creds.get_frozen_credentials()
    aws_req = AWSRequest(method="POST", url=NEPTUNE_SPARQL_ENDPOINT,
                         data=data, headers=headers)
    SigV4Auth(credentials, "neptune-db", REGION).add_auth(aws_req)
    http_req = urllib.request.Request(
        NEPTUNE_SPARQL_ENDPOINT,
        data=aws_req.body.encode() if isinstance(aws_req.body, str) else aws_req.body,
        headers=dict(aws_req.headers),
        method="POST",
    )
    with urllib.request.urlopen(http_req, timeout=10) as resp:
        return json.loads(resp.read())


def _sparql_ask(query: str) -> bool:
    """Execute a SPARQL ASK query and return the boolean result."""
    result = _sparql_query(query)
    return result.get("boolean", False)


# ---------------------------------------------------------------------------
# SPARQL parsing — regex-based extraction
# ---------------------------------------------------------------------------

def _extract_prefixes(sparql: str) -> dict:
    """Extract PREFIX declarations and return a map of prefix -> URI."""
    prefixes = {}
    for m in re.finditer(
        r"PREFIX\s+(\w+):\s*<([^>]+)>", sparql, re.IGNORECASE
    ):
        prefixes[m.group(1)] = m.group(2)
    return prefixes


def _extract_select_variables(sparql: str) -> list:
    """Extract directly-projected variables from the SELECT clause.

    Variables that appear only inside aggregate functions like COUNT(?x),
    SUM(?x), MIN(?x), MAX(?x), AVG(?x), SAMPLE(?x), GROUP_CONCAT(?x) are
    NOT considered projected — only their alias (after AS ?alias) is.
    """
    m = re.search(r"SELECT\s+(?:DISTINCT\s+|REDUCED\s+)?(.*?)\s*(?:WHERE|{)", sparql, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    select_clause = m.group(1).strip()
    if select_clause == "*":
        return []
    # Strip the contents of every aggregate function — keep only the (... AS ?alias) form
    # e.g. "(COUNT(?entity) AS ?count)" -> "(?count)"
    aggregates = r"(?:COUNT|SUM|MIN|MAX|AVG|SAMPLE|GROUP_CONCAT)\s*\([^)]*\)"
    cleaned = re.sub(aggregates, "", select_clause, flags=re.IGNORECASE)
    variables = re.findall(r"\?(\w+)", cleaned)
    return list(dict.fromkeys(variables))


def _extract_where_clause(sparql: str) -> str:
    """Extract the WHERE clause body from a SPARQL query."""
    m = re.search(r"WHERE\s*\{", sparql, re.IGNORECASE)
    if not m:
        m = re.search(r"}\s*\{", sparql)
        if not m:
            return ""
    start = m.end()
    depth = 1
    i = start
    while i < len(sparql) and depth > 0:
        if sparql[i] == "{":
            depth += 1
        elif sparql[i] == "}":
            depth -= 1
        i += 1
    return sparql[start : i - 1]


def _extract_triple_patterns(where_clause: str) -> list:
    """Extract triple patterns from a WHERE clause.

    Handles SPARQL predicate-object lists separated by `;` (subject implicit
    from prior triple) and object lists separated by `,` (subject + predicate
    implicit). The original regex only matched fully-qualified triples with
    explicit subject; that misses every continuation triple after a `;`.

    The strategy: tokenize the cleaned WHERE clause sequentially. Walk the
    tokens with a small state machine: subject -> predicate -> object,
    then on `;` keep the subject and reset to predicate; on `,` keep
    subject + predicate and reset to object; on `.` reset all.
    """
    cleaned = re.sub(r"#[^\n]*", "", where_clause)
    cleaned = re.sub(r"FILTER\s*\([^)]*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"BIND\s*\([^)]*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"OPTIONAL\s*\{", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(ORDER\s+BY|LIMIT|OFFSET|GROUP\s+BY|HAVING)\s+.*", "", cleaned, flags=re.IGNORECASE)
    # Drop nested braces — a single-pass scanner here is fine for our needs
    cleaned = cleaned.replace("{", " ").replace("}", " ")

    # Tokenizer: tokens are either separators (; , .) or atoms
    token_re = re.compile(
        r'\?\w+'                              # variable
        r'|<[^>]+>'                           # IRI
        r'|"(?:[^"\\]|\\.)*"(?:\^\^[^\s;,.]+)?'  # string literal (with optional datatype)
        r'|"(?:[^"\\]|\\.)*"@\w+'             # string with lang tag
        r'|[a-zA-Z_][\w-]*:[\w-]+'           # prefixed name
        r'|\ba\b'                             # the rdf:type shortcut
        r'|-?\d+(?:\.\d+)?'                   # numeric literal
        r'|[;,.]',                            # separators
        re.UNICODE,
    )
    tokens = token_re.findall(cleaned)

    triples = []
    subject = predicate = None
    slot = "s"  # next expected: s | p | o

    for tok in tokens:
        if tok in (";", ",", "."):
            if tok == ";":
                slot = "p"  # keep subject, expect new predicate
            elif tok == ",":
                slot = "o"  # keep subject+predicate, expect new object
            else:  # "."
                subject = predicate = None
                slot = "s"
            continue

        if slot == "s":
            subject = tok
            slot = "p"
        elif slot == "p":
            predicate = tok
            slot = "o"
        elif slot == "o":
            if subject is not None and predicate is not None:
                triples.append((subject, predicate, tok))
            slot = "s"  # default — gets corrected by next separator if not `.`

    # Dedup while preserving order
    seen = set()
    out = []
    for t in triples:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _resolve_full_uri(prefixed: str, prefixes: dict) -> str:
    """Resolve a prefixed name to a full URI."""
    if prefixed.startswith("<") and prefixed.endswith(">"):
        return prefixed[1:-1]
    if ":" in prefixed:
        prefix, local = prefixed.split(":", 1)
        if prefix in prefixes:
            return prefixes[prefix] + local
    return prefixed


def _get_prefix(prefixed: str) -> str:
    """Get the prefix part of a prefixed name."""
    if ":" in prefixed and not prefixed.startswith("<") and not prefixed.startswith('"'):
        return prefixed.split(":")[0]
    return ""


def _is_variable(token: str) -> bool:
    return token.startswith("?")


def _is_literal(token: str) -> bool:
    return token.startswith('"')


def _build_type_bindings(triples: list, prefixes: dict) -> dict:
    """Build a map from variable name -> set of inferred OWL class names.

    For variables whose type is asserted directly (`?x a Foo`), we record a
    single concrete type. For variables whose type is inferred from a property's
    rdfs:domain or rdfs:range, we use union semantics: a property with multiple
    domains constrains the subject to be IN ANY of those classes, not all.

    To represent both shapes uniformly we use a list of frozensets per variable.
    A frozenset of size 1 means "must be exactly this class"; a larger frozenset
    means "must be one of these classes".
    """
    bindings: dict[str, list] = {}

    def add_constraint(var_name: str, classes):
        if isinstance(classes, str):
            classes = [classes]
        cls_set = frozenset(classes)
        if not cls_set:
            return
        bindings.setdefault(var_name, []).append(cls_set)

    for s, p, o in triples:
        if p == "a" or p == "rdf:type":
            if _is_variable(s) and not _is_variable(o) and not _is_literal(o):
                add_constraint(s[1:], _resolve_full_uri(o, prefixes))

        if not _is_variable(p) and p != "a" and p != "rdf:type":
            prefix = _get_prefix(p)
            if prefix in STANDARD_PREFIXES:
                continue

            prop_uri = _resolve_full_uri(p, prefixes)

            if _is_variable(s):
                domains = _query_all_domains(prop_uri)
                if domains:
                    add_constraint(s[1:], domains)

            if _is_variable(o) and not _is_literal(o):
                range_class = _query_range(prop_uri)
                if range_class:
                    add_constraint(o[1:], range_class)

    return bindings


def _query_domain(property_uri: str):
    """Query Neptune for the rdfs:domain(s) of a property.

    Returns the first domain (legacy single-domain callers) and the full
    list (new callers that handle polymorphic domain). Properties with
    multiple rdfs:domain triples are treated as having a union domain
    (the property may apply to instances of any listed class), which is
    the only sensible interpretation for our ontology.
    """
    query = f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?domain WHERE {{
        <{property_uri}> rdfs:domain ?domain .
    }}
    """
    try:
        result = _sparql_query(query)
        bindings = result.get("results", {}).get("bindings", [])
        if bindings:
            domains = [b["domain"]["value"] for b in bindings]
            # Return single domain for back-compat; callers that want all
            # domains use _query_all_domains
            return domains[0] if len(domains) == 1 else domains
    except Exception as e:
        logger.warning("Failed to query domain for %s: %s", property_uri, e)
    return None


def _query_all_domains(property_uri: str) -> list:
    """Return ALL declared rdfs:domain values for a property (union semantics)."""
    query = f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?domain WHERE {{
        <{property_uri}> rdfs:domain ?domain .
    }}
    """
    try:
        result = _sparql_query(query)
        return [b["domain"]["value"] for b in result.get("results", {}).get("bindings", [])]
    except Exception as e:
        logger.warning("Failed to query domains for %s: %s", property_uri, e)
        return []


def _query_range(property_uri: str) -> str | None:
    """Query Neptune for the rdfs:range of a property."""
    query = f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT ?range WHERE {{
        <{property_uri}> rdfs:range ?range .
        {{ <{property_uri}> a owl:ObjectProperty }}
        UNION
        {{ <{property_uri}> a owl:DatatypeProperty }}
    }}
    """
    try:
        result = _sparql_query(query)
        bindings = result.get("results", {}).get("bindings", [])
        if bindings:
            range_val = bindings[0]["range"]["value"]
            if range_val.startswith("http://www.w3.org/2001/XMLSchema#"):
                return None
            return range_val
    except Exception as e:
        logger.warning("Failed to query range for %s: %s", property_uri, e)
    return None


def _short_name(uri: str) -> str:
    """Extract the local name from a full URI."""
    if "#" in uri:
        return uri.split("#")[-1]
    if "/" in uri:
        return uri.rsplit("/", 1)[-1]
    return uri


def _query_subclass(child_uri: str, parent_uri: str) -> bool:
    """Check if child_uri is a subclass of parent_uri in the ontology."""
    if child_uri == parent_uri:
        return True
    query = f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    ASK {{
        <{child_uri}> rdfs:subClassOf+ <{parent_uri}> .
    }}
    """
    try:
        return _sparql_ask(query)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------

def _rule_property_existence(triples: list, prefixes: dict) -> list:
    """Rule 1: Verify every adop: property exists in the ontology."""
    errors = []
    checked = set()

    for s, p, o in triples:
        if _is_variable(p) or p == "a" or p == "rdf:type":
            continue

        prefix = _get_prefix(p)
        if prefix in STANDARD_PREFIXES:
            continue

        prop_uri = _resolve_full_uri(p, prefixes)
        if prop_uri in checked:
            continue
        checked.add(prop_uri)

        ask_query = f"""
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        ASK {{
            {{ <{prop_uri}> a owl:ObjectProperty }}
            UNION
            {{ <{prop_uri}> a owl:DatatypeProperty }}
        }}
        """
        try:
            exists = _sparql_ask(ask_query)
        except Exception as e:
            logger.error("Neptune query failed for property %s: %s", prop_uri, e)
            continue

        if not exists:
            errors.append({
                "rule": "property_existence",
                "message": f"Property {p} does not exist in the ontology as owl:ObjectProperty or owl:DatatypeProperty",
                "property": p,
            })

    return errors


def _flatten_var_types(constraints: list) -> set:
    """Bindings now store list[frozenset]. Return the union of all classes
    that ever appeared as a possible type for the variable."""
    out = set()
    for c in constraints:
        out.update(c)
    return out


def _rule_domain_validation(triples: list, prefixes: dict, bindings: dict) -> list:
    """Rule 2: Validate domain constraints for each triple pattern.

    A property with multiple rdfs:domain values has UNION semantics: the
    subject is valid if its (intersected across constraints) type set has
    a non-empty intersection with the property's domain set.
    """
    errors = []

    for s, p, o in triples:
        if not _is_variable(s) or _is_variable(p) or p == "a" or p == "rdf:type":
            continue

        prefix = _get_prefix(p)
        if prefix in STANDARD_PREFIXES:
            continue

        prop_uri = _resolve_full_uri(p, prefixes)
        domains = _query_all_domains(prop_uri)
        if not domains:
            continue

        var_name = s[1:]
        var_types = _flatten_var_types(bindings.get(var_name, []))
        if not var_types:
            continue

        # Pass if any var_type is a subclass of any domain
        domain_match = any(
            _query_subclass(t, d)
            for t in var_types
            for d in domains
        )
        if not domain_match:
            actual = ", ".join(_short_name(t) for t in sorted(var_types))
            expected = " | ".join(_short_name(d) for d in domains)
            errors.append({
                "rule": "domain",
                "message": (
                    f"{p} has domain {expected}, "
                    f"but subject {s} is typed as {actual}"
                ),
                "triple": f"{s} {p} {o}",
                "expected_type": expected,
                "actual_type": actual,
                "property": p,
            })

    return errors


def _rule_range_validation(triples: list, prefixes: dict, bindings: dict) -> list:
    """Rule 3: Validate range constraints for object property triple patterns."""
    errors = []

    for s, p, o in triples:
        if _is_variable(p) or p == "a" or p == "rdf:type":
            continue
        if not _is_variable(o):
            continue

        prefix = _get_prefix(p)
        if prefix in STANDARD_PREFIXES:
            continue

        prop_uri = _resolve_full_uri(p, prefixes)
        range_uri = _query_range(prop_uri)
        if not range_uri:
            continue

        var_name = o[1:]
        var_types = _flatten_var_types(bindings.get(var_name, []))
        if not var_types:
            continue

        range_match = any(
            _query_subclass(t, range_uri) for t in var_types
        )
        if not range_match:
            actual = ", ".join(_short_name(t) for t in sorted(var_types))
            errors.append({
                "rule": "range",
                "message": (
                    f"{p} has range {_short_name(range_uri)}, "
                    f"but object {o} is typed as {actual}"
                ),
                "triple": f"{s} {p} {o}",
                "expected_type": _short_name(range_uri),
                "actual_type": actual,
                "property": p,
            })

    return errors


def _rule_type_conflict(bindings: dict) -> list:
    """Rule 4: Detect conflicting type bindings on shared variables.

    Each variable has a list of constraints (frozensets of allowed classes
    from each predicate / type-assertion encountered). The variable is
    consistent iff there is at least one type that satisfies ALL the
    constraints (intersection across constraints, where each constraint is
    treated as union of the classes it lists). A constraint can be satisfied
    by a class if the constraint contains that class OR an ancestor.
    """
    errors = []

    for var_name, constraint_list in bindings.items():
        if len(constraint_list) <= 1:
            continue

        # For each pair of constraints, check whether they can be jointly
        # satisfied: there exists a type t1 in c1 and t2 in c2 such that
        # t1 == t2 or one is a subclass of the other.
        for i in range(len(constraint_list)):
            for j in range(i + 1, len(constraint_list)):
                c1, c2 = constraint_list[i], constraint_list[j]
                joinable = False
                for t1 in c1:
                    for t2 in c2:
                        if t1 == t2:
                            joinable = True
                            break
                        if _query_subclass(t1, t2) or _query_subclass(t2, t1):
                            joinable = True
                            break
                    if joinable:
                        break
                if joinable:
                    continue
                expected = " | ".join(_short_name(t) for t in c1)
                actual = " | ".join(_short_name(t) for t in c2)
                errors.append({
                    "rule": "type_conflict",
                    "message": (
                        f"Variable ?{var_name} has conflicting type requirements: "
                        f"{expected} and {actual}"
                    ),
                    "expected_type": expected,
                    "actual_type": actual,
                })

    return errors


def _rule_iri_output(select_vars: list, triples: list, bindings: dict) -> list:
    """Rule 5: Detect SELECT variables bound only to IRI positions without labels."""
    errors = []

    subject_vars = set()
    object_vars = set()
    has_label_pattern = set()

    for s, p, o in triples:
        if _is_variable(s):
            subject_vars.add(s[1:])
        if _is_variable(o):
            object_vars.add(o[1:])

        if p in LABEL_PREDICATES and _is_variable(s):
            has_label_pattern.add(s[1:])

    for var in select_vars:
        if var in subject_vars and var not in has_label_pattern:
            if var in bindings:
                errors.append({
                    "rule": "iri_output",
                    "message": (
                        f"Variable ?{var} is projected in SELECT but is bound to IRI "
                        f"positions without a label triple -- consider selecting "
                        f"adop:entityName or rdfs:label instead"
                    ),
                })

    return errors


def _rule_namespace_validation(triples: list) -> list:
    """Rule 6: All prefixed names must use adop: or standard prefixes."""
    errors = []
    allowed = STANDARD_PREFIXES | {"adop"}
    checked = set()

    for s, p, o in triples:
        for token in (s, p, o):
            if _is_variable(token) or _is_literal(token):
                continue
            if token.startswith("<"):
                continue
            if token == "a":
                continue
            prefix = _get_prefix(token)
            if prefix and prefix not in allowed and token not in checked:
                checked.add(token)
                errors.append({
                    "rule": "namespace",
                    "message": (
                        f"Prefixed name '{token}' uses non-standard prefix '{prefix}:'. "
                        f"Only adop: and standard prefixes (rdf:, rdfs:, xsd:, owl:, skos:) are allowed."
                    ),
                    "property": token,
                })

    return errors


# ---------------------------------------------------------------------------
# Main validation orchestrator
# ---------------------------------------------------------------------------

def validate_sparql(sparql_query: str) -> dict:
    """Validate a SPARQL query against OWL semantics in Neptune DB."""
    errors = []

    prefixes = _extract_prefixes(sparql_query)
    if "adop" not in prefixes:
        prefixes["adop"] = ADOP_PREFIX
    if "rdf" not in prefixes:
        prefixes["rdf"] = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    if "rdfs" not in prefixes:
        prefixes["rdfs"] = "http://www.w3.org/2000/01/rdf-schema#"

    select_vars = _extract_select_variables(sparql_query)
    where_clause = _extract_where_clause(sparql_query)
    triples = _extract_triple_patterns(where_clause)

    if not triples:
        return {"pass": True, "errors": []}

    bindings = _build_type_bindings(triples, prefixes)

    errors.extend(_rule_namespace_validation(triples))
    errors.extend(_rule_property_existence(triples, prefixes))
    errors.extend(_rule_domain_validation(triples, prefixes, bindings))
    errors.extend(_rule_range_validation(triples, prefixes, bindings))
    errors.extend(_rule_type_conflict(bindings))
    errors.extend(_rule_iri_output(select_vars, triples, bindings))

    return {
        "pass": len(errors) == 0,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event, context):
    """Lambda handler for OBQC validation."""
    logger.info("OBQC validation request received")

    sparql_query = event.get("sparql_query", "")
    if not sparql_query:
        return {
            "pass": False,
            "errors": [{"rule": "parse_error", "message": "No SPARQL query provided in event.sparql_query"}],
        }

    try:
        result = validate_sparql(sparql_query)
        logger.info("OBQC validation complete: pass=%s, error_count=%d", result["pass"], len(result["errors"]))
        return result
    except Exception as e:
        logger.error("OBQC validation failed with exception: %s", e, exc_info=True)
        return {
            "pass": False,
            "errors": [{"rule": "parse_error", "message": f"OBQC validation error: {str(e)}"}],
        }
