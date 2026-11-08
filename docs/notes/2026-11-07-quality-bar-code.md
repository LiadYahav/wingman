# Wingman quality bar: practices from server-scan and herzi, and the gaps to close before rewriting day1/day2

Written 2026-11-07. Read-only study, nothing was modified in any repo.

Path abbreviations used throughout:

- **SS** = `team-redbull/server-scan`
- **HZ** = `team-redbull/herzi`
- **WM** = this repository

How to use this file: Part A says what "good" looks like, with evidence from both repos. Part B is the gap table for Wingman, with priorities. Part C is the ordered P0 checklist. Part D is the target layout, and Part E is the test strategy for GitLab. Part F lists the things the exemplar repos get wrong, so we don't copy them.

---

## Part A. The practices

### A1. Code structure and layering

**server-scan (hexagonal, 4 layers)**

The backend has 23.2k lines in `SS/backend/app`, of which 13.5k are vendor collectors.

```
backend/app/
  domain/            # pure: no I/O, no framework
    enums/core.py          StrEnum states (Vendor, HealthSeverity, OpenShiftState, UnreachableReason…)
    models/                pydantic records (server.py, health_policy.py, audit_event.py…)
    value_objects/         parsing/validation (mac_address.py, bmc_address.py, site.py…)
    ports/                 Protocols/ABCs for every external system
      repository.py        ServerRepository Protocol + frozen dataclass DTOs (Page, FleetSnapshot)
      job_runner.py        JobRunner Protocol
      provider.py          ServerInventoryProvider ABC (collector seam)
      credentials.py, regex_engine.py, bmc_reset.py
    services/              pure functions (classification.py, cursor.py, search.py, health/evaluate.py…)
  application/services/  # use cases orchestrating ports (ingest.py, classification_service.py, auth_service.py…)
  infrastructure/        # adapters: mongodb/, redis/, openshift/, ad/, jobs/{kubernetes,fake,factory}.py,
                         #   providers/{fake,redfish,intersight,…}, logging/, blocking.py, singleflight.py
  api/health.py, api/v1/<resource>.py + <resource>_schemas.py   # thin routers + response schemas
  config/settings.py     # the only place env is read
  dependencies.py        # retrieves objects from app.state (no construction)
  errors.py, exception_handlers.py, middleware/request_context.py, observability/metrics.py
  main.py                # create_app() + lifespan = composition root
```

- **The layering is enforced, not just described.** `SS/pyproject.toml:329-368` has four `import-linter` "forbidden" contracts: domain must not import application, infrastructure or api; infrastructure must not import application or api; application must not import api. CI runs them as `uv run lint-imports` (`SS/.github/workflows/ci.yml:95`).
  - A fifth contract, "application never names a concrete adapter", is recorded as known debt and not gated (`pyproject.toml:332-345`). See Part F.
- **Port example:**
  - The port is `JobRunner(Protocol)` (`SS/backend/app/domain/ports/job_runner.py:92`), whose methods have typed DTOs and documented `Raises:`.
  - It has two adapters: `infrastructure/jobs/kubernetes.py` and an in-memory `infrastructure/jobs/fake.py`. The fake has an injectable `clock: Callable[[], datetime]` and seeds believable history.
  - `infrastructure/jobs/factory.py` picks `kubernetes | fake | off` from settings. The fake is used for dev, tests and screenshots, not only in tests.
  - `providers/fake/` is the same idea for the vendor collectors: one deterministic fake vendor drives every dev environment and the E2E seed (`tools/seed_inventory.py --count 300 --seed 42`).
- **Dependency injection.**
  - Clients are constructed once in `main.py`'s lifespan and stored on `app.state`. Functions in `dependencies.py` only *retrieve* them (docstring at `SS/backend/app/dependencies.py:1-16`).
  - Because of this, tests use `app.dependency_overrides` instead of monkeypatching globals (`SS/tests/api/test_auth.py:96-105`).
  - Every dependency is `async def`, which avoids a threadpool hop per dependency (measured at +0.14 ms each).
- **Thin routers.** Example: `SS/backend/app/api/v1/classification_rules.py` validates input, calls a repository or service, maps to a `*Response` schema, and raises a typed `NotFoundError`.
- **Blocking I/O is isolated with explicit reasoning.**
  - `SS/backend/app/infrastructure/blocking.py` records why `asyncio.to_thread` plus `wait_for` is a trap. An abandoned worker thread keeps running, and interpreter shutdown can hang for 300 s or forever.
  - `singleflight.py` coalesces concurrent identical cache misses.

**herzi (functional core, imperative shell)**

- `HZ/internal/pipeline` is pure: "computes pool decisions from snapshots without I/O or implicit clocks" (`types.go:1`). The clock is passed in (`Decide(f, p, now)`, `decide.go:18`).
- **Ports live beside the pure types they return** (`internal/pipeline/ports.go`), "so adapters and controller test fakes share the same contracts" (`docs/design/notes/pipeline.md`).
- **Adapters assert at compile time that they satisfy their port**, e.g. `var _ pipeline.Installer = (*Installer)(nil)` (`internal/installer/installer.go:44`). `temporalx` narrows the Temporal SDK to a 3-method interface (`options.go:15-21`).
- **There is one composition root**, `cmd/main.go`:
  - `run(args) int`, so that only `main` calls `os.Exit`.
  - Secrets are read only there.
  - `controller.New` rejects a nil port (`"port %s is required"`, `reconciler.go:68-89`).

**Rules for Wingman:**
- Pure domain with an injected clock.
- Ports defined as Protocols beside the domain types.
- Adapters constructed only in the lifespan/composition root.
- Routers that only translate HTTP.
- Layering enforced by import-linter from the first commit.

### A2. Typing and validation

**server-scan**

- **Type checker and annotation gate.**
  - The checker is **ty**, pinned exactly (`ty==0.0.78`). The decision is ADR-0019 (`SS/docs/adr/0019-ty-replaces-mypy.md`), with measurements, the alternatives (Pyright, Pyrefly) and rollback triggers in §8.
  - Annotation completeness is gated by ruff `ANN001…ANN206`, listed code by code so a ruff release can't move the gate (`SS/pyproject.toml:170-191`).
  - `ty check backend/app tools tests` checks the tests too.
  - The rules in `[tool.ty.rules]` that were switched off each have a recorded reason.
- **Enums.** States are `StrEnum` (20 of them, `SS/backend/app/domain/enums/core.py`). `ErrorCode` is an append-only string registry (`errors.py:40`).
- **Pydantic.**
  - Domain models are pydantic `BaseModel`, with safe non-null defaults so sorting and indexing never special-case missing values (`domain/models/server.py:8-11`).
  - DTOs are `@dataclass(frozen=True, slots=True)`, with 53 `frozen=True` sites.
  - **Nothing uses `extra="forbid"`.** Settings use `extra="ignore"`.
- **Settings validation.**
  - `Settings` uses `Literal[...]` for enumerated options, `Field(ge=, gt=, le=)` bounds on every timeout and limit, and `SecretStr` for every secret (`SS/backend/app/config/settings.py:37-265`).
  - `@model_validator`s refuse an insecure production config: a blank or committed-default cursor secret, or two roles sharing one token (`settings.py:315-381`).
- **`Any` is allowed only at untyped vendor-SDK boundaries**, and this is documented (ANN401 is deliberately not selected).

