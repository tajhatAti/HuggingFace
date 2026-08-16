from __future__ import annotations

import unittest

from code_assistant.github_client import GitHubError, RepoRef, parse_github_repo


class ParseGitHubRepoTests(unittest.TestCase):
    def test_owner_repo(self):
        self.assertEqual(parse_github_repo("tajhatAti/Claude"), RepoRef("tajhatAti", "Claude"))

    def test_https_url_and_git_suffix(self):
        self.assertEqual(
            parse_github_repo("https://github.com/tajhatAti/ai.git"),
            RepoRef("tajhatAti", "ai"),
        )

    def test_rejects_non_github_host(self):
        with self.assertRaises(GitHubError):
            parse_github_repo("https://example.com/owner/repo")

    def test_rejects_extra_path(self):
        with self.assertRaises(GitHubError):
            parse_github_repo("https://github.com/owner/repo/issues")


if __name__ == "__main__":
    unittest.main()
