"""Safe downloadable Markdown, patch, and JSON artifact generation."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from .domain import PreparedAnalysis, ReviewArtifacts
from .presentation import (
    render_architecture,
    render_dependencies,
    render_findings,
    render_repository_overview,
    render_selected_files,
)
from .security import sanitize_model_output


REPORT_ROOT = Path(os.getenv("REPORT_DIRECTORY", "/tmp/taj-ai-reports"))
REPORT_TTL_SECONDS = 2 * 60 * 60
MAX_REPORT_FILES = 120
DIFF_BLOCK_RE = re.compile(r"```diff\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
SAFE_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _ensure_report_root() -> Path:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        REPORT_ROOT.chmod(0o700)
    except OSError:
        pass
    return REPORT_ROOT


def _cleanup_old_reports() -> None:
    root = _ensure_report_root()
    now = time.time()
    files: list[Path] = []
    for path in root.iterdir():
        if not path.is_file():
            continue
        files.append(path)
        try:
            if now - path.stat().st_mtime > REPORT_TTL_SECONDS:
                path.unlink(missing_ok=True)
        except OSError:
            continue
    remaining = sorted(
        (path for path in files if path.exists()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in remaining[MAX_REPORT_FILES:]:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _safe_slug(value: str, limit: int = 70) -> str:
    slug = SAFE_SLUG_RE.sub("-", value).strip("-._").casefold()
    return (slug or "repository")[:limit]


def _atomic_write(path: Path, content: str) -> None:
    root = _ensure_report_root()
    fd, temporary_name = tempfile.mkstemp(prefix=".writing-", dir=root, text=True)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def extract_unified_diff(review: str) -> str:
    """Extract only plausible unified-diff fences from a sanitized model report."""

    blocks: list[str] = []
    for raw_block in DIFF_BLOCK_RE.findall(review or ""):
        block = sanitize_model_output(raw_block, max_chars=80_000).strip()
        lines = block.splitlines()
        has_old = any(line.startswith("--- ") for line in lines)
        has_new = any(line.startswith("+++ ") for line in lines)
        has_hunk = any(line.startswith("@@") for line in lines)
        if not (has_old and has_new and has_hunk):
            continue
        # Strip control characters and cap pathological model output while preserving diff syntax.
        blocks.append("\n".join(lines[:4_000]).rstrip())
        if sum(len(value) for value in blocks) >= 120_000:
            break
    return "\n\n".join(blocks).strip()


def _report_markdown(prepared: PreparedAnalysis, review: str) -> str:
    sha = prepared.repository.commit_sha or "unknown"
    generated = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    safe_review = sanitize_model_output(review)
    return f"""# Taj AI Code Assistant Pro — Review report

- **Generated:** {generated}
- **Repository:** [{prepared.repository.full_name}]({prepared.repository.html_url})
- **Branch:** `{prepared.repository.branch}`
- **Commit:** `{sha}`
- **Mode:** {prepared.mode.value}
- **Depth:** {prepared.depth.value}
- **Analysis ID:** `{prepared.analysis_id}`
- **Safety:** read-only static inspection; repository code was not executed

## User request

{prepared.task}

---

{render_repository_overview(prepared)}

---

{render_selected_files(prepared)}

---

{render_findings(prepared.findings)}

---

{render_architecture(prepared)}

---

{render_dependencies(prepared)}

---

# AI review

{safe_review or '_No AI review was produced._'}

---

## Verification notice

The deterministic scanner uses bounded heuristics and the language model reviewed only the selected, sanitized text.
No dependency was installed, no test was executed, and no live vulnerability database was queried. A maintainer must
review the patch and run the validation plan in an isolated development environment before merging.
"""


def _report_json(prepared: PreparedAnalysis, review: str, patch_available: bool) -> str:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "analysis_id": prepared.analysis_id,
        "repository": {
            "full_name": prepared.repository.full_name,
            "url": prepared.repository.html_url,
            "branch": prepared.repository.branch,
            "commit_sha": prepared.repository.commit_sha,
            "archived": prepared.repository.archived,
            "fork": prepared.repository.fork,
        },
        "configuration": {"mode": prepared.mode.value, "depth": prepared.depth.value},
        "task": prepared.task,
        "profile": {
            "total_files": prepared.profile.total_files,
            "supported_files": prepared.profile.supported_files,
            "languages": list(prepared.profile.languages),
            "frameworks": list(prepared.profile.frameworks),
            "package_managers": list(prepared.profile.package_managers),
            "entrypoints": list(prepared.profile.entrypoints),
            "test_files": prepared.profile.test_files,
            "documentation_files": prepared.profile.documentation_files,
            "ci_files": list(prepared.profile.ci_files),
        },
        "selected_files": [
            {
                "path": document.path,
                "language": document.language,
                "tree_size": document.size,
                "score": document.score,
                "reasons": list(document.reasons),
                "truncated": document.truncated,
                "symbols": [
                    {
                        "name": symbol.name,
                        "kind": symbol.kind,
                        "line": symbol.line,
                        "signature": symbol.signature,
                    }
                    for symbol in document.symbols
                ],
            }
            for document in prepared.documents
        ],
        "dependencies": [
            {
                "name": dependency.name,
                "specification": dependency.specification,
                "source": dependency.source,
                "group": dependency.group,
                "pinned": dependency.pinned,
            }
            for dependency in prepared.dependencies
        ],
        "findings": [
            {
                "rule_id": finding.rule_id,
                "severity": finding.severity.value,
                "category": finding.category,
                "title": finding.title,
                "path": finding.path,
                "line": finding.line,
                "evidence": finding.evidence,
                "recommendation": finding.recommendation,
                "confidence": finding.confidence,
            }
            for finding in prepared.findings
        ],
        "warnings": list(prepared.warnings),
        "metrics": dict(prepared.metrics),
        "ai_review": sanitize_model_output(review),
        "patch_available": patch_available,
        # Source contents and the full model prompt are deliberately excluded.
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_review_artifacts(prepared: PreparedAnalysis | None, review: str) -> ReviewArtifacts:
    if prepared is None or not review:
        return ReviewArtifacts()
    _cleanup_old_reports()
    root = _ensure_report_root()
    slug = _safe_slug(prepared.repository.full_name.replace("/", "-"))
    suffix = f"{prepared.analysis_id}-{uuid.uuid4().hex[:8]}"
    markdown_path = root / f"{slug}-{suffix}.md"
    json_path = root / f"{slug}-{suffix}.json"
    patch_path = root / f"{slug}-{suffix}.patch"

    safe_review = sanitize_model_output(review)
    patch = extract_unified_diff(safe_review)
    _atomic_write(markdown_path, _report_markdown(prepared, safe_review))
    _atomic_write(json_path, _report_json(prepared, safe_review, bool(patch)))
    if patch:
        _atomic_write(
            patch_path,
            f"# Review before applying. Generated for {prepared.repository.full_name}@"
            f"{prepared.repository.commit_sha or prepared.repository.branch}\n\n{patch}\n",
        )
        patch_value: str | None = str(patch_path)
    else:
        patch_value = None
    return ReviewArtifacts(
        markdown_path=str(markdown_path),
        patch_path=patch_value,
        json_path=str(json_path),
    )