**herzi**

- **Strict YAML decoding.** `dec.KnownFields(true)` (`HZ/internal/config/load.go:63`), plus exactly one document and durations that must be strings.
  - Pointer fields distinguish "unset" from zero.
  - All errors are collected with `errors.Join`.
  - Cross-field rules are checked (`validate.go:122-125`).
- **Removed config keys** produce a typed `RemovedKeyError` whose message deliberately carries no values (`migration.go`). Other decode errors are logged as just "invalid configuration", because they could echo credentials (`cmd/main.go:258-262`).
- **Error scope.** A bad file keeps the last good config (`store.go:33-51`), and an error in one pool blocks only that pool (`validate.go:85-94`).
- **HTTP responses are parsed strictly**: duplicates, trailing data and unknown statuses are rejected, and the body is capped at 1 MiB (`installer.go:247-332`).
- `Intent` is a sealed sum type (`types.go:133-146`).

**Rules for Wingman:**
- One strict checker that gates `src` *and* `tests`.
- Every function annotated.
- States are enums.
- Request bodies and YAML specs use `extra="forbid"`. This goes beyond server-scan, but herzi's `KnownFields` shows the value.
- Value objects validate anything that becomes a GitLab path.
- Secrets are `SecretStr`.
- Startup refuses insecure combinations.

### A3. Testing strategy

**server-scan: about 1,733 pytest functions** (`SS/tests`)

| Directory | Tests | Files | What it covers |
|---|---|---|---|
| `tests/unit/` (`domain/`, `application/`, `infrastructure/`, `observability/`, `tools/`, `config/`) | 1,402 | 86 | Pure logic plus adapters against fake transports |
| `tests/integration/` | 184 | 25 | Repositories, ingest and cache against **real Mongo and Redis** |
| `tests/api/` | 147 | 13 | Full app via lifespan and `dependency_overrides` |

There are also 38 Vitest files and 6 Playwright specs in the frontend.

- **Hand-written fakes over mocks.**
  - `MagicMock`/`AsyncMock` appears in exactly 1 test file. `class _Fake*` fakes appear in about 12, e.g. `_FakeAdApi`, which records which groups were queried (`tests/unit/application/services/test_auth_service.py:24-39`).
  - HTTP adapters are tested with `httpx.MockTransport` handlers (9 files, e.g. `tests/unit/infrastructure/openshift/test_client.py:37-40`).
- **Real backing services, with clean skips.**
  - CI runs `mongo:8` and `redis:8-alpine` as service containers (`ci.yml:194-214`).
  - Each xdist worker gets its own database (`tests/conftest.py:14-30`, ADR-0049).
  - If the stack is down, tests *skip* rather than hang (`tests/_stack_availability.py`, `tests/api/conftest.py`).
  - `testcontainers` is a dev dependency but no test imports it.
- **Markers.** `unit` and `integration` (`pyproject.toml:135-138`), with `asyncio_mode = "auto"`.
- **Guard tests that pin cross-artifact invariants:**
  - `tests/unit/test_no_committed_secrets.py`: an allowlist of placeholder passwords in committed examples.
  - `tests/unit/test_frontend_manager_types.py`: the TypeScript enum copies match the backend's `ManagerType`.
  - A guard test fails if a new per-run stamp is not added to the stable-view set (CLAUDE.md "Key technical facts").
- **Behaviour-sentence test names**, e.g. `test_a_dead_ad_api_raises_not_none_and_not_no_permission`.
- **Coverage is measured but not gated.** CI runs `pytest -n 4`, and on main adds `--cov=app` and uploads XML (`ci.yml:231-244`). There is no `fail_under`.
- **E2E runs against the real backend and a seeded database, with no mock layer** (`ci.yml:280-397`). The Playwright report is uploaded on failure.

**herzi: 35 `*_test.go` files, about 199 `func Test`, plus envtest Ginkgo specs**

- **Fakes, never gomock.** Examples: `sweepFake`, `queuesFake`, `installFake` (`internal/controller/reconciler_test.go:27-80`) and function adapters (`hardening_test.go:143`).
- **The controller-runtime fake client is wrapped for fault injection** (`failingReader`, `deadlineClient`, `patchClient`). HTTP failures are simulated with `httptest.NewTLSServer`, `roundTripFunc` and `brokenBody`.
- **envtest** runs a real kube-apiserver with stub CRDs (`ErrorIfCRDPathMissing: true`). Its "world" fake models reality: installing makes a run appear (`envtest_reconciler_test.go:26-55`).
- **Property tests** with `rapid` (`pipeline/decide_test.go`, `plan_test.go`). **Golden request body** in `internal/installer/testdata/request.json`.
- **Drift tests:**
  - `TestPinnedToThePythonBuilders`: ID formats match the other service.
  - `TestChartDefaultsMatchCode`: reflects over the defaults struct and compares it to the chart values.
  - `TestShippedSampleLoads`.
- **Tests asserting that secrets never reach logs** (`cmd/main_test.go:115,214`).
- **Regression tests named after review findings** (`TestF1…TestF11` in `round2_test.go`). Each was "defect-restoration" checked: the bug was put back and the test was seen to fail.
- **Coverage gate: at least 90% on `internal/pipeline` and `internal/config`** (`HZ/.github/workflows/ci.yml:58-66`). Tests run with `-race`.
- **Chart assertions** (`hack/test-chart.sh`, 223 lines) check RBAC (no wildcards, no write verbs), the hardened securityContext and the schema. **Alert rules are unit-tested** with `promtool test rules`.

**Rules for Wingman:**
- Test pyramid: pure unit, adapter-vs-fake-transport, API via `dependency_overrides`, contract suite against fake and real GitLab, mocked and live Playwright.
- Fakes, not `MagicMock`.
- A coverage floor on domain and application code.
- Guard tests for every cross-artifact copy.
- Every bug fix gets a test that fails with the bug restored.

### A4. CI gates

**server-scan (`SS/.github/workflows/ci.yml`, 745 lines; nothing is allowed to fail)**

- **Workflow-level settings.**
  - `permissions: contents: read`, elevated per job only in `publish`.
  - `concurrency` cancels superseded runs except on main.
  - Every job has `timeout-minutes`.
  - **Every action is SHA-pinned**, with the version in a comment and a paragraph explaining the tj-actions incident (`ci.yml:25-36`, ADR-0013). uv is pinned to `0.12.5`, and `uv sync --all-groups --locked`.
- **`lint` job:**
  - `ruff check`, `ruff format --check`, `ty check backend/app tools tests`
  - the comment-density script, `lint-imports`
  - `pip-audit` (an ephemeral `--with` install), `deptry`
- **`helm` job:** lint every chart (it fails if the glob finds none), then `helm template` under several value combinations that turn on off-by-default features.
- **`test` job:** pytest with Mongo and Redis service containers.
- **`frontend` job:** `npm audit`, lint, typecheck, vitest, build.
- **`e2e` job:** backend, seed, vite, Playwright.
- **`prebuild`:** builds images into the GitHub Actions cache without pushing.
- **`publish` (main only, after all jobs):**
  - semver from Conventional Commits;
  - **refuses a version that does not move forward or would re-tag**;
  - idempotent on re-run;
  - **release notes generated from commit subjects** (there is no CHANGELOG);
  - images tagged `X.Y.Z`, `X.Y`, `X`, `latest`, `sha-`.
