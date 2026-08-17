from __future__ import annotations

import base64
import unittest
from unittest.mock import Mock

import requests

from code_assistant.github_client import (
    GitHubClient,
    GitHubError,
    RepoRef,
    validate_commit_sha,
)


def response(status: int, payload=None, headers=None):
    result = Mock(spec=requests.Response)
    result.status_code = status
    result.headers = requests.structures.CaseInsensitiveDict(headers or {})
    result.json.return_value = payload
    return result


class GitHubVaultClientTests(unittest.TestCase):
    def setUp(self):
        self.client = GitHubClient(timeout=5)
        self.repo = RepoRef("vault-api-owner", "vault-api-repo")

    def test_commit_sha_validation(self):
        self.assertEqual(validate_commit_sha("a" * 40), "a" * 40)
        for invalid in ("main", "abc", "a" * 65, "abc123/other"):
            with self.subTest(value=invalid), self.assertRaises(GitHubError):
                validate_commit_sha(invalid)

    def test_lists_commit_history(self):
        sha = "1" * 40
        self.client.session.get = Mock(
            return_value=response(
                200,
                [
                    {
                        "sha": sha,
                        "commit": {
                            "message": "Fix release build\n\nDetails",
                            "author": {"name": "Builder", "date": "2026-08-01T12:00:00Z"},
                            "verification": {"verified": True},
                        },
                    }
                ],
            )
        )
        commits = self.client.list_commits(self.repo, "main", limit=10)
        self.assertEqual(commits[0].sha, sha)
        self.assertEqual(commits[0].author, "Builder")
        self.assertTrue(commits[0].verified)
        requested_url = self.client.session.get.call_args.args[0]
        self.assertIn("sha=main", requested_url)
        self.assertIn("per_page=10", requested_url)

    def test_maps_commit_changed_files(self):
        sha = "2" * 40
        self.client.session.get = Mock(
            return_value=response(
                200,
                {
                    "commit": {
                        "message": "Rename app",
                        "author": {"name": "Dev", "date": "2026-08-02T00:00:00Z"},
                        "verification": {"verified": False},
                    },
                    "stats": {"additions": 12, "deletions": 3, "total": 15},
                    "files": [
                        {
                            "filename": "src/app.py",
                            "previous_filename": "src/main.py",
                            "status": "renamed",
                            "additions": 12,
                            "deletions": 3,
                            "changes": 15,
                        }
                    ],
                },
            )
        )
        detail = self.client.commit_detail(self.repo, sha)
        self.assertEqual(detail.total_changes, 15)
        self.assertEqual(detail.files[0].previous_path, "src/main.py")

    def test_lists_release_assets(self):
        self.client.session.get = Mock(
            return_value=response(
                200,
                [
                    {
                        "id": 7,
                        "tag_name": "v1.2.0",
                        "name": "Mobile release",
                        "body": "Stable",
                        "html_url": "https://github.com/vault-api-owner/vault-api-repo/releases/tag/v1.2.0",
                        "published_at": "2026-08-03T00:00:00Z",
                        "prerelease": False,
                        "draft": False,
                        "assets": [
                            {
                                "id": 8,
                                "name": "app.apk",
                                "size": 1234,
                                "content_type": "application/vnd.android.package-archive",
                                "download_count": 55,
                                "browser_download_url": "https://github.com/vault-api-owner/vault-api-repo/releases/download/v1.2.0/app.apk",
                                "created_at": "2026-08-03T00:00:00Z",
                                "digest": "sha256:abc",
                            }
                        ],
                    },
                    {"id": 9, "draft": True},
                ],
            )
        )
        releases = self.client.list_releases(self.repo)
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].assets[0].name, "app.apk")
        self.assertEqual(releases[0].assets[0].download_count, 55)

    def test_lists_workflow_runs_and_artifacts(self):
        run_payload = {
            "workflow_runs": [
                {
                    "id": 42,
                    "run_number": 12,
                    "name": "Android build",
                    "display_title": "Build APK",
                    "event": "push",
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "main",
                    "head_sha": "3" * 40,
                    "created_at": "2026-08-04T00:00:00Z",
                    "updated_at": "2026-08-04T01:00:00Z",
                }
            ]
        }
        artifact_payload = {
            "artifacts": [
                {
                    "id": 99,
                    "name": "app-debug",
                    "size_in_bytes": 2048,
                    "expired": False,
                    "created_at": "2026-08-04T01:00:00Z",
                    "expires_at": "2026-11-02T01:00:00Z",
                    "digest": "sha256:def",
                    "workflow_run": {"id": 42},
                }
            ]
        }
        self.client.session.get = Mock(side_effect=[response(200, run_payload), response(200, artifact_payload)])
        runs = self.client.list_workflow_runs(self.repo, branch="main")
        artifacts = self.client.list_run_artifacts(self.repo, runs[0].run_id)
        self.assertEqual(runs[0].conclusion, "success")
        self.assertEqual(artifacts[0].size, 2048)
        self.assertFalse(artifacts[0].expired)

    def test_blob_bytes_decodes_and_enforces_limit(self):
        blob_sha = "4" * 40
        encoded = base64.b64encode(b"repository file").decode()
        self.client.session.get = Mock(
            return_value=response(200, {"encoding": "base64", "content": encoded, "size": 15})
        )
        self.assertEqual(self.client.blob_bytes(self.repo, blob_sha, 15), b"repository file")

        other = GitHubClient(timeout=5)
        other.session.get = Mock(
            return_value=response(200, {"encoding": "base64", "content": encoded, "size": 15})
        )
        with self.assertRaisesRegex(GitHubError, "limit"):
            other.blob_bytes(RepoRef("other-owner", "other-repo"), blob_sha, 5)

        empty = GitHubClient(timeout=5)
        empty.session.get = Mock(
            return_value=response(200, {"encoding": "base64", "content": "", "size": 0})
        )
        self.assertEqual(empty.blob_bytes(RepoRef("empty-owner", "empty-repo"), blob_sha, 1), b"")


if __name__ == "__main__":
    unittest.main()
