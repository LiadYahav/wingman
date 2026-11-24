# Code organisation, in five steps

**Status:** decided 2026-11-24 (the user's sequence, from a read-only review
of main at 3.58.0). Step 1 is done (3.58.1); the others are planned, one or
more refactor PRs each, in this order.

ADR-0056 says where code goes and keeps files and functions small; 23 files
are still in `scripts/file-size-baseline.txt`. The review found the larger
risk elsewhere: one rule written five times, with two meanings (step 1
found seven copies in all, and a third, deliberate meaning in day2). So the
sequence starts with the shared rules, then moves the code the baseline
lists, biggest and most edited first.

How every step is done:

- **Behaviour stays**, unless a copy was wrong: then the commit says so
  (`fix(...)`), has a regression test, and the upgrade index a row.
- **Readability too** (the user): a moved function also gets clearer and
  shorter, in a commit apart from the mechanical move.
- **The baseline only shrinks**: each split lowers or removes its file's
  line, and no exemption is added (ADR-0056).
- **Unit tests come with each split**: a pure helper or model moved out of
  a page gets its own `*.test.ts` or `test_*.py`.

## The steps

| Step | What | Status |
|---|---|---|
| 1 | One version helper in core and one in the web | **Done** 2026-11-24 (3.58.1) |
| 2 | The create page into `components/`; one home per external system in day1; day2's three biggest services split | Planned |
| 3 | The other big pages into `components/`; the composition root into `composition/` | Planned |
| 4 | Typed `day2Api` calls and a `useCatalog` hook; the files near their limit split; ports by area | Planned |
| 5 | The web's `types/` and `lib/` layout; one `useListState` hook | Planned |

### 1. The version helper (done, 3.58.1)

Stripping the architecture from an OpenShift release tag
(`4.16.27-x86_64` → `4.16.27`) and checking a `mastertag`'s shape were
written in seven places:

| Where | What it did | Now |
|---|---|---|
| day1 `domain/openshift_versions.py` (`bare_release`) | removed `-x86_64` only | `without_arch` |
| day1 `domain/upgrades.py` (`_bare`) | removed `-x86_64` only | `without_arch` |
| day1 `domain/quick_links.py` (an MCE card) | cut the hub's version at its first `-`: a prerelease lost its name | `without_arch` |
| web `clusters/new/page.tsx` (`offeredRelease`) | removed `-x86_64` only | `lib/release-tags.ts` |
| web `specs/flavor-editor/preview-plan.ts` (`previewRelease`) | removed `-x86_64` only | `offeredRelease` |
| day1 `domain/cluster_file.py` (`mastertag`) | `X.Y.Z(-[a-z0-9_]+)?`: refused a prerelease | `is_release_tag` |
| day2 `domain/versions.py` (`mastertag_problem`) | `X.Y.Z(-\S+)?`: passed tags no image has | `is_release_tag` |

The rules, in `wingman_core.domain.release_tags` and `apps/web/lib/release-tags.ts`:

- **The release a tag names** (`without_arch`, `withoutArch`): a last part
  that is an architecture OpenShift publishes (`x86_64`, `aarch64`,
  `ppc64le`, `s390x`, `multi`) comes off; a prerelease stays
  (`4.16.0-rc.1-x86_64` is `4.16.0-rc.1`), and so does any other suffix.
- **A release tag** (`is_release_tag`) is what the hostedclusters-setup
  chart renders into a release image (`hc.releaseTag`: a bare `X.Y.Z` gets
  `-x86_64`, any other tag is the image's tag as written): `X.Y.Z`, then
  optionally `-` and lower-case letters, digits, `_`, `.` and `-`, at most
  128 characters.

day2's OCP version is a third rule, and stays apart on purpose: the day2
platform keys its `ocp-versions/<v>/` pins and the `day2.gitops/ocp-version`
label by what comes before a tag's first `-` (`splitList "-" | first`), so a
prerelease is its `X.Y.Z` there. `wingman_day2.domain.versions.ocp_version`
is now its only copy (the upgrade check and its route split the tag again
themselves), and an oracle scenario renders a prerelease to keep it equal
to the platform. ADR-0023 and ADR-0034 are amended.

### 2. The create page, one home per system, day2's big services

- `app/(app)/clusters/new/page.tsx` (1,815 lines, the largest file) and
  `clusters/new/flavor-form.ts` (482) move into
  `components/clusters/create/`: a file per section and dialog, the form's
  state in `use-create-cluster.ts`, its pure logic in `model.ts` with unit
  tests; the route file only reads params and renders it (ADR-0056 web
  rules 1, 3 and 4).
- Alongside, in day1: one home per external system, `infrastructure/<system>/`
  (ADR-0056 Python rule 3). The orchestrator's clients
  (`workflows_api.py`, the provision, upgrade, scale and add-server
  workflows, their payloads, `cached_workflows.py`), the hub's (`hub_api.py`,
  `hub_objects.py`, `cached_hub.py`, `mce_access.py`) and day2's
  (`day2_client.py`, `cached_day2.py`) each become a sub-package of
  `adapter.py`, `parse.py` and `cached.py`; the fakes go to
  `infrastructure/fakes/`.
- day2's `application/changes.py` (895), `authoring.py` (852) and
  `plan_writer.py` (776) split by use case (ADR-0056 Python rule 2).

### 3. The other big pages, the composition root

- `app/(app)/specs/[name]/page.tsx` (666), `approvals/[id]/page.tsx` (626)
  and `addons/page.tsx` (541) move into `components/`, as step 2 does.
- day1's composition root (`main.py`, 526) becomes a `composition/` package
  (ADR-0056 Python rule 4), and its context's fields stop being `Optional`:
  an adapter that is off is a null adapter, not `None` that every caller
  checks.

### 4. Typed day2 calls, `useCatalog`, files near their limit

- `lib/day2.ts` gets typed calls (`day2Api.<area>.<call>`, as
  `lib/api/day1/` has since 3.18.5), and a `useCatalog` hook replaces the six
  copies of the catalog query (the clusters list, a cluster's page and its
  add-ons, the create page, the Addons page, the flavor editor's add-ons).
- The files a few lines under 500 split before the next feature pushes them
  over; the ports split by area.

### 5. The web's `types/` and `lib/` layout, one list-state hook

- day1's types all under `types/day1/` (`inventory.ts`, `scale.ts`,
  `upgrade.ts`, `quick-links.ts` and `platforms.ts` are at the top level
  today), and `lib/` grouped by area: `lib/scale/` (`scale.ts` and the five
  `scale-*.ts`), `lib/upgrade/`.
- One `useListState` hook for the filters and paging (and Clusters' sort)
  that Approvals, Audit and Clusters each keep their own way.

## Waits for the user

Two visible names: "spec" or "flavor" (the code and the UI say both:
the Flavors pages, "preset by spec" on the create form), and "operators"
or "add-ons" (the UI says add-ons since 3.13.0; the API's deprecated
`/teams/{team}/operators` aliases and some code keep the old word).
Renaming them changes what people read, so the user decides first.
