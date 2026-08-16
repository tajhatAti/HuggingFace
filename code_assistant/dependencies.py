"""Safe dependency inventory parsers for common ecosystem manifests.

Parsers consume already downloaded text.  They do not resolve, install, import,
or contact package registries, so untrusted repositories cannot execute code.
"""

from __future__ import annotations

import json
import re
import shlex
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.11+ in production
    tomllib = None  # type: ignore[assignment]

from .domain import DependencyRecord, Finding, Severity

MAX_DEPENDENCIES = 800
MANIFEST_FILENAMES = frozenset(
    {
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "setup.cfg",
        "cargo.toml",
        "go.mod",
        "composer.json",
        "gemfile",
        "pubspec.yaml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "packages.lock.json",
    }
)

PYTHON_REQUIREMENT_RE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?\s*([^;\s]*(?:\s*,\s*[^;\s]+)*)?"
)
POETRY_DEP_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*=\s*(.+?)\s*$")
GO_REQUIRE_RE = re.compile(r"^\s*([A-Za-z0-9._~/-]+)\s+(v[^\s]+)")
GEM_RE = re.compile(r"^\s*gem\s+['\"]([^'\"]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?")
GRADLE_RE = re.compile(
    r"(?m)^\s*(implementation|api|compileOnly|runtimeOnly|testImplementation)\s*\(?\s*['\"]([^:'\"]+):([^:'\"]+):([^'\"]+)['\"]"
)
PEP508_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?\s*(.*)$")


def _is_pinned(specification: str) -> bool:
    value = specification.strip()
    if not value:
        return False
    if value.startswith(("git+", "http://", "https://", "file:", "path:")):
        return False
    if value.startswith("workspace:"):
        return True
    if re.search(r"(?:^|,)\s*(?:==|===)\s*[^*\s,]+", value):
        return True
    return bool(re.fullmatch(r"v?\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?", value))


def _record(name: Any, spec: Any, source: str, group: str) -> DependencyRecord | None:
    clean_name = str(name or "").strip()
    clean_spec = str(spec or "").strip()
    if not clean_name or len(clean_name) > 240 or len(clean_spec) > 500:
        return None
    return DependencyRecord(
        name=clean_name,
        specification=clean_spec or "unspecified",
        source=source,
        group=group,
        pinned=_is_pinned(clean_spec),
    )


def _mapping_records(data: Any, source: str, group: str) -> list[DependencyRecord]:
    if not isinstance(data, dict):
        return []
    records: list[DependencyRecord] = []
    for name, spec in data.items():
        if isinstance(spec, dict):
            spec = spec.get("version") or spec.get("path") or spec.get("git") or json.dumps(spec, sort_keys=True)
        item = _record(name, spec, source, group)
        if item:
            records.append(item)
    return records


def _parse_package_json(path: str, content: str) -> list[DependencyRecord]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    records: list[DependencyRecord] = []
    for key, group in (
        ("dependencies", "runtime"),
        ("devDependencies", "development"),
        ("peerDependencies", "peer"),
        ("optionalDependencies", "optional"),
    ):
        records.extend(_mapping_records(data.get(key), path, group) if isinstance(data, dict) else [])
    return records


def _parse_requirements(path: str, content: str) -> list[DependencyRecord]:
    records: list[DependencyRecord] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "-r", "--requirement", "-c", "--constraint")):
            continue
        if line.startswith(("git+", "http://", "https://", "-e ", "--editable ")):
            candidate = line.rsplit("#egg=", 1)[-1] if "#egg=" in line else "direct-reference"
            item = _record(candidate, line, path, "runtime")
        else:
            match = PYTHON_REQUIREMENT_RE.match(line)
            item = _record(match.group(1), match.group(2) or "", path, "runtime") if match else None
        if item:
            records.append(item)
    return records


def _pep508_record(value: Any, path: str, group: str) -> DependencyRecord | None:
    match = PEP508_RE.match(str(value))
    return _record(match.group(1), match.group(2), path, group) if match else None


