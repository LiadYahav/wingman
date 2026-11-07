# Wingman Web

Next.js frontend for the Wingman Internal Developer Platform.

## Features

- **Cluster Management**: Create, view, and manage OpenShift clusters with drift detection
- **Spec Templates**: Define cluster templates with Day1 provisioning, Day2 addons, and immutable field flags
- **Two-Phase Cluster Form**: Specs define structure; clusters fill values — nodepool count is locked by spec
- **Marketplace Addon Picker**: Browse and select Day2 addons on spec creation/edit pages
- **YAML Fields**: Dynamic form fields accept plain YAML scalars, maps, or lists — no JSON syntax
- **Site/MCE from GitLab**: Dropdowns populated from GitLab folder paths; new names create folders
- **Approval Workflow**: Aggregated view of open MRs from all platform repositories
- **Audit Trail**: Track all cluster lifecycle events with GitLab commit links
- **In-App Documentation**: Full platform guide at `/docs`

## Getting Started

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Build for production |
| `npm run start` | Start production server |
| `npm run lint` | Run ESLint |
| `npm run test:e2e` | Run Playwright E2E tests |
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

```bash
# Run all tests headless
npm run test:e2e

# Interactive mode with test explorer
npm run test:e2e:ui

# Run specific test file
npx playwright test addon-configuration
```

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
│   ├── specs/          # Spec template pages
│   ├── addons/         # Addon catalog
│   ├── approvals/      # MR approval workflow
│   ├── audit/          # Audit trail
│   ├── docs/           # In-app platform documentation
│   └── settings/       # User settings
├── login/              # Authentication
└── layout.tsx          # Root layout

components/
├── ui/                 # Base UI components (shadcn/ui)
├── common/             # Shared components (dialogs, headers)
└── specs/              # Spec-specific components

lib/
├── api-client.ts       # Typed API client; errors are RFC 9457 problems (ApiError)
├── approvals.ts        # How an MR is addressed: day1-<iid>, specs-<iid>, day2-<team>-<iid>
├── live-status.ts      # Live HostedCluster status (501 FEATURE_DISABLED = status is off)
├── utils.ts            # Utility functions
└── diff.ts             # Diff computation utilities

types/
├── index.ts            # Shared types (auth, MRs, audit) and re-exports
├── problem.ts          # RFC 9457 problem bodies and error codes
└── day1.ts             # day1 service shapes (clusters, specs, MCEs, drift)
```

## Environment Variables

The web app uses relative API paths — no `NEXT_PUBLIC_*` env vars are required. In a deployment,
nginx routes `/api/auth`, `/api/day1` and `/api/webhooks` to day1 and `/api/day2` to day2
(`chart/templates/nginx-configmap.yaml`); `proxy.ts` only guards pages.

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
  GITLAB_URL=http://gitlab.invalid GITLAB_TOKEN=test-token-never-logged-0001 \
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
second user: nobody approves a change they requested.

## Docker

```bash
# Build image
docker build -t wingman-web:latest .

# Run container
docker run -p 3000:3000 wingman-web:latest
```
