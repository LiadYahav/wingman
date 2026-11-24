"use client";

import { AdminsOnly } from "@/components/infrastructure/admins-only";
import { SeedList } from "@/components/infrastructure/seed-list";

/** Seeds & KV Clusters (ADR-0067): an admin's. */
export default function Page() {
  return (
    <AdminsOnly>
      <SeedList />
    </AdminsOnly>
  );
}
