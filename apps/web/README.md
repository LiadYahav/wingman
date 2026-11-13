# Wingman Web

Next.js frontend for the Wingman Internal Developer Platform.

## Features

- **Cluster Management**: Create, edit and delete hosted clusters by MR; each is one values file for the hostedclusters-setup chart, with `vlanId`/`dhcp_values` (allocate-segment workflow) and `mcFiles`/`mcConfigMap` (CI) left to automation and shown as pending until written
- **Specs**: Presets for the create form (nodepool shape, preset template inputs, the Day2 addons a cluster should get); every spec fills the one shared `cluster-template.j2`, and "immutable after create" is a hint, not enforced
- **Cluster nodes**: the cluster page's Nodes tab shows each NodePool as the MCE reports it (ready of wanted, version, InPlace or Replace, an update in progress and its progress, its problems), its Machines with the server behind each (linked to server-scan, with its health), the node an update is working on set apart, a waiting or missing node as a placeholder that says why, and the servers server-scan places in the cluster that no Machine has. An admin starts the platform's `uninstall-server-from-hc` workflow on a server (its name typed again) and its run shows beside it: Wingman starts the workflow and shows its phase as the workflow names it, and the NodePool keeps its size, so the node is replaced, not removed
- **Drift**: a cluster is measured against the flavor version its header names (ADR-0044): drifted when a value that version locks differs in its file or an add-on it lists is missing; a newer version is an update, never drift ("Update available", or "Update MR open" linking the MR); an add-on at another version is reported, never fixed (ADR-0025); unknown is never shown as in sync
- **Flavor rollout**: a new flavor version opens one day1 MR per cluster that follows it, which its customer merges when ready; a flavor MR's approve page says what merging it opens (the cluster MRs, the nodes that roll, the configs lost, the decisions), and the flavor's Clusters tab shows where each cluster stands (needs a decision, failed, declined, pending, MR open, on the version), read again while day1 opens MRs; admins can Reconcile now. Saving a flavor edit needs a new version
- **Two-Phase Cluster Form**: Specs (flavors) set the starting nodepools, presets and locked values; clusters fill the rest. Locked values are read-only, presets editable, owners digits only; nodepool configs come from the machine-config picker (the defaults fill every nodepool the flavor leaves open, including ones added at create); under the configs rule each nodepool keeps the names and picks its hardware; day1's 422 problems show at their fields
- **Marketplace Addon Picker**: Browse and select Day2 addons on spec creation/edit pages
- **Charts per Destination**: Install, edit and remove Day2 charts on the hub, MCEs, hosted and UPI clusters; every value shows the layer that set it; bulk install opens one MR per team; a version of its own is a confirmed emergency pin; a removal leaves the workload running (`argocd app delete --cascade` tears it down)
- **Add-ons**: a team's catalog (`operators/<chart>/` in its repo) and the fleet defaults built from it, all on the Addons page (`/addons`, one team with `?team=`; ADR-0043, ADR-0053). A team admin adds an add-on (`/addons/new?team=`, pre-filled from the team's own files) and edits it with **Edit add-on** (deploy config, sync options, ignoreDifferences and its **Sig values**, `operators/<chart>/values.yaml`: chart values → Sig values → cluster values); an add-on's page (`/addons/<team>/<chart>`, Defaults & overrides) shows its files as written, comments and all, and per scope (hosted clusters, MCEs, the hub, UPI clusters) makes it a default and edits that default. Each env (`values-<env>.yaml`) and each MCE, hosted cluster or UPI cluster (`values-<name>.yaml`) can get its own values (the effective values before and after, from `merge-preview`), and **Deploy on specific MCEs** installs it in chosen MCEs' own folders, one MR per MCE, with each install listed and removable. A hosted cluster's own add-ons come from its flavor and the create form. Wingman does not write `exclusions.yaml`. Every authoring write is one MR, previewed with the service's dry run first; the plan lists each destination that changes, those are confirmed, and the MR is opened only against the previewed plan's digest (a repo that moved shows the new plan). Installing it on one cluster is on that cluster's page. 3.12.0's `/operators`, `/teams/<team>/operators[/<chart>]` and `/teams/<team>/new-operator` redirect here (`next.config.ts`)
- **Per-team write access**: a team that has not given Wingman's GitLab account Developer on `sigs/<team>` is read-only, and every write Wingman would offer it says why; the web fails closed, so a team whose access is not known yet (or could not be read) is read-only too
- **Lints**: Every check on the team repos; a finding that names a destination links to its charts. There is no page that lists every destination: a hosted cluster's charts are on its page, an add-on's page names each destination it reaches (MCEs, hosted and UPI clusters), each name a link to its charts, and the old `/destinations` redirects to `/clusters` (`next.config.ts`)
- **YAML Fields**: Dynamic form fields accept plain YAML scalars, maps, or lists — no JSON syntax
- **Sites and MCEs are read-only**: picked from the day1 repo's folders (Wingman never creates them); the MCE's mastertag is the default OpenShift version
- **Naming convention**: new cluster names must follow `ocp4-<env>-<name>-<site>[-<seq>]`; existing off-convention names are flagged, not hidden; a new `<seq>` is one letter, a to z, and creating from a flavor the form suggests the name with the next free letter (ADR-0040)
- **Nodepool ratio**: a flavor may size its nodepools by a ratio (`1:2:1`); the create form asks for one size and fills in each sized nodepool's replicas
- **Approval Workflow**: Aggregated view of open MRs from the day1, specs and team repos; an approval names the commit the reviewer saw, so a branch that moved since is refused, and nobody approves their own change
- **Audit Trail**: Track all cluster lifecycle events with GitLab commit links
- **In-App Documentation**: Full platform guide at `/docs`

