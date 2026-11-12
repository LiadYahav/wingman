"""Specs and the shared template, read from and changed in the specs project.

A spec that fails to parse is listed with its error rather than dropped
(ADR-0004: a read error is never swallowed). Every change is a merge request,
and a spec is saved only when it meets the flavor rules: safe values
(ADR-0013), locks that fix a value (ADR-0026), machine configs that resolve
(ADR-0027) and owner numbers (ADR-0028).

A version, once saved, never changes (ADR-0044): each cluster is measured
against the version its header names, read from the file's history
(:meth:`SpecCatalog.at_version`), so an edit must give the flavor a new
version, and one never used before.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Final

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import Commit, EntryKind, RepoPath
from wingman_core.domain.users import User
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.domain import paths
from wingman_day1.domain.changes import ProvisionResult, SpecAction, SpecChange
from wingman_day1.domain.errors import (
    AlreadyInUseError,
    InvalidInputError,
    InvalidSpecError,
    ResourceNotFoundError,
    StaleError,
)
from wingman_day1.domain.machine_configs import flavor_config_problems
from wingman_day1.domain.specs import (
    ClusterSpec,
    dump_spec,
    parse_spec,
    rule_problems,
    with_template,
)
from wingman_day1.domain.template import TemplateField, analyze_template
from wingman_day1.ports import RepoReads, SpecChanges

VERSION_HISTORY: Final = 100
"""Commits of a flavor's file searched for an older version; one older than that is unknown."""


@dataclass(frozen=True, slots=True)
class SpecEntry:
    """One file under the specs folder: a spec, or why it could not be read."""

    name: str
    spec: ClusterSpec | None
    error: InvalidSpecError | None = None
    last_commit_id: str | None = None
    """The commit that last changed the file; an edit or delete sends it back."""


