"use client";

import { AdminsOnly } from "@/components/infrastructure/admins-only";
import { InfrastructureOverview } from "@/components/infrastructure/infrastructure-overview";

/** The Infrastructure workspace's home (ADR-0067): an admin's. */
export default function Page() {
  return (
    <AdminsOnly>
      <InfrastructureOverview />
    </AdminsOnly>
  );
}
