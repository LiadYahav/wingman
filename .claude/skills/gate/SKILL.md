---
name: gate
description: Run Wingman's full local CI gate (everything .github/workflows/ci.yml runs, in the same order) and report every failure. Use before committing a stage, or when asked to verify the repo.
disable-model-invocation: true
---

Run the gate from the repository root and report each failed step with its
output:

```bash
scripts/gate.sh          # Python and web
scripts/gate.sh python   # Python only
scripts/gate.sh web      # web only
```

If GitLab-facing code changed, also run the contract suite against the local
GitLab (start it with `scripts/dev/gitlab-up.sh token`):

```bash
WINGMAN_TEST_GITLAB_URL=http://localhost:8929 WINGMAN_TEST_GITLAB_TOKEN=wingman-local-dev-token-0001 \
  uv run pytest -m live_gitlab
```

A green gate is not the end: re-read the docs the change made wrong
(CLAUDE.md, the ADRs it touches, `docs/ops/metrics.md`) and fix them in the
same commit.
