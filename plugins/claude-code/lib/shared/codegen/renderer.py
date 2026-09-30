"""Render Jinja2 templates from validated specs — the only legal codegen path."""

import hashlib
import os
import tempfile
from pathlib import Path

import jinja2

from .exceptions import (
    MissingSlotError,
    RenderError,
    TemplateNotFoundError,
    UnsupportedSpecValueError,
)
from .slot_extractor import parse_required_slots_header

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "shared" / "templates"

RENDERER_TOKEN_ENV = "ADOP_RENDERER_TOKEN"

HEADER_TEMPLATE = """\
# spec_hash: {spec_hash}
# template_id: {template_id}
# template_hash: {template_hash}
# schema_version: {schema_version}
# rendered_at: {rendered_at}
"""

HEADER_TEMPLATE_SQL = """\
-- spec_hash: {spec_hash}
-- template_id: {template_id}
-- template_hash: {template_hash}
-- schema_version: {schema_version}
-- rendered_at: {rendered_at}
"""

HEADER_TEMPLATE_YAML = """\
# spec_hash: {spec_hash}
# template_id: {template_id}
# template_hash: {template_hash}
# schema_version: {schema_version}
# rendered_at: {rendered_at}
"""


def _compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_template(template_id: str) -> tuple[str, str, Path]:
    """
    Find and load a template file. Returns (source, template_hash, path).
    Searches for {template_id}.py.j2, {template_id}.sql.j2, {template_id}.yaml.j2.
    """
    for ext in (".py.j2", ".sql.j2", ".yaml.j2"):
        path = TEMPLATES_DIR / f"{template_id}{ext}"
        if path.exists():
            source = path.read_text(encoding="utf-8")
            template_hash = _compute_hash(source.encode("utf-8"))
            return source, template_hash, path

    raise TemplateNotFoundError(template_id, str(TEMPLATES_DIR))


def _get_header_template(template_path: Path) -> str:
    if ".sql." in template_path.name:
        return HEADER_TEMPLATE_SQL
    return HEADER_TEMPLATE


def _validate_slots(source: str, spec: dict, template_id: str) -> None:
    declared = parse_required_slots_header(source)
    if declared:
        missing = declared - set(spec.keys())
        if missing:
            raise MissingSlotError(template_id, missing)


def _make_env(template_id: str) -> "jinja2.Environment":
    """The Jinja environment every template renders in.

    B701: these templates emit Python, SQL and YAML, never HTML.
    autoescape=True would HTML-escape quotes and ampersands and corrupt
    every generated artifact.

    `unsupported()` is exposed to templates so a branch can refuse a value it cannot
    implement instead of inventing one. Before it existed, quality_check.py.j2's
    `{% else %}` arm set `valid_count = total_rows` for any unhandled check_type — a
    score of 1.0 for a check that never ran. A template with no way to say "I cannot do
    this" will always find a way to say "fine".
    """
    env = jinja2.Environment(  # nosec B701
        loader=jinja2.BaseLoader(),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    def unsupported(detail: str) -> None:
        raise UnsupportedSpecValueError(template_id, detail)

    env.globals["unsupported"] = unsupported
    return env


def render(
    spec: dict,
    spec_hash: str,
    template_id: str,
    template_version: str,
    output_path: Path,
    run_started_at: str,
    schema_version: str = "v1",
) -> tuple[bytes, str]:
    """
    Render a template with spec slot values. Only entrypoint allowed to write
    to workloads/*/scripts/**, dags/**, sql/**.

    Returns:
        Tuple of (rendered_bytes, artifact_hash).

    Raises:
        TemplateNotFoundError, MissingSlotError, RenderError
    """
    source, template_hash, template_path = _load_template(template_id)
    _validate_slots(source, spec, template_id)

    env = _make_env(template_id)

    try:
        template = env.from_string(source)
        rendered_body = template.render(**spec)
    except jinja2.UndefinedError as e:
        raise RenderError(template_id, f"Undefined variable: {e}") from e
    except jinja2.TemplateError as e:
        raise RenderError(template_id, str(e)) from e

    header_tpl = _get_header_template(template_path)
    header = header_tpl.format(
        spec_hash=spec_hash,
        template_id=template_id,
        template_hash=template_hash,
        schema_version=schema_version,
        rendered_at=run_started_at,
    )

    rendered_content = header + rendered_body
    rendered_bytes = rendered_content.encode("utf-8")
    artifact_hash = _compute_hash(rendered_bytes)

    token = _compute_hash(f"{template_id}{spec_hash}".encode("utf-8"))
    os.environ[RENDERER_TOKEN_ENV] = token
    try:
        _atomic_write(output_path, rendered_bytes)
    finally:
        os.environ.pop(RENDERER_TOKEN_ENV, None)

    return rendered_bytes, artifact_hash


def _atomic_write(path: Path, data: bytes) -> None:
    """Write atomically via tempfile + os.replace to prevent partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".render_"
    )
    try:
        os.write(fd, data)
        os.close(fd)
        os.replace(tmp_path, str(path))
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def render_dry_run(
    spec: dict,
    spec_hash: str,
    template_id: str,
    template_version: str,
    run_started_at: str,
    schema_version: str = "v1",
) -> tuple[bytes, str]:
    """
    Render without writing to disk. For drift validation and previews.
    Returns (rendered_bytes, artifact_hash).
    """
    source, template_hash, template_path = _load_template(template_id)
    _validate_slots(source, spec, template_id)

    env = _make_env(template_id)

    try:
        template = env.from_string(source)
        rendered_body = template.render(**spec)
    except jinja2.TemplateError as e:
        raise RenderError(template_id, str(e)) from e

    header_tpl = _get_header_template(template_path)
    header = header_tpl.format(
        spec_hash=spec_hash,
        template_id=template_id,
        template_hash=template_hash,
        schema_version=schema_version,
        rendered_at=run_started_at,
    )

    rendered_content = header + rendered_body
    rendered_bytes = rendered_content.encode("utf-8")
    artifact_hash = _compute_hash(rendered_bytes)

    return rendered_bytes, artifact_hash
