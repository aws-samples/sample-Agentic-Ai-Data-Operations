"""Extract required template slots from Jinja2 template AST."""

from pathlib import Path

import jinja2
import jinja2.meta

from .exceptions import MissingSlotError


def extract_slots(template_source: str) -> set[str]:
    """
    Parse a Jinja2 template and return the set of top-level variable names (slots)
    required to render it.

    Loop variables (e.g., 'x' in '{% for x in items %}') are excluded.
    Dotted access (e.g., '{{ spec.key }}') returns only the root name ('spec').
    """
    env = jinja2.Environment()
    ast = env.parse(template_source)
    all_vars = jinja2.meta.find_undeclared_variables(ast)
    return all_vars


def extract_slots_from_file(template_path: Path) -> set[str]:
    """Extract slots from a template file on disk."""
    with open(template_path) as f:
        source = f.read()
    return extract_slots(source)


def parse_required_slots_header(template_source: str) -> set[str]:
    """
    Parse the {# required_slots: ... #} header comment from a template.
    Returns the declared set of required slot names.
    """
    for line in template_source.splitlines():
        stripped = line.strip()
        if stripped.startswith("{#") and "required_slots:" in stripped:
            # Extract the value after "required_slots:"
            _, _, slots_str = stripped.partition("required_slots:")
            slots_str = slots_str.rstrip("#}").strip()
            return {s.strip() for s in slots_str.split(",") if s.strip()}
    return set()


def validate_slots(
    template_source: str, spec: dict, template_id: str
) -> None:
    """
    Validate that the spec provides all slots required by the template.

    Checks both AST-extracted variables and the declared required_slots header.
    Raises MissingSlotError if any required slot is not present in the spec.
    """
    declared_slots = parse_required_slots_header(template_source)

    if declared_slots:
        missing = declared_slots - set(spec.keys())
    else:
        ast_slots = extract_slots(template_source)
        missing = ast_slots - set(spec.keys())

    if missing:
        raise MissingSlotError(template_id, missing)
