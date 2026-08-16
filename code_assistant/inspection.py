"""Static, non-executing repository structure and symbol inspection."""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import PurePosixPath

from .domain import CodeSymbol, RepositoryFile, RepositoryProfile


LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".c": "C",
    ".h": "C/C++",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".dart": "Dart",
    ".scala": "Scala",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".astro": "Astro",
    ".json": "JSON",
    ".jsonc": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".proto": "Protocol Buffers",
    ".md": "Markdown",
    ".mdx": "Markdown",
    ".rst": "reStructuredText",
    ".txt": "Text",
}

SPECIAL_LANGUAGE_FILENAMES = {
    "dockerfile": "Dockerfile",
    "makefile": "Makefile",
    "justfile": "Just",
    "gemfile": "Ruby",
    "rakefile": "Ruby",
    "procfile": "Procfile",
    "jenkinsfile": "Groovy",
}

ENTRYPOINT_NAMES = {
    "app.py",
    "main.py",
    "server.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "index.js",
    "index.ts",
    "index.tsx",
    "main.js",
    "main.ts",
    "main.tsx",
    "server.js",
    "server.ts",
    "main.go",
    "main.rs",
    "program.cs",
    "application.java",
}

MANIFEST_TO_MANAGER = {
    "package.json": "npm-compatible",
    "pnpm-workspace.yaml": "pnpm",
    "yarn.lock": "Yarn",
    "bun.lock": "Bun",
    "bun.lockb": "Bun",
    "requirements.txt": "pip",
    "pyproject.toml": "Python/PyPI",
    "setup.py": "setuptools",
    "setup.cfg": "setuptools",
    "pipfile": "Pipenv",
    "poetry.lock": "Poetry",
    "uv.lock": "uv",
    "cargo.toml": "Cargo",
    "go.mod": "Go modules",
    "composer.json": "Composer",
    "gemfile": "Bundler",
    "pubspec.yaml": "Dart pub",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle",
    "packages.lock.json": "NuGet",
}

FRAMEWORK_PATH_SIGNALS: tuple[tuple[str, str], ...] = (
    ("next.config.", "Next.js"),
    ("nuxt.config.", "Nuxt"),
    ("vite.config.", "Vite"),
    ("svelte.config.", "SvelteKit"),
    ("astro.config.", "Astro"),
    ("angular.json", "Angular"),
    ("manage.py", "Django-compatible"),
    ("wsgi.py", "Python WSGI"),
    ("asgi.py", "Python ASGI"),
    ("fastapi", "FastAPI-compatible"),
    ("tailwind.config.", "Tailwind CSS"),
    ("playwright.config.", "Playwright"),
    ("cypress.config.", "Cypress"),
    ("storybook", "Storybook"),
    ("dockerfile", "Docker"),
    ("docker-compose", "Docker Compose"),
    ("compose.yaml", "Docker Compose"),
    ("compose.yml", "Docker Compose"),
    ("terraform", "Terraform"),
)

TEST_MARKERS = (
    "/test/",
    "/tests/",
    "/__tests__/",
    ".test.",
    ".spec.",
    "test_",
    "_test.go",
    "tests.rs",
)

DOC_MARKERS = ("readme", "changelog", "contributing", "license", "docs/", ".md", ".mdx", ".rst")


