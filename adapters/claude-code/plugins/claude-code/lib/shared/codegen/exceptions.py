"""Typed exceptions for the codegen pipeline."""


class CodegenError(Exception):
    """Base exception for all codegen operations."""


class SpecValidationError(CodegenError):
    """Spec YAML failed JSON Schema validation."""

    def __init__(self, schema_path: str, errors: list[str]):
        self.schema_path = schema_path
        self.errors = errors
        super().__init__(
            f"Spec validation failed against {schema_path}: {'; '.join(errors)}"
        )


class SchemaVersionError(CodegenError):
    """Requested schema version directory does not exist."""

    def __init__(self, version: str):
        self.version = version
        super().__init__(f"Schema version '{version}' not found in contracts/")


class SpecHashMismatchError(CodegenError):
    """Manifest spec_hash does not match the computed hash of the spec."""

    def __init__(self, spec_type: str, expected: str, actual: str):
        self.spec_type = spec_type
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Hash mismatch for {spec_type}: manifest says {expected}, computed {actual}"
        )


class MissingSlotError(CodegenError):
    """Template requires slots not present in the spec."""

    def __init__(self, template_id: str, missing: set[str]):
        self.template_id = template_id
        self.missing = missing
        super().__init__(
            f"Template '{template_id}' requires slots not in spec: {sorted(missing)}"
        )


class TemplateNotFoundError(CodegenError):
    """Requested template file does not exist."""

    def __init__(self, template_id: str, searched_path: str):
        self.template_id = template_id
        self.searched_path = searched_path
        super().__init__(
            f"Template '{template_id}' not found at {searched_path}"
        )


class RenderError(CodegenError):
    """Jinja2 rendering failed."""

    def __init__(self, template_id: str, detail: str):
        self.template_id = template_id
        self.detail = detail
        super().__init__(f"Render failed for '{template_id}': {detail}")


class UnsupportedSpecValueError(CodegenError):
    """A template was given a contract-valid value it cannot implement.

    The counterpart to MissingSlotError. That one fires when a template needs a slot the
    spec lacks; this one fires when the spec carries a value the template has no branch
    for. Both are the same failure — the contract and the templates disagreeing about
    what is expressible — seen from opposite ends.

    It exists because the alternative is what quality_check.py.j2 used to do: an
    unhandled `check_type` fell through to `valid_count = total_rows`, scoring 1.0. A
    rule the template could not run reported perfect compliance, and because the overall
    score is an unweighted mean, adding an unimplementable rule *raised* it.

    Failing the render is the lesser harm. A render that stops is a bug someone fixes; a
    pipeline that reports 1.0 for a check that never executed is a bug someone trusts.
    """

    def __init__(self, template_id: str, detail: str):
        self.template_id = template_id
        self.detail = detail
        super().__init__(f"Template '{template_id}' cannot implement: {detail}")


class DriftDetectedError(CodegenError):
    """Artifact on disk does not match re-render from spec."""

    def __init__(self, artifact_path: str, expected_hash: str, actual_hash: str):
        self.artifact_path = artifact_path
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Drift in {artifact_path}: expected {expected_hash[:16]}..., got {actual_hash[:16]}..."
        )
