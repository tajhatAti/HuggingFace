"""Read-only GitHub repository explorer, snapshot browser, and bounded downloads.

RepoVault intentionally handles public GitHub data only. It never clones a
repository, executes its content, accepts visitor credentials, or proxies an
arbitrary host. Full archives and Actions artifact downloads stay on GitHub;
selected-file bundles are assembled from exact Git blob IDs with hard limits.
"""

from __future__ import annotations

import mimetypes
import os
import re
import time
import uuid
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlparse

from .domain import RepositoryFile
from .github_client import (
    ArtifactRecord,
    CommitDetail,
    CommitRecord,
    GitHubClient,
    GitHubError,
    ReleaseRecord,
    RepoMetadata,
    RepoRef,
    TreeSnapshot,
    WorkflowRunRecord,
    parse_github_repo,
    validate_branch,
    validate_commit_sha,
)
from .inspection import detect_language

MAX_VAULT_TREE_FILES = 20_000
MAX_VISIBLE_FILES = 1_000
MAX_SELECTED_FILES = 20
MAX_SINGLE_DOWNLOAD_BYTES = 25_000_000
MAX_SELECTED_ZIP_BYTES = 50_000_000
MAX_PREVIEW_BYTES = 300_000
VAULT_ROOT = Path(os.getenv("VAULT_DIRECTORY", "/tmp/taj-repovault"))
VAULT_TTL_SECONDS = 2 * 60 * 60
MAX_VAULT_OUTPUTS = 120

