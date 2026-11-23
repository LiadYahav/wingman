"""A pool's servers are named by its InfraEnv's agentLabels, as add-server-to-mce draws them."""

from __future__ import annotations

import pytest

from wingman_day1.domain.infra_env_pools import InfraEnvObservation, Pool, pool_label_problems

LABELS = {
    "redbull.io/flavor": "c200",
    "redbull.io/size": "mtl",
    "redbull.io/site": "five",
    "topology.kubernetes.io/zone": "az1",
}


def test_the_labels_name_the_servers_flavor_size_site_and_never_the_zone() -> None:
    pool = Pool.observed(InfraEnvObservation("c200-mtl-az1", LABELS))
    assert (pool.server_prefix, pool.label_problems) == ("ocp-c200-mtl-five-", ())
    assert pool.names("ocp-c200-mtl-five-fch2145v1ab")
    assert not pool.names("ocp-c200-mtl-fivex-fch2145v1ab"), "the prefix ends where a word ends"
    assert not pool.names("ocp-c200n-mtl-five-fch2145v1ab"), "a variant is another flavor"
    assert not pool.names("ocp-c200-kv32-five-02a1b2c3d4e5")
    assert not pool.names("OCP-C200-MTL-FIVE-FCH2145V1AB"), "case as given, as the regex"


def test_a_vm_pool_is_named_by_its_size_too() -> None:
    labels = {**LABELS, "redbull.io/size": "kv32"}
    pool = Pool.observed(InfraEnvObservation("c200-kv32-az1", labels))
    assert pool.names("ocp-c200-kv32-five-02a1b2c3d4e5")


@pytest.mark.parametrize(
    ("labels", "problems"),
    [
        ({}, ("redbull.io/flavor is missing", "redbull.io/size is missing",
              "redbull.io/site is missing")),
        ({**LABELS, "redbull.io/site": ""}, ("redbull.io/site is missing",)),
        ({**LABELS, "redbull.io/site": "bat-yam"},
         ("redbull.io/site='bat-yam' is not one lowercase word of letters and digits",)),
        ({**LABELS, "redbull.io/flavor": "C200"},
         ("redbull.io/flavor='C200' is not one lowercase word of letters and digits",)),
    ],
)  # fmt: skip
def test_labels_that_cannot_name_servers_say_why_in_the_workflows_words(
    labels: dict[str, str], problems: tuple[str, ...]
) -> None:
    assert pool_label_problems(labels) == problems
    pool = Pool.observed(InfraEnvObservation("x", labels))
    assert (pool.server_prefix, pool.label_problems) == (None, problems)
    assert not pool.names("ocp-c200-mtl-five-a")


def test_an_unread_pool_names_no_server_and_has_no_problem() -> None:
    pool = Pool.unread("c200-mtl-az1")
    assert (pool.server_prefix, pool.label_problems) == (None, ())
    assert not pool.names("ocp-c200-mtl-five-a")