## Getting Started

```bash
# Install dependencies, at the repository root (one lockfile, ADR-0003)
npm ci

# Start the development server (from apps/web)
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser. Without the services behind it
every API call fails: see [Running against local services](#running-against-local-services).

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Build for production |
| `npm run start` | Start production server |
| `npm run lint` | Run ESLint |
| `npm run test:e2e` | Run Playwright E2E tests (both projects) |
| `npm run test:e2e:mocked` | Run the mocked project, as CI does |
| `npm run test:e2e:ui` | Open Playwright interactive UI |
| `npm run test:e2e:headed` | Run tests in visible browser |

## E2E Testing

E2E tests use Playwright and are located in `e2e/`:

```
e2e/
├── fixtures/           # Mock data and API route handlers
├── pages/              # Page objects (abstraction layer)
└── tests/              # Test specifications
```

### Running Tests

Two Playwright projects (`playwright.config.ts`): `mocked` is every spec but `live-*.spec.ts`,
with every API call intercepted (`e2e/fixtures/`), and is what CI runs; `live` is the three
`live-*` specs, against a running stack.

```bash
# The mocked suite, no backend needed (CI runs it against a production build)
npm run test:e2e:mocked

# Interactive mode with test explorer
npm run test:e2e:ui

# Run specific test file
npx playwright test addon-configuration

# The day1 flows against a running stack (see "Running against local services"): the
# dashboard; a cluster created, found among the approvals, approved by a second user (a
# branch that moved since the review is refused), edited and deleted with last_commit_id;
# live status (off is not an error); a spec built from the catalog, its history, an edit and
# a delete; the audit log. Every step opens a real MR, so use a disposable GitLab only (the
# in-memory fake or the seeded local GitLab CE).
WINGMAN_DEV_AUTH_SECRET=<DEV_AUTH_SECRET> PLAYWRIGHT_BASE_URL=http://localhost:3000 \
  npx playwright test live-day1-flows --project=live
# The day2 pages against the same stack: the catalog, a hosted cluster's charts from its day1
# page, install/update/remove/bulk, an MCE, a UPI fleet default, the hub, the /destinations redirect, lints
DEV_AUTH_SECRET=<DEV_AUTH_SECRET> PLAYWRIGHT_BASE_URL=http://localhost:3000 \
  npx playwright test live-day2 --project=live
# Flavors v2: a hand-written cluster joins a flavor (the flavor's page), a second admin merges
# it, then it is synced from its Drift tab. Needs a freshly seeded GitLab: the fixture cluster
# ocp4-prod-lark-site1 must follow no flavor yet (seed_gitlab.py --reset)
WINGMAN_DEV_AUTH_SECRET=<DEV_AUTH_SECRET> PLAYWRIGHT_BASE_URL=http://localhost:3000 \
  npx playwright test live-flavors --project=live
```

`npm run test:e2e` runs both projects; without a stack the `live` specs skip (no secret) or fail.

### Page Objects

Tests use the Page Object pattern for maintainability:

```typescript
import { SpecNewPage } from "../pages/spec-new.page";
import { ConfigureDialogPage } from "../pages/configure-dialog.page";

test("can configure addon fields", async ({ page }) => {
  const specPage = new SpecNewPage(page);
  const configDialog = new ConfigureDialogPage(page);

  await specPage.goto();
  await specPage.selectAddon("platform", "cert-manager");
  await specPage.openConfigureDialog("platform", "cert-manager");
  
  await configDialog.toggleField("replicas");
  await configDialog.save();
});
```

## Project Structure

```
app/
├── (app)/              # Authenticated routes
│   ├── clusters/       # Cluster management pages
│   ├── specs/          # Spec pages (presets for the create form)
│   ├── addons/         # The add-on catalog, a new add-on (new/), one add-on's defaults and overrides ([team]/[addon]/)
│   ├── lints/          # Day2 lint findings
│   ├── approvals/      # MR approval workflow
│   ├── audit/          # Audit trail
│   ├── docs/           # In-app platform documentation
│   └── settings/       # User settings
├── login/              # Authentication
└── layout.tsx          # Root layout

components/
├── ui/                 # Base UI components (shadcn/ui)
├── common/             # Shared components (empty states, problems, diffs, review dialog)
├── layout/             # The app shell, sidebar, user menu, providers
├── clusters/           # Cluster facts, drift, live status, the template-driven form
├── addons/             # A destination's charts (values editor, cards, bulk install), the authoring flow (sync options, dry-run plans, confirmations), and an add-on's scope panels (per-destination values, deploy on specific MCEs)
└── specs/              # Spec-specific components

