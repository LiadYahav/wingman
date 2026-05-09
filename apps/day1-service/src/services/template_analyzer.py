"""
Jinja2 template AST analyzer.

Walks the Jinja2 AST to extract a variable schema that describes what inputs
the template requires. The schema is used to render a dynamic form in the UI.

Supported patterns:
  {{ var }}                      → required top-level string variable
  {{ var | default(val) }}       → optional variable (with default)
  {% for item in list_var %}     → list_var is a list variable; item becomes a loop var
  {{ item.field }}               → field of the list variable's items
  {{ item.field | default(x) }}  → optional field with default
  {% for x in item.sub_list %}   → sub_list is a nested list field
  {{ x.key }}                    → sub-field of nested list items
"""

from __future__ import annotations

from typing import Any

from jinja2 import Environment
from jinja2 import nodes as jnodes

_JINJA2_BUILTINS = frozenset({
    "loop", "range", "namespace", "lipsum", "dict", "true", "false",
    "none", "True", "False", "None", "not", "and", "or", "is", "in",
    "recursive", "caller", "super", "varargs", "kwargs", "joiner",
})


class _VarSchema:
    """Mutable variable descriptor built during AST traversal."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.required = True
        self.default: Any = None
        self.fields: dict[str, _VarSchema] = {}

    def mark_optional(self, default: Any = None) -> None:
        self.required = False
        if default is not None and self.default is None:
            self.default = default

    def get_or_add_field(self, name: str) -> _VarSchema:
        if name not in self.fields:
            self.fields[name] = _VarSchema(name)
        return self.fields[name]

    def infer_type(self) -> str:
        if self.fields:
            return "list"
        if self.default == [] or self.default == "__list__":
            return "list"
        if self.default == {} or self.default == "__object__":
            return "object"
        return "string"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.infer_type(),
            "required": self.required,
        }
        if self.default is not None and self.default not in ("__list__", "__object__"):
            d["default"] = self.default
        elif self.default == "__list__":
            d["default"] = []
        elif self.default == "__object__":
            d["default"] = {}
        if self.fields:
            d["fields"] = [f.to_dict() for f in self.fields.values()]
        return d


def _extract_default(filter_node: jnodes.Filter) -> Any:
    """Return the default value from `| default(...)`, or None."""
    if filter_node.name != "default" or not filter_node.args:
        return None
    arg = filter_node.args[0]
    if isinstance(arg, jnodes.Const):
        return arg.value
    if isinstance(arg, jnodes.List):
        return "__list__" if not arg.items else arg.items
    if isinstance(arg, jnodes.Dict):
        return "__object__" if not arg.items else arg.items
    return "__default__"


def _strip_filters(expr: jnodes.Expr) -> tuple[jnodes.Expr, bool, Any]:
    """
    Strip filter wrappers, returning (inner_expr, has_default_filter, default_val).
    """
    is_optional = False
    default_val: Any = None
    node = expr
    while isinstance(node, jnodes.Filter):
        if node.name == "default":
            is_optional = True
            d = _extract_default(node)
            if d is not None and default_val is None:
                default_val = d
        node = node.node
    return node, is_optional, default_val


def _walk_expr(
    expr: jnodes.Expr,
    loop_ctx: dict[str, _VarSchema],
    top_level: dict[str, _VarSchema],
    internal: set[str],
) -> None:
    """
    Walk an expression node, collecting variable references.

    loop_ctx maps loop-variable-name → the parent VarSchema (whose fields dict
    will receive discovered sub-field schemas).
    """
    if expr is None:
        return

    if isinstance(expr, jnodes.Name):
        n = expr.name
        if n in loop_ctx or n in internal or n in _JINJA2_BUILTINS or n.startswith("_"):
            return
        if n not in top_level:
            top_level[n] = _VarSchema(n)

    elif isinstance(expr, jnodes.Getattr):
        inner, optional, default_val = _strip_filters(expr.node)
        if isinstance(inner, jnodes.Name) and inner.name in loop_ctx:
            parent = loop_ctx[inner.name]
            field = parent.get_or_add_field(expr.attr)
            if optional:
                field.mark_optional(default_val)
        else:
            _walk_expr(expr.node, loop_ctx, top_level, internal)

    elif isinstance(expr, jnodes.Filter):
        inner, is_opt, default_val = _strip_filters(expr)
        if isinstance(inner, jnodes.Name):
            n = inner.name
            if n not in loop_ctx and n not in internal and n not in _JINJA2_BUILTINS and not n.startswith("_"):
                if n not in top_level:
                    top_level[n] = _VarSchema(n)
                if is_opt:
                    top_level[n].mark_optional(default_val)
        elif isinstance(inner, jnodes.Getattr):
            base, _, _ = _strip_filters(inner.node)
            if isinstance(base, jnodes.Name) and base.name in loop_ctx:
                parent = loop_ctx[base.name]
                field = parent.get_or_add_field(inner.attr)
                if is_opt:
                    field.mark_optional(default_val)
            else:
                _walk_expr(inner, loop_ctx, top_level, internal)
        # Walk filter args too (e.g. default value expressions)
        for arg in getattr(expr, "args", []):
            _walk_expr(arg, loop_ctx, top_level, internal)

    elif isinstance(expr, (jnodes.Add, jnodes.Sub, jnodes.Mul, jnodes.Div,
                           jnodes.FloorDiv, jnodes.Mod, jnodes.Pow)):
        _walk_expr(expr.left, loop_ctx, top_level, internal)
        _walk_expr(expr.right, loop_ctx, top_level, internal)

    elif isinstance(expr, jnodes.Concat):
        for child in expr.nodes:
            _walk_expr(child, loop_ctx, top_level, internal)

    elif isinstance(expr, (jnodes.List, jnodes.Tuple)):
        for item in expr.items:
            _walk_expr(item, loop_ctx, top_level, internal)

    elif isinstance(expr, jnodes.Call):
        _walk_expr(expr.node, loop_ctx, top_level, internal)
        for arg in expr.args:
            _walk_expr(arg, loop_ctx, top_level, internal)

    elif isinstance(expr, jnodes.Getitem):
        _walk_expr(expr.node, loop_ctx, top_level, internal)

    elif isinstance(expr, jnodes.Compare):
        _walk_expr(expr.expr, loop_ctx, top_level, internal)
        for op in expr.ops:
            _walk_expr(op.expr, loop_ctx, top_level, internal)

    elif isinstance(expr, jnodes.CondExpr):
        _walk_expr(expr.test, loop_ctx, top_level, internal)
        _walk_expr(expr.expr1, loop_ctx, top_level, internal)
        _walk_expr(expr.expr2, loop_ctx, top_level, internal)


def _walk_stmts(
    body: list[jnodes.Node],
    loop_ctx: dict[str, _VarSchema],
    top_level: dict[str, _VarSchema],
    internal: set[str],
) -> None:
    for stmt in body:
        if isinstance(stmt, jnodes.Output):
            for child in stmt.nodes:
                _walk_expr(child, loop_ctx, top_level, internal)

        elif isinstance(stmt, jnodes.Assign):
            # Mark the target as internal
            if isinstance(stmt.target, jnodes.Name):
                internal.add(stmt.target.name)
            # Still walk the RHS to collect variable references
            _walk_expr(stmt.node, loop_ctx, top_level, internal)

        elif isinstance(stmt, jnodes.For):
            # Determine the iterable: may be `list_var` or `loop_var.sub_field`
            iter_inner, is_opt, default_val = _strip_filters(stmt.iter)

            if isinstance(stmt.target, jnodes.Name):
                loop_var = stmt.target.name
                internal_copy = internal | {loop_var}

                if isinstance(iter_inner, jnodes.Name):
                    n = iter_inner.name
                    if n not in internal and not n.startswith("_") and n not in loop_ctx:
                        # Top-level list variable
                        if n not in top_level:
                            top_level[n] = _VarSchema(n)
                        schema = top_level[n]
                        if is_opt:
                            schema.mark_optional(default_val)
                        new_ctx = {**loop_ctx, loop_var: schema}
                        _walk_stmts(list(stmt.body), new_ctx, top_level, internal_copy)
                    else:
                        # Iterating over an internal/loop var — just walk body
                        _walk_stmts(list(stmt.body), loop_ctx, top_level, internal_copy)

                elif isinstance(iter_inner, jnodes.Getattr):
                    # for label in np.node_labels | default([])
                    base, _, _ = _strip_filters(iter_inner.node)
                    if isinstance(base, jnodes.Name) and base.name in loop_ctx:
                        parent = loop_ctx[base.name]
                        field = parent.get_or_add_field(iter_inner.attr)
                        if is_opt:
                            field.mark_optional(default_val)
                        new_ctx = {**loop_ctx, loop_var: field}
                        _walk_stmts(list(stmt.body), new_ctx, top_level, internal_copy)
                    else:
                        _walk_stmts(list(stmt.body), loop_ctx, top_level, internal_copy)
                else:
                    _walk_stmts(list(stmt.body), loop_ctx, top_level, internal_copy)

        elif isinstance(stmt, jnodes.If):
            _walk_expr(stmt.test, loop_ctx, top_level, internal)
            _walk_stmts(list(stmt.body), loop_ctx, top_level, internal)
            if hasattr(stmt, "elif_clauses"):
                _walk_stmts(list(stmt.elif_clauses), loop_ctx, top_level, internal)
            if hasattr(stmt, "else_"):
                _walk_stmts(list(stmt.else_), loop_ctx, top_level, internal)

        elif isinstance(stmt, jnodes.Block):
            _walk_stmts(list(stmt.body), loop_ctx, top_level, internal)

        elif isinstance(stmt, jnodes.CallBlock):
            _walk_expr(stmt.call, loop_ctx, top_level, internal)
            _walk_stmts(list(stmt.body), loop_ctx, top_level, internal)

        elif isinstance(stmt, jnodes.ExprStmt):
            _walk_expr(stmt.node, loop_ctx, top_level, internal)


# Variables that are cluster identity inputs (shown separately in the form)
IDENTITY_VARS = frozenset({
    "cluster_name", "site_name", "site", "mce_name", "mce",
})

# Variables that get a dedicated UI widget (not part of the generic dynamic form)
RESERVED_VARS = frozenset({
    "openshift_release_version",
}) | IDENTITY_VARS


def analyze_template(template_str: str, *, include_reserved: bool = False) -> list[dict[str, Any]]:
    """
    Parse a Jinja2 template and return a list of variable schemas.

    Each schema is a dict with keys:
      name     — variable name
      type     — "string" | "integer" | "boolean" | "list" | "object"
      required — bool
      default  — optional default value
      fields   — optional list of sub-schemas (for list-of-objects)

    By default, identity and reserved variables (cluster_name, openshift_release_version,
    etc.) are excluded — they have dedicated form widgets on the cluster creation page.
    Pass include_reserved=True to get every variable (used by the spec creation page so
    users can toggle immutability on these fields).
    """
    env = Environment()
    ast = env.parse(template_str)

    top_level: dict[str, _VarSchema] = {}
    internal: set[str] = set(_JINJA2_BUILTINS)

    _walk_stmts(list(ast.body), {}, top_level, internal)

    skip = set() if include_reserved else RESERVED_VARS
    return [
        v.to_dict()
        for v in top_level.values()
        if v.name not in internal and not v.name.startswith("_") and v.name not in skip
    ]
