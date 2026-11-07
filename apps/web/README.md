# Wingman Web

Next.js frontend for the Wingman Internal Developer Platform.

## Features

- **Cluster Management**: Create, view, and manage OpenShift clusters with drift detection
- **Spec Templates**: Define cluster templates with Day1 provisioning, Day2 addons, and immutable field flags
- **Two-Phase Cluster Form**: Specs define structure; clusters fill values — nodepool count is locked by spec
- **Marketplace Addon Picker**: Browse and select Day2 addons on spec creation/edit pages
- **Charts per Destination**: Install, edit and remove Day2 charts on the hub, MCEs, hosted and UPI clusters; every value shows the layer that set it
- **Destinations and Lints**: Every place teams deploy to, and every check on the team repos
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
│   ├── destinations/   # Day2 destinations (hub, MCEs, hosted, UPI)
│   ├── lints/          # Day2 lint findings
│   ├── approvals/      # MR approval workflow
│   ├── audit/          # Audit trail
│   ├── docs/           # In-app platform documentation
│   └── settings/       # User settings
├── login/              # Authentication
└── layout.tsx          # Root layout

components/
├── ui/                 # Base UI components (shadcn/ui)
├── common/             # Shared components (dialogs, headers)
├── addons/             # A destination's charts: values editor, cards, bulk install
└── specs/              # Spec-specific components

lib/
├── api-client.ts       # Typed API client
├── day2.ts             # Day2 paths, query keys, layer roles, problems
├── values.ts           # Helm values as data: leaves, paths, YAML
├── utils.ts            # Utility functions
└── diff.ts             # Diff computation utilities

types/
├── index.ts            # TypeScript type definitions
└── day2.ts             # The day2 service's bodies (from its Pydantic schemas)
```

## Environment Variables

The web app uses relative API paths — no `NEXT_PUBLIC_*` env vars are required. API routes
(`/api/day1`, `/api/day2`, `/api/auth`) are proxied at runtime by the ingress or, in local
development, by `proxy.ts`.

## Docker

```bash
# Build image
docker build -t wingman-web:latest .

# Run container
docker run -p 3000:3000 wingman-web:latest
```
