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


class DriftDetectedError(CodegenError):
    """Artifact on disk does not match re-render from spec."""

    def __init__(self, artifact_path: str, expected_hash: str, actual_hash: str):
        self.artifact_path = artifact_path
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Drift in {artifact_path}: expected {expected_hash[:16]}..., got {actual_hash[:16]}..."
        )
