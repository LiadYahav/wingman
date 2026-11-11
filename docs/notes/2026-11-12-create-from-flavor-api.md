# Creating a cluster from a flavor: the API the web reads (2026-11-12)

Three additions to creating a cluster from a flavor, and one rule
(ADR-0040):

1. a flavor may size its nodepools by a **ratio** (`1:2:1`), and the create
   form asks for one size;
2. each nodepool's **InfraEnv** is picked from the MCE's InfraEnvs (the
   route existed; it is now cached);
3. day1 **suggests the cluster's name** from the flavor, the site and the
   MCE's env, with the next free letter;
4. a new cluster's **sequence is one letter**, `a` to `z`, never a number.

## 1. The nodepool ratio

A flavor gains `spec.day1.nodepool_ratio`: one whole number per nodepool of
the flavor, in order. Empty (the default) is no ratio: the flavor behaves as
before.

```yaml
spec:
  day1:
    nodepool_ratio: [1, 2, 1]   # zone a, b, c
    structure:
      nodepools: [{}, {}, {}]
    values:
      nodepools:
        - infra_env: dell-r660-zone-a
        - infra_env: dell-r660-zone-b
        - infra_env: dell-r660-zone-c
```

It is not a template input: the cluster file still gets a plain `replicas`
per nodepool, and the chart's values contract does not change.

**Saving a flavor** (`POST`/`PUT /specs`) refuses, as one of its `problems`
(a stored flavor that breaks them still loads, with them as `warnings`):

- `nodepool_ratio: each entry must be a whole number from 1 to 100`;
- `nodepool_ratio: 2 entries for 3 nodepools; give one per nodepool`;
- `nodepool_ratio: nodepools[1].replicas is locked; a ratio sizes it, so it cannot be locked too`.

**Creating a cluster** (`POST /clusters/preview`, `POST /clusters`) with
such a flavor: the first *n* nodepools of the request (n = the ratio's
length) must have `replicas` of `ratio[i] * size` for one whole size of at
least 1. Otherwise 422 `VALIDATION_ERROR` with, e.g.:

```
nodepools[1].replicas: the flavor sizes its nodepools 1:2:1, so the replicas must be 1, 2 and 1 times one size (e.g. 2, 4, 2); got 2, 3, 2
```

Nodepools after the first *n* (added at create) are sized freely. A ratio
that breaks the save rules is not enforced, as for locks.

Drift, import and sync do not read the ratio: changing an existing
cluster's size is left for later.

## 2. InfraEnvs

`GET /api/day1/mces/{mce}/infraenvs` is unchanged: InfraEnv names, sorted;
501 `FEATURE_DISABLED` with live status off. It is now cached per replica
for `MCE_INFRAENV_CACHE_SECONDS` (default `600`; `0` reads the hub every
time). A failure is not cached. The MCE token's reads are unchanged: it
already lists `infraenvs`.

The create form picks each nodepool's `infra_env` from this list. With live
status off it is free text, with a quiet note; when the read fails, free
text with the problem.

## 3. `GET /api/day1/clusters/name-suggestion?site=&mce=&flavor=`

Any signed-in user. All three parameters are required.

```json
{
  "name": "ocp4-prod-rcs-site1-a",
  "env": "prod",
  "short_name": "rcs",
  "sequence": "a",
  "problems": []
}
```

- `env` is the MCE's (`ocp4-<env>-mce-<site>-<letter>`), as the chart
  derives it.
- `short_name` is the flavor's name, DNS-safe (lowercase, other characters
  become `-`, repeated dashes collapse), cut short when the HostedCluster's
  control-plane namespace would pass 63 characters.
- `sequence` is the first letter, `a` to `z`, that makes a name no cluster
  has. The taken names are every cluster file in the day1 repo, under any
  site, and every open Wingman MR that creates one.
- `name` is `null`, with `problems` saying why, when the MCE does not
  follow the convention (no env) or every letter is taken.

Errors: `404 NOT_FOUND` for an unknown site, MCE or flavor; `422` for a
missing parameter.

The form fills the name in once site, MCE and flavor are chosen, and fills
it in again when they change, until the person edits the name. An edited
name is the person's (an override), still checked by the rules below.

## 4. The sequence is one letter

`POST /clusters/preview` and `POST /clusters` refuse a name whose sequence
is not one letter `a` to `z`, with the other naming problems (422
`VALIDATION_ERROR`):

```
sequence '01' of cluster 'ocp4-prod-rcs-site1-01' must be one letter, a to z (ocp4-prod-rcs-site1-a): a number is not the convention
```

A name with no sequence is still accepted. Existing clusters with a
numeric sequence read, list and edit as before: the rule is for new names
only.
