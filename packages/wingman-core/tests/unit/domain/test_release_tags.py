"""An OpenShift release tag: the release it names, and the shape the chart renders."""

from __future__ import annotations

import pytest

from wingman_core.domain.release_tags import ARCHES, MAX_TAG_LENGTH, is_release_tag, without_arch


@pytest.mark.parametrize("arch", ARCHES)
def test_every_openshift_arch_comes_off(arch: str) -> None:
    assert without_arch(f"4.16.27-{arch}") == "4.16.27"


@pytest.mark.parametrize(
    ("tag", "release"),
    [
        ("4.16.0-rc.1-x86_64", "4.16.0-rc.1"),  # a prerelease stays
        ("4.16.0-ec.2-aarch64", "4.16.0-ec.2"),
        ("4.16.0-rc.1", "4.16.0-rc.1"),  # no arch: nothing comes off
        ("4.16.27", "4.16.27"),
        ("", ""),
    ],
)
def test_a_prerelease_is_kept_and_a_tag_without_an_arch_is_left_alone(
    tag: str, release: str
) -> None:
    assert without_arch(tag) == release


@pytest.mark.parametrize(
    "tag",
    [
        "4.19.10-multi-arch",  # 'arch' is no architecture
        "4.16.27-X86_64",  # architectures are lower case
        "4.16.27-x86_64 ",  # the caller trims what a person typed
        "4.16.27-",
        "x86_64",
    ],
)
def test_a_suffix_that_is_no_arch_stays(tag: str) -> None:
    assert without_arch(tag) == tag


def test_only_the_last_part_is_an_arch() -> None:
    assert without_arch("4.16.27-x86_64-x86_64") == "4.16.27-x86_64"
    assert without_arch("4.16.27-multi-rc.1") == "4.16.27-multi-rc.1"


@pytest.mark.parametrize(
    "tag",
    [
        "4.18.22",
        "4.18.22-x86_64",
        "4.21.40-multi",
        "4.16.0-rc.1-x86_64",  # a prerelease, dots and a second dash
        "4.16.0-0.nightly-2026-11-01-000000",
        "10.0.0-s390x",
        "4.16.27-" + "a" * (MAX_TAG_LENGTH - len("4.16.27-")),  # as long as a tag may be
    ],
)
def test_a_release_with_an_optional_lower_case_suffix_is_a_release_tag(tag: str) -> None:
    assert is_release_tag(tag)


@pytest.mark.parametrize(
    "tag",
    [
        "",
        "4.16",
        "4.16.x",
        "latest",
        "v4.16.27",
        "4.16.27-",  # a dash with nothing after it
        "4.16.27_x86_64",  # the release and its arch are split by '-'
        "4.16.27-X86_64",  # OpenShift's tags are lower case
        "4.16.27-x86_64:latest",  # what follows ':' is no part of a tag
        "4.16.27-x86_64@sha256",
        "4.16.27-x86/64",
        "4.16.27 -x86_64",
        " 4.16.27",
        "4.16.27-x86_64\n",
        "\u0664.16.27",  # a digit, but not an ASCII one
        "4.16.27-" + "a" * (MAX_TAG_LENGTH + 1 - len("4.16.27-")),  # one too long
    ],
)
def test_anything_else_is_not_a_release_tag(tag: str) -> None:
    assert not is_release_tag(tag)
