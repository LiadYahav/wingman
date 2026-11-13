import { InventoryPage } from "@/components/inventory/inventory-page";

/**
 * Inventory Management (ADR-0057, docs/notes/2026-11-13-inventory-management-api.md):
 * each MCE's available Agents by pool, installing servers, and the add-server runs.
 * Everyone signed in reads it; only admins install servers.
 */
export default function Page() {
  return <InventoryPage />;
}