SENSITIVE_NAMES = {
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials.json",
    "service-account.json",
    "secrets.json",
    "master.key",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class VaultSession:
    repo: RepoRef
    metadata: RepoMetadata
    requested_ref: str
    snapshot: TreeSnapshot
    commits: tuple[CommitRecord, ...]
    releases: tuple[ReleaseRecord, ...]
    workflow_runs: tuple[WorkflowRunRecord, ...]
    warnings: tuple[str, ...] = ()

    @property
    def exact_ref(self) -> str:
        return self.snapshot.commit_sha or self.requested_ref

    @property
    def files(self) -> tuple[RepositoryFile, ...]:
        return self.snapshot.files

    def file_map(self) -> dict[str, RepositoryFile]:
        return {item.path: item for item in self.files}


@dataclass(frozen=True)
class FilePreview:
    path: str
    markdown: str
    content: str
    download_path: str | None
    raw_url: str


def format_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _markdown_text(value: str, limit: int = 500) -> str:
    clean = " ".join((value or "").replace("\x00", "").split())[:limit]
    for character in ("\\", "`", "*", "_", "[", "]", "<", ">", "|"):
        clean = clean.replace(character, f"\\{character}")
    return clean


def _safe_temp_name(path: str, prefix: str = "file") -> str:
    basename = PurePosixPath(path).name or prefix
    safe = SAFE_FILENAME_RE.sub("-", basename).strip("-._") or prefix
    stem = safe[:120]
    return f"{uuid.uuid4().hex[:12]}-{stem}"


def _ensure_root() -> Path:
    VAULT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        VAULT_ROOT.chmod(0o700)
    except OSError:
        pass
    return VAULT_ROOT


def _cleanup_outputs() -> None:
    root = _ensure_root()
    now = time.time()
    files: list[Path] = []
    for item in root.iterdir():
        if not item.is_file():
            continue
        files.append(item)
        try:
            if now - item.stat().st_mtime > VAULT_TTL_SECONDS:
                item.unlink(missing_ok=True)
        except OSError:
            continue
    remaining = sorted((item for item in files if item.exists()), key=lambda item: item.stat().st_mtime, reverse=True)
    for item in remaining[MAX_VAULT_OUTPUTS:]:
        try:
            item.unlink(missing_ok=True)
        except OSError:
            pass


def _valid_archive_path(path: str) -> bool:
    if not path or "\x00" in path or "\\" in path:
        return False
    pure = PurePosixPath(path)
    return not pure.is_absolute() and all(part not in {"", ".", ".."} for part in pure.parts)


def is_sensitive_download_path(path: str) -> bool:
    pure = PurePosixPath(path)
    name = pure.name.casefold()
    return (
        name in SENSITIVE_NAMES
        or name.startswith(".env")
        or name.endswith(SENSITIVE_SUFFIXES)
        or any(part.casefold() == ".git" for part in pure.parts)
    )


def _raw_url(session: VaultSession, path: str) -> str:
    encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
    return (
        f"https://raw.githubusercontent.com/{session.repo.owner}/{session.repo.repo}/"
        f"{quote(session.exact_ref, safe='')}/{encoded_path}"
    )


def archive_urls(session: VaultSession) -> tuple[str, str]:
    """Return immutable commit archive URLs hosted directly by GitHub."""

    exact = quote(session.exact_ref, safe="")
    base = f"https://github.com/{session.repo.owner}/{session.repo.repo}/archive/{exact}"
    return f"{base}.zip", f"{base}.tar.gz"


def archive_links_markdown(session: VaultSession) -> str:
    zip_url, tar_url = archive_urls(session)
    return f"""## Download complete snapshot

The archive is generated and served directly by GitHub for immutable commit `{session.exact_ref[:12]}`.

- [⬇️ Download all files as ZIP]({zip_url})
- [⬇️ Download all files as TAR.GZ]({tar_url})
- [🔗 Open repository tree](https://github.com/{session.repo.owner}/{session.repo.repo}/tree/{session.exact_ref})

> Full archives may include sensitive files already committed to the public repository. RepoVault does not copy or inspect the archive.
"""


def load_vault(
    repo_value: str,
    ref_value: str = "",
    *,
    client: GitHubClient | None = None,
) -> VaultSession:
    client = client or GitHubClient()
    repo = parse_github_repo(repo_value)
    metadata = client.metadata(repo)
    if metadata.private:
        raise ValueError("এই public RepoVault private repository পড়ে না।")
    ref = validate_branch(ref_value, metadata.default_branch)
    snapshot = client.tree_snapshot(repo, ref)
    if len(snapshot.files) > MAX_VAULT_TREE_FILES:
        raise ValueError(
            f"Repository-তে {len(snapshot.files):,} files আছে; public explorer limit {MAX_VAULT_TREE_FILES:,}।"
        )

    warnings: list[str] = []
    try:
        commits = client.list_commits(repo, ref, limit=50)
    except GitHubError as exc:
        commits = ()
        warnings.append(f"Commit history unavailable: {exc}")
    try:
        releases = client.list_releases(repo, limit=20)
    except GitHubError as exc:
        releases = ()
        warnings.append(f"Releases unavailable: {exc}")
    try:
        workflow_runs = client.list_workflow_runs(repo, branch="", limit=40)
    except GitHubError as exc:
        workflow_runs = ()
        warnings.append(f"Actions runs unavailable: {exc}")

    return VaultSession(
        repo=repo,
        metadata=metadata,
        requested_ref=ref,
        snapshot=snapshot,
        commits=commits,
        releases=releases,
        workflow_runs=workflow_runs,
        warnings=tuple(warnings),
    )


def load_commit_snapshot(
    session: VaultSession,
    commit_sha: str,
    *,
    client: GitHubClient | None = None,
) -> VaultSession:
    sha = validate_commit_sha(commit_sha)
    client = client or GitHubClient()
    snapshot = client.tree_snapshot(session.repo, sha)
    if len(snapshot.files) > MAX_VAULT_TREE_FILES:
        raise ValueError("Commit snapshot public explorer limit অতিক্রম করেছে।")
    return replace(session, requested_ref=sha, snapshot=snapshot)


def matching_file_paths(session: VaultSession, query: str = "") -> list[str]:
    """Search the entire bounded tree and return stable path ordering."""

    raw_query = (query or "").strip()
    if len(raw_query) > 500:
        raise ValueError("File search সর্বোচ্চ 500 characters হতে পারে।")
    normalized = raw_query.casefold()
    terms = [term for term in normalized.split() if term][:20]
    paths = [
        item.path
        for item in session.files
        if not terms or all(term in item.path.casefold() for term in terms)
    ]
    paths.sort(key=lambda path: (len(PurePosixPath(path).parts), path.casefold()))
    return paths


def filter_files(session: VaultSession, query: str = "", limit: int = MAX_VISIBLE_FILES) -> list[str]:
    """Return bounded dropdown choices while searching the complete tree."""

    return matching_file_paths(session, query)[: max(1, min(int(limit), MAX_VISIBLE_FILES))]


def files_table(
    session: VaultSession,
    query: str = "",
    *,
    page: int = 1,
    page_size: int = 500,
) -> list[list[str | int]]:
    file_map = session.file_map()
    paths = matching_file_paths(session, query)
    bounded_page_size = max(1, min(int(page_size), 500))
    bounded_page = min(MAX_VAULT_TREE_FILES, max(1, int(page)))
    start = (bounded_page - 1) * bounded_page_size
    rows: list[list[str | int]] = []
    for path in paths[start : start + bounded_page_size]:
        item = file_map[path]
        rows.append(
            [
                path,
                detect_language(path),
                format_bytes(item.size),
                item.sha[:12],
                "blocked" if is_sensitive_download_path(path) else "ready",
            ]
        )
    return rows


def file_page_status(session: VaultSession, query: str = "", page: int = 1, page_size: int = 500) -> str:
    matches = len(matching_file_paths(session, query))
    bounded_page_size = max(1, min(int(page_size), 500))
    bounded_page = min(MAX_VAULT_TREE_FILES, max(1, int(page)))
    start = (bounded_page - 1) * bounded_page_size
    if not matches or start >= matches:
        return f"No files on page {bounded_page}; {matches:,} total matches."
    end = min(start + bounded_page_size, matches)
    total_pages = (matches + bounded_page_size - 1) // bounded_page_size
    return f"Showing {start + 1:,}–{end:,} of {matches:,} matching files · page {bounded_page}/{total_pages}"


def repository_dashboard(session: VaultSession) -> str:
    total_size = sum(max(0, item.size) for item in session.files)
    release_assets = sum(len(release.assets) for release in session.releases)
    short_sha = session.exact_ref[:12]
    warning_text = "\n".join(f"- ⚠️ {_markdown_text(item)}" for item in session.warnings)
    warnings = f"\n\n### Partial data warnings\n{warning_text}" if warning_text else ""
    return f"""## {_markdown_text(session.metadata.full_name)}

{_markdown_text(session.metadata.description or 'No repository description')}

| Snapshot | Files | Source size | History | Releases | Assets | Actions runs |
|---|---:|---:|---:|---:|---:|---:|
| `{_markdown_text(session.requested_ref)}` @ `{short_sha}` | {len(session.files):,} | {format_bytes(total_size)} | {len(session.commits)} | {len(session.releases)} | {release_assets} | {len(session.workflow_runs)} |

[Open on GitHub](https://github.com/{session.repo.owner}/{session.repo.repo}) · ⭐ {session.metadata.stars:,} · {('Archived repository' if session.metadata.archived else 'Active repository')}

**Mode:** public · immutable snapshot · read-only · no clone · no execution{warnings}
"""


def commit_choices(session: VaultSession) -> list[tuple[str, str]]:
    return [
        (
            (
                f"{item.sha[:8]} · {item.date[:10] or 'unknown date'} · "
                f"{item.message.splitlines()[0][:72] or 'No message'}"
            ),
            item.sha,
        )
        for item in session.commits
    ]


def workflow_choices(session: VaultSession) -> list[tuple[str, str]]:
    return [
        (
            f"#{item.run_number} · {item.name} · {item.conclusion or item.status} · {item.created_at[:16]}",
            str(item.run_id),
        )
        for item in session.workflow_runs
    ]


def commits_table(session: VaultSession) -> list[list[str]]:
    return [
        [
            item.sha[:12],
            item.date.replace("T", " ").replace("Z", " UTC")[:24],
            item.author,
            item.message.splitlines()[0][:180],
            "verified" if item.verified else "unverified",
        ]
        for item in session.commits
    ]


def render_commit_detail(detail: CommitDetail, session: VaultSession) -> str:
    lines = [
        f"## Commit `{detail.commit.sha[:12]}`",
        "",
        f"**{_markdown_text(detail.commit.message.splitlines()[0] or 'No message')}**",
        "",
        (
            f"Author: {_markdown_text(detail.commit.author)} · {detail.commit.date or 'unknown date'} · "
            f"{'✅ verified signature' if detail.commit.verified else 'signature not verified'}"
        ),
        "",
        (
            f"[Open commit on GitHub]({detail.commit.html_url}) · "
            f"[Download this commit ZIP](https://github.com/{session.repo.owner}/{session.repo.repo}/archive/"
            f"{detail.commit.sha}.zip)"
        ),
        "",
        f"**{len(detail.files)} changed files** · +{detail.additions:,} / -{detail.deletions:,} · {detail.total_changes:,} total",
        "",
        "| Status | File | Delta |",
        "|---|---|---:|",
    ]
    for item in detail.files[:150]:
        rename = f" ← `{_markdown_text(item.previous_path)}`" if item.previous_path else ""
        lines.append(
            f"| {_markdown_text(item.status)} | `{_markdown_text(item.path)}`{rename} | "
            f"+{item.additions}/-{item.deletions} |"
        )
    if len(detail.files) > 150:
        lines.append(f"\n_{len(detail.files) - 150} additional files omitted._")
    return "\n".join(lines)


def _trusted_release_url(session: VaultSession, value: str) -> str | None:
    parsed = urlparse(value)
    expected_prefix = f"/{session.repo.owner}/{session.repo.repo}/releases/download/".casefold()
    if parsed.scheme == "https" and parsed.netloc.casefold() == "github.com" and parsed.path.casefold().startswith(
        expected_prefix
    ):
        return value
    return None


def render_releases(session: VaultSession) -> str:
    if not session.releases:
        return "## Releases & attached files\n\n_No published GitHub releases were found._"
    lines = [
        "## Releases & attached files",
        "",
        "APK, AAB, ZIP and other assets below are served directly by GitHub—not proxied through this Space.",
    ]
    for release in session.releases:
        badge = "prerelease" if release.prerelease else "release"
        encoded_tag = quote(release.tag, safe="")
        lines.extend(
            (
                "",
                f"### {_markdown_text(release.name)} · `{_markdown_text(release.tag)}` · {badge}",
                (
                    f"Published: {release.published_at or 'unknown'} · "
                    f"[release notes](https://github.com/{session.repo.owner}/{session.repo.repo}/releases/tag/"
                    f"{encoded_tag}) · "
                    f"[source ZIP](https://github.com/{session.repo.owner}/{session.repo.repo}/archive/refs/tags/"
                    f"{encoded_tag}.zip) · "
                    f"[source TAR.GZ](https://github.com/{session.repo.owner}/{session.repo.repo}/archive/refs/tags/"
                    f"{encoded_tag}.tar.gz)"
                ),
            )
        )
        if not release.assets:
            lines.append("- No attached assets")
            continue
        for asset in release.assets:
            url = _trusted_release_url(session, asset.download_url)
            name = _markdown_text(asset.name)
            suffix = PurePosixPath(asset.name).suffix.casefold()
            icon = "📱" if suffix in {".apk", ".aab"} else "🗜️" if suffix in {".zip", ".gz", ".tar"} else "📦"
            if url:
                lines.append(
                    f"- {icon} [{name}]({url}) · {format_bytes(asset.size)} · "
                    f"{asset.download_count:,} downloads · `{_markdown_text(asset.content_type)}`"
                )
            else:
                lines.append(f"- {icon} {name} · download URL rejected by host validation")
    return "\n".join(lines)


def render_actions(session: VaultSession) -> str:
    if not session.workflow_runs:
        return "## GitHub Actions runs\n\n_No public workflow runs were found or Actions is unavailable._"
    lines = [
        "## GitHub Actions runs",
        "",
        "Select a run below to list its retained artifacts. GitHub may require you to sign in before downloading.",
        "",
        "| Run | Workflow | Result | Branch | Event | Created |",
        "|---:|---|---|---|---|---|",
    ]
    for item in session.workflow_runs[:40]:
        result = item.conclusion or item.status
        icon = "✅" if result == "success" else "❌" if result == "failure" else "⏳"
        lines.append(
            f"| [#{item.run_number}]({item.html_url}) | {_markdown_text(item.name)} | {icon} {_markdown_text(result)} | "
            f"`{_markdown_text(item.branch)}` | {_markdown_text(item.event)} | {item.created_at[:16]} |"
        )
    return "\n".join(lines)


def render_artifacts(session: VaultSession, artifacts: tuple[ArtifactRecord, ...], run_id: int) -> str:
    run_url = f"https://github.com/{session.repo.owner}/{session.repo.repo}/actions/runs/{run_id}"
    if not artifacts:
        return f"## Run artifacts\n\n_No retained artifacts found._ [Open run on GitHub]({run_url})"
    lines = [
        f"## Artifacts for run `{run_id}`",
        "",
        (
            "Actions artifacts are ZIP archives. GitHub requires Actions-read authentication for the actual download; "
            "RepoVault never asks for or exposes your token."
        ),
        "",
    ]
    for item in artifacts:
        web_url = f"{run_url}/artifacts/{item.artifact_id}"
        status = "expired" if item.expired else f"expires {item.expires_at or 'per GitHub retention'}"
        lines.append(
            f"- {'⌛' if item.expired else '🧰'} [{_markdown_text(item.name)}.zip]({web_url}) · "
            f"{format_bytes(item.size)} · {status}"
        )
    lines.append(f"\n[Open complete workflow run]({run_url})")
    return "\n".join(lines)


def inspect_file(
    session: VaultSession,
    path: str,
    *,
    client: GitHubClient | None = None,
) -> FilePreview:
    if not path or path not in session.file_map():
        raise ValueError("একটি valid repository file select করুন।")
    item = session.file_map()[path]
    raw_url = _raw_url(session, path)
    if is_sensitive_download_path(path):
        return FilePreview(
            path=path,
            markdown=(
                f"## `{_markdown_text(path)}`\n\n"
                "🔒 RepoVault potential credential/key file proxy বা preview করে না। "
                f"[GitHub-এ file দেখুন](https://github.com/{session.repo.owner}/{session.repo.repo}/blob/"
                f"{session.exact_ref}/{quote(path, safe='/')})."
            ),
            content="",
            download_path=None,
            raw_url=raw_url,
        )
    if item.size > MAX_SINGLE_DOWNLOAD_BYTES:
        return FilePreview(
            path=path,
            markdown=(
                f"## `{_markdown_text(path)}`\n\nSize: **{format_bytes(item.size)}** · RepoVault proxy limit "
                f"{format_bytes(MAX_SINGLE_DOWNLOAD_BYTES)}। [Open raw file on GitHub]({raw_url})"
            ),
            content="",
            download_path=None,
            raw_url=raw_url,
        )

    client = client or GitHubClient()
    raw = client.blob_bytes(session.repo, item.sha, MAX_SINGLE_DOWNLOAD_BYTES)
    _cleanup_outputs()
    destination = _ensure_root() / _safe_temp_name(path)
    destination.write_bytes(raw)
    try:
        destination.chmod(0o600)
    except OSError:
        pass

    sample = raw[:MAX_PREVIEW_BYTES]
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    language = detect_language(path)
    binary = b"\x00" in sample
    if not binary:
        decoded = sample.decode("utf-8", errors="replace")
        replacement_ratio = decoded.count("�") / max(len(decoded), 1)
        binary = replacement_ratio > 0.03
    if binary:
        content = ""
        preview_note = "Binary file—text preview disabled."
    else:
        content = decoded
        preview_note = (
            f"Showing first {format_bytes(len(sample))}." if len(raw) > len(sample) else "Complete text preview."
        )
    markdown = f"""## `{_markdown_text(path)}`

**{format_bytes(len(raw))}** · `{_markdown_text(mime)}` · {language} · blob `{item.sha[:12]}`

{preview_note} [Open immutable raw file on GitHub]({raw_url})
"""
    return FilePreview(path, markdown, content, str(destination), raw_url)


def build_selected_zip(
    session: VaultSession,
    selected_paths: list[str] | tuple[str, ...] | str | None,
    *,
    client: GitHubClient | None = None,
) -> tuple[str, str]:
    if isinstance(selected_paths, str):
        paths = [selected_paths] if selected_paths else []
    else:
        paths = list(selected_paths or [])
    paths = list(dict.fromkeys(paths))
    if not paths:
        raise ValueError("ZIP বানানোর জন্য অন্তত একটি file select করুন।")
    if len(paths) > MAX_SELECTED_FILES:
        raise ValueError(f"একবারে সর্বোচ্চ {MAX_SELECTED_FILES}টি selected file ZIP করা যাবে।")

    file_map = session.file_map()
    selected: list[RepositoryFile] = []
    for path in paths:
        item = file_map.get(path)
        if item is None or not _valid_archive_path(path):
            raise ValueError(f"Invalid selected path: {path}")
        if is_sensitive_download_path(path):
            raise ValueError(f"Potential credential/key file selected ZIP-এ দেওয়া হবে না: {path}")
        if item.size > MAX_SINGLE_DOWNLOAD_BYTES:
            raise ValueError(f"Selected file per-file limit অতিক্রম করেছে: {path}")
        selected.append(item)
    declared_total = sum(item.size for item in selected)
    if declared_total > MAX_SELECTED_ZIP_BYTES:
        raise ValueError(
            f"Selected files {format_bytes(declared_total)}; ZIP limit {format_bytes(MAX_SELECTED_ZIP_BYTES)}।"
        )

    client = client or GitHubClient()
    _cleanup_outputs()
    archive_name = (
        f"{SAFE_FILENAME_RE.sub('-', session.repo.full_name).strip('-') or 'repository'}-"
        f"{session.exact_ref[:12]}-selected-{uuid.uuid4().hex[:8]}.zip"
    )
    destination = _ensure_root() / archive_name
    written = 0
    try:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for item in selected:
                remaining = MAX_SELECTED_ZIP_BYTES - written
                raw = client.blob_bytes(session.repo, item.sha, min(MAX_SINGLE_DOWNLOAD_BYTES, remaining + 1))
                written += len(raw)
                if written > MAX_SELECTED_ZIP_BYTES:
                    raise ValueError("Downloaded files selected ZIP limit অতিক্রম করেছে।")
                archive.writestr(item.path, raw)
            manifest = (
                "Taj RepoVault selected-file archive\n"
                f"Repository: {session.repo.full_name}\n"
                f"Commit: {session.exact_ref}\n"
                f"Files: {len(selected)}\n"
                "Source files were fetched read-only from exact public Git blob IDs.\n"
            )
            archive.writestr("REPOVAULT-MANIFEST.txt", manifest)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    try:
        destination.chmod(0o600)
    except OSError:
        pass
    return str(destination), f"✅ {len(selected)} files · {format_bytes(written)} · commit `{session.exact_ref[:12]}`"
