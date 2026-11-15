import type { TuningProfiles } from "@/types";

/**
 * `GET /api/day1/tuning-profiles` on the fixtures
 * (docs/notes/2026-11-15-tuning-profiles-api.md §1, ADR-0061): three Tuned,
 * one of which builds on the one PerformanceProfile, a variant for
 * prod-lark-site1, and the misnamed file in `problems`.
 */
export const mockTuningProfiles: TuningProfiles = {
  folder: "tuning",
  found: true,
  profiles: [
    {
      name: "performance-pinned",
      kind: "PerformanceProfile",
      summary: null,
      path: "tuning/performance-pinned.yaml",
      clusters: [],
      requires_performance_profile: null,
    },
    {
      name: "tuned-network-latency",
      kind: "Tuned",
      summary: "Lower network latency on worker nodes",
      path: "tuning/tuned-network-latency.yaml",
      clusters: ["prod-lark-site1"],
      requires_performance_profile: null,
    },
    {
      name: "tuned-pinned-irq",
      kind: "Tuned",
      summary: "Keep interrupts off the pinned CPUs",
      path: "tuning/tuned-pinned-irq.yaml",
      clusters: [],
      requires_performance_profile: "performance-pinned",
    },
    {
      name: "tuned-sysctl-baseline",
      kind: "Tuned",
      summary: "Raise the kernel's file and connection limits",
      path: "tuning/tuned-sysctl-baseline.yaml",
      clusters: [],
      requires_performance_profile: null,
    },
  ],
  problems: [
    {
      path: "tuning/tuned-misnamed.yaml",
      detail: "metadata.name is tuned-renamed; it must be the file's name, tuned-misnamed",
    },
  ],
};
