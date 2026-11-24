"""What a viewer may know of day2's destinations, and how their answers name them (ADR-0068)."""

from __future__ import annotations

import pytest

from wingman_core.domain.redaction import HIDDEN
from wingman_core.domain.users import Role, User
from wingman_day2.domain.clusters import ClusterRef, DefaultsScope
from wingman_day2.domain.visibility import (
    Sight,
    is_tenant,
    real_path,
    sees_destination,
    sees_scope,
)

MCE = "ocp4-prod-mce-site1-a"
SEED = "ocp4-prod-seed-site1-az1-a"
LARK = ClusterRef.hosted("site1", "prod", MCE, "ocp4-prod-lark-site1")
OWL = ClusterRef.hosted("site1", "prod", MCE, "ocp4-prod-owl-site1")
KV = ClusterRef.hosted("site1", "prod", SEED, "ocp4-prod-kv-site1-az1-a")
HUB = ClusterRef.hub()
MCE_HUB = ClusterRef.mce_hub("site1", "prod", MCE)
SEED_HUB = ClusterRef.mce_hub("site1", "prod", SEED)
UPI = ClusterRef.upi("site1", "prod", "ocp4-dok-site1")
LABELS = {
    DefaultsScope.HUB: "the hub",
    DefaultsScope.MCES: "every MCE",
    DefaultsScope.HOSTED_CLUSTERS: "every hosted cluster",
    DefaultsScope.UPI: "every UPI cluster",
}
SIGHT = Sight.of([HUB, MCE_HUB, SEED_HUB, LARK, OWL, KV, UPI], LABELS)
VIEWER = User("vic", Role.VIEWER)
ADMIN = User("jane", Role.ADMIN)


def test_a_viewer_knows_the_tenants_clusters_and_the_hosted_clusters_scope_alone() -> None:
    assert [r for r in (HUB, MCE_HUB, SEED_HUB, LARK, KV, UPI) if is_tenant(r)] == [LARK]
    assert sees_destination(VIEWER, LARK) and not sees_destination(VIEWER, UPI)
    assert all(sees_destination(ADMIN, r) for r in (HUB, MCE_HUB, KV, UPI))
    assert [s for s in DefaultsScope if sees_scope(VIEWER, s)] == [DefaultsScope.HOSTED_CLUSTERS]
    assert all(sees_scope(ADMIN, s) for s in DefaultsScope)


def test_the_redactor_has_every_hidden_name_and_no_tenants() -> None:
    assert SIGHT.redactor.names == {
        MCE,
        SEED,
        KV.name,
        UPI.name,
        "prod-hub",
        "prod-hub-upi",
    }


def test_a_tenants_id_reads_as_its_name_and_its_folder_from_it() -> None:
    folder = f"sites/site1/prod/mces/{MCE}/{LARK.name}"
    assert SIGHT.rename(LARK.id) == LARK.name
    assert SIGHT.rename(f"{folder}/cert/values.yaml") == f"{LARK.name}/cert/values.yaml"
    assert SIGHT.rename(folder) == LARK.name
    assert SIGHT.rename(f"sites/site1/prod/mces/{MCE}/values.yaml") == (
        f"sites/site1/prod/mces/{MCE}/values.yaml"
    ), "the redactor hides the MCE in it"
    assert SIGHT.rename(KV.id) == KV.id
    assert SIGHT.path(f"sites/site1/prod/mces/{MCE}/in-cluster/cert/values.yaml") is None


def test_a_viewers_path_is_mapped_back_to_the_repos() -> None:
    assert real_path(LARK, f"{LARK.name}/cert/values.yaml") == (
        f"sites/site1/prod/mces/{MCE}/{LARK.name}/cert/values.yaml"
    )
    assert real_path(LARK, f"sites/site1/prod/mces/{HIDDEN}/values.yaml") == (
        f"sites/site1/prod/mces/{MCE}/values.yaml"
    )
    assert real_path(LARK, "operators/cert/values.yaml") == "operators/cert/values.yaml"


@pytest.mark.parametrize(
    ("path", "shown"),
    [
        (
            f"sites/site1/prod/mces/{MCE}/{LARK.name}/cert/values.yaml",
            f"{LARK.name}/cert/values.yaml",
        ),
        ("operators/cert/values.yaml", "operators/cert/values.yaml"),
        ("defaults/hosted-clusters/cert/values.yaml", "defaults/hosted-clusters/cert/values.yaml"),
        (
            "defaults/hosted-clusters/cert/values-prod.yaml",
            "defaults/hosted-clusters/cert/values-prod.yaml",
        ),
        (
            f"defaults/hosted-clusters/cert/values-{LARK.name}.yaml",
            f"defaults/hosted-clusters/cert/values-{LARK.name}.yaml",
        ),
        (f"defaults/hosted-clusters/cert/values-{KV.name}.yaml", None),
        ("defaults/hosted-clusters/exclusions.yaml", None),
        ("defaults/mces/cert/values.yaml", None),
        ("defaults/hub/cert/values.yaml", None),
        (f"sites/site1/prod/mces/{MCE}/in-cluster/cert/values.yaml", None),
        (f"sites/site1/prod/mces/{SEED}/{KV.name}/cert/values.yaml", None),
        (f"sites/site1/prod/mces/{MCE}/values.yaml", None),
        ("sites/site1/prod/upi/ocp4-dok-site1/cert/values.yaml", None),
    ],
)
def test_a_viewer_reads_a_tenants_files_and_the_teams_own(path: str, shown: str | None) -> None:
    assert SIGHT.file(path) == shown


def test_a_viewers_findings_are_about_a_tenant_or_no_destination() -> None:
    assert SIGHT.finding("", "") and SIGHT.finding(LARK.id, "")
    assert SIGHT.finding("", "operators/cert/cert.yaml")
    assert not SIGHT.finding(MCE_HUB.id, "") and not SIGHT.finding("", "defaults/mces/cert")
    assert not SIGHT.finding(LARK.id, f"sites/site1/prod/mces/{MCE}/values.yaml")


@pytest.mark.parametrize(
    ("text", "about"),
    [
        (f"Install addon t/cert on {LARK.name}", True),
        (f"Install cert on lark\n\nCluster: {LARK.id}", True),
        (f"Install cert on {LARK.name}: ArgoCD on {MCE} generates it", True),
        ("Promote addon t/cert to a fleet default on every hosted cluster", True),
        (f"Install addon t/cert on {MCE}", False),
        (f"Install addon t/cert on {LARK.name}, and {SEED} too", False),
        (f"Install cert on {MCE}\n\nCluster: {MCE_HUB.id}", False),
        (f"Install addon t/cert on {KV.name}", False),
        ("Install addon t/cert on prod-hub", False),
        (f"Install addon t/cert on {UPI.name}", False),
        ("Promote addon t/cert to a fleet default on every MCE", False),
        (f"Update addon t/cert fleet default on every hosted cluster\n- **x** (`{UPI.id}`)", False),
        ("Update addon t/cert Sig values", False),
        (f"Install addon t/cert on {LARK.name}-old", False),
    ],
)
def test_a_merge_request_or_commit_is_a_viewers_when_about_a_tenant_alone(
    text: str, about: bool
) -> None:
    assert SIGHT.about(text) is about
