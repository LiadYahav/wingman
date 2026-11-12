# ADR-0040: Creating from a flavor: a nodepool ratio, a suggested name, a one-letter sequence

Date: 2026-11-12
Status: Accepted

## Context

Creating a cluster from a flavor asked the person for everything a flavor
could already say. The user asked for four things:

- **Sizing.** A flavor whose nodepools are three zones should keep them in
  proportion (`1:2:1`), so the person picks one size, not three replica
  counts.
- **InfraEnvs.** A nodepool's InfraEnv should be picked from the MCE.
  InfraEnvs rarely change, so the list can be cached.
- **The name.** It follows from the flavor, the site and the MCE's env:
  `ocp4-prod-rcs-site1-a` for flavor `rcs` on a prod MCE of `site1`, and
  `-b` when `-a` exists.
- **The sequence.** It is a letter, `a`, `b`, `c`, never a number.

The InfraEnv select already existed (`GET /mces/{mce}/infraenvs`, with a
free-text fallback); it read the hub on every form load.

## Decision

1. **`spec.day1.nodepool_ratio`.**
   - It is one whole number from 1 to 100 per nodepool of the flavor, in
     order. Empty means no ratio.
   - It sits beside `values`, not in it: it is not a template input, and the
     cluster file still gets plain `replicas`.
   - Saving a flavor refuses a ratio:
     - without one entry per nodepool (the longer of `structure` and
       `values`);
     - or one that sizes a nodepool whose `replicas` is locked: a size sets
       them, so a lock would fight it.

     A stored flavor that breaks these rules still loads, with them as
     `warnings`, and its ratio is not enforced, as for locks (ADR-0026).
   - Create refuses replicas off the ratio. The first *n* nodepools must be
     `ratio[i] * size` for one whole size of at least 1. A nodepool added
     at create, after those, is sized freely.
   - The create form asks for the size and fills in each sized nodepool's
     replicas, read-only.
   - In the flavor editor the sized nodepools' replica presets move
     together: setting one sets the size, and the others follow (at 1:2:1,
     3 on the first gives 3 · 6 · 3). A number that is not a multiple of its
     nodepool's part stays as typed and is flagged.
   - Drift, import and sync do not read the ratio (left for later, below).
2. **InfraEnvs are kept for `MCE_INFRAENV_CACHE_SECONDS`** (default 600)
   per replica, separately from live status, which still reads the hub
   every time. A failure is not kept. The MCE token's reads do not change.
3. **day1 suggests the name**, at `GET /clusters/name-suggestion?site=&mce=&flavor=`.
   - The name is `ocp4-<env>-<flavor>-<site>-<letter>`.
   - The env is the MCE's, by its name, as the chart derives it.
   - The flavor's name is made DNS-safe. It is cut short, from the end, until
     the HostedCluster's control-plane namespace fits in 63 characters.
   - The letter is the first, `a` to `z`, that no cluster file under any
     site and no open create MR has.
   - The suggestion is computed by day1 because names are unique across
     sites and open MRs, which the browser does not see.
   - The form fills the name in, and again when site, MCE or flavor change,
     until the person edits it. Then the name is theirs, checked by the same
     rules.
4. **A new cluster's sequence is one letter, `a` to `z`.**
   - `new_cluster_problems` refuses a number, or more than one letter.
   - A name with no sequence is still accepted for a new cluster.
   - Existing clusters with a numeric sequence still read, list and edit
     as before. The rule is for new names (ADR-0014's "only new names are
     refused").

## Consequences

- A flavor can carry the shape of its nodepools, not only their contents.
  A cluster made from it starts in proportion.
- The create form loads InfraEnvs from cache after the first person; a new
  InfraEnv shows up within ten minutes, or at once after a restart.
- Every name Wingman suggests follows the convention and is free when
  suggested. Two people creating at the same moment can still get the
  same letter: the second create is refused with "already in use" (the
  open-MR check), and its form suggests the next letter.
- Once `a` to `z` are taken under one base name, no name is suggested
  (`problems` says so). The person picks another short name. 26 clusters of
  one flavor on one site was judged not to need `aa`.

## Left for later

- Changing an existing cluster's size, keeping its ratio (an edit, or sync).
- Drift for replicas that left the ratio.
- Ratios on import: a cluster joining a flavor is not checked against its
  ratio.
