"""Kubernetes label selectors, as the Agent provider applies a NodePool's (ADR-0038).

A NodePool's ``spec.platform.agent.agentLabelSelector`` decides which Agents
its Machines may take. Day1 counts the matching Agents itself, so it applies
the selector with Kubernetes' own rules (``metav1.LabelSelectorAsSelector``):
every ``matchLabels`` pair and every ``matchExpressions`` requirement must
hold. ``NotIn`` also matches an Agent without the key. An empty selector
matches every Agent, and so does a NodePool without one: the provider then
uses ``labels.NewSelector()`` (cluster-api-provider-agent,
``controllers/agentmachine_controller.go``, ``findAgent``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Operator(StrEnum):
    """A ``matchExpressions`` operator."""

    IN = "In"
    NOT_IN = "NotIn"
    EXISTS = "Exists"
    DOES_NOT_EXIST = "DoesNotExist"


@dataclass(frozen=True, slots=True)
class LabelRequirement:
    """One ``matchExpressions`` entry."""

    key: str
    operator: Operator
    values: tuple[str, ...] = ()

    def matches(self, labels: Mapping[str, str]) -> bool:
        """Whether ``labels`` meet this requirement."""
        match self.operator:
            case Operator.IN:
                return self.key in labels and labels[self.key] in self.values
            case Operator.NOT_IN:
                return self.key not in labels or labels[self.key] not in self.values
            case Operator.EXISTS:
                return self.key in labels
            case Operator.DOES_NOT_EXIST:
                return self.key not in labels

    def describe(self) -> str:
        """The requirement as ``kubectl`` writes it: ``k in (a, b)``, ``k``, ``!k``."""
        values = ", ".join(self.values)
        match self.operator:
            case Operator.IN:
                return f"{self.key} in ({values})"
            case Operator.NOT_IN:
                return f"{self.key} notin ({values})"
            case Operator.EXISTS:
                return self.key
            case Operator.DOES_NOT_EXIST:
                return f"!{self.key}"


@dataclass(frozen=True, slots=True)
class LabelSelector:
    """A label selector: ``matchLabels`` and ``matchExpressions``, all of which must hold."""

    match_labels: tuple[tuple[str, str], ...] = ()
    match_expressions: tuple[LabelRequirement, ...] = ()

    def matches(self, labels: Mapping[str, str]) -> bool:
        """Whether an object with ``labels`` is selected. An empty selector selects all."""
        return all(labels.get(key) == value for key, value in self.match_labels) and all(
            requirement.matches(labels) for requirement in self.match_expressions
        )

    def describe(self) -> str | None:
        """The selector in words, ``k=v, k2 in (a, b)``; ``None`` when it selects everything."""
        parts = [f"{key}={value}" for key, value in sorted(self.match_labels)]
        parts += [requirement.describe() for requirement in self.match_expressions]
        return ", ".join(parts) or None


def selects(selector: LabelSelector | None, labels: Mapping[str, str]) -> bool:
    """Whether ``selector`` selects ``labels``; no selector selects everything."""
    return selector is None or selector.matches(labels)
