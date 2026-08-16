"""Production repository preparation pipeline.

The pipeline is deliberately read-only: parse a canonical GitHub identifier,
fetch public metadata/tree/text, rank a bounded file set, redact secrets,
neutralize prompt injection, extract static structure, and build one model prompt.
No repository code is cloned, imported, installed, or executed.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from .dependencies import dependency_findings, merge_dependencies, parse_dependencies
from .domain import (
    AnalysisMode,
    MutableMetrics,
    PreparedAnalysis,
    RepositoryFile,
    RepositorySnapshot,
    ReviewDepth,
    SourceDocument,
    sort_findings,
)
from .github_client import (
    GitHubClient,
    GitHubError,
    RepoRef,
    TreeSnapshot,
    parse_github_repo,
    validate_branch,
)
from .inspection import build_repository_profile, detect_language, extract_symbols
from .prompting import build_review_prompt
from .ranking import (
    MAX_SELECTED_FILES,
    MAX_TREE_FILES,
    rank_candidate_paths,
    select_candidate_paths,
)
from .security import (
    MAX_STATIC_FINDINGS_TOTAL,
    UnsafeRequestError,
    ensure_safe_request,
    is_safe_path,
    redact_secrets,
    sanitize_repository_content,
    scan_static_findings,
)

MAX_FILE_BYTES = 24_000
MAX_CONTEXT_CHARS = 48_000
DEFAULT_FILE_LIMIT = 8


@dataclass(frozen=True)
class PreparedRepository:
    """Backward-compatible compact result used by the original public API."""

    repo_name: str
    repo_url: str
    branch: str
    description: str
    selected_files: tuple[str, ...]
    prompt: str


def _coerce_tree(client: Any, repo: RepoRef, branch: str) -> TreeSnapshot:
    if hasattr(client, "tree_snapshot"):
        snapshot = client.tree_snapshot(repo, branch)
        if isinstance(snapshot, TreeSnapshot):
            return snapshot

    raw_tree = client.tree(repo, branch)
    files: list[RepositoryFile] = []
    for item in raw_tree:
        if not isinstance(item, dict) or item.get("type", "blob") != "blob":
            continue
        try:
            size = max(0, int(item.get("size") or 0))
        except (TypeError, ValueError):
            size = 0
        files.append(
            RepositoryFile(
                path=str(item.get("path") or ""),
                size=size,
                sha=str(item.get("sha") or ""),
            )
        )
    return TreeSnapshot(commit_sha="", files=tuple(files), truncated=False)


def _truncate_source(content: str, limit: int) -> tuple[str, bool]:
    if len(content) <= limit:
        return content, False
    if limit < 500:
        return content[:limit], True
    head_size = int(limit * 0.72)
    tail_size = limit - head_size - 100
    head = content[:head_size].rstrip()
    tail = content[-max(tail_size, 0) :].lstrip()
    return f"{head}\n\n<TRUNCATED_MIDDLE_FOR_CONTEXT_BUDGET>\n\n{tail}", True


def _depth_for_legacy_limit(file_limit: int) -> ReviewDepth:
    if file_limit <= 5:
        return ReviewDepth.QUICK
    if file_limit >= 10:
        return ReviewDepth.DEEP
    return ReviewDepth.STANDARD


def prepare_analysis(
    repo_value: str,
    branch_value: str,
    task: str,
    *,
    mode: AnalysisMode | str = AnalysisMode.COMPREHENSIVE,
    depth: ReviewDepth | str = ReviewDepth.STANDARD,
    file_limit: int | None = None,
    client: GitHubClient | None = None,
) -> PreparedAnalysis:
    """Prepare a complete, sanitized repository intelligence snapshot."""

    started = time.monotonic()
    ensure_safe_request(task)
    resolved_mode = AnalysisMode.coerce(mode)
    resolved_depth = ReviewDepth.coerce(depth)
    resolved_limit = resolved_depth.default_file_limit if file_limit is None else int(file_limit)
    resolved_limit = max(3, min(resolved_limit, MAX_SELECTED_FILES))
    client = client or GitHubClient()
    metrics = MutableMetrics()
    warnings: list[str] = []

    repo = parse_github_repo(repo_value)
    metadata = client.metadata(repo)
    if metadata.private:
        raise ValueError(
            "নিরাপত্তার জন্য এই public Space private repository পড়ে না। Public repo দিন অথবা self-hosted edition ব্যবহার করুন।"
        )
    if getattr(metadata, "archived", False):
        warnings.append("Repository archived; suggested changes may require a maintained fork.")
    branch = validate_branch(branch_value, metadata.default_branch)
    snapshot = _coerce_tree(client, repo, branch)
    if snapshot.truncated:
        raise ValueError("GitHub সম্পূর্ণ repository tree দেয়নি; ছোট branch ব্যবহার করুন।")
    if not snapshot.files:
        raise ValueError("Repository branch-এ কোনো file পাওয়া যায়নি।")
    if len(snapshot.files) > MAX_TREE_FILES:
        raise ValueError(
            f"Repository-তে {len(snapshot.files):,} files আছে; safe public limit {MAX_TREE_FILES:,}। "
            "ছোট branch বা আলাদা sub-project ব্যবহার করুন।"
        )

    all_files = list(snapshot.files)
    reviewable = {
        item.path
        for item in all_files
        if is_safe_path(item.path) and 0 <= item.size <= MAX_FILE_BYTES * 4
    }
    profile = build_repository_profile(all_files, reviewable)
    metrics.set("tree_files", len(all_files))
    metrics.set("reviewable_files", len(reviewable))

    ranked = rank_candidate_paths(all_files, task, resolved_mode, resolved_limit)
    if not ranked:
        raise ValueError("Review করার মতো supported source/documentation file পাওয়া যায়নি।")

    context_budget = min(MAX_CONTEXT_CHARS, resolved_depth.max_context_chars)
    allocation = min(
        resolved_depth.per_file_chars,
        max(2_500, context_budget // max(len(ranked), 1)),
    )
    documents: list[SourceDocument] = []
    dependency_groups = []
    findings = []
    secret_count = 0
    injection_count = 0
    unavailable_count = 0
    used_chars = 0

    for ranked_item in ranked:
        item = ranked_item.file
        if used_chars >= context_budget:
            break
        read_limit = min(MAX_FILE_BYTES, max(allocation * 2, resolved_depth.per_file_chars))
        try:
            raw_content = client.text_file(repo, branch, item.path, read_limit)
        except (GitHubError, ValueError, UnicodeError):
            unavailable_count += 1
            continue

        findings.extend(scan_static_findings(item.path, raw_content))
        sanitized, file_secret_count, file_injection_count = sanitize_repository_content(raw_content)
        secret_count += file_secret_count
        injection_count += file_injection_count
        dependency_groups.append(parse_dependencies(item.path, sanitized))

        remaining = context_budget - used_chars
        document_limit = min(allocation, remaining)
        content, truncated = _truncate_source(sanitized, document_limit)
        symbols = extract_symbols(item.path, sanitized, limit=80)
        documents.append(
            SourceDocument(
                path=item.path,
                content=content,
                language=detect_language(item.path),
                size=item.size,
                score=ranked_item.score,
                reasons=ranked_item.reasons,
                truncated=truncated or len(raw_content) >= read_limit,
                symbols=symbols,
            )
        )
        used_chars += len(content)

    if not documents:
        raise ValueError("Selected files download করা যায়নি। GitHub rate limit অথবা file format পরীক্ষা করুন।")

    dependencies = merge_dependencies(dependency_groups)
    findings.extend(dependency_findings(dependencies))
    ordered_findings = sort_findings(findings)[:MAX_STATIC_FINDINGS_TOTAL]

    if secret_count:
        warnings.append(f"{secret_count} secret-like value(s) were redacted before AI processing.")
    if injection_count:
        warnings.append(f"{injection_count} repository-embedded instruction line(s) were neutralized.")
    if unavailable_count:
        warnings.append(f"{unavailable_count} selected file(s) could not be downloaded and were skipped.")
    truncated_count = sum(1 for document in documents if document.truncated)
    if truncated_count:
        warnings.append(f"{truncated_count} large file(s) were truncated to fit the bounded context window.")
    if profile.total_files and profile.test_files == 0:
        warnings.append("No conventional test path was detected in the repository tree.")

    repository = RepositorySnapshot(
        full_name=metadata.full_name,
        html_url=metadata.html_url,
        description=metadata.description,
        default_branch=metadata.default_branch,
        branch=branch,
        commit_sha=snapshot.commit_sha,
        private=metadata.private,
        archived=getattr(metadata, "archived", False),
        fork=getattr(metadata, "fork", False),
        stars=getattr(metadata, "stars", 0),
        files=tuple(all_files),
    )
    metrics.set("selected_files", len(documents))
    metrics.set("context_chars", used_chars)
    metrics.set("symbols", sum(len(document.symbols) for document in documents))
    metrics.set("dependencies", len(dependencies))
    metrics.set("static_findings", len(ordered_findings))
    metrics.set("secret_redactions", secret_count)
    metrics.set("prompt_injection_redactions", injection_count)
    metrics.set("preparation_ms", int((time.monotonic() - started) * 1000))

    frozen_warnings = tuple(warnings)
    prompt = build_review_prompt(
        repo_name=repository.full_name,
        branch=branch,
        commit_sha=repository.commit_sha,
        description=repository.description,
        task=task.strip(),
        mode_directive=resolved_mode.directive,
        mode_name=resolved_mode.value,
        depth_name=resolved_depth.value,
        profile=profile,
        documents=tuple(documents),
        dependencies=dependencies,
        findings=ordered_findings,
        warnings=frozen_warnings,
    )
    return PreparedAnalysis(
        analysis_id=uuid.uuid4().hex[:16],
        repository=repository,
        mode=resolved_mode,
        depth=resolved_depth,
        task=task.strip(),
        profile=profile,
        documents=tuple(documents),
        dependencies=dependencies,
        findings=ordered_findings,
        prompt=prompt,
        warnings=frozen_warnings,
        metrics=metrics.freeze(),
    )


def prepare_repository(
    repo_value: str,
    branch_value: str,
    task: str,
    file_limit: int = DEFAULT_FILE_LIMIT,
    client: GitHubClient | None = None,
) -> PreparedRepository:
    """Compatibility API returning the original compact result shape."""

    prepared = prepare_analysis(
        repo_value,
        branch_value,
        task,
        mode=AnalysisMode.COMPREHENSIVE,
        depth=_depth_for_legacy_limit(int(file_limit)),
        file_limit=file_limit,
        client=client,
    )
    return PreparedRepository(
        repo_name=prepared.repository.full_name,
        repo_url=prepared.repository.html_url,
        branch=prepared.repository.branch,
        description=prepared.repository.description,
        selected_files=prepared.selected_files,
        prompt=prepared.prompt,
    )


__all__ = [
    "DEFAULT_FILE_LIMIT",
    "MAX_CONTEXT_CHARS",
    "MAX_FILE_BYTES",
    "PreparedAnalysis",
    "PreparedRepository",
    "UnsafeRequestError",
    "ensure_safe_request",
    "is_safe_path",
    "prepare_analysis",
    "prepare_repository",
    "redact_secrets",
    "select_candidate_paths",
]