def _parse_pyproject(path: str, content: str) -> list[DependencyRecord]:
    if tomllib is None:
        return []
    try:
        data = tomllib.loads(content)
    except (ValueError, TypeError):
        return []
    records: list[DependencyRecord] = []
    project = data.get("project", {}) if isinstance(data, dict) else {}
    if isinstance(project, dict):
        for value in project.get("dependencies", []) or []:
            item = _pep508_record(value, path, "runtime")
            if item:
                records.append(item)
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group_name, values in optional.items():
                if not isinstance(values, list):
                    continue
                for value in values:
                    item = _pep508_record(value, path, f"optional:{group_name}")
                    if item:
                        records.append(item)

    tool = data.get("tool", {}) if isinstance(data, dict) else {}
    poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
    if isinstance(poetry, dict):
        for key, group in (("dependencies", "runtime"), ("dev-dependencies", "development")):
            records.extend(_mapping_records(poetry.get(key), path, group))
        poetry_groups = poetry.get("group", {})
        if isinstance(poetry_groups, dict):
            for group_name, group_data in poetry_groups.items():
                if isinstance(group_data, dict):
                    records.extend(
                        _mapping_records(group_data.get("dependencies"), path, f"group:{group_name}")
                    )
    return [item for item in records if item.name.casefold() != "python"]


def _parse_cargo(path: str, content: str) -> list[DependencyRecord]:
    if tomllib is None:
        return []
    try:
        data = tomllib.loads(content)
    except (ValueError, TypeError):
        return []
    records: list[DependencyRecord] = []
    for key, group in (
        ("dependencies", "runtime"),
        ("dev-dependencies", "development"),
        ("build-dependencies", "build"),
    ):
        records.extend(_mapping_records(data.get(key), path, group) if isinstance(data, dict) else [])
    return records


def _parse_go_mod(path: str, content: str) -> list[DependencyRecord]:
    records: list[DependencyRecord] = []
    in_require = False
    for raw_line in content.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if line == "require (":
            in_require = True
            continue
        if in_require and line == ")":
            in_require = False
            continue
        if line.startswith("require "):
            line = line[len("require ") :].strip()
        elif not in_require:
            continue
        match = GO_REQUIRE_RE.match(line)
        if match:
            item = _record(match.group(1), match.group(2), path, "runtime")
            if item:
                records.append(item)
    return records


def _parse_composer(path: str, content: str) -> list[DependencyRecord]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    return _mapping_records(data.get("require"), path, "runtime") + _mapping_records(
        data.get("require-dev"), path, "development"
    )


def _parse_gemfile(path: str, content: str) -> list[DependencyRecord]:
    records: list[DependencyRecord] = []
    for line in content.splitlines():
        match = GEM_RE.match(line)
        if match:
            item = _record(match.group(1), match.group(2) or "", path, "runtime")
            if item:
                records.append(item)
    return records


def _xml_text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _parse_maven(path: str, content: str) -> list[DependencyRecord]:
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError):
        return []
    records: list[DependencyRecord] = []
    for dependency in root.findall(".//{*}dependency"):
        group_id = _xml_text(dependency.find("{*}groupId"))
        artifact_id = _xml_text(dependency.find("{*}artifactId"))
        version = _xml_text(dependency.find("{*}version"))
        scope = _xml_text(dependency.find("{*}scope")) or "runtime"
        name = f"{group_id}:{artifact_id}".strip(":")
        item = _record(name, version, path, scope)
        if item:
            records.append(item)
    return records


def _parse_gradle(path: str, content: str) -> list[DependencyRecord]:
    records: list[DependencyRecord] = []
    for match in GRADLE_RE.finditer(content):
        item = _record(
            f"{match.group(2)}:{match.group(3)}",
            match.group(4),
            path,
            match.group(1),
        )
        if item:
            records.append(item)
    return records


def _parse_pubspec(path: str, content: str) -> list[DependencyRecord]:
    # A deliberately small YAML subset avoids adding a parser that could construct objects.
    records: list[DependencyRecord] = []
    group = ""
    for raw_line in content.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith((" ", "\t")) and raw_line.rstrip().endswith(":"):
            section = raw_line.strip().rstrip(":")
            group = section if section in {"dependencies", "dev_dependencies"} else ""
            continue
        if not group:
            continue
        match = re.match(r"^\s{2,}([A-Za-z0-9_-]+)\s*:\s*([^#\s].*?)?\s*$", raw_line)
        if match:
            item = _record(match.group(1), match.group(2) or "unspecified", path, group)
            if item:
                records.append(item)
    return records