_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
JS_FUNCTION_RE = re.compile(
    rf"(?m)^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+({_IDENTIFIER})\s*\(([^)]*)\)"
)
JS_ARROW_RE = re.compile(
    rf"(?m)^\s*(?:export\s+)?(?:const|let|var)\s+({_IDENTIFIER})\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>"
)
JS_CLASS_RE = re.compile(rf"(?m)^\s*(?:export\s+)?(?:default\s+)?class\s+({_IDENTIFIER})\b")
GO_FUNCTION_RE = re.compile(r"(?m)^func\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)")
RUST_ITEM_RE = re.compile(
    r"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(fn|struct|enum|trait|mod)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
JVM_TYPE_RE = re.compile(
    r"(?m)^\s*(?:public|private|protected|internal|abstract|final|sealed|open|data|static|\s)*"
    r"(class|interface|enum|record|object)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
PHP_FUNCTION_RE = re.compile(r"(?m)^\s*(?:public|private|protected|static|final|abstract|\s)*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)")
RUBY_ITEM_RE = re.compile(r"(?m)^\s*(class|module|def)\s+([A-Za-z_][A-Za-z0-9_!?=]*(?:::[A-Za-z_][A-Za-z0-9_]*)*)")


def detect_language(path: str) -> str:
    pure = PurePosixPath(path)
    name = pure.name.casefold()
    if name in SPECIAL_LANGUAGE_FILENAMES:
        return SPECIAL_LANGUAGE_FILENAMES[name]
    return LANGUAGE_BY_EXTENSION.get(pure.suffix.casefold(), "Other")


def is_test_path(path: str) -> bool:
    normalized = f"/{path.casefold().strip('/')}"
    name = PurePosixPath(normalized).name
    return any(marker in normalized or marker in name for marker in TEST_MARKERS)


def is_documentation_path(path: str) -> bool:
    normalized = path.casefold()
    name = PurePosixPath(normalized).name
    return any(marker in normalized or marker in name for marker in DOC_MARKERS)


def _top_directory(path: str) -> str:
    parts = PurePosixPath(path).parts
    return parts[0] if len(parts) > 1 else "(root)"


def build_repository_profile(files: list[RepositoryFile], supported_paths: set[str]) -> RepositoryProfile:
    language_counts: Counter[str] = Counter()
    directory_counts: Counter[str] = Counter()
    frameworks: set[str] = set()
    managers: set[str] = set()
    entrypoints: list[str] = []
    ci_files: list[str] = []
    test_files = 0
    documentation_files = 0

    for item in files:
        normalized = item.path.casefold()
        name = PurePosixPath(normalized).name
        directory_counts[_top_directory(item.path)] += 1

        if item.path in supported_paths:
            language = detect_language(item.path)
            if language not in {"Other", "Text"}:
                language_counts[language] += 1

        if is_test_path(item.path):
            test_files += 1
        if is_documentation_path(item.path):
            documentation_files += 1
        if name in ENTRYPOINT_NAMES:
            entrypoints.append(item.path)
        if normalized.startswith(".github/workflows/") or any(
            marker in normalized
            for marker in (".gitlab-ci", "circleci/config", "azure-pipelines", "jenkinsfile")
        ):
            ci_files.append(item.path)

        manager = MANIFEST_TO_MANAGER.get(name)
        if manager:
            managers.add(manager)
        for signal, framework in FRAMEWORK_PATH_SIGNALS:
            if signal in normalized:
                frameworks.add(framework)

    languages = tuple(sorted(language_counts.items(), key=lambda pair: (-pair[1], pair[0])))
    directories = tuple(sorted(directory_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:20])
    return RepositoryProfile(
        total_files=len(files),
        supported_files=len(supported_paths),
        total_bytes=sum(max(item.size, 0) for item in files),
        languages=languages,
        frameworks=tuple(sorted(frameworks)),
        package_managers=tuple(sorted(managers)),
        entrypoints=tuple(sorted(entrypoints)[:20]),
        test_files=test_files,
        documentation_files=documentation_files,
        ci_files=tuple(sorted(ci_files)[:20]),
        directories=directories,
    )


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, max(offset, 0)) + 1


def _compact_signature(value: str, limit: int = 160) -> str:
    compact = " ".join(value.replace("\n", " ").split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _python_symbols(path: str, content: str, limit: int) -> list[CodeSymbol]:
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError, TypeError, MemoryError):
        return []

    symbols: list[CodeSymbol] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = [argument.arg for argument in node.args.args]
            if node.args.vararg:
                arguments.append("*" + node.args.vararg.arg)
            if node.args.kwarg:
                arguments.append("**" + node.args.kwarg.arg)
            symbols.append(
                CodeSymbol(
                    name=node.name,
                    kind="async function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                    path=path,
                    line=getattr(node, "lineno", None),
                    signature=_compact_signature(f"{node.name}({', '.join(arguments)})"),
                )
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(
                CodeSymbol(
                    name=node.name,
                    kind="class",
                    path=path,
                    line=getattr(node, "lineno", None),
                    signature=node.name,
                )
            )
        if len(symbols) >= limit:
            break
    return sorted(symbols, key=lambda symbol: (symbol.line or 0, symbol.name.casefold()))[:limit]


def _regex_symbols(path: str, content: str, language: str, limit: int) -> list[CodeSymbol]:
    matches: list[tuple[int, CodeSymbol]] = []

    def add(match: re.Match[str], name_group: int, kind: str, signature: str = "") -> None:
        name = match.group(name_group)
        matches.append(
            (
                match.start(),
                CodeSymbol(
                    name=name,
                    kind=kind,
                    path=path,
                    line=_line_number(content, match.start()),
                    signature=_compact_signature(signature or match.group(0)),
                ),
            )
        )

    if language in {"JavaScript", "TypeScript", "Vue", "Svelte"}:
        for match in JS_FUNCTION_RE.finditer(content):
            add(match, 1, "function")
        for match in JS_ARROW_RE.finditer(content):
            add(match, 1, "function")
        for match in JS_CLASS_RE.finditer(content):
            add(match, 1, "class")
    elif language == "Go":
        for match in GO_FUNCTION_RE.finditer(content):
            add(match, 1, "function")
    elif language == "Rust":
        for match in RUST_ITEM_RE.finditer(content):
            add(match, 2, match.group(1))
    elif language in {"Java", "Kotlin", "C#", "Scala"}:
        for match in JVM_TYPE_RE.finditer(content):
            add(match, 2, match.group(1))
    elif language == "PHP":
        for match in PHP_FUNCTION_RE.finditer(content):
            add(match, 1, "function")
    elif language == "Ruby":
        for match in RUBY_ITEM_RE.finditer(content):
            add(match, 2, match.group(1))

    matches.sort(key=lambda item: (item[0], item[1].name.casefold()))
    return [symbol for _, symbol in matches[:limit]]


def extract_symbols(path: str, content: str, limit: int = 80) -> tuple[CodeSymbol, ...]:
    """Extract a bounded symbol outline without importing or executing source."""

    if not content or limit <= 0:
        return ()
    language = detect_language(path)
    if language == "Python":
        symbols = _python_symbols(path, content, limit)
    else:
        symbols = _regex_symbols(path, content, language, limit)
    return tuple(symbols[:limit])


def render_architecture_map(profile: RepositoryProfile, symbols: list[CodeSymbol]) -> str:
    lines = [
        "## Repository architecture",
        "",
        f"- **Primary language:** {profile.primary_language}",
        f"- **Language mix:** {profile.language_summary()}",
        f"- **Files:** {profile.total_files:,} total · {profile.supported_files:,} reviewable",
        f"- **Tests/docs:** {profile.test_files:,} test files · {profile.documentation_files:,} documentation files",
        f"- **Framework signals:** {', '.join(profile.frameworks) or 'None detected from paths'}",
        f"- **Package managers:** {', '.join(profile.package_managers) or 'None detected'}",
    ]

    if profile.entrypoints:
        lines.extend(("", "### Entrypoints", *[f"- `{path}`" for path in profile.entrypoints[:12]]))
    if profile.directories:
        lines.extend(
            (
                "",
                "### Largest top-level areas",
                *[f"- `{directory}` — {count:,} files" for directory, count in profile.directories[:12]],
            )
        )
    if symbols:
        lines.extend(("", "### Selected-file symbols"))
        for symbol in symbols[:80]:
            suffix = f":{symbol.line}" if symbol.line else ""
            signature = f" — `{symbol.signature}`" if symbol.signature else ""
            lines.append(f"- **{symbol.kind}** `{symbol.name}` in `{symbol.path}{suffix}`{signature}")
    else:
        lines.extend(("", "_No supported symbols were detected in the selected files._"))
    return "\n".join(lines)
