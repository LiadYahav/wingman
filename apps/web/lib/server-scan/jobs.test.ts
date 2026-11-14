/**
 * server-scan's Jobs page cases at 92146d3 (`JobsPage.test.tsx`; decision
 * 18), on the pure functions the page renders: its CronJob and Job as its
 * test makes them, and its cases where they decide a word, a poll or a log.
 */

import { describe, expect, it } from "vitest";
import type { CronJob, JobRun, JobsOverview } from "@/types/server-scan-jobs";
import {
  backendNote, enabledLabel, isUnfinished, jobsPollMs, LIST_POLL_MS, logsBody, logsCaption, manualText, noRunsText,
  podButtonLabel, runBlocked, runTimesHint, scheduleHint, startedPod,
} from "./jobs";

const POD = { name: "r-collector-oneview-123-abcde", phase: "Succeeded", started_at: null };

function job(overrides: Partial<JobRun> = {}): JobRun {
  return {
    name: "r-collector-oneview-123",
    created_at: "2026-11-01T06:00:00Z",
    started_at: null,
    finished_at: null,
    active: 0,
    succeeded: 1,
    failed: 0,
    state: "succeeded",
    manual: false,
    triggered_by: null,
    pods: [POD],
    ...overrides,
  };
}

function cronjob(name: string, overrides: Partial<CronJob> = {}): CronJob {
  return {
    name,
    schedule: "0 6 * * *",
    suspend: false,
    last_schedule_time: null,
    last_successful_time: null,
    warning: null,
    active: false,
    enabled: true,
    deployed: true,
    jobs: [job()],
    ...overrides,
  };
}

const overview = (cronjobs: CronJob[], backend: JobsOverview["backend"] = "kubernetes"): JobsOverview => ({
  enabled: true,
  backend,
  namespace: "ns",
  cronjobs,
});

describe("how often the page reads", () => {
  it("polls the list every 5 seconds while a CronJob has a running Job, else every 30", () => {
    expect(jobsPollMs(overview([cronjob("idle"), cronjob("busy", { active: true })]))).toBe(LIST_POLL_MS);
    expect(jobsPollMs(overview([cronjob("idle")]))).toBe(30_000);
    expect(jobsPollMs(undefined)).toBe(30_000);
  });

  it("refreshes an open log only while its Job is unfinished, from the latest list", () => {
    const pick = { cronjob: "c", job: "r-collector-oneview-123", pod: POD.name };
    expect(isUnfinished([cronjob("c", { jobs: [job({ state: "active" })] })], pick)).toBe(true);
    expect(isUnfinished([cronjob("c", { jobs: [job({ state: "pending" })] })], pick)).toBe(true);
    expect(isUnfinished([cronjob("c", { jobs: [job({ state: "failed" })] })], pick)).toBe(false);
    expect(isUnfinished([cronjob("c")], pick)).toBe(false);
    // A Job gone from the list (its history limit) is not running
    expect(isUnfinished([cronjob("c", { jobs: [] })], pick)).toBe(false);
    expect(isUnfinished(undefined, pick)).toBe(false);
  });
});

describe("a card's words", () => {
  it("shows each job's values.yaml flag", () => {
    expect(enabledLabel(cronjob("on"))).toBe("enabled: true");
    expect(enabledLabel(cronjob("off", { enabled: false, deployed: false, jobs: [], schedule: "" }))).toBe("enabled: false");
  });

  it("says a CronJob has no Job yet, or is switched off in values.yaml", () => {
    expect(noRunsText(cronjob("on", { jobs: [] }))).toBe("No Jobs yet.");
    expect(noRunsText(cronjob("off", { deployed: false, jobs: [] }))).toMatch(/switched off in values\.yaml/);
  });

  it("names a pod's button by its name's last five characters and its phase", () => {
    expect(podButtonLabel(POD)).toBe("Logs · abcde · Succeeded");
  });

  it("marks a Job started by hand, and who server-scan says started it", () => {
    expect(manualText(job())).toBeNull();
    expect(manualText(job({ manual: true }))).toBe("by hand");
    expect(manualText(job({ manual: true, triggered_by: "api-token-admin" }))).toBe("by hand (api-token-admin)");
  });

  it("says the jobs are simulated with server-scan's fake backend only", () => {
    expect(backendNote(overview([], "fake"))).toBe("This deployment uses simulated jobs.");
    expect(backendNote(overview([]))).toBeNull();
    expect(backendNote(undefined)).toBeNull();
  });

  it("gives the schedule's and a Job's times in tooltips, in Israel's time", () => {
    const ran = cronjob("c", { last_schedule_time: "2026-07-15T03:00:00Z", last_successful_time: "2026-07-15T03:04:00Z" });
    expect(scheduleHint(ran)).toMatch(/^Last scheduled 15\/07\/2026, 06:00:00.*\nLast succeeded 15\/07\/2026, 06:04:00/);
    expect(scheduleHint(cronjob("new"))).toBe("It has not run yet.");
    expect(runTimesHint(job({ started_at: "2026-11-01T06:00:05Z" })).split("\n")).toHaveLength(2);
  });
});

describe("Run job", () => {
  it("is off for a CronJob that already has a running Job", () => {
    expect(runBlocked(cronjob("idle"))).toBeNull();
    expect(runBlocked(cronjob("busy", { active: true }))).toBe("A Job of this CronJob is already running");
  });

  it("cannot run one that is not deployed", () => {
    expect(runBlocked(cronjob("off", { enabled: false, deployed: false, jobs: [], schedule: "" }))).toBe("Not deployed: turn it on in values.yaml first");
  });

  it("opens the new Job's first pod's log when the answer already names one", () => {
    expect(startedPod("c", job({ name: "new-job", state: "active", active: 1, pods: [] }))).toBeNull();
    expect(startedPod("c", job({ name: "new-job" }))).toEqual({ cronjob: "c", job: "new-job", pod: POD.name });
  });
});

describe("a pod's log", () => {
  it("shows its text, says when it has none, and loads", () => {
    expect(logsBody({ pod: POD.name, tail: 500, text: "collector.done\n" })).toBe("collector.done\n");
    expect(logsBody({ pod: POD.name, tail: 500, text: "" })).toBe("(no output yet)");
    expect(logsBody(undefined)).toBe("Loading…");
  });

  it("says its tail, and that it refreshes while the Job runs", () => {
    expect(logsCaption(false)).toBe("Last 500 lines.");
    expect(logsCaption(true)).toBe("Last 500 lines, refreshing every 3 s while the job runs.");
  });
});
