# GitLab fixtures

Realistic repo trees for developing and testing Wingman without the air-gapped
GitLab. Each top-level folder is a GitLab group and each folder under it is a
project, laid out exactly as production lays them out:

| Project | What it is | Source (team-redbull, public) |
|---|---|---|
| `gitops-day1/platform-config` | day1 values repo: `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml` plus the site, MCE and global value layers, and `mc-files/` (the machine-config sources the CI renders) | `gitops-day1-platform-config` @ `d6e43de`, plus the extra hosted clusters of `sim-day2-day1-platform-config` @ `b46d426`; `mc-files/` written for Wingman |
| `wingman/cluster-specs` | Wingman's specs repo: `cluster-template.j2`, `openshift-versions.txt`, `nodepool-defaults.yaml`, `specs/*.yaml` | Written for Wingman (no upstream) |
| `sigs/redbull` | day2 team repo | `gitops-day2-prod/sigs/redbull` @ `979e306` |
| `sigs/{falcon,lynx,orca}` | day2 team repos (simulation data) | `sim-day2-sigs-{falcon,lynx,orca}` @ 2026-09-29 |
| `helm-charts/<chart>` | one chart repo per chart; each branch is a frozen release | Stub charts written for Wingman; `sim-day2-helm-charts` @ `c3d8b1e` |

## Changes made to the upstream content

- `.github/`, `scripts/` and `tests/` of the day1 repo are left out; Wingman never reads them.
- Two hosted clusters are written for Wingman, shaped like production's hand-written files and not created by Wingman (no flavor header): `ocp4-prod-lark-site1` (production's compact list style, an extra and a `legacy/` config, `nodeLabels`) and `ocp4-prod-heron-site1` (one nodepool without a network config, one with two). Both carry a `vlanId`, `dhcp_values` and a `# === Added by CI ===` block with placeholder `mcConfigMap` entries; import and sync are tested on them.
- `mc-files/` is a small made-up tree with placeholder bodies (no real servers, addresses or hostnames), shaped like the real one: static configs at the root and in `kubevirt/`, a `legacy/` file that Wingman must not offer, and three network templates whose hardware types overlap (`dell`, `dell-data`, `cisco`). ADR-0027 has the rule Wingman reads it by.
- Chart repo URLs point at the local GitLab: every `repourl` is `{{GITLAB_URL}}/helm-charts/<chart>.git`, and the seed substitutes `{{GITLAB_URL}}`. Upstream had sanitized placeholders (`...helm-charts...`) or the sim's GitHub URL.
- `sigs/redbull/operators/kyverno/kyverno.yaml` keeps the **`repoUrl`** spelling on purpose. Production has several files with this known bug (ArgoCD reads only lowercase `repourl`, so the app renders an empty `repoURL`), and Wingman must flag it.

## The day1 template

`wingman/cluster-specs/cluster-template.j2` renders the slim values file the
hostedclusters-setup chart consumes. It is the reference copy: put it at the
root of the real specs repo. It was checked with `helm template` against both
the sandbox chart (`helm-charts-hostedclusters-setup`) and the production chart
from the air-gapped export, using the same value layers ArgoCD's hcAppset uses.