- **`deploy`:** bumps the GitOps repo and renders the chart with that repo's values.

**herzi (`HZ/.github/workflows/ci.yml`, 290 lines)**

- **Jobs:**
  - `lint`: `make fmt-check lint`
  - `vuln`: govulncheck
  - `unit`: race, plus the 90% coverage check
  - `integration`: envtest
  - `chart`: helm lint `--strict`, chart tests, promtool, and an RBAC `manifests-drift` check
  - `image`: build only, never pushed
  - `publish`: the same forward-only semver and release notes as server-scan
- **Supply chain:** helm and promtool downloads are verified with `sha256sum --check --strict`, and checkout uses `persist-credentials: false`.
- **No `continue-on-error`.** The only `|| true` is a benign `git describe` fallback.
- A **local mirror of CI** exists in both repos: `make ci` (`HZ/Makefile`) and `/gate` → `SS/.claude/skills/gate/gate.sh`, which runs every step in CI's order and reports all failures.

### A5. Tooling configuration

- **server-scan ruff** (`SS/pyproject.toml:149-280`):
  - `line-length 100`, `target-version py312` (the floor, not the CI interpreter).
  - `select`: `E F I UP B C4 SIM RUF ASYNC S W605 ANN001-206 PTH LOG RET PERF FURB TRY004 TRY300 TRY400 D`, with `pydocstyle convention = "google"`. `C901` was rejected with a reason.
  - Per-file ignores for tests: `S101 S105 S106 S311 D`.
  - `flake8-bugbear extend-immutable-calls = ["fastapi.Query", "fastapi.Depends"]`.
  - Every default is written out explicitly "so an upstream default flip cannot move this gate".
- **Exact pins with a reason comment on every dependency** (`SS/pyproject.toml:9-103`), e.g. why `python-multipart` was removed rather than bumped (7 CVEs, never imported).
  - One `uv.lock`, plus exported `requirements.txt`/`pylock.toml` for the air-gapped build.
