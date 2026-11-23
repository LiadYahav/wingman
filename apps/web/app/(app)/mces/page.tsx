"use client";

import { AdminsOnly } from "@/components/infrastructure/admins-only";
import { MceList } from "@/components/infrastructure/mce-list";

/** Customer MCEs, by site (ADR-0067, ADR-0018): an admin's. */
export default function Page() {
  return (
    <AdminsOnly>
      <MceList />
    </AdminsOnly>
  );
}
