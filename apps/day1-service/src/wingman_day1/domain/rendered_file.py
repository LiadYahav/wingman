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
:func:`render_new_file` runs every check a new file's inputs and text need,
for a tenant's create from a flavor and for a KV cluster's (ADR-0069).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from wingman_day1.domain import excluded_agent_labels, nodepool_infra_envs, scale_down_policy
from wingman_day1.domain.cluster_file import (
    WorkflowKeys,
    load_values,
    rendered_file_problems,
    require_valid,
)
from wingman_day1.domain.errors import InvalidInputError, RenderError
from wingman_day1.domain.image_mirrors import mirror_problems, unrendered_mirrors
from wingman_day1.domain.machine_configs import (
    MachineConfigCatalog,
    cluster_config_problems,
    expand_network_configs,
)
from wingman_day1.domain.owners import owner_problems
from wingman_day1.domain.template import render_cluster_file
from wingman_day1.domain.tuning_profiles import TuningCatalog
from wingman_day1.domain.tuning_profiles import input_problems as tuning_problems
from wingman_day1.domain.tuning_rule import render_inputs
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


def render_new_file(
    template: str,
    inputs: Mapping[str, object],
    *,
    catalog: MachineConfigCatalog,
    tuning: TuningCatalog,
    owned: WorkflowKeys,
    cluster_name: str,
    problems: Sequence[str] = (),
) -> str:
    """A new cluster file from ``inputs`` (already ``check_inputs``-safe), after every check.

    ``problems`` are the caller's own (a flavor's locks and sizing); then the
    owners, the image mirrors, the machine configs for the chart's
    ``cluster_name``, the tuning profiles and the newer nodepool inputs. The
    network config is expanded, the deployment's excluded Agent labels added
    (ADR-0065), and the rendered text must keep the values-file contract and
    hold every input as given.
    """
    found = [*problems, *owner_problems(inputs), *mirror_problems(inputs)]
    found += cluster_config_problems(inputs, catalog, cluster_name=cluster_name)
    found += tuning_problems(inputs, tuning)
    found += input_problems(inputs, owned)
    if found:
        raise InvalidInputError("the cluster's inputs are not acceptable", found)
    ready = render_inputs(expand_network_configs(inputs, cluster_name=cluster_name))
    ready = with_agent_labels(ready, owned)  # the deployment's (ADR-0065)
    if not template.strip():
        raise RenderError("the specs project has no cluster-template.j2")
    rendered = render_cluster_file(template, ready)
    require_valid(  # and what it must hold
        rendered_problems(ready, rendered),
        message="the rendered cluster file breaks the values-file contract",
    )
    return rendered
