"""Jinja2-based renderer for cluster spec templates.

Renders a ClusterSpec's Jinja2 template with user-supplied variables
to produce the multi-document YAML that goes into the day1 repo.
"""

from __future__ import annotations

import logging
from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateError, UndefinedError
from wingman_shared.models import ClusterSpec

logger = logging.getLogger(__name__)


class RenderError(ValueError):
    """Raised when template rendering fails (missing var, syntax error, etc.)."""


def render_spec(spec: ClusterSpec, variables: dict[str, Any]) -> str:
    """Render a cluster spec template with the given variables.

    Args:
        spec: The ClusterSpec whose day1.template will be rendered.
        variables: User-provided values for template placeholders.
                   Must satisfy all required variables defined in spec.day1.variables.

    Returns:
        Rendered multi-document YAML string ready to commit.

    Raises:
        RenderError: if a required variable is missing, undefined, or template is invalid.
    """
    if not spec.spec.day1.template.strip():
        raise RenderError("Spec has no template — add a .j2 template file or set day1.template in the spec YAML")

    _validate_variables(spec, variables)

    env = Environment(
        undefined=StrictUndefined,  # raise on any missing variable
        autoescape=False,  # YAML, not HTML
        keep_trailing_newline=True,
        trim_blocks=True,   # remove newline after {% %} tags
        lstrip_blocks=True, # strip leading whitespace before {% %} tags
    )

    try:
        template = env.from_string(spec.spec.day1.template)
        rendered = template.render(**variables)
    except UndefinedError as exc:
        raise RenderError(f"Template references undefined variable: {exc}") from exc
    except TemplateError as exc:
        raise RenderError(f"Template rendering failed: {exc}") from exc

    if not rendered.strip():
        raise RenderError("Rendered template is empty")

    return rendered


def _validate_variables(spec: ClusterSpec, variables: dict[str, Any]) -> None:
    """Validate that all required spec variables are provided with correct types."""
    errors: list[str] = []

    for var in spec.spec.day1.variables:
        value = variables.get(var.name)

        if value is None:
            if var.required and var.default is None:
                errors.append(f"Required variable '{var.name}' is missing")
            continue

        # Type checking
        if var.type == "string" and not isinstance(value, str):
            errors.append(f"Variable '{var.name}' must be a string")
        elif var.type == "integer" and not isinstance(value, int):
            errors.append(f"Variable '{var.name}' must be an integer")
        elif var.type == "boolean" and not isinstance(value, bool):
            errors.append(f"Variable '{var.name}' must be a boolean")

        # Enum validation
        if var.enum and str(value) not in var.enum:
            errors.append(f"Variable '{var.name}' must be one of: {', '.join(var.enum)}")

        # Range validation for integers
        if var.type == "integer" and isinstance(value, int):
            if var.minimum is not None and value < var.minimum:
                errors.append(f"Variable '{var.name}' must be >= {var.minimum} (got {value})")
            if var.maximum is not None and value > var.maximum:
                errors.append(f"Variable '{var.name}' must be <= {var.maximum} (got {value})")

    if errors:
        raise RenderError("; ".join(errors))


def apply_variable_defaults(spec: ClusterSpec, variables: dict[str, Any]) -> dict[str, Any]:
    """Return a new variables dict with defaults applied for missing optional vars."""
    merged = dict(variables)
    for var in spec.spec.day1.variables:
        if var.name not in merged and var.default is not None:
            merged[var.name] = var.default
    return merged
