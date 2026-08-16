"""Typed domain models shared by repository inspection, prompting, and UI layers.

The application intentionally keeps these models independent from Gradio and
network clients.  This makes the production pipeline straightforward to test
without downloading a language model or contacting GitHub.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class AnalysisMode(str, Enum):
    """Supported professional review workflows."""

    COMPREHENSIVE = "Comprehensive review"
    BUG_HUNT = "Bug hunt"
    SECURITY = "Security audit"
    PERFORMANCE = "Performance"
    ARCHITECTURE = "Architecture"
    TESTING = "Test strategy"
    DOCUMENTATION = "Documentation"

    @classmethod
    def coerce(cls, value: str | "AnalysisMode" | None) -> "AnalysisMode":
        if isinstance(value, cls):
            return value
        normalized = (value or "").strip().casefold()
        aliases = {
            "comprehensive": cls.COMPREHENSIVE,
            "comprehensive review": cls.COMPREHENSIVE,
            "bug": cls.BUG_HUNT,
            "bug hunt": cls.BUG_HUNT,
            "security": cls.SECURITY,
            "security audit": cls.SECURITY,
            "performance": cls.PERFORMANCE,
            "architecture": cls.ARCHITECTURE,
            "testing": cls.TESTING,
            "test strategy": cls.TESTING,
            "documentation": cls.DOCUMENTATION,
            "docs": cls.DOCUMENTATION,
        }
        return aliases.get(normalized, cls.COMPREHENSIVE)

    @property
    def directive(self) -> str:
        return {
            self.COMPREHENSIVE: (
                "Review correctness, maintainability, security, performance, tests, and developer "
                "experience. Prioritize only material findings."
            ),
            self.BUG_HUNT: (
                "Trace control flow and data assumptions. Look for edge cases, invalid states, race "
                "conditions, error-handling gaps, and regressions."
            ),
            self.SECURITY: (
                "Perform a defensive security review using least privilege and OWASP-style threat "
                "thinking. Do not provide offensive exploitation instructions."
            ),
            self.PERFORMANCE: (
                "Identify algorithmic, I/O, memory, concurrency, caching, and rendering bottlenecks. "
                "Avoid micro-optimizations without evidence."
            ),
            self.ARCHITECTURE: (
                "Evaluate module boundaries, coupling, cohesion, dependency direction, configuration, "
                "observability, and paths for incremental evolution."
            ),
            self.TESTING: (
                "Evaluate testability, missing high-value cases, fixtures, isolation, determinism, and "
                "a practical test pyramid."
            ),
            self.DOCUMENTATION: (
                "Evaluate onboarding, API and configuration documentation, examples, operational "
                "runbooks, and places where code and docs can drift."
            ),
        }[self]

    @property
    def ranking_terms(self) -> frozenset[str]:
        return {
            self.COMPREHENSIVE: frozenset(),
            self.BUG_HUNT: frozenset({"error", "exception", "handler", "service", "state", "validation"}),
            self.SECURITY: frozenset(
                {"auth", "login", "permission", "session", "token", "crypto", "middleware", "security"}
            ),
            self.PERFORMANCE: frozenset(
                {"cache", "query", "database", "worker", "queue", "stream", "render", "performance"}
            ),
            self.ARCHITECTURE: frozenset(
                {"main", "app", "server", "config", "container", "router", "service", "module"}
            ),
            self.TESTING: frozenset({"test", "spec", "fixture", "mock", "integration", "e2e"}),
            self.DOCUMENTATION: frozenset({"readme", "docs", "guide", "example", "changelog", "api"}),
        }[self]


class ReviewDepth(str, Enum):
    """Resource profiles that keep public Space usage bounded."""

    QUICK = "Quick"
    STANDARD = "Standard"
    DEEP = "Deep"

    @classmethod
    def coerce(cls, value: str | "ReviewDepth" | None) -> "ReviewDepth":
        if isinstance(value, cls):
            return value
        normalized = (value or "").strip().casefold()
        return {
            "quick": cls.QUICK,
            "standard": cls.STANDARD,
            "deep": cls.DEEP,
        }.get(normalized, cls.STANDARD)

    @property
    def default_file_limit(self) -> int:
        return {self.QUICK: 5, self.STANDARD: 8, self.DEEP: 12}[self]

    @property
    def max_context_chars(self) -> int:
        return {self.QUICK: 22_000, self.STANDARD: 36_000, self.DEEP: 48_000}[self]

    @property
    def per_file_chars(self) -> int:
        return {self.QUICK: 8_000, self.STANDARD: 13_000, self.DEEP: 18_000}[self]


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def weight(self) -> int:
        return {
            self.CRITICAL: 50,
            self.HIGH: 40,
            self.MEDIUM: 30,
            self.LOW: 20,
            self.INFO: 10,
        }[self]

    @property
    def icon(self) -> str:
        return {
            self.CRITICAL: "🔴",
            self.HIGH: "🟠",
            self.MEDIUM: "🟡",
            self.LOW: "🔵",
            self.INFO: "⚪",
        }[self]


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    size: int
    sha: str = ""


@dataclass(frozen=True)
class CodeSymbol:
    name: str
    kind: str
    path: str
    line: int | None = None
    signature: str = ""


@dataclass(frozen=True)
class DependencyRecord:
    name: str
    specification: str
    source: str
    group: str = "runtime"
    pinned: bool = False


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    category: str
    title: str
    path: str
    line: int | None
    evidence: str
    recommendation: str
    confidence: str = "medium"

    @property
    def location(self) -> str:
        if not self.path:
            return "repository"
        if self.line:
            return f"{self.path}:{self.line}"
        return self.path


@dataclass(frozen=True)
class SourceDocument:
    path: str
    content: str
    language: str
    size: int
    score: float = 0.0
    reasons: tuple[str, ...] = ()
    truncated: bool = False
    symbols: tuple[CodeSymbol, ...] = ()


@dataclass(frozen=True)
class RepositoryProfile:
    total_files: int
    supported_files: int
    total_bytes: int
    languages: tuple[tuple[str, int], ...]
    frameworks: tuple[str, ...]
    package_managers: tuple[str, ...]
    entrypoints: tuple[str, ...]
    test_files: int
    documentation_files: int
    ci_files: tuple[str, ...]
    directories: tuple[tuple[str, int], ...]

    @property
    def primary_language(self) -> str:
        return self.languages[0][0] if self.languages else "Unknown"

    def language_summary(self, limit: int = 5) -> str:
        return ", ".join(f"{name} ({count})" for name, count in self.languages[:limit]) or "Unknown"


@dataclass(frozen=True)
class RepositorySnapshot:
    full_name: str
    html_url: str
    description: str
    default_branch: str
    branch: str
    commit_sha: str
    private: bool
    archived: bool
    fork: bool
    stars: int
    files: tuple[RepositoryFile, ...]


@dataclass(frozen=True)
class PreparedAnalysis:
    analysis_id: str
    repository: RepositorySnapshot
    mode: AnalysisMode
    depth: ReviewDepth
    task: str
    profile: RepositoryProfile
    documents: tuple[SourceDocument, ...]
    dependencies: tuple[DependencyRecord, ...]
    findings: tuple[Finding, ...]
    prompt: str
    warnings: tuple[str, ...] = ()
    metrics: tuple[tuple[str, int | float | str], ...] = ()

    @property
    def selected_files(self) -> tuple[str, ...]:
        return tuple(document.path for document in self.documents)

    def metric(self, name: str, default: Any = None) -> Any:
        return dict(self.metrics).get(name, default)


@dataclass(frozen=True)
class ReviewArtifacts:
    markdown_path: str | None = None
    patch_path: str | None = None
    json_path: str | None = None


def sort_findings(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    """Return deterministic severity/path/rule ordering."""

    return tuple(
        sorted(
            findings,
            key=lambda item: (-item.severity.weight, item.path.casefold(), item.line or 0, item.rule_id),
        )
    )


@dataclass
class MutableMetrics:
    """Small mutable collector converted to immutable UI-safe tuples at the boundary."""

    values: dict[str, int | float | str] = field(default_factory=dict)

    def set(self, name: str, value: int | float | str) -> None:
        self.values[name] = value

    def increment(self, name: str, amount: int = 1) -> None:
        current = self.values.get(name, 0)
        self.values[name] = int(current) + amount

    def freeze(self) -> tuple[tuple[str, int | float | str], ...]:
        return tuple(sorted(self.values.items()))