hooks/
└── use-bulk-status.ts  # Live status of every listed cluster in one request

stores/
└── auth-store.ts       # The signed-in user and role (zustand)

lib/
├── api-client.ts       # Typed API client; errors are RFC 9457 problems (ApiError)
├── approvals.ts        # How an MR is addressed: day1-<iid>, specs-<iid>, day2-<team>-<iid>
├── clusters.ts         # Links to a cluster's pages
├── specs.ts            # The rules day1 checks a spec against, and the document a spec write sends
├── mr-toast.ts         # The "MR opened" toast, with a link to its review page
├── day2.ts             # Day2 paths, query keys, layer roles, problems
├── live-status.ts      # Live HostedCluster status (501 FEATURE_DISABLED = status is off)
├── values.ts           # Helm values as data: leaves, paths, YAML
├── utils.ts            # Utility functions
└── diff.ts             # Diff computation utilities

types/
├── index.ts            # Shared types (auth, MRs, audit) and re-exports
├── problem.ts          # RFC 9457 problem bodies and error codes
├── day1.ts             # day1 service shapes (clusters, specs, MCEs, drift)
└── day2.ts             # The day2 service's bodies (from its Pydantic schemas)
```

## UI conventions

- **Dropdowns** are `Select` (`components/ui/select.tsx`), never a native `<select>`: the
  browser draws its arrow against the border. The arrow sits as far from the right border as
  the text from the left; sizes `sm` and `default` match `Input`, `lg` the page forms' own
  `px-3 py-2` inputs.
- **A list that can grow** (sites, MCEs, infra envs, chart revisions, versions) is a `Combobox`
  (`components/ui/combobox.tsx`): the same closed look plus a search box, keyboard only if need
  be. Options are `{ value, label, description?, group?, disabled? }`; the search matches the
  label, description and group. The trigger is the `combobox` and carries the `aria-label` and
  `data-testid` you pass.
- **Every read has three more states.** Loading is `Skeleton`s shaped like what will be there
  (rows, cards, lines). A list with nothing in it is an `EmptyState`
  (`components/common/empty-state.tsx`): what would be here and, when the viewer can take it,
  the next step (`EmptyStateLink`); `NoMatches` when search or filters emptied it. A failed read
  is a `ProblemList` (`components/common/problem-list.tsx`) given the error itself, so it shows
  the problem's detail, every broken rule and the request id: never `error.message` in a
  string, and never an empty list or a missing section.

## Environment Variables

The web app uses relative API paths — no `NEXT_PUBLIC_*` env vars are required. In a deployment,
nginx routes `/api/auth`, `/api/day1` and `/api/webhooks` to day1 and `/api/day2` to day2
(`deploy/helm/wingman/templates/nginx-configmap.yaml`); `proxy.ts` only guards pages.

### Running against local services

`next dev` proxies the same paths when these are set (development server only; a production build
never has the rewrites, see `next.config.ts`):

| Variable | Example | Proxies |
|---|---|---|
| `WINGMAN_DEV_DAY1_URL` | `http://127.0.0.1:8001` | `/api/auth/*`, `/api/day1/*`, `/api/webhooks/*` |
| `WINGMAN_DEV_DAY2_URL` | `http://127.0.0.1:8002` | `/api/day2/*` |

```bash
# Both services on the in-memory GitLab seeded from dev/gitlab-fixtures (no network needed),
# from the repository root; both need the same JWT_SECRET_KEY (32+ characters).
export WINGMAN_ENVIRONMENT=development WINGMAN_GIT_BACKEND=fake \
  JWT_SECRET_KEY=local-jwt-secret-at-least-32-characters \
  DAY1_GITLAB_PROJECT_ID=gitops-day1/platform-config SPECS_GITLAB_PROJECT_ID=wingman/cluster-specs \
  DAY2_SIGS_GROUP_PATH=sigs DAY2_SERVICE_URL=http://127.0.0.1:8002
DEV_AUTH_ENABLED=true DEV_AUTH_SECRET=local-dev-login-secret-32-characters \
  uv run uvicorn wingman_day1.main:app --port 8001 &
uv run uvicorn wingman_day2.main:app --port 8002 &

cd apps/web
WINGMAN_DEV_DAY1_URL=http://127.0.0.1:8001 WINGMAN_DEV_DAY2_URL=http://127.0.0.1:8002 npm run dev
```

Sign in on `/login` with any lowercase username and the `DEV_AUTH_SECRET`. Approving needs a
second user: nobody approves a change they requested. Each service seeds its own in-memory GitLab,
so a change one makes is not seen by the other (DEVELOPMENT.md has the local GitLab instead).

## Image

Built from the repository root, so `npm ci` installs exactly what the root lockfile names
(`docs/ops/images.md`):

```bash
podman build -f apps/web/Dockerfile -t wingman-web:dev .
podman run -p 3000:3000 wingman-web:dev
```