class SpecCatalog:
    """Read specs and the template; propose spec changes."""

    def __init__(
        self,
        specs: RepoReads,
        changes: SpecChanges,
        machine_configs: MachineConfigService,
        *,
        specs_root: str,
    ) -> None:
        """Read through ``specs`` (cached), write through ``changes``, resolve configs."""
        self._specs = specs
        self._changes = changes
        self._machine_configs = machine_configs
        self._root = specs_root
        self._versions: dict[tuple[str, str], ClusterSpec] = {}
        """Older versions found in history: a saved version never changes, so kept for good."""
        self._missing: dict[tuple[str, str], str] = {}
        """Versions history did not have, by the commit the repo was read at then."""
        self._looking: dict[tuple[str, str], asyncio.Lock] = {}

    # ── Reads ───────────────────────────────────────────────────────────────

    async def template(self) -> str:
        """The shared ``cluster-template.j2``; empty when the project has none."""
        try:
            return (await self._specs.read(paths.TEMPLATE_FILE)).content
        except NotFoundError:
            return ""

    async def schema(self, *, include_reserved: bool = False) -> list[TemplateField]:
        """The template's inputs, for the create form."""
        template = await self.template()
        return analyze_template(template, include_reserved=include_reserved) if template else []

    async def entries(self) -> list[SpecEntry]:
        """Every ``<name>.yaml`` under the specs folder, with the template filled in."""
        try:
            entries = await self._specs.tree(RepoPath(self._root))
        except NotFoundError:
            return []
        names = sorted(
            e.name.removesuffix(paths.SPEC_SUFFIX)
            for e in entries
            if e.kind is EntryKind.FILE and e.name.endswith(paths.SPEC_SUFFIX)
        )
        template = await self.template()
        return list(await asyncio.gather(*(self._entry(name, template) for name in names)))

    async def get(self, name: str) -> ClusterSpec:
        """One spec with the template filled in. Missing → ``ResourceNotFoundError``."""
        spec, _ = await self._read(name)
        return with_template(spec, await self.template())

    async def entry(self, name: str) -> SpecEntry:
        """One spec with the template and its file's ``last_commit_id``.

        Missing → ``ResourceNotFoundError``; a file that does not parse raises
        its ``InvalidSpecError``.
        """
        spec, last_commit_id = await self._read(name)
        return SpecEntry(name, with_template(spec, await self.template()), None, last_commit_id)

    async def history(self, name: str) -> list[Commit]:
        """Commits that changed a spec's file."""
        return await self._specs.history(self._path(name))

    async def at_version(self, name: str, version: str) -> ClusterSpec | None:
        """The flavor as it was at ``version``, with the template; ``None`` when it never was.

        The file on main when it is at that version; otherwise the newest of
        the last ``VERSION_HISTORY`` commits of the file whose content names
        it. A version found in history is kept for good (versions never
        change once saved); one not found is looked for again once the
        repository moves.
        """
        key = (name, version)
        if key in self._versions:
            return self._versions[key]
        path = self._path(name)
        try:
            file = await self._specs.read(path)
        except NotFoundError:
            return None
        template = await self.template()
        with contextlib.suppress(InvalidSpecError):
            current = parse_spec(file.content, expected_name=name)
            if current.metadata.version == version:
                return with_template(current, template)
        lock = self._looking.setdefault(key, asyncio.Lock())
        async with lock:
            if key in self._versions:
                return self._versions[key]
            if self._missing.get(key) == file.last_commit_id:
                return None
            for commit in await self._specs.history(path, limit=VERSION_HISTORY):
                try:
                    old = (await self._specs.read(path, ref=commit.id)).content
                    spec = parse_spec(old, expected_name=name)
                except (NotFoundError, InvalidSpecError):
                    continue
                if spec.metadata.version == version:
                    found = with_template(spec, template)
                    self._versions[key] = found
                    return found
            self._missing[key] = file.last_commit_id
            return None

    async def at(self, name: str, sha: str) -> str:
        """A spec file's text at a commit."""
        try:
            return (await self._specs.read(self._path(name), ref=sha)).content
        except NotFoundError as exc:
            raise ResourceNotFoundError(f"spec {name!r} does not exist at {sha}") from exc

    # ── Changes ─────────────────────────────────────────────────────────────

    async def create(self, spec: ClusterSpec, *, user: User) -> ProvisionResult:
        """Propose a new spec."""
        await self._require_savable(spec)
        name = spec.metadata.name
        try:
            await self._specs.read(self._path(name))
        except NotFoundError:
            pass
        else:
            raise AlreadyInUseError(f"spec {name!r} already exists")
        return await self._changes.apply(
            SpecChange(
                action=SpecAction.CREATE,
                name=name,
                version=spec.metadata.version,
                requested_by=user,
                summary=_summary("Creating", spec),
                content=dump_spec(spec),
            )
        )

    async def update(
        self, name: str, spec: ClusterSpec, *, user: User, last_commit_id: str | None = None
    ) -> ProvisionResult:
        """Propose a new version of a spec; the name cannot change."""
        if spec.metadata.name != name:
            raise InvalidInputError(
                "a spec cannot be renamed",
                [f"metadata.name is {spec.metadata.name!r}, the spec being updated is {name!r}"],
            )
        await self._require_savable(spec)
        current = await self._current(name, last_commit_id)
        await self._require_new_version(name, spec.metadata.version)
        return await self._changes.apply(
            SpecChange(
                action=SpecAction.UPDATE,
                name=name,
                version=spec.metadata.version,
                requested_by=user,
                summary=_summary("Updating", spec),
                content=dump_spec(spec),
                last_commit_id=current,
            )
        )

    async def delete(
        self, name: str, *, user: User, last_commit_id: str | None = None
    ) -> ProvisionResult:
        """Propose removing a spec. Clusters created from it keep their files."""
        current = await self._current(name, last_commit_id)
        version = "?"
        with contextlib.suppress(InvalidSpecError):  # a broken spec can still be deleted
            version = (await self.get(name)).metadata.version
        return await self._changes.apply(
            SpecChange(
                action=SpecAction.DELETE,
                name=name,
                version=version,
                requested_by=user,
                summary=(
                    f"Deleting cluster spec **{name}**. Clusters already created from it keep "
                    "their files; they are no longer linked to a spec."
                ),
                last_commit_id=current,
            )
        )

    # ── Internals ───────────────────────────────────────────────────────────

    async def _require_savable(self, spec: ClusterSpec) -> None:
        """Every flavor rule a spec must meet before it is proposed; all problems at once."""
        problems = rule_problems(spec)
        catalog = await self._machine_configs.catalog()
        problems += flavor_config_problems(spec.spec.day1.values, catalog)
        if problems:
            raise InvalidSpecError(f"spec {spec.metadata.name!r} cannot be saved", problems)

    async def _require_new_version(self, name: str, version: str) -> None:
        """An edit gives the flavor a version never saved before (ADR-0044)."""
        problem = None
        with contextlib.suppress(InvalidSpecError):  # a broken file can still be fixed
            if (await self.get(name)).metadata.version == version:
                problem = (
                    f"metadata.version: {version} is the current version; an edit needs a new "
                    "one, which reaches each cluster through its own merge request"
                )
        if problem is None and await self.at_version(name, version) is not None:
            problem = (
                f"metadata.version: {version} was used before; a version never changes once saved"
            )
        if problem is not None:
            raise InvalidSpecError(f"spec {name!r} cannot be saved", [problem])

    def _path(self, name: str) -> RepoPath:
        try:
            return paths.spec_file(self._root, name)
        except ValueError as exc:
            raise ResourceNotFoundError(f"spec {name!r} does not exist") from exc

    async def _read(self, name: str) -> tuple[ClusterSpec, str]:
        try:
            file = await self._specs.read(self._path(name))
        except NotFoundError as exc:
            raise ResourceNotFoundError(f"spec {name!r} does not exist") from exc
        return parse_spec(file.content, expected_name=name), file.last_commit_id

    async def _current(self, name: str, expected: str | None) -> str:
        try:
            file = await self._specs.read(self._path(name))
        except NotFoundError as exc:
            raise ResourceNotFoundError(f"spec {name!r} does not exist") from exc
        if (
            expected is not None
            and expected != file.last_commit_id
            and await self._specs.changed_since(self._path(name), expected)
        ):
            raise StaleError(
                f"spec {name!r} changed since it was read ({expected[:8]} → "
                f"{file.last_commit_id[:8]}); reload and try again"
            )
        return expected or file.last_commit_id

    async def _entry(self, name: str, template: str) -> SpecEntry:
        try:
            file = await self._specs.read(self._path(name))
        except NotFoundError as exc:
            raise ResourceNotFoundError(f"spec {name!r} does not exist") from exc
        try:
            spec = parse_spec(file.content, expected_name=name)
        except InvalidSpecError as exc:
            return SpecEntry(name, None, exc, file.last_commit_id)
        return SpecEntry(name, with_template(spec, template), None, file.last_commit_id)


def _summary(verb: str, spec: ClusterSpec) -> str:
    addons = ", ".join(f"`{a.team}/{a.name}@{a.version}`" for a in spec.spec.day2.addons)
    return (
        f"{verb} cluster spec **{spec.metadata.name}** v{spec.metadata.version}.\n\n"
        f"{spec.metadata.description}\n\n"
        f"Preset values: {len(spec.spec.day1.values)}; day2 addons: {addons or 'none'}."
    ).replace("\n\n\n\n", "\n\n")
