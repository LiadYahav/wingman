"""Cluster specs: named presets for the cluster template's inputs (ADR-0013).

A spec ("flavor" in the UI) lives at ``specs/<name>.yaml`` in the specs
project. The document shape is the legacy one, so every spec already in
GitLab still loads, plus ``spec.day1.values``: values for the template's
inputs. Each value is a preset, merged under what the user enters at create
time, or locked: its path is in ``spec.day1.locked_paths`` and the create
must use it (ADR-0026). ``locked_paths`` was ``immutable_paths``, a form
hint, which is still read as the same list. ``structure`` (list shapes for
the form) and ``day2.addons`` keep their meaning. ``day1.template`` is never
stored: it is the shared ``cluster-template.j2``, filled in on read.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from wingman_day1.domain.addons import AddonKey, RequestedAddon
from wingman_day1.domain.errors import InvalidSpecError
from wingman_day1.domain.locks import Lock, enforced_locks, lock_problems
from wingman_day1.domain.owners import owner_problems
from wingman_day1.domain.template import check_inputs

_NAME = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
MAX_NAME: Final = 63


def _name(value: str, *, what: str) -> str:
    if len(value) > MAX_NAME or not _NAME.match(value):
        raise ValueError(f"{what} {value!r} must be a DNS-1123 label (lowercase, digits, '-')")
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpecVariable(_Strict):
    """A legacy declared variable; new specs leave the list empty."""

    name: str
    type: Literal["string", "integer", "boolean", "list", "object"]
    required: bool = True
    default: Any = None
    description: str = ""
    pattern: str | None = None
    enum: list[str] | None = None
    minimum: int | None = None
    maximum: int | None = None


class OverrideableField(_Strict):
    """A day2 value the cluster creator may set for a spec addon."""

    path: str = Field(min_length=1, max_length=253)
    type: Literal["string", "integer", "boolean", "object", "array"] = "string"
    default: Any = None
    description: str = ""


class SpecAddon(_Strict):
    """A day2 addon every cluster of this spec should get."""

    team: str
    name: str
    version: str = Field(min_length=1, max_length=128)
    overrideable: list[OverrideableField] = Field(default_factory=list)

    @field_validator("team", "name")
    @classmethod
    def _labels(cls, value: str) -> str:
        return _name(value, what="addon team/name")

    @property
    def key(self) -> AddonKey:
        """``team/name``."""
        return AddonKey(self.team, self.name)


LEGACY_LOCKED_PATHS: Final = "immutable_paths"


class Day1Config(_Strict):
    """What the spec says about the cluster file."""

    variables: list[SpecVariable] = Field(default_factory=list)
    structure: dict[str, Any] = Field(default_factory=dict)
    locked_paths: list[str] = Field(default_factory=list)
    """Template-input paths whose value in ``values`` every create must use (ADR-0026)."""
    template: str = ""
    values: dict[str, Any] = Field(default_factory=dict)
    """Inputs for the template: presets the user may change, and the locked values."""

    @model_validator(mode="before")
    @classmethod
    def _read_legacy_locked_paths(cls, data: object) -> object:
        """``immutable_paths`` is the old name of ``locked_paths``; it is read, never written."""
        if not isinstance(data, Mapping) or LEGACY_LOCKED_PATHS not in data:
            return data
        document = dict(cast("Mapping[str, object]", data))
        if "locked_paths" in document:
            raise ValueError(
                f"{LEGACY_LOCKED_PATHS} is the old name of locked_paths; give only locked_paths"
            )
        document["locked_paths"] = document.pop(LEGACY_LOCKED_PATHS)
        return document


class Day2Config(_Strict):
    """What the spec says about day2."""

    addons: list[SpecAddon] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_addons(self) -> Day2Config:
        keys = [str(a.key) for a in self.addons]
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            raise ValueError(f"addons listed twice: {', '.join(duplicates)}")
        return self


class SpecMetadata(_Strict):
    """A spec's name, version and labels."""

    name: str
    description: str = ""
    version: str = "1.0.0"
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name_is_a_label(cls, value: str) -> str:
        return _name(value, what="spec name")

    @field_validator("version")
    @classmethod
    def _version_is_one_token(cls, value: str) -> str:
        if not _VERSION.match(value):
            raise ValueError(f"spec version {value!r} must be one word, like 1.2.0")
        return value


