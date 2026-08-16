from __future__ import annotations

import unittest

from code_assistant.domain import AnalysisMode, RepositoryFile
from code_assistant.ranking import rank_candidate_paths, request_terms, select_candidate_paths


class RequestTermTests(unittest.TestCase):
    def test_removes_generic_stopwords(self):
        terms = request_terms("Please review authentication middleware code")
        self.assertIn("authentication", terms)
        self.assertIn("middleware", terms)
        self.assertNotIn("please", terms)
        self.assertNotIn("code", terms)


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.files = [
            RepositoryFile("src/routes/profile.py", 900),
            RepositoryFile("src/routes/auth.py", 1_200),
            RepositoryFile("src/security/session.py", 1_100),
            RepositoryFile("tests/test_auth.py", 800),
            RepositoryFile("app.py", 700),
            RepositoryFile("requirements.txt", 300),
            RepositoryFile("README.md", 500),
            RepositoryFile("dist/generated.js", 200),
        ]

    def test_task_terms_prioritize_relevant_source(self):
        ranked = rank_candidate_paths(self.files, "Fix authentication login flow", AnalysisMode.BUG_HUNT, 5)
        paths = [item.file.path for item in ranked]
        self.assertIn("src/routes/auth.py", paths[:3])
        self.assertNotIn("dist/generated.js", paths)

    def test_security_mode_adds_security_signal(self):
        ranked = rank_candidate_paths(self.files, "Review access controls", AnalysisMode.SECURITY, 4)
        paths = [item.file.path for item in ranked]
        self.assertIn("src/security/session.py", paths)

    def test_diversifies_with_entrypoint_manifest_and_test(self):
        ranked = rank_candidate_paths(self.files, "Authentication behavior", AnalysisMode.COMPREHENSIVE, 7)
        paths = {item.file.path for item in ranked}
        self.assertIn("app.py", paths)
        self.assertIn("requirements.txt", paths)
        self.assertIn("tests/test_auth.py", paths)

    def test_explicit_path_mention_wins(self):
        ranked = rank_candidate_paths(
            self.files,
            "Please inspect src/routes/profile.py for an edge case",
            AnalysisMode.BUG_HUNT,
            3,
        )
        self.assertEqual(ranked[0].file.path, "src/routes/profile.py")
        self.assertIn("explicitly mentioned", ranked[0].reasons)

    def test_limit_is_bounded(self):
        many = [RepositoryFile(f"src/module_{index}.py", 10) for index in range(100)]
        self.assertEqual(len(rank_candidate_paths(many, "Review module behavior", limit=99)), 14)

    def test_path_compatibility_helper(self):
        selected = select_candidate_paths(
            [item.path for item in self.files],
            "authentication session review",
            limit=2,
            mode=AnalysisMode.SECURITY,
        )
        self.assertEqual(len(selected), 2)
        self.assertTrue(any("auth" in path or "session" in path for path in selected))


if __name__ == "__main__":
    unittest.main()
