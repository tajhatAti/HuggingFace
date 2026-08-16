"""A small, read-only GitHub client.

The Space intentionally talks only to api.github.com/raw.githubusercontent.com.
It never clones, executes, writes to, or pushes a repository.
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


_GITHUB_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


class GitHubError(RuntimeError):
    """A user-facing GitHub access error."""


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


def parse_github_repo(value: str) -> RepoRef:
    """Parse only canonical GitHub repository identifiers.

    Restricting accepted hosts prevents the repository input from becoming an
    SSRF primitive.
    """

    normalized = (value or "").strip()
    match = _GITHUB_RE.fullmatch(normalized)
    if not match:
        raise GitHubError(
            "GitHub repo ঠিকভাবে দিন—যেমন `tajhatAti/Claude` অথবা "
            "`https://github.com/tajhatAti/Claude`।"
        )
    return RepoRef(owner=match.group("owner"), repo=match.group("repo"))


class GitHubClient:
    """Read public repository metadata, trees, and small text files."""

    API_ROOT = "https://api.github.com"
    RAW_ROOT = "https://raw.githubusercontent.com"

    def __init__(self, token: str | None = None, timeout: int = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "taj-ai-code-assistant/1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        resolved_token = token or os.getenv("GITHUB_TOKEN", "").strip()
        if resolved_token:
            self.session.headers["Authorization"] = f"Bearer {resolved_token}"

    def _json(self, url: str) -> Any:
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise GitHubError("GitHub-এর সাথে সংযোগ করা যায়নি। পরে আবার চেষ্টা করুন।") from exc

        if response.status_code == 404:
            raise GitHubError("Repository/branch পাওয়া যায়নি অথবা এটি private।")
        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                raise GitHubError("GitHub API rate limit শেষ। কিছুক্ষণ পরে আবার চেষ্টা করুন।")
            raise GitHubError("GitHub এই request অনুমোদন করেনি।")
        if response.status_code >= 400:
            raise GitHubError(f"GitHub API error ({response.status_code})।")

        try:
            return response.json()
        except ValueError as exc:
            raise GitHubError("GitHub থেকে invalid response এসেছে।") from exc

    def metadata(self, repo: RepoRef) -> RepoMetadata:
        data = self._json(f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}")
        return RepoMetadata(
            full_name=str(data.get("full_name") or repo.full_name),
            default_branch=str(data.get("default_branch") or "main"),
            description=str(data.get("description") or ""),
            html_url=str(data.get("html_url") or f"https://github.com/{repo.full_name}"),
            private=bool(data.get("private", False)),
        )

    def tree(self, repo: RepoRef, branch: str) -> list[dict[str, Any]]:
        encoded_branch = quote(branch, safe="")
        data = self._json(
            f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/git/trees/{encoded_branch}?recursive=1"
        )
        if data.get("truncated"):
            raise GitHubError("Repository tree অনেক বড়; GitHub সম্পূর্ণ file list দেয়নি।")
        return [item for item in data.get("tree", []) if item.get("type") == "blob"]

    def text_file(self, repo: RepoRef, branch: str, path: str, max_bytes: int) -> str:
        """Read a small file through the GitHub Contents API.

        Keeping all traffic on api.github.com makes the network allowlist easy
        to audit and avoids turning redirects/raw hosts into an SSRF surface.
        """

        safe_branch = quote(branch, safe="")
        safe_path = "/".join(quote(part, safe="") for part in path.split("/"))
        data = self._json(
            f"{self.API_ROOT}/repos/{repo.owner}/{repo.repo}/contents/{safe_path}?ref={safe_branch}"
        )
        if not isinstance(data, dict) or data.get("type") != "file":
            raise GitHubError(f"`{path}` text file নয়।")
        if data.get("encoding") != "base64" or not data.get("content"):
            raise GitHubError(f"`{path}` content পাওয়া যায়নি।")

        try:
            raw = base64.b64decode(str(data["content"]), validate=False)
        except (ValueError, TypeError) as exc:
            raise GitHubError(f"`{path}` decode করা যায়নি।") from exc
        raw = raw[:max_bytes]
        if b"\x00" in raw:
            raise GitHubError(f"`{path}` text file নয়।")
        return raw.decode("utf-8", errors="replace")