class SpecBody(_Strict):
    """``spec``: the day1 and day2 parts."""

    day1: Day1Config = Field(default_factory=Day1Config)
    day2: Day2Config = Field(default_factory=Day2Config)


class ClusterSpec(_Strict):
    """A cluster spec document."""

    apiVersion: Literal["wingman.io/v1"] = "wingman.io/v1"
    kind: Literal["ClusterSpec"] = "ClusterSpec"
    metadata: SpecMetadata
    spec: SpecBody = Field(default_factory=SpecBody)

    def presets(self) -> dict[str, object]:
        """The preset inputs: legacy variable defaults, then ``spec.day1.values`` over them."""
        presets: dict[str, object] = {
            v.name: v.default for v in self.spec.day1.variables if v.default is not None
        }
        presets.update(self.spec.day1.values)
        return presets

    def locks(self) -> tuple[Lock, ...]:
        """The locks a create enforces (a lock that breaks the save rules is not one)."""
        return enforced_locks(self.spec.day1.locked_paths, self.spec.day1.values)

    def requested_addons(
        self, overrides: Mapping[str, Mapping[str, object]]
    ) -> list[RequestedAddon]:
        """The spec's addons with the create-time override values (keyed ``team/name``).

        Raises ``InvalidSpecError`` for overrides of addons the spec does not list.
        """
        known = {str(a.key) for a in self.spec.day2.addons}
        unknown = sorted(set(overrides) - known)
        if unknown:
            raise InvalidSpecError(
                f"spec {self.metadata.name} has no such addons",
                [
                    f"override for {key!r}: the spec lists {sorted(known) or 'no addons'}"
                    for key in unknown
                ],
            )
        return [
            RequestedAddon(a.team, a.name, a.version, dict(overrides.get(str(a.key), {})))
            for a in self.spec.day2.addons
        ]


def parse_spec(content: str, *, expected_name: str | None = None) -> ClusterSpec:
    """Parse a spec file. Raises ``InvalidSpecError`` with every problem found."""
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise InvalidSpecError("the spec is not valid YAML", [str(exc)]) from exc
    if not isinstance(document, dict):
        raise InvalidSpecError("the spec is not a YAML mapping")
    try:
        spec = ClusterSpec.model_validate(document)
    except ValidationError as exc:
        raise InvalidSpecError("the spec is not a valid ClusterSpec", _problems(exc)) from exc
    if expected_name is not None and spec.metadata.name != expected_name:
        raise InvalidSpecError(
            "the spec's name does not match its file",
            [f"metadata.name is {spec.metadata.name!r}, the file is {expected_name}.yaml"],
        )
    return spec


def validate_spec(document: Mapping[str, object]) -> ClusterSpec:
    """Validate a spec sent by a client. Raises ``InvalidSpecError``."""
    try:
        return ClusterSpec.model_validate(document)
    except ValidationError as exc:
        raise InvalidSpecError("the spec is not a valid ClusterSpec", _problems(exc)) from exc


def rule_problems(spec: ClusterSpec) -> list[str]:
    """The flavor rules ``spec`` breaks that need no other file.

    Safe values (ADR-0013), owner numbers (ADR-0028) and locks (ADR-0026).
    A save refuses them, together with configs that do not resolve
    (ADR-0027); a spec already in GitLab that breaks them still loads, and
    the API lists them as its ``warnings``.
    """
    values = spec.spec.day1.values
    return [
        *check_inputs(values),
        *owner_problems(values),
        *lock_problems(spec.spec.day1.locked_paths, values),
    ]


def dump_spec(spec: ClusterSpec) -> str:
    """The file content for a spec; the shared template is never stored in it."""
    document = spec.model_dump(mode="json", exclude={"spec": {"day1": {"template"}}})
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)


def with_template(spec: ClusterSpec, template: str) -> ClusterSpec:
    """The spec as the API returns it: ``day1.template`` filled with the shared template."""
    day1 = spec.spec.day1.model_copy(update={"template": template})
    return spec.model_copy(update={"spec": spec.spec.model_copy(update={"day1": day1})})


def _problems(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(p) for p in error['loc']) or '(document)'}: {error['msg']}"
        for error in exc.errors()
    ]
