"""Hardened read-only GitHub REST client.

Only canonical ``api.github.com`` endpoints are constructed.  Repository input
cannot select a host, redirects are rejected, and downloaded blobs are bounded.
The client never clones, executes, writes, commits, or pushes repository code.
"""

from __future__ import annotations

import base64
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cache import TTLCache
from .domain import ChangeRecord, RepositoryFile

_GITHUB_RE = re.compile(
    r"^(?:https://github\.com/)?(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/(?P<repo>[A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$",
    re.IGNORECASE,
)
_BRANCH_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


class GitHubError(RuntimeError):
    """A localized, user-facing GitHub access error."""


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass(frozen=True)
class RepoMetadata:
    full_name: str
    default_branch: str
    description: str
    html_url: str
    private: bool
    archived: bool = False
    fork: bool = False
    stars: int = 0
    size_kb: int = 0
    language: str = ""


@dataclass(frozen=True)
class TreeSnapshot:
    commit_sha: str
    files: tuple[RepositoryFile, ...]
    truncated: bool = False


@dataclass(frozen=True)
class CompareSnapshot:
    base_sha: str
    head_sha: str
    status: str
    ahead_by: int
    behind_by: int
    total_commits: int
    files: tuple[ChangeRecord, ...]


@dataclass(frozen=True)
class BranchRecord:
    name: str
    sha: str
    protected: bool = False


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    message: str
    author: str
    date: str
    html_url: str
    verified: bool = False


@dataclass(frozen=True)
class CommitFileRecord:
    path: str
    status: str
    additions: int
    deletions: int
    changes: int
    previous_path: str = ""


@dataclass(frozen=True)
class CommitDetail:
    commit: CommitRecord
    files: tuple[CommitFileRecord, ...]
    additions: int = 0
    deletions: int = 0
    total_changes: int = 0


@dataclass(frozen=True)
class ReleaseAssetRecord:
    asset_id: int
    name: str
    size: int
    content_type: str
    download_count: int
    download_url: str
    created_at: str
    digest: str = ""


@dataclass(frozen=True)
class ReleaseRecord:
    release_id: int
    tag: str
    name: str
    body: str
    html_url: str
    published_at: str
    prerelease: bool
    assets: tuple[ReleaseAssetRecord, ...]


@dataclass(frozen=True)
class WorkflowRunRecord:
    run_id: int
    run_number: int
    name: str
    display_title: str
    event: str
    status: str
    conclusion: str
    branch: str
    head_sha: str
    created_at: str
    updated_at: str
    html_url: str


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: int
    run_id: int
    name: str
    size: int
    expired: bool
    created_at: str
    expires_at: str
    digest: str


@dataclass(frozen=True)
class RateLimitInfo:
    remaining: int | None
    limit: int | None
    reset_epoch: int | None


_PUBLIC_CACHE: TTLCache[tuple[str, ...], Any] = TTLCache(max_entries=512, ttl_seconds=600)


def parse_github_repo(value: str) -> RepoRef:
    """Parse only canonical GitHub repository identifiers.

    Restricting accepted hosts prevents repository input from becoming an SSRF
    primitive. Query strings, fragments, credentials, and extra paths fail the
    full regular-expression match.
    """

    normalized = (value or "").strip()
    match = _GITHUB_RE.fullmatch(normalized)
    if not match:
        raise GitHubError(
            "GitHub repo ঠিকভাবে দিন—যেমন `tajhatAti/Claude` অথবা "
            "`https://github.com/tajhatAti/Claude`।"
        )
    return RepoRef(owner=match.group("owner"), repo=match.group("repo"))


def validate_branch(value: str, default: str = "main") -> str:
    branch = (value or "").strip() or default
    if len(branch) > 200 or _BRANCH_CONTROL_RE.search(branch):
        raise GitHubError("Branch name invalid।")
    if branch.startswith("-") or branch.endswith(("/", ".")) or ".." in branch or "@{" in branch:
        raise GitHubError("Branch name invalid।")
    return branch


def validate_commit_sha(value: str) -> str:
    sha = (value or "").strip()
    if not _COMMIT_SHA_RE.fullmatch(sha):
        raise GitHubError("Commit SHA invalid।")
    return sha


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


