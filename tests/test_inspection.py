from __future__ import annotations

import unittest

from code_assistant.domain import RepositoryFile
from code_assistant.inspection import (
    build_repository_profile,
    detect_language,
    extract_symbols,
    is_documentation_path,
    is_test_path,
    render_architecture_map,
)


class LanguageTests(unittest.TestCase):
    def test_detects_language_by_extension_and_special_name(self):
        cases = {
            "src/app.py": "Python",
            "web/page.tsx": "TypeScript",
            "cmd/main.go": "Go",
            "Dockerfile": "Dockerfile",
            "README.md": "Markdown",
            "unknown.asset": "Other",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(detect_language(path), expected)

    def test_classifies_tests_and_docs(self):
        self.assertTrue(is_test_path("tests/test_auth.py"))
        self.assertTrue(is_test_path("src/auth.spec.ts"))
        self.assertTrue(is_documentation_path("docs/setup.mdx"))
        self.assertFalse(is_documentation_path("src/app.ts"))


class ProfileTests(unittest.TestCase):
    def test_builds_repository_profile(self):
        files = [
            RepositoryFile("app.py", 100),
            RepositoryFile("src/auth.py", 200),
            RepositoryFile("web/page.tsx", 300),
            RepositoryFile("tests/test_auth.py", 150),
            RepositoryFile("README.md", 80),
            RepositoryFile("package.json", 70),
            RepositoryFile("next.config.ts", 50),
            RepositoryFile(".github/workflows/test.yml", 40),
        ]
        profile = build_repository_profile(files, {item.path for item in files})
        self.assertEqual(profile.total_files, 8)
        self.assertEqual(profile.primary_language, "Python")
        self.assertIn("Next.js", profile.frameworks)
        self.assertIn("npm-compatible", profile.package_managers)
        self.assertIn("app.py", profile.entrypoints)
        self.assertEqual(profile.test_files, 1)
        self.assertEqual(profile.documentation_files, 1)
        self.assertEqual(profile.ci_files, (".github/workflows/test.yml",))


class SymbolTests(unittest.TestCase):
    def test_extracts_python_symbols_without_importing(self):
        source = """
class Service:
    def run(self, value):
        return value

async def fetch(url, **kwargs):
    return None
"""
        symbols = extract_symbols("service.py", source)
        by_name = {symbol.name: symbol for symbol in symbols}
        self.assertEqual(by_name["Service"].kind, "class")
        self.assertEqual(by_name["fetch"].kind, "async function")
        self.assertIn("url", by_name["fetch"].signature)

    def test_invalid_python_produces_empty_outline(self):
        self.assertEqual(extract_symbols("broken.py", "def broken("), ())

    def test_extracts_javascript_go_rust_and_java(self):
        js = extract_symbols("app.ts", "export async function load(id) {}\nconst save = (item) => item;\nclass Store {}")
        go = extract_symbols("main.go", "func Handle(value string) error { return nil }")
        rust = extract_symbols("lib.rs", "pub struct Config {}\npub fn run() {}")
        java = extract_symbols("App.java", "public class App {}")
        self.assertEqual({item.name for item in js}, {"load", "save", "Store"})
        self.assertEqual(go[0].name, "Handle")
        self.assertEqual({item.name for item in rust}, {"Config", "run"})
        self.assertEqual(java[0].name, "App")

    def test_architecture_render_is_bounded_and_informative(self):
        files = [RepositoryFile("app.py", 100), RepositoryFile("tests/test_app.py", 100)]
        profile = build_repository_profile(files, {item.path for item in files})
        symbols = list(extract_symbols("app.py", "def main():\n    return 0\n"))
        rendered = render_architecture_map(profile, symbols)
        self.assertIn("Repository architecture", rendered)
        self.assertIn("`main()`", rendered)


if __name__ == "__main__":
    unittest.main()
