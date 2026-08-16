from __future__ import annotations

import unittest

from code_assistant.dependencies import (
    dependency_findings,
    is_dependency_manifest,
    merge_dependencies,
    parse_dependencies,
    render_dependency_inventory,
)


class ManifestDetectionTests(unittest.TestCase):
    def test_detects_nested_manifest_case_insensitively(self):
        self.assertTrue(is_dependency_manifest("services/api/requirements.txt"))
        self.assertTrue(is_dependency_manifest("Cargo.toml"))
        self.assertFalse(is_dependency_manifest("src/requirements.py"))


class DependencyParserTests(unittest.TestCase):
    def test_parses_package_json_groups(self):
        records = parse_dependencies(
            "package.json",
            '{"dependencies":{"react":"19.1.0","zod":"^4.0.0"},"devDependencies":{"vitest":"3.2.1"}}',
        )
        by_name = {item.name: item for item in records}
        self.assertEqual(set(by_name), {"react", "zod", "vitest"})
        self.assertTrue(by_name["react"].pinned)
        self.assertFalse(by_name["zod"].pinned)
        self.assertEqual(by_name["vitest"].group, "development")

    def test_parses_python_requirements_without_options(self):
        records = parse_dependencies(
            "requirements.txt",
            "requests==2.34.2\ntransformers>=5,<6\n-r base.txt\n# comment\n",
        )
        by_name = {item.name: item for item in records}
        self.assertTrue(by_name["requests"].pinned)
        self.assertFalse(by_name["transformers"].pinned)
        self.assertNotIn("-r", by_name)

    def test_parses_pep621_and_poetry_pyproject(self):
        content = """
[project]
dependencies = ["httpx==0.28.1", "pydantic>=2"]
[project.optional-dependencies]
test = ["pytest==8.4.0"]
[tool.poetry.dependencies]
python = ">=3.12"
rich = "^14.0"
"""
        records = parse_dependencies("pyproject.toml", content)
        names = {item.name for item in records}
        self.assertEqual(names, {"httpx", "pydantic", "pytest", "rich"})

    def test_parses_cargo_and_go(self):
        cargo = parse_dependencies(
            "Cargo.toml",
            '[dependencies]\nserde = "1.0.219"\ntokio = { version = "1.45.0", features = ["full"] }\n',
        )
        go = parse_dependencies(
            "go.mod",
            "module example.test/app\nrequire (\n github.com/gin-gonic/gin v1.10.1\n)\n",
        )
        self.assertEqual({item.name for item in cargo}, {"serde", "tokio"})
        self.assertEqual(go[0].name, "github.com/gin-gonic/gin")
        self.assertTrue(go[0].pinned)

    def test_parses_composer_gemfile_maven_gradle_and_pubspec(self):
        composer = parse_dependencies("composer.json", '{"require":{"laravel/framework":"11.0.0"}}')
        gem = parse_dependencies("Gemfile", "gem 'rails', '8.0.0'\n")
        maven = parse_dependencies(
            "pom.xml",
            "<project><dependencies><dependency><groupId>org.example</groupId>"
            "<artifactId>core</artifactId><version>1.2.3</version></dependency></dependencies></project>",
        )
        gradle = parse_dependencies("build.gradle", "implementation 'org.example:core:1.2.3'\n")
        pub = parse_dependencies("pubspec.yaml", "dependencies:\n  flutter: 3.32.0\n")
        self.assertEqual(composer[0].name, "laravel/framework")
        self.assertEqual(gem[0].name, "rails")
        self.assertEqual(maven[0].name, "org.example:core")
        self.assertEqual(gradle[0].name, "org.example:core")
        self.assertEqual(pub[0].name, "flutter")

    def test_invalid_manifests_fail_closed_without_exception(self):
        self.assertEqual(parse_dependencies("package.json", "{"), ())
        self.assertEqual(parse_dependencies("pyproject.toml", "[broken"), ())
        self.assertEqual(parse_dependencies("pom.xml", "<broken>"), ())


class DependencyAnalysisTests(unittest.TestCase):
    def test_merge_deduplicates_same_manifest_group(self):
        first = parse_dependencies("package.json", '{"dependencies":{"react":"19.1.0"}}')
        second = parse_dependencies("package.json", '{"dependencies":{"react":"19.2.0"}}')
        merged = merge_dependencies((first, second))
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].specification, "19.1.0")

    def test_broad_runtime_dependency_creates_low_severity_lead(self):
        records = parse_dependencies("package.json", '{"dependencies":{"zod":"^4.0.0"}}')
        findings = dependency_findings(records)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "DEP-BROAD-RANGE")

    def test_render_inventory_has_verification_notice(self):
        records = parse_dependencies("requirements.txt", "requests==2.34.2\n")
        rendered = render_dependency_inventory(records)
        self.assertIn("Dependency inventory", rendered)
        self.assertIn("not a live vulnerability lookup", rendered)


if __name__ == "__main__":
    unittest.main()
