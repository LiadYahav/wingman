# GitLab fixtures

Realistic repo trees for developing and testing Wingman without the air-gapped
GitLab. Each top-level folder is a GitLab group and each folder under it is a
project, laid out exactly as production lays them out:

| Project | What it is | Source (team-redbull, public) |
|---|---|---|
| `gitops-day1/platform-config` | day1 values repo: `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml` plus the site, MCE and global value layers, and `upgrade/` (the ladder and one `mces/<mce>.yaml` per MCE: the versions the create form offers) | `gitops-day1-platform-config` @ `d6e43de`, plus the extra hosted clusters of `sim-day2-day1-platform-config` @ `b46d426` |
| `wingman/cluster-specs` | Wingman's specs repo: `cluster-template.j2`, `specs/*.yaml` | Written for Wingman (no upstream) |
| `sigs/redbull` | day2 team repo | `gitops-day2-prod/sigs/redbull` @ `979e306` |
| `sigs/{falcon,lynx,orca}` | day2 team repos (simulation data) | `sim-day2-sigs-{falcon,lynx,orca}` @ 2026-09-29 |
| `helm-charts/<chart>` | one chart repo per chart; each branch is a frozen release | Stub charts written for Wingman; `sim-day2-helm-charts` @ `c3d8b1e` |

## Changes made to the upstream content

- `.github/`, `scripts/` and `tests/` of the day1 repo are left out; Wingman never reads them.
- `upgrade/mces/` has a file for every MCE, not only the sandbox's `ocp4-mce-workflow-test`. They are written for Wingman, so that clusters can be created on each MCE: the production MCEs host 4.16 to 4.18 and `ocp4-prep-mce-site1-a` hosts 4.17 to 4.21, so the offered versions differ per MCE (ADR-0034).
- Chart repo URLs point at the local GitLab: every `repourl` is `{{GITLAB_URL}}/helm-charts/<chart>.git`, and the seed substitutes `{{GITLAB_URL}}`. Upstream had sanitized placeholders (`...helm-charts...`) or the sim's GitHub URL.
- `sigs/redbull/operators/kyverno/kyverno.yaml` keeps the **`repoUrl`** spelling on purpose. Production has several files with this known bug (ArgoCD reads only lowercase `repourl`, so the app renders an empty `repoURL`), and Wingman must flag it.

## The day1 template

`wingman/cluster-specs/cluster-template.j2` renders the slim values file the
hostedclusters-setup chart consumes. It is the reference copy: put it at the
root of the real specs repo. It was checked with `helm template` against both
the sandbox chart (`helm-charts-hostedclusters-setup`) and the production chart
from the air-gapped export, using the same value layers ArgoCD's hcAppset uses.
