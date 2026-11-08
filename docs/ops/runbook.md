# Runbook

One section per alert in `deploy/helm/wingman/files/alerts.rules.yaml`; each alert's
`runbook` annotation points here. Metric meanings are in `metrics.md`.
`job` is the Service that was scraped (`wingman-day1` or `wingman-day2`).

## WingmanServiceDown

Prometheus has not scraped a Wingman service for 5 minutes.

1. `oc -n <ns> get pods -l app.kubernetes.io/name=wingman`. A crash loop at
   start-up is usually a settings validator refusing the configuration (it
   names the variable; ADR-0009): an empty `GITLAB_TOKEN`, a `JWT_SECRET_KEY`
   under 32 characters, or the fake Git backend in production.
2. If the pod runs but is not scraped, check the ServiceMonitor selects the
   Service (`monitoring.serviceMonitor` values) and that `/metrics` answers on
   the pod's port: `oc exec <pod> -- curl -s localhost:8001/metrics | head`
   (day1's port; day2 listens on 8002).

## WingmanHighServerErrorRate

More than 5% of a service's requests end in a 5xx for 10 minutes.

1. Split by route: `sum by (route) (rate(wingman_http_requests_total{job="<job>",status_class="5xx"}[10m]))`.
2. If the errors are GitLab's (502 `GIT_*`, 503 `GIT_UNAVAILABLE`, 504
   `AMBIGUOUS_WRITE`), follow the GitLab sections below.
3. Otherwise, find the request ids in the error bodies users report
   (`request_id`) and search the service log for them.

## WingmanVersionSkew

day1 and day2 report different versions for an hour. Images are copied into
the air gap by hand, so one is usually missing.

1. `wingman_build_info` shows which component runs which `version` and `commit`.
2. Roll the lagging component to the same image tag (`image.<component>.tag`).

## WingmanGitLabTokenRejected

GitLab answered 401 or 403 to **Wingman's own token**. Every user is affected.

1. Check the token in the `wingman-secrets` Secret (`GITLAB_TOKEN`, from the
   Helm value `gitlab.accessToken`): has it expired or been revoked? GitLab shows its expiry under the owning
   account's access tokens.
2. Check the account is still a member of the day1 project, the specs project
   and every team project in the sigs group, with at least Developer role (it
   pushes branches and opens merge requests) and the right to merge.
3. Replace the token (`helm upgrade` with the new `gitlab.accessToken`: a
   changed Secret restarts both services); the alert clears 10 minutes after
   the last denied call.

## WingmanGitLabUnavailable

More than 20% of a service's GitLab calls fail with "unavailable" (unreachable,
or 5xx after retries) for 10 minutes. No write was attempted for these.

1. Is GitLab itself healthy? Check its status page or `/-/readiness` from
   inside the cluster.
2. If GitLab is fine, check the path from the pod: DNS, proxy, and TLS
   (`GITLAB_VERIFY_TLS`, from `gitlab.verifyTls`, and the CA bundle in
   `tls.caBundle`).
3. `wingman_dependency_request_duration_seconds` shows whether calls time out
   (near the read timeout) or fail fast (refused connection).

## WingmanGitLabSlow

The 95th percentile of a service's GitLab call time is over 5 seconds for 15
minutes. Pages that walk many files (the cluster list, a team's installed
charts) become slow.

1. Which operations: `histogram_quantile(0.95, sum by (operation, le) (rate(wingman_dependency_request_duration_seconds_bucket{job="<job>"}[15m])))`.
2. GitLab's own load, or rate limiting (429s are retried and show up as slow
   calls).

## WingmanAmbiguousWrite

A write (commit, branch, merge request, approval or merge) was sent to GitLab
but its outcome is unknown: it timed out, or GitLab answered 5xx after it was
sent. Wingman never retries writes (ADR-0006), so nothing is duplicated, but
someone must look.

1. The `operation` label says which write. The service log line with the same
   time has the request id and the merge request or branch involved.
2. In GitLab, check whether the commit, branch or MR exists or the MR was
   merged. If it did happen, nothing to do. If not, ask the user to retry from
   Wingman.
