"""What a freshly rendered cluster file must hold before a create proposes it.

Each specs project has its own ``cluster-template.j2``, so an older template
may not read an input a newer Wingman offers. Rather than drop such an input
silently, a create checks the rendered file: the values-file contract
(ADR-0012), then every input the template must write as given:

- each nodepool's ``tuning_config`` as ``tuningConfig`` (ADR-0061);
- the image mirrors as ``imageContentSources`` and ``disableIdmsMerge`` (ADR-0063);
- each nodepool's ``additional_infra_envs`` as ``additionalInfraEnvNames`` (ADR-0064);
- each nodepool's ``scale_down_policy`` as its ``redbull.io/scale-down-policy``
  annotation (ADR-0062);
- the deployment's ``excluded_agent_labels`` as every agent nodepool's
  ``excludeAgentLabels`` (ADR-0065), which :func:`with_agent_labels` sets.

A flavor that gives one of the newer inputs is also refused at its save
while the template does not read it (``specs.rule_problems``). The newer
nodepool inputs' own rules, which need no catalog, are :func:`input_problems`.
"""

from __future__ import annotations

from collections.abc import Mapping

from wingman_day1.domain import excluded_agent_labels, nodepool_infra_envs, scale_down_policy
from wingman_day1.domain.cluster_file import WorkflowKeys, load_values, rendered_file_problems
from wingman_day1.domain.image_mirrors import unrendered_mirrors
from wingman_day1.domain.tuning_rule import rendered_problems as unrendered_tuning


def rendered_problems(inputs: Mapping[str, object], rendered: str) -> list[str]:
    """Why ``rendered``, made from ``inputs``, may not be proposed; empty when it may."""
    problems = rendered_file_problems(rendered)
    if problems:
        return problems
    written = load_values(rendered)
    return [
        *unrendered_tuning(inputs, written),
        *unrendered_mirrors(inputs, written),
        *nodepool_infra_envs.rendered_problems(inputs, written),
        *scale_down_policy.rendered_problems(inputs, written),
        *excluded_agent_labels.rendered_problems(inputs, written),
    ]


def input_problems(inputs: Mapping[str, object], owned: WorkflowKeys) -> list[str]:
    """Why a create's nodepools' other InfraEnvs, scale-down policies or excluded labels fail.

    Other InfraEnvs need ``DAY1_MULTI_INFRAENV_NODEPOOLS`` (ADR-0064); a policy
    needs no setting (ADR-0062); the excluded Agent labels are the
    deployment's, never sent otherwise (ADR-0065).
    """
    return [
        *nodepool_infra_envs.input_problems(inputs, enabled=owned.infra_envs),
        *scale_down_policy.input_problems(inputs),
        *excluded_agent_labels.input_problems(inputs, owned.excluded_agent_labels),
    ]


def with_agent_labels(inputs: Mapping[str, object], owned: WorkflowKeys) -> dict[str, object]:
    """The render's inputs with the deployment's excluded Agent labels (ADR-0065)."""
    return excluded_agent_labels.with_labels(inputs, owned.excluded_agent_labels)
