# ADR-0028: The owner fields are numbers

Date: 2026-11-08
Status: Accepted

## Context

A cluster file names its owner as three organisation numbers,
`owner.merkaz`, `owner.anaf` and `owner.mador`, filled from the template
inputs `owner_merkaz`, `owner_anaf` and `owner_mador`. The create form took
any text, so names, typos and spaces reached the file, and nothing could
filter or group clusters by owner reliably. User decision 2026-11-08
(flavors v2): owners are numbers only, three numeric fields, with no names
and no catalogue.

## Decision

- Each owner input is a string of 1 to 10 ASCII digits (`0`-`9`). It stays a
  string, so a leading zero survives, and the template quotes it, so the
  file holds exactly what was given.
- Day1 checks the merged inputs at preview and at create, and a flavor's
  values at save, where an owner is a preset or a lock (ADR-0026). An input
  that is absent is not checked here; the template's own `StrictUndefined`
  reports it as missing.
- A broken owner is one line of the 422 problem's `details.problems`
  (`owner_anaf: must be a number of 1 to 10 digits, ...`), listed with every
  other broken rule of the request.

## Alternatives rejected

- **Accept JSON numbers too**: `0042` cannot be a JSON number, and the form
  already sends strings; one type is simpler to reason about.
- **Unicode digits (`\d`)**: Arabic-Indic or full-width digits are digits to
  Python's `re`, not owner numbers.
- **A catalogue of teams with names**: the user chose numbers only; a name
  can change, the number is what the organisation uses.

## Consequences

- The cluster list can filter and group by the three numbers.
- Existing cluster files are not touched; a flavor's owner preset that is
  not a number cannot be saved until it is fixed.

## Verification

- `apps/day1-service/tests/unit/domain/test_owners.py`: what is accepted and
  what is refused.
- `apps/day1-service/tests/unit/application/test_flavor_rules.py` and
  `apps/day1-service/tests/api/test_flavor_rules_api.py`: the 422 at create
  and at flavor save, together with config problems, and a flavor's owner
  preset reaching the file.