class GitHubClient:
    """Read public repository metadata, trees, and bounded text files."""

    API_ROOT = "https://api.github.com"

    def __init__(self, token: str | None = None, timeout: int = 20) -> None:
        self.timeout = max(5, min(int(timeout), 60))
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "taj-github-repovault/3.0",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        resolved_token = token or os.getenv("GITHUB_TOKEN", "").strip()
        self.authenticated = bool(resolved_token)
        if resolved_token:
            self.session.headers["Authorization"] = f"Bearer {resolved_token}"

        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.35,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
        self.session.mount("https://api.github.com/", adapter)
        # Archive traffic intentionally has no Authorization header. Complete
        # snapshots come from a fixed first-party codeload host and are streamed.
        self.archive_session = requests.Session()
        self.archive_session.headers.update({"User-Agent": "taj-github-repovault/4.0"})
        self.archive_session.mount("https://codeload.github.com/", adapter)
        self.last_rate_limit = RateLimitInfo(None, None, None)

    @staticmethod
    def _integer_header(headers: requests.structures.CaseInsensitiveDict[str], name: str) -> int | None:
        try:
            value = headers.get(name)
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _json(self, url: str) -> Any:
        if not url.startswith(f"{self.API_ROOT}/"):
            raise GitHubError("Internal GitHub URL safety check failed।")
        try:
            response = self.session.get(url, timeout=(5, self.timeout), allow_redirects=False)
        except requests.Timeout as exc:
            raise GitHubError("GitHub response দিতে বেশি সময় নিচ্ছে। আবার চেষ্টা করুন।") from exc
        except requests.RequestException as exc:
            raise GitHubError("GitHub-এর সাথে সংযোগ করা যায়নি। পরে আবার চেষ্টা করুন।") from exc

        self.last_rate_limit = RateLimitInfo(
            remaining=self._integer_header(response.headers, "X-RateLimit-Remaining"),
            limit=self._integer_header(response.headers, "X-RateLimit-Limit"),
            reset_epoch=self._integer_header(response.headers, "X-RateLimit-Reset"),
        )

        if 300 <= response.status_code < 400:
            raise GitHubError("GitHub অপ্রত্যাশিত redirect দিয়েছে; নিরাপত্তার জন্য request বন্ধ করা হয়েছে।")
        if response.status_code == 404:
            raise GitHubError("Repository, branch অথবা file পাওয়া যায়নি; এটি private-ও হতে পারে।")
        if response.status_code == 401:
            raise GitHubError("Configured GitHub credential invalid অথবা expired।")
        if response.status_code in {403, 429}:
            if self.last_rate_limit.remaining == 0 or response.status_code == 429:
                raise GitHubError(
                    "GitHub API rate limit শেষ। কিছুক্ষণ পরে আবার চেষ্টা করুন; owner চাইলে read-only token configure করতে পারেন।"
                )
            raise GitHubError("GitHub এই read request অনুমোদন করেনি।")
        if response.status_code == 422:
            raise GitHubError("GitHub repository/branch request process করতে পারেনি।")
        if response.status_code >= 400:
            raise GitHubError(f"GitHub API error ({response.status_code})।")

        try:
            return response.json()
        except ValueError as exc:
            raise GitHubError("GitHub থেকে invalid response এসেছে।") from exc

    def metadata(self, repo: RepoRef) -> RepoMetadata:
        key = ("metadata", repo.owner.casefold(), repo.repo.casefold())
        cached = _PUBLIC_CACHE.get(key)
        if isinstance(cached, RepoMetadata):
            return cached

        data = self._json(f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}")
        metadata = RepoMetadata(
            full_name=str(data.get("full_name") or repo.full_name),
            default_branch=str(data.get("default_branch") or "main"),
            description=str(data.get("description") or ""),
            html_url=str(data.get("html_url") or f"https://github.com/{repo.full_name}"),
            private=bool(data.get("private", False)),
            archived=bool(data.get("archived", False)),
            fork=bool(data.get("fork", False)),
            stars=max(0, int(data.get("stargazers_count") or 0)),
            size_kb=max(0, int(data.get("size") or 0)),
            language=str(data.get("language") or ""),
        )
        # Never cache metadata for a private resource across public sessions.
        if not metadata.private:
            _PUBLIC_CACHE.set(key, metadata, ttl_seconds=600)
        return metadata

    def tree_snapshot(self, repo: RepoRef, branch: str) -> TreeSnapshot:
        branch = validate_branch(branch)
        key = ("tree", repo.owner.casefold(), repo.repo.casefold(), branch)
        cached = _PUBLIC_CACHE.get(key)
        if isinstance(cached, TreeSnapshot):
            return cached

        encoded_branch = quote(branch, safe="")
        data = self._json(
            f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/git/trees/{encoded_branch}?recursive=1"
        )
        if not isinstance(data, dict):
            raise GitHubError("GitHub tree invalid response দিয়েছে।")
        truncated = bool(data.get("truncated"))
        if truncated:
            raise GitHubError(
                "Repository tree GitHub-এর response limit ছাড়িয়েছে। ছোট branch অথবা নির্দিষ্ট sub-project ব্যবহার করুন।"
            )
        files: list[RepositoryFile] = []
        for item in data.get("tree", []):
            if not isinstance(item, dict) or item.get("type") != "blob":
                continue
            path = str(item.get("path") or "")
            blob_sha = str(item.get("sha") or "")
            if not path or not _COMMIT_SHA_RE.fullmatch(blob_sha):
                continue
            try:
                size = max(0, int(item.get("size") or 0))
            except (TypeError, ValueError):
                size = 0
            files.append(RepositoryFile(path=path, size=size, sha=blob_sha))
        resolved_sha = str(data.get("sha") or "")
        if not _COMMIT_SHA_RE.fullmatch(resolved_sha):
            raise GitHubError("GitHub tree exact commit SHA দেয়নি।")
        snapshot = TreeSnapshot(
            commit_sha=resolved_sha,
            files=tuple(files),
            truncated=False,
        )
        _PUBLIC_CACHE.set(key, snapshot, ttl_seconds=300)
        return snapshot

    def tree(self, repo: RepoRef, branch: str) -> list[dict[str, Any]]:
        """Backward-compatible tree shape used by older integrations and tests."""

        snapshot = self.tree_snapshot(repo, branch)
        return [
            {"path": item.path, "type": "blob", "size": item.size, "sha": item.sha}
            for item in snapshot.files
        ]

    def compare_refs(self, repo: RepoRef, base: str, head: str) -> CompareSnapshot:
        """Read bounded public compare metadata without downloading patch bodies."""

        base = validate_branch(base)
        head = validate_branch(head)
        key = ("compare", repo.owner.casefold(), repo.repo.casefold(), base, head)
        cached = _PUBLIC_CACHE.get(key)
        if isinstance(cached, CompareSnapshot):
            return cached

        encoded_base = quote(base, safe="")
        encoded_head = quote(head, safe="")
        data = self._json(
            f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/compare/{encoded_base}...{encoded_head}"
        )
        records: list[ChangeRecord] = []
        for item in data.get("files", [])[:300]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("filename") or "")
            if not path:
                continue
            records.append(
                ChangeRecord(
                    path=path,
                    status=str(item.get("status") or "modified"),
                    additions=max(0, int(item.get("additions") or 0)),
                    deletions=max(0, int(item.get("deletions") or 0)),
                    changes=max(0, int(item.get("changes") or 0)),
                    previous_path=str(item.get("previous_filename") or ""),
                )
            )
        base_data = data.get("base_commit") if isinstance(data.get("base_commit"), dict) else {}
        head_data = data.get("merge_base_commit") if isinstance(data.get("merge_base_commit"), dict) else {}
        commits = data.get("commits") if isinstance(data.get("commits"), list) else []
        if commits and isinstance(commits[-1], dict):
            head_sha = str(commits[-1].get("sha") or "")
        else:
            head_sha = str(head_data.get("sha") or "")
        comparison = CompareSnapshot(
            base_sha=str(base_data.get("sha") or ""),
            head_sha=head_sha,
            status=str(data.get("status") or "unknown"),
            ahead_by=max(0, int(data.get("ahead_by") or 0)),
            behind_by=max(0, int(data.get("behind_by") or 0)),
            total_commits=max(0, int(data.get("total_commits") or 0)),
            files=tuple(records),
        )
        _PUBLIC_CACHE.set(key, comparison, ttl_seconds=300)
        return comparison

    def list_branches(
        self,
        repo: RepoRef,
        *,
        limit: int = 300,
    ) -> tuple[BranchRecord, ...]:
        """List up to 300 public branches in stable API order."""

        bounded_limit = max(1, min(int(limit), 300))
        cache_key = ("branches", repo.owner.casefold(), repo.repo.casefold(), str(bounded_limit))
        cached = _PUBLIC_CACHE.get(cache_key)
        if isinstance(cached, tuple) and all(isinstance(item, BranchRecord) for item in cached):
            return cached

        records: list[BranchRecord] = []
        page = 1
        while len(records) < bounded_limit and page <= 3:
            page_size = min(100, bounded_limit - len(records))
            data = self._json(
                f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/branches?"
                f"per_page={page_size}&page={page}"
            )
            if not isinstance(data, list):
                raise GitHubError("GitHub branch list invalid response দিয়েছে।")
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "")[:200]
                commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
                sha = str(commit.get("sha") or "")
                if not name or not _COMMIT_SHA_RE.fullmatch(sha):
                    continue
                records.append(
                    BranchRecord(
                        name=name,
                        sha=sha,
                        protected=bool(item.get("protected", False)),
                    )
                )
                if len(records) >= bounded_limit:
                    break
            if len(data) < page_size:
                break
            page += 1

        result = tuple(records)
        _PUBLIC_CACHE.set(cache_key, result, ttl_seconds=300)
        return result

    def list_commits(
        self,
        repo: RepoRef,
        ref: str,
        *,
        limit: int = 40,
        path: str = "",
    ) -> tuple[CommitRecord, ...]:
        """List recent commits for a public ref, optionally filtered by one path."""

        ref = validate_branch(ref)
        bounded_limit = max(1, min(int(limit), 100))
        query: dict[str, str | int] = {"sha": ref, "per_page": bounded_limit}
        if path:
            if "\\" in path or "\x00" in path or any(part in {"", ".", ".."} for part in path.split("/")):
                raise GitHubError("Commit history file path invalid।")
            query["path"] = path
        cache_key = (
            "commits",
            repo.owner.casefold(),
            repo.repo.casefold(),
            ref,
            path,
            str(bounded_limit),
        )
        cached = _PUBLIC_CACHE.get(cache_key)
        if isinstance(cached, tuple) and all(isinstance(item, CommitRecord) for item in cached):
            return cached
        data = self._json(f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/commits?{urlencode(query)}")
        if not isinstance(data, list):
            raise GitHubError("GitHub commit list invalid response দিয়েছে।")
        records: list[CommitRecord] = []
        for item in data[:bounded_limit]:
            if not isinstance(item, dict):
                continue
            sha = str(item.get("sha") or "")
            commit_data = item.get("commit") if isinstance(item.get("commit"), dict) else {}
            author_data = commit_data.get("author") if isinstance(commit_data.get("author"), dict) else {}
            verification = (
                commit_data.get("verification") if isinstance(commit_data.get("verification"), dict) else {}
            )
            if not _COMMIT_SHA_RE.fullmatch(sha):
                continue
            records.append(
                CommitRecord(
                    sha=sha,
                    message=str(commit_data.get("message") or "")[:2_000],
                    author=str(author_data.get("name") or "Unknown")[:200],
                    date=str(author_data.get("date") or ""),
                    html_url=f"https://github.com/{repo.owner}/{repo.repo}/commit/{sha}",
                    verified=bool(verification.get("verified", False)),
                )
            )
        result = tuple(records)
        _PUBLIC_CACHE.set(cache_key, result, ttl_seconds=300)
        return result

    def commit_detail(self, repo: RepoRef, sha: str) -> CommitDetail:
        """Return one commit and its bounded changed-file metadata."""

        sha = validate_commit_sha(sha)
        cache_key = ("commit-detail", repo.owner.casefold(), repo.repo.casefold(), sha)
        cached = _PUBLIC_CACHE.get(cache_key)
        if isinstance(cached, CommitDetail):
            return cached
        data = self._json(f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/commits/{sha}")
        if not isinstance(data, dict):
            raise GitHubError("GitHub commit detail invalid response দিয়েছে।")
        commit_data = data.get("commit") if isinstance(data.get("commit"), dict) else {}
        author_data = commit_data.get("author") if isinstance(commit_data.get("author"), dict) else {}
        verification = commit_data.get("verification") if isinstance(commit_data.get("verification"), dict) else {}
        record = CommitRecord(
            sha=sha,
            message=str(commit_data.get("message") or "")[:4_000],
            author=str(author_data.get("name") or "Unknown")[:200],
            date=str(author_data.get("date") or ""),
            html_url=f"https://github.com/{repo.owner}/{repo.repo}/commit/{sha}",
            verified=bool(verification.get("verified", False)),
        )
        files: list[CommitFileRecord] = []
        for item in data.get("files", [])[:300]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("filename") or "")
            if not path:
                continue
            files.append(
                CommitFileRecord(
                    path=path,
                    status=str(item.get("status") or "modified"),
                    additions=_nonnegative_int(item.get("additions")),
                    deletions=_nonnegative_int(item.get("deletions")),
                    changes=_nonnegative_int(item.get("changes")),
                    previous_path=str(item.get("previous_filename") or ""),
                )
            )
        stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
        detail = CommitDetail(
            commit=record,
            files=tuple(files),
            additions=_nonnegative_int(stats.get("additions")),
            deletions=_nonnegative_int(stats.get("deletions")),
            total_changes=_nonnegative_int(stats.get("total")),
        )
        _PUBLIC_CACHE.set(cache_key, detail, ttl_seconds=600)
        return detail

    def list_releases(self, repo: RepoRef, *, limit: int = 20) -> tuple[ReleaseRecord, ...]:
        """List published releases and their direct public GitHub assets."""

        bounded_limit = max(1, min(int(limit), 100))
        cache_key = ("releases", repo.owner.casefold(), repo.repo.casefold(), str(bounded_limit))
        cached = _PUBLIC_CACHE.get(cache_key)
        if isinstance(cached, tuple) and all(isinstance(item, ReleaseRecord) for item in cached):
            return cached
        data = self._json(
            f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/releases?per_page={bounded_limit}"
        )
        if not isinstance(data, list):
            raise GitHubError("GitHub releases invalid response দিয়েছে।")
        releases: list[ReleaseRecord] = []
        for item in data[:bounded_limit]:
            if not isinstance(item, dict) or bool(item.get("draft", False)):
                continue
            assets: list[ReleaseAssetRecord] = []
            for asset in item.get("assets", [])[:100]:
                if not isinstance(asset, dict):
                    continue
                assets.append(
                    ReleaseAssetRecord(
                        asset_id=_nonnegative_int(asset.get("id")),
                        name=str(asset.get("name") or "asset")[:500],
                        size=_nonnegative_int(asset.get("size")),
                        content_type=str(asset.get("content_type") or "application/octet-stream")[:200],
                        download_count=_nonnegative_int(asset.get("download_count")),
                        download_url=str(asset.get("browser_download_url") or ""),
                        created_at=str(asset.get("created_at") or ""),
                        digest=str(asset.get("digest") or "")[:200],
                    )
                )
            release_id = _nonnegative_int(item.get("id"))
            tag = str(item.get("tag_name") or "")[:300]
            releases.append(
                ReleaseRecord(
                    release_id=release_id,
                    tag=tag,
                    name=str(item.get("name") or tag or f"Release {release_id}")[:500],
                    body=str(item.get("body") or "")[:8_000],
                    html_url=str(item.get("html_url") or ""),
                    published_at=str(item.get("published_at") or item.get("created_at") or ""),
                    prerelease=bool(item.get("prerelease", False)),
                    assets=tuple(assets),
                )
            )
        result = tuple(releases)
        _PUBLIC_CACHE.set(cache_key, result, ttl_seconds=300)
        return result

    def list_workflow_runs(
        self,
        repo: RepoRef,
        *,
        branch: str = "",
        limit: int = 30,
    ) -> tuple[WorkflowRunRecord, ...]:
        """List public Actions workflow runs without requesting write authority."""

        bounded_limit = max(1, min(int(limit), 100))
        query: dict[str, str | int] = {"per_page": bounded_limit}
        if branch:
            query["branch"] = validate_branch(branch)
        cache_key = (
            "workflow-runs",
            repo.owner.casefold(),
            repo.repo.casefold(),
            branch,
            str(bounded_limit),
        )
        cached = _PUBLIC_CACHE.get(cache_key)
        if isinstance(cached, tuple) and all(isinstance(item, WorkflowRunRecord) for item in cached):
            return cached
        data = self._json(
            f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/actions/runs?{urlencode(query)}"
        )
        if not isinstance(data, dict):
            raise GitHubError("GitHub workflow runs invalid response দিয়েছে।")
        runs: list[WorkflowRunRecord] = []
        for item in data.get("workflow_runs", [])[:bounded_limit]:
            if not isinstance(item, dict):
                continue
            run_id = _nonnegative_int(item.get("id"))
            if not run_id:
                continue
            runs.append(
                WorkflowRunRecord(
                    run_id=run_id,
                    run_number=_nonnegative_int(item.get("run_number")),
                    name=str(item.get("name") or "Workflow")[:300],
                    display_title=str(item.get("display_title") or item.get("name") or "Workflow run")[:500],
                    event=str(item.get("event") or "")[:100],
                    status=str(item.get("status") or "unknown")[:100],
                    conclusion=str(item.get("conclusion") or "")[:100],
                    branch=str(item.get("head_branch") or "")[:300],
                    head_sha=str(item.get("head_sha") or "")[:64],
                    created_at=str(item.get("created_at") or ""),
                    updated_at=str(item.get("updated_at") or ""),
                    html_url=f"https://github.com/{repo.owner}/{repo.repo}/actions/runs/{run_id}",
                )
            )
        result = tuple(runs)
        _PUBLIC_CACHE.set(cache_key, result, ttl_seconds=120)
        return result

    def list_run_artifacts(
        self,
        repo: RepoRef,
        run_id: int,
        *,
        limit: int = 100,
    ) -> tuple[ArtifactRecord, ...]:
        """List artifact metadata; downloads remain on GitHub's authenticated web UI."""

        resolved_run_id = int(run_id)
        if resolved_run_id <= 0:
            raise GitHubError("Workflow run ID invalid।")
        bounded_limit = max(1, min(int(limit), 100))
        cache_key = (
            "run-artifacts",
            repo.owner.casefold(),
            repo.repo.casefold(),
            str(resolved_run_id),
            str(bounded_limit),
        )
        cached = _PUBLIC_CACHE.get(cache_key)
        if isinstance(cached, tuple) and all(isinstance(item, ArtifactRecord) for item in cached):
            return cached
        data = self._json(
            f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/actions/runs/"
            f"{resolved_run_id}/artifacts?per_page={bounded_limit}"
        )
        if not isinstance(data, dict):
            raise GitHubError("GitHub Actions artifacts invalid response দিয়েছে।")
        artifacts: list[ArtifactRecord] = []
        for item in data.get("artifacts", [])[:bounded_limit]:
            if not isinstance(item, dict):
                continue
            artifact_id = _nonnegative_int(item.get("id"))
            if not artifact_id:
                continue
            workflow_run = item.get("workflow_run") if isinstance(item.get("workflow_run"), dict) else {}
            artifacts.append(
                ArtifactRecord(
                    artifact_id=artifact_id,
                    run_id=_nonnegative_int(workflow_run.get("id")) or resolved_run_id,
                    name=str(item.get("name") or f"artifact-{artifact_id}")[:500],
                    size=_nonnegative_int(item.get("size_in_bytes")),
                    expired=bool(item.get("expired", False)),
                    created_at=str(item.get("created_at") or ""),
                    expires_at=str(item.get("expires_at") or ""),
                    digest=str(item.get("digest") or "")[:200],
                )
            )
        result = tuple(artifacts)
        _PUBLIC_CACHE.set(cache_key, result, ttl_seconds=120)
        return result

    def blob_bytes(self, repo: RepoRef, blob_sha: str, max_bytes: int) -> bytes:
        """Download one exact Git blob as bytes, with a strict caller-provided ceiling."""

        blob_sha = validate_commit_sha(blob_sha)
        if max_bytes < 1 or max_bytes > 50_000_000:
            raise ValueError("max_bytes must be between 1 and 50000000")
        data = self._json(f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/git/blobs/{blob_sha}")
        if not isinstance(data, dict):
            raise GitHubError("GitHub blob invalid response দিয়েছে।")
        declared_size = _nonnegative_int(data.get("size"))
        if declared_size > max_bytes:
            raise GitHubError(f"File download limit {max_bytes:,} bytes অতিক্রম করেছে।")
        if data.get("encoding") != "base64" or data.get("content") is None:
            raise GitHubError("GitHub blob content পাওয়া যায়নি।")
        try:
            raw = base64.b64decode(str(data["content"]), validate=False)
        except (ValueError, TypeError) as exc:
            raise GitHubError("GitHub blob decode করা যায়নি।") from exc
        if len(raw) > max_bytes:
            raise GitHubError(f"File download limit {max_bytes:,} bytes অতিক্রম করেছে।")
        return raw

    def download_archive_zip(
        self,
        repo: RepoRef,
        commit_sha: str,
        destination: str | Path,
        *,
        max_bytes: int,
    ) -> int:
        """Stream one immutable public source ZIP from GitHub's fixed codeload host."""

        sha = validate_commit_sha(commit_sha)
        if max_bytes < 1 or max_bytes > 1_000_000_000:
            raise ValueError("max_bytes must be between 1 and 1000000000")
        output = Path(destination)
        part = output.with_suffix(f"{output.suffix}.part")
        url = f"https://codeload.github.com/{repo.owner}/{repo.repo}/zip/{sha}"
        written = 0
        response: requests.Response | None = None
        try:
            response = self.archive_session.get(
                url,
                timeout=(5, 120),
                allow_redirects=False,
                stream=True,
            )
            if 300 <= response.status_code < 400:
                raise GitHubError("GitHub archive unexpected redirect দিয়েছে।")
            if response.status_code == 404:
                raise GitHubError("এই repository snapshot archive পাওয়া যায়নি।")
            if response.status_code >= 400:
                raise GitHubError(f"GitHub archive error ({response.status_code})।")
            try:
                declared = int(response.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                declared = 0
            if declared > max_bytes:
                raise GitHubError(f"Complete ZIP limit {max_bytes:,} bytes অতিক্রম করেছে।")
            prefix = bytearray()
            with part.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    if written == 0:
                        prefix.extend(chunk)
                        if len(prefix) < 2:
                            continue
                        if not prefix.startswith(b"PK"):
                            raise GitHubError("GitHub archive ZIP signature invalid।")
                        chunk = bytes(prefix)
                    written += len(chunk)
                    if written > max_bytes:
                        raise GitHubError(f"Complete ZIP limit {max_bytes:,} bytes অতিক্রম করেছে।")
                    handle.write(chunk)
            if not prefix:
                raise GitHubError("GitHub archive empty response দিয়েছে।")
            if written == 0 or not zipfile.is_zipfile(part):
                raise GitHubError("GitHub archive ZIP structure invalid বা incomplete।")
            part.replace(output)
        except requests.Timeout as exc:
            raise GitHubError("GitHub archive download timeout হয়েছে।") from exc
        except requests.RequestException as exc:
            raise GitHubError("GitHub archive download করা যায়নি।") from exc
        finally:
            if response is not None:
                response.close()
            part.unlink(missing_ok=True)
        return written

    def text_file(self, repo: RepoRef, branch: str, path: str, max_bytes: int) -> str:
        """Read one bounded UTF-8-ish file through the GitHub Contents API."""

        if max_bytes < 1 or max_bytes > 100_000:
            raise ValueError("max_bytes must be between 1 and 100000")
        branch = validate_branch(branch)
        if not path or "\\" in path or "\x00" in path:
            raise GitHubError("File path invalid।")
        parts = path.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise GitHubError("File path invalid।")

        key = ("file", repo.owner.casefold(), repo.repo.casefold(), branch, path, str(max_bytes))
        cached = _PUBLIC_CACHE.get(key)
        if isinstance(cached, str):
            return cached

        safe_branch = quote(branch, safe="")
        safe_path = "/".join(quote(part, safe="") for part in parts)
        data = self._json(
            f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/contents/{safe_path}?ref={safe_branch}"
        )
        if not isinstance(data, dict) or data.get("type") != "file":
            raise GitHubError(f"`{path}` text file নয়।")
        declared_size = int(data.get("size") or 0)
        if declared_size > max_bytes * 4:
            raise GitHubError(f"`{path}` review limit-এর চেয়ে বড়।")
        if data.get("encoding") != "base64" or not data.get("content"):
            raise GitHubError(f"`{path}` content পাওয়া যায়নি।")

        try:
            raw = base64.b64decode(str(data["content"]), validate=False)
        except (ValueError, TypeError) as exc:
            raise GitHubError(f"`{path}` decode করা যায়নি।") from exc
        raw = raw[:max_bytes]
        if b"\x00" in raw:
            raise GitHubError(f"`{path}` text file নয়।")
        text = raw.decode("utf-8", errors="replace")
        _PUBLIC_CACHE.set(key, text, ttl_seconds=900)
        return text
