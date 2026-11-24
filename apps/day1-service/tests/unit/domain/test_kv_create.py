"""A new KV cluster's name, zone, pool, model and inputs (ADR-0069)."""

from __future__ import annotations

from wingman_day1.domain.cluster_file import read_values
from wingman_day1.domain.kv_create import (
    KvModel,
    KvPool,
    choose_model,
    default_version,
    kv_inputs,
    kv_name_problems,
    model_of,
    next_kv_name,
    owner_gaps,
    pool_zone,
    version_choices,
    workers_problems,
    zone_pools,
    zones_of,
)
from wingman_day1.domain.names import Env, HostedClusterNaming
from wingman_day1.domain.paths import ClusterRef

SEED = "ocp4-prod-seed-five-az1-a"
POOLS = ["c200-mtl-az1", "r760-mtl-az2", "c200-kv32-az1", "dell-r660-site1-128c", "r760-mtl-az1"]


def model(name: str, *, mce: str = SEED, site: str = "five") -> KvModel:
    return KvModel(ClusterRef(site, mce, name), {"merkaz": "1"}, (), None, ("r760-mtl-az1",))


def test_a_bare_metal_infra_env_names_its_zone_and_nothing_else_does() -> None:
    assert pool_zone("c200-mtl-az1") == "az1"
    assert pool_zone("c200-kv32-az1") is None  # a VM pool
    assert pool_zone("dell-r660-site1-128c") is None
    assert zones_of(POOLS) == ("az1", "az2")
    assert zone_pools(POOLS, "az1") == ("c200-mtl-az1", "r760-mtl-az1")
    assert zone_pools(POOLS, "az3") == ()


def test_the_name_takes_the_lowest_free_id_letter() -> None:
    taken = {"ocp4-prod-kv-five-az1-a", "ocp4-prod-kv-five-az1-c"}
    assert next_kv_name(Env.PROD, site="five", zone="az1", taken=taken) == (
        "ocp4-prod-kv-five-az1-b"
    )
    every = {f"ocp4-test-kv-five-az1-{c}" for c in "abcdefghijklmnopqrstuvwxyz"}
    assert next_kv_name(Env.TEST, site="five", zone="az1", taken=every) is None


def test_the_name_follows_the_kv_rule_and_provision_clusters_length() -> None:
    naming = HostedClusterNaming()
    assert kv_name_problems("ocp4-prod-kv-five-az1-a", site="five", naming=naming) == []
    long_site = "a-very-long-site-x"
    problems = kv_name_problems(f"ocp4-prod-kv-{long_site}-az1-a", site=long_site, naming=naming)
    assert any("provision-cluster takes at most 24" in p for p in problems)


def test_workers_are_one_to_the_policys_max() -> None:
    assert workers_problems(1) == workers_problems(40) == []
    assert workers_problems(0) and workers_problems(41)


def test_the_model_is_the_newest_on_the_seed_else_the_site_else_any() -> None:
    a, b = model("ocp4-prod-kv-five-az1-a"), model("ocp4-prod-kv-five-az1-b")
    other_seed = model("ocp4-prod-kv-five-az2-c", mce="ocp4-prod-seed-five-az2-a")
    elsewhere = model("ocp4-prod-kv-six-az1-d", mce="ocp4-prod-seed-six-az1-a", site="six")
    every = [a, b, other_seed, elsewhere]
    assert choose_model(every, seed=SEED, site="five") == b
    assert choose_model([other_seed, elsewhere], seed=SEED, site="five") == other_seed
    assert choose_model([elsewhere], seed=SEED, site="five") == elsewhere
    assert choose_model([], seed=SEED, site="five") is None
    # A name off the convention has no id letter: any convention name is newer
    off = model("ocp4-kubevirt-five-az1-9")
    assert choose_model([off, a], seed=SEED, site="five") == a


def test_a_model_gives_its_owner_and_first_nodepools_configs_and_tuning() -> None:
    values = read_values(
        {
            "owner": {"merkaz": "1000", "anaf": 10, "mador": True},
            "nodepool": [
                {"infraEnvName": "r760-mtl-az1", "configs": [{"name": "chrony"}],
                 "tuningConfig": ["kv-tuned"]},
                {"infraEnvName": "c200-mtl-az1"},
            ],
        }
    )  # fmt: skip
    found = model_of(ClusterRef("five", SEED, "ocp4-prod-kv-five-az1-a"), values)
    assert found.owner == {"merkaz": "1000", "anaf": "10"}  # a boolean is no number
    assert owner_gaps(found.owner) == ["mador"]
    assert (found.configs, found.tuning_config) == (("chrony",), ["kv-tuned"])
    assert found.infra_envs == ("r760-mtl-az1", "c200-mtl-az1")
    assert found.letter == "a"


def test_the_inputs_are_one_nodepool_with_the_zone_and_the_models_network_config_reexpanded() -> (
    None
):
    copied = KvModel(
        ClusterRef("five", SEED, "ocp4-prod-kv-five-az1-a"),
        {"merkaz": "1", "anaf": "2", "mador": "3"},
        ("chrony", "nm-conf-prod-kv-five-az1-a-r760", "nm-conf"),
        "kv-tuned",
        ("r760-mtl-az1",),
    )
    inputs = kv_inputs(
        KvPool("r760-mtl-az1", 3, "az1"),
        owner=copied.owner,
        model=copied,
        model_cluster="prod-kv-five-az1-a",
    )
    assert inputs == {
        "owner_merkaz": "1",
        "owner_anaf": "2",
        "owner_mador": "3",
        "nodepools": [
            {
                "infra_env": "r760-mtl-az1",
                "replicas": 3,
                "node_labels": {"topology.kubernetes.io/zone": "az1"},
                "configs": [
                    {"name": "chrony"},
                    {"name": "nm-conf", "hardware": "r760"},
                    {"name": "nm-conf", "hardware": "generic"},
                ],
                "tuning_config": "kv-tuned",
            }
        ],
    }
    bare = kv_inputs(KvPool("c200-mtl-az1", 1, "az1"), owner={}, model=None, model_cluster="")
    assert bare == {
        "nodepools": [
            {
                "infra_env": "c200-mtl-az1",
                "replicas": 1,
                "node_labels": {"topology.kubernetes.io/zone": "az1"},
            }
        ]
    }


def test_the_version_is_the_seeds_default_when_it_offers_it_spelled_as_its_values() -> None:
    offered = ("4.18.56", "4.18.22", "4.17.58")
    assert version_choices("4.18.22-x86_64", offered) == ("4.18.56", "4.18.22-x86_64", "4.17.58")
    assert default_version("4.18.22-x86_64", offered) == "4.18.22-x86_64"
    assert default_version("4.16.1", offered) == "4.18.56"  # not offered: the newest
    assert default_version(None, ()) is None
