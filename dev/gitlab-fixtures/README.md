# GitLab fixtures

Realistic repo trees for developing and testing Wingman without the air-gapped
GitLab. Each top-level folder is a GitLab group and each folder under it is a
project, laid out exactly as production lays them out:

| Project | What it is | Source (team-redbull, public) |
|---|---|---|
| `gitops-day1/platform-config` | day1 values repo: `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml` plus the site, MCE and global value layers, `upgrade/` (the ladder and one `mces/<mce>.yaml` per MCE: the versions the create form offers), and `mc-files/` (the machine-config sources the CI renders) | `gitops-day1-platform-config` @ `d6e43de`, plus the extra hosted clusters of `sim-day2-day1-platform-config` @ `b46d426`; `mc-files/` written for Wingman |
| `wingman/cluster-specs` | Wingman's specs repo: `cluster-template.j2`, `nodepool-defaults.yaml`, `specs/*.yaml` | Written for Wingman (no upstream) |
| `sigs/redbull` | day2 team repo | `gitops-day2-prod/sigs/redbull` @ `979e306` |
| `sigs/{falcon,lynx,orca}` | day2 team repos (simulation data) | `sim-day2-sigs-{falcon,lynx,orca}` @ 2026-09-29 |
| `helm-charts/<chart>` | one chart repo per chart; each branch is a frozen release | Stub charts written for Wingman; `sim-day2-helm-charts` @ `c3d8b1e` |

## Changes made to the upstream content

- `.github/`, `scripts/` and `tests/` of the day1 repo are left out; Wingman never reads them.
- Two hosted clusters are written for Wingman, shaped like production's hand-written files and not created by Wingman (no flavor header): `ocp4-prod-lark-site1` (production's compact list style, an extra and a `legacy/` config, `nodeLabels`) and `ocp4-prod-heron-site1` (one nodepool without a network config, one with two). Both carry a `vlanId`, `dhcp_values` and a `# === Added by CI ===` block with placeholder `mcConfigMap` entries; import and sync are tested on them.
- `mc-files/` is a small made-up tree with placeholder bodies (no real servers, addresses or hostnames), shaped like the real one: static configs at the root and in `kubevirt/`, a `legacy/` file that Wingman must not offer, and three network templates whose hardware types overlap (`dell`, `dell-data`, `cisco`). ADR-0027 has the rule Wingman reads it by.
- `upgrade/mces/` has a file for every MCE, not only the sandbox's `ocp4-mce-workflow-test`. They are written for Wingman, so that clusters can be created on each MCE: the production MCEs host 4.16 to 4.18 and `ocp4-prep-mce-site1-a` hosts 4.17 to 4.21, so the offered versions differ per MCE (ADR-0034).
- `sites/site1/mces/ocp4-prod-mce-site1-b` and `-c` are written for MCE placement (ADR-0050): two prod MCEs with no cluster yet, so site1 has three prod candidates. `-c` hosts 4.16 and 4.17 only. With `DAY1_FAKE_FLEET`, `dev/fleet-fixtures/mce.yaml` (`hubs:`) gives every MCE its nodes and pods: `-b` has room, `-a` less, `-c` too little.
- Chart repo URLs point at the local GitLab: every `repourl` is `{{GITLAB_URL}}/helm-charts/<chart>.git`, and the seed substitutes `{{GITLAB_URL}}`. Upstream had sanitized placeholders (`...helm-charts...`) or the sim's GitHub URL.
- `access.yaml` (not a project) gives Wingman's account a role below owner on some projects:
  `sigs/orca` is `reporter`, so the fake backend and the tests have one team that has not opted in
  to day2 writes (ADR-0043): its pages load and every write to it is refused with `TEAM_READ_ONLY`.
  The fake applies it; `scripts/dev/seed_gitlab.py` cannot (it seeds as root, who owns what it
  creates) and lists the projects it would apply to.
- `sigs/redbull/operators/kyverno/kyverno.yaml` keeps the **`repoUrl`** spelling on purpose. Production has several files with this known bug (ArgoCD reads only lowercase `repourl`, so the app renders an empty `repoURL`), and Wingman must flag it.

## The day1 template

`wingman/cluster-specs/cluster-template.j2` renders the slim values file the
hostedclusters-setup chart consumes. It is the reference copy: put it at the
root of the real specs repo. It was checked with `helm template` against both
the sandbox chart (`helm-charts-hostedclusters-setup`) and the production chart
from the air-gapped export, using the same value layers ArgoCD's hcAppset uses.
