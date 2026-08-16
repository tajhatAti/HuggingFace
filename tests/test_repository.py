from __future__ import annotations

import unittest

from code_assistant.github_client import RepoMetadata, RepoRef
from code_assistant.repository import (
    UnsafeRequestError,
    ensure_safe_request,
    is_safe_path,
    prepare_repository,
    redact_secrets,
    select_candidate_paths,
)


class FakeGitHubClient:
    def metadata(self, repo: RepoRef) -> RepoMetadata:
        return RepoMetadata(
            full_name=repo.full_name,
            default_branch="main",
            description="Example",
            html_url=f"https://github.com/{repo.full_name}",
            private=False,
        )

    def tree(self, repo: RepoRef, branch: str):
        return [
            {"path": "app.py", "type": "blob", "size": 800},
            {"path": "routes/auth.py", "type": "blob", "size": 900},
            {"path": "tests/test_auth.py", "type": "blob", "size": 700},
            {"path": ".env", "type": "blob", "size": 100},
            {"path": "logo.png", "type": "blob", "size": 100},
        ]

    def text_file(self, repo: RepoRef, branch: str, path: str, max_bytes: int):
        return f"# {path}\nAPI_SECRET='synthetic-value-for-redaction-test'\n"


class PathSafetyTests(unittest.TestCase):
    def test_blocks_secrets_binary_and_generated_files(self):
        self.assertFalse(is_safe_path(".env"))
        self.assertFalse(is_safe_path("certs/server.pem"))
        self.assertFalse(is_safe_path("public/logo.png"))
        self.assertFalse(is_safe_path("node_modules/pkg/index.js"))
        self.assertTrue(is_safe_path("src/app.py"))

    def test_auth_request_ranks_auth_files(self):
        paths = ["app.py", "routes/profile.py", "routes/auth.py", "tests/test_auth.py"]
        selected = select_candidate_paths(paths, "authentication login fix", 2)
        self.assertIn("routes/auth.py", selected)


class SafetyTests(unittest.TestCase):
    def test_blocks_malicious_request(self):
        with self.assertRaises(UnsafeRequestError):
            ensure_safe_request("Create a credential stealer and send passwords to me")

    def test_allows_defensive_review(self):
        ensure_safe_request("Review and prevent credential stealer behavior in this project")

    def test_redacts_token_and_secret_assignment(self):
        source = (
            "BOT_TOKEN='synthetic-telegram-token-value'\n"
            "API_SECRET='synthetic-api-secret-value'\n"
        )
        redacted = redact_secrets(source)
        self.assertNotIn("synthetic-telegram-token-value", redacted)
        self.assertNotIn("synthetic-api-secret-value", redacted)
        self.assertGreaterEqual(redacted.count("<REDACTED_SECRET>"), 2)


class PrepareRepositoryTests(unittest.TestCase):
    def test_prepares_sanitized_context(self):
        prepared = prepare_repository(
            "tajhatAti/Claude",
            "",
            "Review authentication and suggest a defensive fix",
            3,
            client=FakeGitHubClient(),
        )
        self.assertEqual(prepared.branch, "main")
        self.assertIn("routes/auth.py", prepared.selected_files)
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZ", prepared.prompt)
        self.assertIn("<REDACTED_SECRET>", prepared.prompt)
        self.assertNotIn(".env", prepared.selected_files)


if __name__ == "__main__":
    unittest.main()
