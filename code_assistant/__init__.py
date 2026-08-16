"""Safe building blocks for the Taj AI Code Assistant."""

from .github_client import GitHubClient, GitHubError, RepoRef, parse_github_repo
from .repository import (
    PreparedRepository,
    UnsafeRequestError,
    prepare_repository,
    select_candidate_paths,
)

__all__ = [
    "GitHubClient",
    "GitHubError",
    "PreparedRepository",
    "RepoRef",
    "UnsafeRequestError",
    "parse_github_repo",
    "prepare_repository",
    "select_candidate_paths",
]
