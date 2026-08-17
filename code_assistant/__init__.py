"""Safe production building blocks for Taj GitHub Repository Vault and AI review."""

from .domain import AnalysisMode, PreparedAnalysis, ReviewDepth, Severity
from .github_client import GitHubClient, GitHubError, RepoRef, parse_github_repo
from .repository import (
    PreparedRepository,
    UnsafeRequestError,
    prepare_analysis,
    prepare_repository,
    select_candidate_paths,
)

__all__ = [
    "AnalysisMode",
    "GitHubClient",
    "GitHubError",
    "PreparedAnalysis",
    "PreparedRepository",
    "RepoRef",
    "ReviewDepth",
    "Severity",
    "UnsafeRequestError",
    "parse_github_repo",
    "prepare_analysis",
    "prepare_repository",
    "select_candidate_paths",
]