- **Claude-side tooling** (`SS/.claude/`):
  - `settings.json` hooks: `ruff format` on every Python edit; refuse an edit to the lint baseline file; refuse attribution trailers (that last one is *that user's* policy).
  - `permissions.allow` covers exactly the gate commands.
  - Path-scoped rules (`rules/{collectors,mongodb,frontend}.md` with `paths:` frontmatter).
  - Read-only reviewer agents: `docs-drift-checker` (`file:line — what it says — what is true now`) and `stored-shape-reviewer` (does the change still work on data the previous code wrote?).
- **Custom gates in `SS/scripts/`:**
  - `check_comment_density.py`: fails on more than 3 consecutive comment lines or a docstring summary longer than 3 lines.
  - The baseline file "may only shrink" and is now empty.
- **herzi Makefile** (`HZ/Makefile`):
  - `SHELL bash -euo pipefail`; tool versions pinned into `./bin`.
  - Targets: `help`, `fmt-check`, `lint`, `vuln`, `test` (race and coverage), `test-integration`, `helm-lint`, `helm-test`, `test-alerts`, `manifests-drift` (`gen-rbac.sh --check`), `ci`, and a guarded `deploy` that requires `VALUES`/`IMG_REPO`/`IMG_TAG`.
- **herzi `.golangci.yml`** (v2, `default: none`): 19 linters listed explicitly, plus a depguard ban on `sort` in favour of `slices`.

### A6. Docs practice

- **ADRs** (`SS/docs/adr/`, 57 files):
  - Named `NNNN-kebab-slug.md`, where the slug is the decision as a sentence (`0027-unknown-is-not-a-reading.md`).
  - The **index is a table in `SS/docs/arc42.md` §9**, and a missing row is a docs-drift finding.
  - **Supersession is written in prose at the top and history is never deleted**, e.g. "Superseded in part by ADR-0057 (2026-11-05)…", "Amends ADR-0007", "Extends ADR-0024. Supersedes nothing." Dead text is struck through with "*(Superseded, kept for the record.)*". Living ADRs get dated `## Update YYYY-MM-DD` sections appended.
  - The structure of one ADR, `SS/docs/adr/0028-operator-writes-clear-the-list-cache.md`:
    ```
    # ADR-0028: an operator write clears the list cache; an ingest write does not

    Date: 2026-09-12
    Status: Accepted

    Amends `docs/adr/0007-scale-verification-and-request-coalescing.md`, which
    introduced the cache-aside list page and its TTL.

    ## Context            (the symptom the operator reported; why the TTL is not survivable)
    ## Decision           (**PUT and DELETE …/maintenance clear every cached list page and facet count. Nothing else does.**
                           then "Three properties are load-bearing: …")
    ## Alternatives rejected   (**Shorten the list TTL to ~1s.** … a 1-second window is still a window …)
    ## Consequences       (… `tests/api/test_maintenance_and_events.py` pins both, and both fail if
                           `_invalidate_list_cache` is removed — verified by removing it.)
    ```
  - Other recurring headings: `## Alternatives rejected`, `## Verification`, `## Evidence`, `## What is still unproven`, `## Deferred`.
  - Representative titles:
    - 0002 RFC 9457 errors
    - 0003 native async PyMongo, not Motor
    - 0010 images versioned by Conventional Commits
    - 0013 SHA pinning without Dependabot
    - 0019 ty replaces mypy
    - 0023 provider ABC contract
    - 0028 cache invalidation
    - 0034 AD login and roles
    - 0044 ingest writes with a revision check
    - 0049 parallel CI tests
- **herzi has no ADR directory.** Its design doc `HZ/docs/design/herzi-design.md` contains:
  - an **Invariants table "(write these tests first)" with columns Invariant | Protects against**;
  - a **Decision log (Topic | Decision)**;
  - "accepted residual risks" and "to verify on a real hub".
  
  `HZ/docs/PLAN.md` has "Decisions already made (do not reopen)", a file-ownership table for parallel agents, and a metrics catalogue ("names are a contract"). Rationale is moved out of code into `docs/design/notes/<package>.md`.
- **Review records** (`HZ/docs/review/*`): verbatim, findings numbered with severity and `file:line`, a concrete failure scenario, **Fix:**, and a table of Finding | Implementation | Regression tests.
- **Runbook** (`HZ/docs/ops/runbook.md`): one section per alert with the exact PromQL, remediation and what *not* to do.
- **CLAUDE.md style:**
  - **server-scan** (`SS/CLAUDE.md`, 489 lines), in order:
    - a doc map ("this file is loaded every session, so it stays short")
    - Claude assets
    - What this is
    - **11 numbered standing conventions**, each with a bold rule, the reason, a dated incident and an ADR pointer
    - Current status and "Explicitly NOT done yet (priority order)"
    - Key technical facts (cross-cutting traps)
    - Verifying your work (the exact commands)
    - Keeping CI current (a quarterly checklist)
    - Where to continue right now (a single entry; older ones move to `docs/notes/session-log.md`)
  - **herzi** (`HZ/CLAUDE.md`, 123 lines): Hard rules ("Fail closed"…), commands, "The gate — agent reports are not proof", Layout, "Behaviour that must not change without a design decision", Pitfalls we hit.
- **Two server-scan rules worth adopting verbatim:**
  - "**Every change updates the docs it makes wrong, in the same commit** (a stale sentence is worse than none: the next session acts on it)."
  - "**Judge each audit by its exit code (`; echo $?`), never by piped or truncated output.**"
- **`.env.example`** (`SS/.env.example`, 495 lines): 24 sections, each non-trivial variable commented with format, default rationale and ADR link. It is the only documented config surface; "do not read os.environ anywhere else".
- **No CHANGELOG in either repo.** Release notes come from commit subjects.

### A7. Error handling, logging, observability

- **server-scan errors** (`SS/backend/app/errors.py`):
  - `AppError` subclasses carry `status_code` and `code`. They are rendered as **RFC 9457 problem+json** with `type`, `title`, `status`, `detail`, `instance`, `code`, `request_id` and `details` (ADR-0002, `exception_handlers.py`).
  - `ErrorCode` is append-only, because clients match on it.
  - **Services raise domain errors, never `HTTPException`.**
  - `RevisionConflictError` (409) carries `current_revision`, which implements optimistic concurrency (ADR-0044: a revision compare-and-set with 3 retries, then an error).
- **herzi errors:**
  - Sentinels `ErrAmbiguous` and `ErrRejected`.
  - A typed `InstallError{Kind,…}` whose `Kind` comes from a **bounded vocabulary of 18 that doubles as the metric label**.
  - Transport errors are classified as *ambiguous*, and the **non-idempotent POST is never retried**.
  - A block marker is written *before* the POST.
  - Ports return results with an `Err` field: "unknown runs must never count as zero" (`internal/pipeline/types.go:51`).
- **Logging:**
  - **server-scan.** structlog JSON in production and console in dev (`infrastructure/logging/config.py`).
    - A pure-ASGI `RequestContextMiddleware` reuses or creates `X-Request-Id`, binds it to contextvars, echoes it in the response and the error body, and logs one structured line per request (`middleware/request_context.py`).
    - A processor drops `password|token|authorization|secret|api_key|credential` keys at any depth (`logging/config.py:30-68`).
    - Event names are dotted (`auth.rejected`, `jobs.disabled`).
  - **herzi.** Messages are sanitized: userinfo, query strings and bearer tokens are stripped and text is capped at 600 chars (`controller/logging.go:92-110`). Repeated errors are de-duplicated.
- **Metrics:**
  - **server-scan** (`observability/metrics.py`): `http_requests_total`, `http_request_duration_seconds`, `dependency_call_duration_seconds`, `cache_operations_total`, `auth_logins_total`, and fleet gauges. There is also a ServiceMonitor and PrometheusRule in the chart.
  - **herzi** (`internal/metrics/metrics.go:65-117`):
    - `herzi_*` names with bounded labels, and series deleted when a pool goes away.
    - There is a `herzi_last_successful_reconcile_timestamp_seconds`.
    - 10 alerts, tested with promtool.
- **Health** (`SS/backend/app/api/health.py`):
  - `/health/live` has no dependency checks.
  - `/health/ready` returns 503 only when the source of truth (Mongo) is down; the Redis cache is reported but degrades.
  - herzi's Temporal client is lazy, so an outage doesn't fail startup probes.
- **Timeouts** are explicit and bounded `Field(gt=0)` settings for every client (`settings.py:225-232`). herzi uses a per-reconcile `context.WithTimeout`, 3 s per Temporal call, and `WithoutCancel` plus 10 s for state patches.

### A8. Config and security

- **One settings module.**
  - server-scan's `config/settings.py` is the only `os.environ` reader, with an `INVENTORY_` prefix.
  - **It refuses insecure production config at startup** (`settings.py:315-381`) and gives dev defaults loud names (`dev-insecure-…-change-in-production`).
  - herzi reads secrets only in `cmd/main.go`, only from env or files via `secretKeyRef`: "never put credentials in values or the ConfigMap". Tokens with CR/LF are rejected.
- **Auth** (server-scan):
  - Roles are a `Role` enum, with `require_admin` and `require_audit_access` dependencies.
  - Bearer tokens are compared with `hmac.compare_digest`.
  - An unknown login is **403, never silently read-only**.
  - Router-level `dependencies=_authenticated` (`main.py:217-223`).
  - A login throttle (ADR-0039).
- **Least privilege:**
  - herzi RBAC is *generated* from markers (get/list/watch, plus patch on one resource). `hack/test-chart.sh` asserts no wildcards and no write verbs. `docs/ops/rbac.md` includes a negative `kubectl auth can-i` check.
  - Both charts set `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, `drop: [ALL]`, seccomp `RuntimeDefault`, and `automountServiceAccountToken: false` where no API access is needed.
  - Images: herzi uses distroless nonroot; server-scan uses a UBI-minimal multi-stage build with `USER 1001`, GID 0 group-writable for OpenShift, and a `HEALTHCHECK`.
- **Chart values validation.** herzi's `values.schema.json` has 16 `additionalProperties: false`, so a typo in values fails `helm install`.
- **Safe defaults.** herzi's dry run is on by default and logged at startup and on every reload.

### A9. Commit and PR conventions

- **Both repos use Conventional Commits, and CI derives the semver from them** (`feat` = minor, `!`/`BREAKING CHANGE` = major).
- **Subjects are written as operator-facing release notes** (CLAUDE.md convention 9). They name the env var, endpoint or Helm value; "`fix: correct the thing` is a wasted line".
- **Bodies (server-scan) have a fixed shape:**
  - an `Operator action: …` line;
  - a `Docs:` list of the files updated in the same commit;
  - ADR references;
  - measurements ("Full suite green (2064 tests)").
- **herzi bodies** give the cause, the measurements and the test evidence, and reference finding IDs and advisory IDs.
- `refactor/test/chore/ci` are deliberately excluded from the release notes.
- Both repos forbid attribution trailers, enforced by a hook in server-scan. **That is those repos' owner's preference, not a quality practice.** Wingman's attribution policy is the Wingman owner's call.

### A10. Frontend practices (server-scan, briefly)

- **Stack:** Vite 8, React 19, react-router 8, TanStack Query 5 and TanStack Table, Tailwind 4, TS 7.
- **oxlint** with `typeAware: true` and `--deny-warnings`.
- **tsconfig** goes beyond `strict`: `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noUnusedLocals/Parameters`, `verbatimModuleSyntax`. The e2e specs are type-checked too (project references).
- **`src/` layout:**
  - `api/` holds one module per resource, `client.ts` and **`queryKeys.ts` (a hierarchical key factory)**.
  - `features/<feature>/` holds `hooks.ts`, pages and **pure logic modules with co-located tests** (e.g. `inventory/rows.ts`).
  - Also `components/`, `lib/` and `types/`.
- **`api/client.ts`** parses every non-2xx response as an RFC 9457 `ApiError`, and a 401 invalidates the `auth.me` query.
- **Query defaults:** `staleTime: 30_000, retry: 1, refetchOnWindowFocus: false` (`lib/query-client.ts`).
- **Mutations** use `setQueryData` and then invalidate.
- **Hand-written API types** with a stated null rule (`X | null` means always sent, `?:` means the API may omit it). Drift is guarded from the Python side.
- **Tests:**
  - 38 Vitest files that stub `fetch` by pathname.
  - 6 Playwright specs against the real backend and a seeded DB, with `workers: 1`, `forbidOnly` in CI, and `trace: retain-on-failure`.

---

## Part B. Gap analysis for Wingman

Priority key:
- **P0**: in place before the first line of the day1/day2 rewrite.
- **P1**: built as part of the rewrite.
- **P2**: after the rewrite.

All Wingman citations are relative to WM.

| # | Area | Wingman today (cited) | Change needed | Prio |
|---|---|---|---|---|
| 1 | Layering | Two layers only: `routers/` and `services/`. Services raise `fastapi.HTTPException` in 7 files (e.g. `apps/day1-service/src/services/cluster_service.py:206,259,304`, `apps/day2-service/src/services/addon_service.py:442,524`). Business logic sits in routers (`routers/clusters.py:60-119,390-463`, `routers/specs.py:126-207`). God-class `addon_service.py` is 879 lines. No ports anywhere. | domain / application / infrastructure / api per service (Part D). Services raise `AppError`s. import-linter with **all five** contracts, including the one server-scan couldn't gate. | P0 (skeleton and contracts), P1 (fill in) |
| 2 | GitLab seam | One concrete `GitLabClient` over python-gitlab. Every async method is `asyncio.to_thread` around a sync call (`packages/shared-python/src/wingman_shared/gitlab_client.py:452-568`). Returns raw `dict[str, Any]`. The lazy `project` property does network I/O when first touched, from sync code (`:77-93`). | A `GitRepository`/`GitLabPort` Protocol with typed DTOs. An httpx.AsyncClient adapter (ADR). An `InMemoryGitLab` fake. A contract suite run against both (Part E). | **P0** |
| 3 | Async correctness | About 60 sync GitLab calls inside `async def` (`cluster_service.py:175,258,285…`, both `approval_service.py`, `drift_detector.py:129,224`). The `asyncio.gather` at `apps/day1-service/src/services/approval_service.py:59` therefore runs serially. | A native-async adapter removes the problem by construction. Enable ruff `ASYNC`. | P0 (via #2) |
| 4 | DI and global state | `@lru_cache` module singletons (`apps/day1-service/src/dependencies.py:38-98,197`). `logging.basicConfig(get_settings())` runs at import (`main.py:18`). Cache warmers build services by hand (`day1 main.py:52-70`). The auth deps are copied verbatim between services (day1 `dependencies.py:104-134`, day2 `:73-102`). The shared `make_auth_dependency` is dead code. | Construct in the lifespan and store on `app.state`; deps only retrieve (SS `dependencies.py` pattern). `create_app()` factory with no import-time side effects. Shared auth deps in the core package. | P0 |
| 5 | Type checking | mypy is not strict (`disallow_untyped_defs = false`, `apps/day1-service/pyproject.toml:47`). CI adds `--ignore-missing-imports`. Counts: about 157 `Any`, 109 `dict[str, Any]`, 9 `type: ignore`. JWT role is unvalidated `str` plus `type: ignore` (`day1 dependencies.py:122`). | Choose in an ADR: **mypy `--strict` with the pydantic plugin** (recommended for a from-scratch codebase: it refuses untyped defs on its own), or server-scan's `ty==<exact>` plus ruff `ANN001-206`, for one toolchain across the team's repos. Either way, check `tests/` too and drop `--ignore-missing-imports` in favour of per-module overrides. | **P0** |
| 6 | Validation and enums | No `extra="forbid"`, `strict` or `frozen` anywhere. The only enum is `Role`, and it isn't even used for `UserInfo.role`. Request models have no constraints, so `name/site/mce` flow into GitLab paths (`routers/clusters.py:42-49`). Responses are `response_model=dict` (`clusters.py:249`, `addons.py:125`). | Request schemas use `ConfigDict(extra="forbid", frozen=True)`. Value objects `ClusterName`/`SiteName`/`MceName`/`TeamSlug` with a DNS-1123 regex. Enums `MRState`, `DriftReason`, `ChangeKind`, `ClusterPhase`. Every endpoint has a typed `response_model`. | P0 (value objects, enums), P1 (rest) |
| 7 | Tests | **Zero Python tests.** `src/tests/__init__.py` is empty. CI runs `uv run pytest tests/ -v --tb=short \|\| echo "No tests found"` (`.github/workflows/ci.yml:89,136,183`), and it targets `tests/`, not `src/tests/`, so new tests wouldn't even be collected. Web has 8 Playwright specs (about 121 tests), but none run in CI. There is no vitest. | pytest, pytest-asyncio (auto), pytest-xdist, pytest-cov, hypothesis. A `tests/{unit,api,contract}` tree per package. Fakes, not `pytest-mock`. `--cov-fail-under` of 90 on `domain` and `application` (herzi-style), with an overall floor that ratchets upward. Add the mocked Playwright `user-flows.spec.ts` to CI. | **P0** |
| 8 | CI | Lint and type checks block, but the config is lax. pytest can't fail. **No `permissions:` block.** Actions are tag-pinned (`@v4`). setup-uv runs `version: "latest"`. `uv sync --extra dev` without `--locked`. No `ruff format --check`, helm lint, pip-audit/npm audit, coverage, e2e or timeouts. `paths-filter` plus `always()` lets image builds run with checks skipped (`ci.yml:228-232`). | Remove `\|\| echo`. Add `permissions: contents: read`, SHA pins, pinned uv, `--locked`, `timeout-minutes`, concurrency. Add `ruff format --check`, the checker, `lint-imports`, `pip-audit`, `deptry`, pytest with coverage, `helm lint` plus `helm template`, `npm audit`, and mocked Playwright. Drop the path filter: the suite is small, and both exemplars run everything on every push. Images only after every job is green. | **P0** |
| 9 | Tooling | No pre-commit, Makefile/justfile or CODEOWNERS. Three separate `uv.lock`s. The Dockerfiles **ignore the lockfiles**: `pip install` of unpinned ranges (`apps/day1-service/Dockerfile:14-20`, `kubernetes>=26.1.0` against pyproject's `>=29,<32`), and web runs `npm install` without the lock (`apps/web/Dockerfile:10-11`). ruff `select=["E","F","I","UP","B","SIM"]`, yet there are 18 `# noqa: PLC0415` for rules that aren't enabled. | A root **uv workspace** with one `uv.lock` and one tooling config (Part D). Copy server-scan's ruff `select` block, plus `BLE001` (Wingman has 52 `except Exception`). A `Makefile` or `scripts/gate.sh` that mirrors CI exactly. Dockerfiles install from the lock (`uv sync --locked --no-dev --package …`, `npm ci`). | P0 (workspace, lint, gate), P1 (Dockerfiles) |
| 10 | Error model | `exceptions.py` has 6 classes, 2 of them unused. **No exception handler is registered.** Each service maps errors by hand and leaks GitLab text (`apps/day2-service/src/services/approval_service.py:81 detail=str(exc)`). Errors are swallowed: drift failure is reported as `is_drifted: False` (`routers/clusters.py:112-114`), and clusters are silently dropped on a read error (`cluster_service.py:114-119,168,187`). | Port `SS/backend/app/errors.py` and `exception_handlers.py` (RFC 9457, append-only `ErrorCode`, `request_id`). herzi's three-outcome rule: a read error means *unknown* and is surfaced, never treated as empty or healthy. Distinct `GitLabUnavailable`, `RevisionConflict` and `AmbiguousWrite` errors. | P0 (types and handler), P1 |
| 11 | Logging | Plain-text `logging.basicConfig`. No request ID. No secret scrubbing. | structlog JSON. Pure-ASGI request-context middleware. A scrub processor. A test asserting the GitLab token never appears in logs (herzi `cmd/main_test.go:115`). | P1 |
| 12 | Metrics and health | No metrics. `/api/day{1,2}/cache/stats` is unauthenticated (`apps/day1-service/src/main.py:128`). `/healthz` is static (`main.py:123-125`) and serves as both liveness and readiness (`chart/templates/day1-deployment.yaml:60-71`). | `/health/live` (no dependencies) and `/health/ready` (a cached, short-timeout GitLab probe; semantics in an ADR). prometheus-client: `http_*`, `gitlab_requests_total{op,outcome}`, `gitlab_request_duration_seconds{op}`, `cache_operations_total{cache,result}`, with a bounded label vocabulary shared with logs. | P1 |
| 13 | Timeouts and retries | `gitlab.Gitlab(...)` has **no timeout** (`gitlab_client.py:67,613`) and no retries. The OAuth httpx client has no timeout (`wingman_shared/auth/openshift_oauth.py:66,108,148`). | Every client timeout is a bounded `Settings` field. Idempotent GETs retry on 429/5xx with backoff and `Retry-After`. **Writes (commit, branch, MR) are never auto-retried.** A timeout after a write is *ambiguous* and is resolved by re-reading the branch head or MR list. | P0 (in the adapter) |
| 14 | Write concurrency | Commits don't use `last_commit_id`, so concurrent edits clobber each other. There's no record of which reads produced a given write. | Every update action carries the `last_commit_id` the read returned. A mismatch becomes `RevisionConflictError` (409 with `details.current_commit`), as in SS ADR-0044. The contract suite pins GitLab's exact response for a stale `last_commit_id`. | P0 (port design) |
| 15 | MR identity | **day2 routes by bare `mr_iid`** (`apps/day2-service/src/routers/approvals.py:18-35`). `_find_client_for_mr` returns the *first team* whose project has that IID (`approval_service.py:46-60`), so approve, merge or reject can act on another team's MR. | Value object `MergeRequestRef(project: ProjectPath, iid: int)` in the domain. Routes take the team or project. A regression test that fails with the bug restored. | P0 (domain), P1 (routes) |
| 16 | MR conventions | Bulk-install titles are `"[Day2] Install …"` (`addon_service.py:618-620`) instead of `[Wingman/Day2]`, so the audit parser (`wingman_shared/mr_conventions.py:163`) misses them. | `mr_conventions` becomes a pure domain module with `format()`/`parse()`. A hypothesis property test that `parse(format(x)) == x`. Every MR title goes through `format()`. | P0 |
| 17 | Cache | In-process TTL plus stale-while-revalidate, per replica (`wingman_shared/cache.py`). `_key_locks` is never pruned. The `create_task` result isn't stored. **Keys don't match their invalidations**: `approvals:combined:list` vs `approvals:day1:list`, metadata keyed by site/mce/cluster vs by name, the detail key ignores site/mce (`cluster_service.py:191,221`, `webhooks.py:108,131`). Dead TTL settings. | One `cache_keys.py` module that both writers and invalidators import (as SS `infrastructure/redis/keys.py`). An ADR on per-replica vs shared cache and on the webhook's reach (SS ADR-0028 style). API tests that fail if invalidation is removed. TTLs come from Settings. | P1 |
| 18 | Data correctness | Drift and sync-yaml use variables that are always empty since `.wingman.yaml` was removed (`cluster_service.py:181-188`, `drift_detector.py:142,223-228`). `POST /{name}/sync-yaml` can open an MR that overwrites a cluster with defaults (`routers/clusters.py:373-387`). | Write the invariants table first, herzi-style ("a sync never writes a value the cluster's file didn't already have"), then encode it as tests. | P1 |
| 19 | Config and security | Secrets are plain `str`. `OPENSHIFT_SSL_VERIFY` defaults to false. **CORS `*` with credentials** (`apps/day1-service/src/main.py:105-111`). **The dev-login mints an admin token when `DEV_AUTH_SECRET` is empty** (`routers/auth.py:139`). The webhook is open when its secret is empty (`webhooks.py:30-31`). OAuth has no `state` parameter, so no CSRF protection (`openshift_oauth.py:86-91`). Jinja isn't sandboxed (`yaml_renderer.py:42`). There is no `.env.example`, although `DEVELOPMENT.md:68` refers to it. | `SecretStr` throughout. `model_validator`s refuse each of these combinations at startup (SS `settings.py:315-381` pattern). Explicit CORS origin list. OAuth `state` plus URL encoding. `SandboxedEnvironment` with `StrictUndefined`. A committed `.env.example`, plus a parity test against the `Settings` fields. | P0 (settings validators), P1 (rest) |
| 20 | Chart and image | Only pod `runAsNonRoot` (`chart/templates/day1-deployment.yaml:30-31`). No container securityContext. `nginx:latest`. Image defaults are `latest` despite the comment in `chart/values.yaml:20-23`. No `values.schema.json`. | The full securityContext set (A8). `automountServiceAccountToken: false` unless cluster-status is enabled. `values.schema.json` with `additionalProperties: false`. `helm template` matrix plus assertions in CI. Numeric UID. Base images pinned to a minor version or digest. | P2 (CI lint is P0) |
| 21 | Docs | No ADRs and no CHANGELOG. Known drift: `.env.example`, the `DEVELOPMENT.md:253-266` test example, the "all reads go through CacheManager" claim (`gitlab_client.py:15`), and `.wingman.yaml` in `drift_detector.py:120`. | `docs/adr/` with the first ADRs written *before* code (list below). Rewrite CLAUDE.md in the server-scan shape. The "docs updated in the same commit" convention. A `/gate` skill or script. A path-scoped `.claude/rules/gitlab.md`. | P0 (ADRs, CLAUDE.md), P2 (agents, skills) |
| 22 | Commits and releases | Conventional prefixes, but some subjects run the body together (`2f4772f`, `e391c90`) and some bundle unrelated changes (`08c59f2 "…; add easter egg"`). The manual `VERSION` file isn't synced to the chart. | Subject equals the release note. Body has `Operator action:` and `Docs:` lines. One unit of work per commit. Later: CI-computed semver, forward-only tag check, generated release notes, retiring `VERSION`. | P0 (convention), P2 (automation) |
| 23 | Frontend | `tsconfig` has only `strict: true`. ESLint is Next's default (`apps/web/eslint.config.mjs`, 465 B). No `typecheck` script (CI calls `tsc` directly). No vitest. No query-key factory (`apps/web/lib/` has only `api-client.ts`, `diff.ts`, `utils.ts`). Playwright isn't in CI. zod is a dependency. | Add `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes` and `noUnused*`. `typecheck` and `test` scripts. Vitest for pure logic. `queryKeys.ts`. The API client parses RFC 9457. **Generate TypeScript types from the services' OpenAPI** with a CI `--check` diff, which is stronger than server-scan's hand-written mirror. The mocked Playwright suite in CI. | P1 (types from OpenAPI), P2 (rest) |

### First ADRs to write (before code), using a single template

server-scan has five different ways of writing Status. Pick one:

```
# ADR-NNNN: <the decision, as a sentence>

Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by ADR-NNNN | Superseded in part by ADR-NNNN
Amends / Extends / Supersedes: ADR-NNNN        (optional, one line)

## Context
## Decision
## Alternatives rejected
## Consequences
## Verification          (the test or measurement that pins it; "fails if X is removed — verified")
```

The index is a table in `docs/adr/README.md`. The ADRs:

1. Layered packages with ports; the import-linter contracts.
2. GitLab adapter on `httpx.AsyncClient`, not python-gitlab with `to_thread`. Reasons: native async, explicit timeouts, typed DTOs, and server-scan's `blocking.py` lesson about abandoned threads.
3. Type checker and strictness (mypy `--strict` vs ty plus ruff ANN).
4. RFC 9457 error envelope and the `ErrorCode` registry.
5. In-memory fake GitLab as the test and dev backend, plus a contract suite against real GitLab.
6. Write semantics: `last_commit_id` compare-and-set, no automatic write retries, ambiguous outcomes resolved by re-reading.
7. Merge-request identity is `(project, iid)`; MR title and branch conventions are a contract.
8. Cache scope (per replica vs shared) and invalidation on the operator write path.
9. Fail-closed startup validation of security settings.
10. Health and readiness semantics when GitLab is down.

---

## Part C. Ordered P0 checklist (do these before rewriting day1/day2)

1. **CI that can fail.**
   - Delete `|| echo "No tests found"` (`ci.yml:89,136,183`).
   - Add `permissions: contents: read`, SHA-pinned actions, pinned uv, `uv sync --locked`, and `timeout-minutes`.
   - Add `ruff format --check`, `pip-audit`, `deptry`, `helm lint` and `helm template`.
   - Drop the paths-filter/`always()` logic.
2. **uv workspace and a single tooling config.**
   - Root `pyproject.toml` with ruff (server-scan's set plus `BLE001`), the type checker, pytest (`asyncio_mode=auto`, markers), coverage and import-linter.
   - One `uv.lock`.
   - `scripts/gate.sh` (or `make ci`) runs exactly what CI runs.
3. **Write ADRs 1–7.** Decide the type checker.
4. **Core package skeleton:**
   - `errors.py` and the exception handlers;
   - `Settings` with `SecretStr` and fail-closed validators;
   - the request-context middleware;
   - the `GitLabPort` Protocol and DTOs;
   - the `InMemoryGitLab` fake;
   - the httpx adapter with timeouts and GET-only retries;
   - the **contract suite** (Part E);
   - `mr_conventions` with a round-trip property test.
5. **Test harness:**
   - `tests/conftest.py` with fixtures `fake_gitlab`, `seeded_gitlab` (loaded from `tests/fixtures/repos/`), `app` (with `dependency_overrides`) and `client` (`httpx.AsyncClient(transport=ASGITransport(app))`);
   - a coverage floor of 90 on domain and application.
6. **Value objects and enums** for names, paths, MR refs and MR states, with the DNS-1123 validation.
7. **Rewrite CLAUDE.md** in the server-scan shape:
   - numbered conventions with reasons;
   - "Verifying your work" with the gate commands;
   - Key technical facts;
   - Where to continue right now.
   
   Fix the known drift (`.env.example`, `DEVELOPMENT.md`, the `.wingman.yaml` reference). Commit a real `.env.example`.
8. **Regression tests for bugs already known.** Write them against the new code as it lands, starting with the day2 MR routing bug, the cache key mismatches and the MR title convention.

---

## Part D. Proposed target layout

The layout is modelled on server-scan's layers, with herzi's "ports beside the domain types" and "one composition root". Packages get real names, not `src.main:app`.

```
wingman/
  pyproject.toml              # uv workspace root: [tool.uv.workspace] members; ruff, mypy|ty, pytest,
                              #   coverage (fail_under), import-linter contracts; dev dependency group
  uv.lock                     # ONE lock for all Python packages
  .env.example                # every setting, sectioned, commented, ADR-linked
  scripts/gate.sh             # CI's steps in CI's order; reports every failure
  docs/
    adr/README.md             # index table: | ADR | Decision |
    adr/0001-….md …
    architecture.md           # subsystem overview; links ADRs
    notes/                    # dated working notes, session-log.md
    ops/runbook.md            # one section per alert (later)
  packages/wingman-core/
    pyproject.toml
    src/wingman_core/
      domain/
        git.py                # ProjectPath, Ref, CommitId, FilePath (validated), FileContent, TreeEntry,
                              #   CommitAction(kind: ChangeKind, path, content, last_commit_id)
        merge_request.py      # MergeRequestRef(project, iid), MRState(StrEnum), MergeRequest
        mr_conventions.py     # pure format()/parse() for branch names and MR titles (audit contract)
        names.py              # ClusterName, SiteName, MceName, TeamSlug (DNS-1123 value objects)
        audit.py              # commit → FileDiff mapping (written once; today it appears 4 times)
      ports/
        gitlab.py             # GitLabPort Protocol (read_file, list_tree, commit, create_branch,
                              #   open_mr, get_mr, list_mrs, approve, merge, close, compare)
        clock.py              # Clock = Callable[[], datetime]
      application/
        approvals.py          # the approve/update/reject flow written once (today it is copied in day1 and day2)
        audit.py
      infrastructure/
        gitlab/
          http.py             # httpx.AsyncClient factory: timeouts, retry policy (GET only), pagination
          adapter.py          # GitLabAdapter(GitLabPort): REST v4 → domain DTOs; status → AppError
        fake_gitlab/
          gitlab.py           # InMemoryGitLab(GitLabPort): projects, branches, commits, MRs, CAS, clock
          seed.py             # load a fixture directory tree into a fake project
        logging.py            # structlog config + scrub processor
        metrics.py            # prometheus collectors; bounded label vocabularies
        cache.py, cache_keys.py
      auth/                   # jwt.py, rbac.py (Role enum), openshift_oauth.py, dependencies.py
                              #   (CurrentUser, AdminUser written once)
      web/
        errors.py             # AppError hierarchy + ErrorCode registry (RFC 9457)
        exception_handlers.py
        request_context.py    # pure-ASGI request id + access log
        health.py             # /health/live, /health/ready router factory
        app_factory.py        # create_base_app(settings): middleware, handlers, health, metrics
      settings.py             # BaseWingmanSettings: GitLab URL/token(SecretStr)/timeouts, JWT, CORS,
                              #   fail-closed validators; git_backend: Literal["gitlab","fake"]
      testing/
        gitlab_contract.py    # reusable contract test class, run against fake and real GitLab
    tests/
      unit/  contract/  conftest.py
  apps/day1-service/
    pyproject.toml            # depends on wingman-core (workspace = true)
    Dockerfile                # uv sync --locked --no-dev --package wingman-day1; numeric USER
    src/wingman_day1/
      main.py                 # create_app() + lifespan: builds GitLab adapter|fake, cache, clients → app.state
      settings.py             # Day1Settings(BaseWingmanSettings): project IDs, TTLs, feature flags
      dependencies.py         # retrieve-only Annotated deps
      domain/
        models.py             # Cluster, ClusterSpec, Site, Mce, DriftReport (frozen)
        enums.py              # DriftReason, ClusterPhase
        services/             # template_analyzer.py (pure Jinja AST), rendering.py (SandboxedEnvironment,
                              #   StrictUndefined), drift.py (pure diff), paths.py (repo path rules)
        ports.py              # Day2AddonsPort, ClusterStatusPort, ClusterRepository Protocol
      application/
        clusters.py, specs.py, drift.py, approvals.py (thin wrapper over core), audit.py
      infrastructure/
        cluster_repository.py # ClusterRepository over GitLabPort: YAML ↔ domain models, cache
        spec_repository.py
        day2_client.py        # httpx to day2 (the only place day1 knows day2 exists)
        cluster_status/{kubernetes.py,fake.py}
      api/
        v1/clusters.py + clusters_schemas.py, specs.py + specs_schemas.py, sites.py, mces.py,
           approvals.py, audit.py, webhooks.py
    tests/
      conftest.py             # fake_gitlab seeded from fixtures/repos/{day1,specs}/
      fixtures/repos/…        # small realistic repo trees
      unit/domain/…, unit/application/…, unit/infrastructure/…
      api/                    # ASGITransport client; asserts RFC 9457 bodies, RBAC, cache invalidation
  apps/day2-service/          # same shape: domain/{catalog, addon, version rules}, application/addons.py,
                              #   infrastructure/{addon_repository, helm_values}.py, api/v1/…
  apps/web/                   # + src/api/generated/ (types from OpenAPI), queryKeys.ts, vitest
```

**import-linter contracts** (all gated from day one):

1. For each of `wingman_core`, `wingman_day1` and `wingman_day2`:
   - `*.domain` cannot import `application`, `infrastructure`, `api`/`web` or `fastapi`.
   - `*.application` cannot import `infrastructure` or `api` (this is the contract server-scan couldn't gate).
   - `*.infrastructure` cannot import `application` or `api`.
2. `wingman_day1` and `wingman_day2` never import each other. They talk over HTTP through a port.
3. Only `main.py` (the composition root) is exempt from rule 1's adapter ban, via `ignore_imports` for `*.main`.

---

## Part E. Testing code that talks to GitLab

**Recommendation:** an in-memory fake GitLab behind the port as the default for every test, kept honest by a shared contract suite. That suite runs against the fake on every push and against a real GitLab on a schedule. Plain mocks are not enough, and a real GitLab per push is too expensive.

1. **Tier 1: `InMemoryGitLab` (every test run, milliseconds).** It implements `GitLabPort` with real semantics. It is **not** a `MagicMock` (server-scan uses `MagicMock` in exactly 1 test file), because mocks don't enforce behaviour. It must model:
   - multiple projects in a group (day2 has one project per team);
   - branches with a default branch, plus commits (id, parent, author, message, timestamp from an injected clock) and per-commit file trees;
   - commit actions create, update, delete and move, with GitLab's failure modes:
     - create on an existing path;
     - update or delete of a missing path;
     - **update with a stale `last_commit_id`, which becomes a revision conflict**;
   - create-branch when the branch exists;
   - MRs with a per-project `iid` counter, `opened → merged | closed`, approvals, and labels;
   - merge applying the source branch's tree to the target;
   - a duplicate open MR for the same source branch;
   - `compare(from, to)` diffs for audit.
   
   herzi's lesson applies: make the fake model reality. Its envtest "world" registers a run when an install happens; here, opening an MR makes it appear in `list_mrs`. `seed.py` loads `tests/fixtures/repos/<name>/` into a project, so tests read like real repo states.
2. **Tier 2: adapter tests with `httpx.MockTransport`** (as in server-scan's `tests/unit/infrastructure/openshift/test_client.py`). They use **recorded real GitLab v4 JSON** under `tests/fixtures/gitlab_api/` and pin:
   - URL encoding of file paths (`%2F`);
   - pagination (`X-Next-Page` / `Link`);
   - status-to-error mapping (401, 403, 404, 400/409 conflicts, 429 with `Retry-After`, 5xx);
   - that GETs retry and POSTs don't;
   - timeout classification;
   - token redaction in error text;
   - **golden request bodies** for the commit and MR-create payloads (herzi's `installer/testdata/request.json`).
3. **Tier 3: contract suite (`wingman_core/testing/gitlab_contract.py`).** One parametrized test class runs against `fake`, always, and against `gitlab`, marked `live_gitlab`. Example tests:
   - `test_update_with_stale_last_commit_id_is_a_revision_conflict`
   - `test_mr_iids_are_per_project`
   - `test_merged_mr_changes_target_tree`
   
   How the real run is wired:
   - The real target is a sandbox group on the team's GitLab when `WINGMAN_TEST_GITLAB_URL` and `…_TOKEN` are set; otherwise those tests **skip cleanly**, as server-scan's `_stack_availability.py` does.
   - In CI, it runs nightly or on `workflow_dispatch` against a `gitlab/gitlab-ce` service container (pin its version).
   - Not on every push: the image is several GB, needs about 4 GB of RAM and takes minutes to boot, unlike server-scan's Mongo and Redis.
   - Every behaviour the fake asserts must also pass against real GitLab. A failing contract test means the fake has drifted, so fix the fake first.
4. **API and use-case tests** run the real FastAPI app with `dependency_overrides` swapping in a seeded `InMemoryGitLab`. They assert:
   - RFC 9457 bodies;
   - RBAC (a viewer gets 403 on writes);
   - MR titles and branches round-tripping through `mr_conventions` (this catches the `[Day2]` bug);
   - **that cache invalidation happens**, as a test that fails when the invalidation line is removed (SS ADR-0028's consequence).
5. **The fake is also a dev and E2E backend.** `git_backend=fake` with deterministic seeds lets developers run the full stack and the live Playwright suite in CI without GitLab, as server-scan's `fake` collector and `FakeJobRunner` do. A settings validator refuses `git_backend=fake` when `environment=production`.
6. **Property tests (hypothesis)** for the pure modules: `mr_conventions` round-trip, path rules and value objects, and the template analyzer and renderer.

---

## Part F. What not to copy from the exemplars

- **server-scan:**
  - Application services and routers construct concrete `Mongo*Repository` classes, which is why the fifth import contract is ungated (`SS/pyproject.toml:332-345`, `SS/backend/app/api/v1/classification_rules.py:35-47`). Wingman should gate it from day one.
  - ADR Status lines come in five formats, and there's no index inside `docs/adr/`.
  - No coverage threshold.
  - No `extra="forbid"`.
  - `testcontainers` is a dependency but unused.
  - `playwright.config.ts` refers to a missing `e2e/README.md`.
- **herzi:**
  - `cmd/main_test.go` (10 tests) is never run in CI (`HZ/Makefile:27-28` excludes `./cmd`). Make sure every test package is collected.
  - `.devcontainer/` has drifted (Go 1.26 vs 1.27.3, "latest" kind).
  - `AGENTS.md` is mostly the Kubebuilder template.
  - No executable e2e suite.
  - Statuses are untyped string constants.
- **Both:**
  - The no-attribution-trailer rule is the owner's preference, not a quality practice.
  - Their very long dependency and CI comments work because a comment-density gate pushes rationale into ADRs. Copy the gate, not the walls of text.
