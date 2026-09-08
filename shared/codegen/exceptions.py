"""Codegen exceptions (subset of official ADOP shared.codegen.exceptions)."""


class CodegenError(Exception):
    pass


class SpecValidationError(CodegenError):
    def __init__(self, schema_path: str, errors: list[str]):
        super().__init__(f"Spec validation failed against {schema_path}: {'; '.join(errors)}")


class MissingSlotError(CodegenError):
    def __init__(self, template_id: str, missing: set[str]):
        super().__init__(f"Template '{template_id}' missing slots: {sorted(missing)}")


class TemplateNotFoundError(CodegenError):
    def __init__(self, template_id: str, searched_path: str):
        super().__init__(f"Template '{template_id}' not found under {searched_path}")


class RenderError(CodegenError):
    def __init__(self, template_id: str, detail: str):
        super().__init__(f"Render failed for '{template_id}': {detail}")
