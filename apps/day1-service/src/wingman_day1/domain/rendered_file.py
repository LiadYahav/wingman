"""What a freshly rendered cluster file must hold before a create proposes it.

Each specs project has its own ``cluster-template.j2``, so an older template
may not read an input a newer Wingman offers. Rather than drop such an input
silently, a create checks the rendered file: the values-file contract
(ADR-0012), then every input the template must write as given:

- each nodepool's ``tuning_config`` as ``tuningConfig`` (ADR-0061);
- the image mirrors as ``imageContentSources`` and ``disableIdmsMerge`` (ADR-0063);
- each nodepool's ``additional_infra_envs`` as ``additionalInfraEnvNames`` (ADR-0064).

A flavor that gives one of the newer inputs is also refused at its save
while the template does not read it (``specs.rule_problems``).
"""

from __future__ import annotations

from collections.abc import Mapping

from wingman_day1.domain import nodepool_infra_envs
from wingman_day1.domain.cluster_file import load_values, rendered_file_problems
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
    ]
