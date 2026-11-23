"use client";

import { AdminsOnly } from "@/components/infrastructure/admins-only";
import { InventoryPage } from "@/components/inventory/inventory-page";

/**
 * Inventory Management (ADR-0057, docs/notes/2026-11-13-inventory-management-api.md):
 * each MCE's available Agents by pool, installing servers, and the add-server runs.
 * In the Infrastructure workspace, an admin's (ADR-0067): herzi fills the customers' demand.
 */
export default function Page() {
  return (
    <AdminsOnly>
      <InventoryPage />
    </AdminsOnly>
  );
}
