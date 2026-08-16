from __future__ import annotations

import base64
import unittest
from unittest.mock import Mock

import requests

from code_assistant.github_client import (
    GitHubClient,
    GitHubError,
    RepoRef,
    parse_github_repo,
    validate_branch,
)


def response(status: int, payload=None, headers=None):
    result = Mock(spec=requests.Response)
    result.status_code = status
    result.headers = requests.structures.CaseInsensitiveDict(headers or {})
    result.json.return_value = payload
    return result


class RepositoryParsingExtendedTests(unittest.TestCase):
    def test_rejects_query_fragment_credentials_and_non_https_variants(self):
        invalid = (
            "owner/repo?tab=readme",
            "owner/repo#fragment",
            "https://user@github.com/owner/repo",
            "git://github.com/owner/repo",
            "https://github.com.evil.test/owner/repo",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(GitHubError):
                parse_github_repo(value)

    def test_validates_branch(self):
        self.assertEqual(validate_branch("", "develop"), "develop")
        self.assertEqual(validate_branch("feature/safe"), "feature/safe")
        for branch in ("-bad", "bad/", "bad..name", "bad@{name", "bad\nname"):
            with self.subTest(branch=branch), self.assertRaises(GitHubError):
                validate_branch(branch)


class GitHubClientRequestTests(unittest.TestCase):
    def setUp(self):
        self.client = GitHubClient(timeout=5)

    def test_metadata_maps_production_fields_and_rate_limit(self):
        self.client.session.get = Mock(
            return_value=response(
                200,
                {
                    "full_name": "unique-owner/unique-repo",
                    "default_branch": "develop",
                    "description": "Example",
                    "html_url": "https://github.com/unique-owner/unique-repo",
                    "private": False,
                    "archived": True,
                    "fork": True,
                    "stargazers_count": 12,
                    "size": 400,
                    "language": "Python",
                },
                {"X-RateLimit-Remaining": "49", "X-RateLimit-Limit": "60"},
            )
        )
        metadata = self.client.metadata(RepoRef("unique-owner", "unique-repo"))
        self.assertEqual(metadata.default_branch, "develop")
        self.assertTrue(metadata.archived)
        self.assertTrue(metadata.fork)
        self.assertEqual(metadata.stars, 12)
        self.assertEqual(self.client.last_rate_limit.remaining, 49)
        _, kwargs = self.client.session.get.call_args
        self.assertFalse(kwargs["allow_redirects"])

    def test_tree_snapshot_keeps_only_blobs(self):
        self.client.session.get = Mock(
            return_value=response(
                200,
                {
                    "sha": "abc123",
                    "truncated": False,
                    "tree": [
                        {"path": "src", "type": "tree", "sha": "tree"},
                        {"path": "src/app.py", "type": "blob", "size": 42, "sha": "blob"},
                    ],
                },
            )
        )
        snapshot = self.client.tree_snapshot(RepoRef("tree-owner", "tree-repo"), "main")
        self.assertEqual(snapshot.commit_sha, "abc123")
        self.assertEqual(len(snapshot.files), 1)
        self.assertEqual(snapshot.files[0].path, "src/app.py")

    def test_rejects_truncated_tree(self):
        self.client.session.get = Mock(return_value=response(200, {"sha": "x", "truncated": True, "tree": []}))
        with self.assertRaises(GitHubError):
            self.client.tree_snapshot(RepoRef("truncated-owner", "repo"), "main")

    def test_compare_refs_maps_changed_file_metadata(self):
        self.client.session.get = Mock(
            return_value=response(
                200,
                {
                    "status": "ahead",
                    "ahead_by": 2,
                    "behind_by": 0,
                    "total_commits": 2,
                    "base_commit": {"sha": "base123"},
                    "commits": [{"sha": "first"}, {"sha": "head456"}],
                    "files": [
                        {
                            "filename": "src/auth.py",
                            "status": "modified",
                            "additions": 8,
                            "deletions": 3,
                            "changes": 11,
                        }
                    ],
                },
            )
        )
        comparison = self.client.compare_refs(RepoRef("compare-owner", "repo"), "main", "feature/auth")
        self.assertEqual(comparison.base_sha, "base123")
        self.assertEqual(comparison.head_sha, "head456")
        self.assertEqual(comparison.total_commits, 2)
        self.assertEqual(comparison.files[0].path, "src/auth.py")
        self.assertEqual(comparison.files[0].additions, 8)

    def test_decodes_and_bounds_contents_api_file(self):
        encoded = base64.b64encode(b"hello world").decode()
        self.client.session.get = Mock(
            return_value=response(200, {"type": "file", "encoding": "base64", "content": encoded, "size": 11})
        )
        text = self.client.text_file(RepoRef("file-owner", "repo"), "main", "src/app.py", 5)
        self.assertEqual(text, "hello")

    def test_rejects_redirect_and_rate_limit(self):
        self.client.session.get = Mock(return_value=response(302, {}))
        with self.assertRaises(GitHubError):
            self.client.metadata(RepoRef("redirect-owner", "repo"))
        self.client.session.get = Mock(
            return_value=response(403, {}, {"X-RateLimit-Remaining": "0", "X-RateLimit-Limit": "60"})
        )
        with self.assertRaisesRegex(GitHubError, "rate limit"):
            self.client.metadata(RepoRef("rate-owner", "repo"))

    def test_rejects_binary_and_traversal_content_paths(self):
        encoded = base64.b64encode(b"a\x00b").decode()
        self.client.session.get = Mock(
            return_value=response(200, {"type": "file", "encoding": "base64", "content": encoded, "size": 3})
        )
        with self.assertRaises(GitHubError):
            self.client.text_file(RepoRef("binary-owner", "repo"), "main", "asset.txt", 100)
        with self.assertRaises(GitHubError):
            self.client.text_file(RepoRef("binary-owner", "repo"), "main", "../secret.txt", 100)


if __name__ == "__main__":
    unittest.main()
