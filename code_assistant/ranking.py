"""Deterministic file relevance ranking for bounded large-repository review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from .dependencies import is_dependency_manifest
from .domain import AnalysisMode, RepositoryFile
from .inspection import ENTRYPOINT_NAMES, is_documentation_path, is_test_path
from .security import is_safe_path

MAX_TREE_FILES = 20_000
MAX_SELECTED_FILES = 14
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
PATH_TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+")

STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "before",
        "change",
        "code",
        "could",
        "file",
        "from",
        "have",
        "into",
        "make",
        "please",
        "project",
        "repo",
        "repository",
        "review",
        "should",
        "that",
        "their",
        "there",
        "these",
        "this",
        "want",
        "will",
        "with",
        "would",
        "করো",
        "করে",
        "করা",
        "চাই",
        "একটা",
        "যেন",
        "আমার",
        "দেও",
        "দেখো",
    }
)

KEY_FILENAMES = {
    "app.py": 8.0,
    "main.py": 8.0,
    "server.py": 8.0,
    "manage.py": 8.0,
    "index.ts": 7.0,
    "index.tsx": 7.0,
    "index.js": 7.0,
    "main.ts": 7.0,
    "main.tsx": 7.0,
    "main.js": 7.0,
    "main.go": 8.0,
    "main.rs": 8.0,
    "program.cs": 8.0,
    "dockerfile": 4.0,
    "pyproject.toml": 4.0,
    "package.json": 4.0,
    "requirements.txt": 4.0,
    "cargo.toml": 4.0,
    "go.mod": 4.0,
}

MODE_PATH_HINTS = {
    AnalysisMode.BUG_HUNT: ("error", "exception", "handler", "service", "state", "valid", "core"),
    AnalysisMode.SECURITY: ("auth", "login", "permission", "session", "token", "middleware", "security"),
    AnalysisMode.PERFORMANCE: ("cache", "query", "database", "worker", "queue", "stream", "render"),
    AnalysisMode.ARCHITECTURE: ("main", "app", "server", "config", "router", "service", "container"),
    AnalysisMode.TESTING: ("test", "spec", "fixture", "mock", "integration", "e2e"),
    AnalysisMode.DOCUMENTATION: ("readme", "docs", "guide", "example", "api", "changelog"),
    AnalysisMode.COMPREHENSIVE: (),
}


@dataclass(frozen=True)
class RankedPath:
    file: RepositoryFile
    score: float
    reasons: tuple[str, ...]


def request_terms(task: str) -> frozenset[str]:
    base = {
        token.casefold()
        for token in TOKEN_RE.findall((task or "").casefold())
        if len(token) >= 3 and token.casefold() not in STOPWORDS
    }
    # Repository filenames commonly abbreviate product vocabulary. Expanding a
    # small, explicit synonym set makes `authentication` reliably find `auth.py`
    # without fuzzy matching unrelated paths.
    expansions = {
        "authentication": {"auth", "login", "session"},
        "authenticate": {"auth", "login"},
        "authorization": {"auth", "permission", "access"},
        "authorisation": {"auth", "permission", "access"},
        "database": {"db", "sql", "query"},
        "configuration": {"config", "settings"},
        "documentation": {"docs", "readme"},
        "javascript": {"js"},
        "typescript": {"ts"},
        "performance": {"perf", "cache"},
    }
    expanded = set(base)
    for term in base:
        expanded.update(expansions.get(term, ()))
    return frozenset(expanded)


def _path_terms(path: str) -> frozenset[str]:
    normalized = path.casefold().replace("/", " ").replace("-", " ").replace(".", " ")
    return frozenset(TOKEN_RE.findall(normalized))


def _score_file(
    item: RepositoryFile,
    task: str,
    mode: AnalysisMode,
    changed_paths: frozenset[str],
) -> RankedPath | None:
    if not is_safe_path(item.path):
        return None
    path = item.path.casefold()
    name = PurePosixPath(path).name
    stem = PurePosixPath(path).stem
    terms = request_terms(task)
    path_terms = _path_terms(path)
    explicit_paths = {value.casefold().strip("`'\".,") for value in PATH_TOKEN_RE.findall(task or "")}
    score = 0.0
    reasons: list[str] = []

    if path in explicit_paths or any(path.endswith(value) for value in explicit_paths):
        score += 80.0
        reasons.append("explicitly mentioned")
    if item.path in changed_paths:
        score += 30.0
        reasons.append("changed against base")

    exact_hits = sorted(term for term in terms if term == stem or term == name)
    name_hits = sorted(term for term in terms if term in name and term not in exact_hits)
    path_hits = sorted(term for term in terms if term in path and term not in exact_hits and term not in name_hits)
    token_hits = sorted(term for term in terms if term in path_terms and term not in exact_hits)
    if exact_hits:
        score += 18.0 * len(exact_hits)
        reasons.append("exact request term")
    if name_hits:
        score += 11.0 * len(name_hits)
        reasons.append("request term in filename")
    if path_hits:
        score += 6.0 * len(path_hits)
        reasons.append("request term in path")
    if token_hits:
        score += 3.0 * len(token_hits)

    mode_hits = [hint for hint in MODE_PATH_HINTS[mode] if hint in path]
    if mode_hits:
        score += min(15.0, 4.0 * len(mode_hits))
        reasons.append(f"{mode.value.casefold()} signal")

    key_score = KEY_FILENAMES.get(name, 0.0)
    if key_score:
        score += key_score
        reasons.append("project entry/configuration")
    if name in ENTRYPOINT_NAMES:
        score += 3.0
    if is_dependency_manifest(item.path):
        score += 4.0
        reasons.append("dependency manifest")
    if is_test_path(item.path):
        if mode in {AnalysisMode.TESTING, AnalysisMode.BUG_HUNT, AnalysisMode.COMPREHENSIVE} or "test" in terms:
            score += 7.0
            reasons.append("test coverage")
        else:
            score -= 1.5
    if is_documentation_path(item.path):
        if mode is AnalysisMode.DOCUMENTATION:
            score += 9.0
            reasons.append("documentation")
        elif name.startswith("readme"):
            score += 1.2
        else:
            score -= 2.0
    if path.startswith(".github/workflows/"):
        score += 4.0 if mode in {AnalysisMode.SECURITY, AnalysisMode.COMPREHENSIVE} else 1.0
        reasons.append("CI workflow")
    if any(part in path for part in ("generated/", ".min.", "snapshot", "fixtures/", "examples/")):
        score -= 5.0
    depth = len(PurePosixPath(path).parts)
    score += max(0.0, 1.2 - (depth - 1) * 0.15)
    if item.size <= 0:
        score -= 3.0
    elif item.size < 30_000:
        score += 0.5

    return RankedPath(item, round(score, 3), tuple(dict.fromkeys(reasons)) or ("supported source",))


def _best_matching(ranked: list[RankedPath], predicate, chosen: set[str]) -> RankedPath | None:
    return next((item for item in ranked if item.file.path not in chosen and predicate(item)), None)


def rank_candidate_paths(
    files: list[RepositoryFile],
    task: str,
    mode: AnalysisMode | str = AnalysisMode.COMPREHENSIVE,
    limit: int = 8,
    changed_paths: set[str] | frozenset[str] | None = None,
) -> list[RankedPath]:
    """Rank files and reserve a small amount of architectural diversity."""

    resolved_mode = AnalysisMode.coerce(mode)
    bounded_limit = max(1, min(int(limit), MAX_SELECTED_FILES))
    resolved_changes = frozenset(changed_paths or ())
    ranked = [
        result
        for item in files[:MAX_TREE_FILES]
        if (result := _score_file(item, task, resolved_mode, resolved_changes)) is not None
    ]
    ranked.sort(key=lambda item: (-item.score, len(item.file.path), item.file.path.casefold()))
    if not ranked:
        return []
    if bounded_limit <= 3:
        return ranked[:bounded_limit]

    selected: list[RankedPath] = []
    chosen: set[str] = set()

    def include(candidate: RankedPath | None) -> None:
        if candidate and candidate.file.path not in chosen and len(selected) < bounded_limit:
            selected.append(candidate)
            chosen.add(candidate.file.path)

    # Start with the strongest task-specific results.
    for item in ranked[: max(1, bounded_limit - 3)]:
        include(item)

    # Preserve enough context to understand and validate a patch.
    include(_best_matching(ranked, lambda item: PurePosixPath(item.file.path).name.casefold() in ENTRYPOINT_NAMES, chosen))
    include(_best_matching(ranked, lambda item: is_dependency_manifest(item.file.path), chosen))
    if resolved_mode in {AnalysisMode.TESTING, AnalysisMode.BUG_HUNT, AnalysisMode.COMPREHENSIVE}:
        include(_best_matching(ranked, lambda item: is_test_path(item.file.path), chosen))
    if resolved_mode is AnalysisMode.DOCUMENTATION:
        include(_best_matching(ranked, lambda item: is_documentation_path(item.file.path), chosen))

    for item in ranked:
        include(item)
        if len(selected) >= bounded_limit:
            break

    # Final output follows relevance ordering even when diversity reservations were appended.
    selected.sort(key=lambda item: (-item.score, len(item.file.path), item.file.path.casefold()))
    return selected[:bounded_limit]


def select_candidate_paths(
    paths: list[str],
    task: str,
    limit: int = 8,
    mode: AnalysisMode | str = AnalysisMode.COMPREHENSIVE,
) -> list[str]:
    """Compatibility helper for callers that only have path strings."""

    files = [RepositoryFile(path=path, size=1) for path in paths]
    return [item.file.path for item in rank_candidate_paths(files, task, mode, limit)]
