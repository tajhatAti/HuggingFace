"""Hardened read-only GitHub REST client.

Only canonical ``api.github.com`` endpoints are constructed.  Repository input
cannot select a host, redirects are rejected, and downloaded blobs are bounded.
The client never clones, executes, writes, commits, or pushes repository code.
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cache import TTLCache
from .domain import RepositoryFile


_GITHUB_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
_BRANCH_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


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


class GitHubClient:
    """Read public repository metadata, trees, and bounded text files."""

    API_ROOT = "https://api.github.com"

    def __init__(self, token: str | None = None, timeout: int = 20) -> None:
        self.timeout = max(5, min(int(timeout), 60))
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "taj-ai-code-assistant/2.0",
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
        self.session.mount("https://api.github.com/", HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8))
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
            try:
                size = max(0, int(item.get("size") or 0))
            except (TypeError, ValueError):
                size = 0
            files.append(RepositoryFile(path=path, size=size, sha=str(item.get("sha") or "")))
        snapshot = TreeSnapshot(
            commit_sha=str(data.get("sha") or ""),
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
