# Wingman Web

Next.js frontend for the Wingman Internal Developer Platform.

## Features

- **Cluster Management**: Create, view, and manage OpenShift clusters
- **Spec Templates**: Define cluster templates with Day1 provisioning and Day2 addons
- **Addon Configuration**: Configure which addon fields can be overridden at cluster creation
- **Approval Workflow**: Review and approve GitLab MRs for infrastructure changes
- **Audit Trail**: Track all cluster lifecycle events

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
│   └── audit/          # Audit trail
├── login/              # Authentication
└── layout.tsx          # Root layout

components/
├── ui/                 # Base UI components (shadcn/ui)
├── common/             # Shared components (dialogs, headers)
└── specs/              # Spec-specific components

lib/
├── api-client.ts       # Typed API client
├── utils.ts            # Utility functions
└── diff.ts             # Diff computation utilities

types/
└── index.ts            # TypeScript type definitions
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_DAY1_API` | Day1 service URL | `/api/day1` |
| `NEXT_PUBLIC_DAY2_API` | Day2 service URL | `/api/day2` |

## Docker

```bash
# Build image
docker build -t wingman-web:latest .

# Run container
docker run -p 3000:3000 wingman-web:latest
```
