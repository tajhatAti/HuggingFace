"""Markdown renderers for the production Gradio interface and exports."""

from __future__ import annotations

from collections import Counter

from .dependencies import render_dependency_inventory
from .domain import Finding, PreparedAnalysis, Severity
from .inspection import render_architecture_map


def format_bytes(value: int) -> str:
    size = float(max(value, 0))
    units = ("B", "KB", "MB", "GB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _escape_table(value: str) -> str:
    return " ".join((value or "").replace("|", "\\|").replace("\n", " ").split())


def render_repository_overview(prepared: PreparedAnalysis) -> str:
    repo = prepared.repository
    profile = prepared.profile
    sha = repo.commit_sha[:12] if repo.commit_sha else "unknown"
    description = repo.description or "No repository description"
    warnings = "\n".join(f"- ⚠️ {warning}" for warning in prepared.warnings)
    warning_section = f"\n\n### Pipeline notes\n{warnings}" if warnings else ""
    severity_counts = Counter(finding.severity for finding in prepared.findings)
    finding_summary = " · ".join(
        f"{severity.icon} {severity_counts.get(severity, 0)} {severity.value}"
        for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW)
        if severity_counts.get(severity, 0)
    ) or "No deterministic leads"

    return f"""## Repository intelligence

### [{repo.full_name}]({repo.html_url})

{description}

| Snapshot | Analysis | Scope | Signals |
|---|---|---|---|
| `{repo.branch}` @ `{sha}` | {prepared.mode.value} · {prepared.depth.value} | {len(prepared.documents)} files · {prepared.metric('context_chars', 0):,} chars | {finding_summary} |

- **Primary language:** {profile.primary_language}
- **Languages:** {profile.language_summary()}
- **Repository scale:** {profile.total_files:,} files · {format_bytes(profile.total_bytes)} indexed from tree metadata
- **Detected stack:** {', '.join(profile.frameworks) or 'No path-level framework signal'}
- **Package managers:** {', '.join(profile.package_managers) or 'Not detected'}
- **Read-only guarantee:** no clone · no execution · no install · no write · no push
{warning_section}
"""


def render_selected_files(prepared: PreparedAnalysis) -> str:
    lines = [
        "## Selected evidence",
        "",
        "Files are ranked deterministically from the request, analysis mode, project entrypoints, manifests, and tests.",
        "",
        "| # | File | Language | Tree size | Score | Why selected | Symbols |",
        "|---:|---|---|---:|---:|---|---:|",
    ]
    for index, document in enumerate(prepared.documents, 1):
        reasons = _escape_table(", ".join(document.reasons))
        truncated = " · truncated" if document.truncated else ""
        lines.append(
            f"| {index} | `{document.path}`{truncated} | {document.language} | "
            f"{format_bytes(document.size)} | {document.score:.1f} | {reasons} | {len(document.symbols)} |"
        )
    lines.extend(
        (
            "",
            f"**Bounded context:** {prepared.metric('context_chars', 0):,} sanitized characters · "
            f"{prepared.metric('secret_redactions', 0)} secret redactions · "
            f"{prepared.metric('prompt_injection_redactions', 0)} prompt-injection redactions",
        )
    )
    return "\n".join(lines)


def render_findings(findings: tuple[Finding, ...]) -> str:
    if not findings:
        return (
            "## Deterministic review leads\n\n"
            "✅ No configured static heuristic matched the selected files. This does not prove the repository is defect-free."
        )
    counts = Counter(item.severity for item in findings)
    lines = [
        "## Deterministic review leads",
        "",
        "These are bounded text heuristics, **not confirmed vulnerabilities**. The AI review must verify each lead against context.",
        "",
        " · ".join(
            f"{severity.icon} **{counts.get(severity, 0)} {severity.value}**"
            for severity in Severity
            if counts.get(severity, 0)
        ),
        "",
        "| Severity | Rule | Location | Finding | Evidence | Recommendation |",
        "|---|---|---|---|---|---|",
    ]
    for item in findings[:50]:
        lines.append(
            f"| {item.severity.icon} **{item.severity.value.upper()}** | `{item.rule_id}` | "
            f"`{item.location}` | {_escape_table(item.title)} | `{_escape_table(item.evidence)}` | "
            f"{_escape_table(item.recommendation)} |"
        )
    return "\n".join(lines)


def render_architecture(prepared: PreparedAnalysis) -> str:
    symbols = [symbol for document in prepared.documents for symbol in document.symbols]
    return render_architecture_map(prepared.profile, symbols)


def render_dependencies(prepared: PreparedAnalysis) -> str:
    return render_dependency_inventory(prepared.dependencies)


def render_empty_state() -> tuple[str, str, str, str, str]:
    return (
        "## Repository intelligence\n\nRun a professional review to inspect a public GitHub repository.",
        "## Selected evidence\n\n_Selected files will appear here._",
        "## Deterministic review leads\n\n_Static leads will appear here._",
        "## Repository architecture\n\n_Architecture and symbols will appear here._",
        "## Dependency inventory\n\n_Dependencies will appear here._",
    )