PARSERS = {
    "package.json": _parse_package_json,
    "requirements.txt": _parse_requirements,
    "pyproject.toml": _parse_pyproject,
    "cargo.toml": _parse_cargo,
    "go.mod": _parse_go_mod,
    "composer.json": _parse_composer,
    "gemfile": _parse_gemfile,
    "pubspec.yaml": _parse_pubspec,
    "pom.xml": _parse_maven,
    "build.gradle": _parse_gradle,
    "build.gradle.kts": _parse_gradle,
}


def is_dependency_manifest(path: str) -> bool:
    return PurePosixPath(path).name.casefold() in MANIFEST_FILENAMES


def parse_dependencies(path: str, content: str) -> tuple[DependencyRecord, ...]:
    parser = PARSERS.get(PurePosixPath(path).name.casefold())
    if not parser:
        return ()
    try:
        records = parser(path, content)
    except (ValueError, TypeError, KeyError, IndexError, shlex.Error):
        return ()
    deduplicated: dict[tuple[str, str, str], DependencyRecord] = {}
    for item in records:
        key = (item.name.casefold(), item.source, item.group)
        deduplicated.setdefault(key, item)
        if len(deduplicated) >= MAX_DEPENDENCIES:
            break
    return tuple(sorted(deduplicated.values(), key=lambda item: (item.group, item.name.casefold())))


def merge_dependencies(groups: Iterable[Iterable[DependencyRecord]]) -> tuple[DependencyRecord, ...]:
    merged: dict[tuple[str, str, str], DependencyRecord] = {}
    for records in groups:
        for item in records:
            merged.setdefault((item.name.casefold(), item.source, item.group), item)
            if len(merged) >= MAX_DEPENDENCIES:
                break
    return tuple(sorted(merged.values(), key=lambda item: (item.source, item.group, item.name.casefold())))


def dependency_findings(dependencies: Iterable[DependencyRecord], limit: int = 12) -> tuple[Finding, ...]:
    """Flag broad/unversioned production dependencies without claiming vulnerability data."""

    findings: list[Finding] = []
    for item in dependencies:
        if item.group.casefold() in {"development", "dev", "test", "testimplementation"}:
            continue
        specification = item.specification.strip()
        broad = specification in {"", "*", "latest", "unspecified"} or specification.startswith(
            (">=", "^", "~", ">", "http://", "git+")
        )
        if not broad:
            continue
        findings.append(
            Finding(
                rule_id="DEP-BROAD-RANGE",
                severity=Severity.LOW,
                category="Supply chain",
                title=f"Dependency `{item.name}` is not reproducibly pinned",
                path=item.source,
                line=None,
                evidence=f"{item.name}: {specification or 'unspecified'}",
                recommendation=(
                    "Use a lockfile or a reviewed bounded version policy, then automate dependency updates and tests."
                ),
                confidence="high",
            )
        )
        if len(findings) >= limit:
            break
    return tuple(findings)


def render_dependency_inventory(dependencies: tuple[DependencyRecord, ...]) -> str:
    if not dependencies:
        return "## Dependency inventory\n\n_No supported dependency manifest was selected or no dependencies were parsed._"

    runtime = sum(1 for item in dependencies if item.group.casefold() in {"runtime", "dependencies"})
    development = sum(
        1 for item in dependencies if item.group.casefold() in {"development", "dev", "dev_dependencies"}
    )
    pinned = sum(1 for item in dependencies if item.pinned)
    sources = sorted({item.source for item in dependencies})
    lines = [
        "## Dependency inventory",
        "",
        (
            f"**{len(dependencies):,} packages** · {runtime:,} runtime · {development:,} development · "
            f"{pinned:,} exactly pinned"
        ),
        "",
        f"Manifests: {', '.join(f'`{source}`' for source in sources)}",
        "",
        "| Package | Specification | Group | Manifest |",
        "|---|---|---|---|",
    ]
    for item in dependencies[:150]:
        name = item.name.replace("|", "\\|")
        spec = item.specification.replace("|", "\\|")
        group = item.group.replace("|", "\\|")
        lines.append(f"| `{name}` | `{spec}` | {group} | `{item.source}` |")
    if len(dependencies) > 150:
        lines.append(f"\n_Inventory table limited to 150 of {len(dependencies):,} records._")
    lines.append(
        "\n> This is a static inventory, not a live vulnerability lookup. Versions must be checked against "
        "the ecosystem's current advisory database in CI."
    )
    return "\n".join(lines)
