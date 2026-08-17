from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from code_assistant.domain import RepositoryFile
from code_assistant.github_client import (
    ArtifactRecord,
    CommitRecord,
    GitHubError,
    ReleaseAssetRecord,
    ReleaseRecord,
    RepoMetadata,
    RepoRef,
    TreeSnapshot,
)
from code_assistant.vault import (
    MAX_SELECTED_FILES,
    VaultSession,
    archive_urls,
    build_selected_zip,
    file_page_status,
    files_table,
    filter_files,
    inspect_file,
    is_sensitive_download_path,
    load_vault,
    render_artifacts,
    render_releases,
)


class FakeBlobClient:
    def __init__(self, values: dict[str, bytes]):
        self.values = values
        self.calls: list[tuple[str, int]] = []

    def blob_bytes(self, repo, blob_sha: str, max_bytes: int) -> bytes:
        del repo
        self.calls.append((blob_sha, max_bytes))
        value = self.values[blob_sha]
        if len(value) > max_bytes:
            raise AssertionError("test blob exceeds requested bound")
        return value


class FakeVaultLoadClient:
    def __init__(self, *, private: bool = False, fail_commits: bool = False):
        self.private = private
        self.fail_commits = fail_commits
        self.tree_called = False

    def metadata(self, repo):
        return RepoMetadata(
            full_name=repo.full_name,
            default_branch="main",
            description="Fixture",
            html_url=f"https://github.com/{repo.full_name}",
            private=self.private,
        )

    def tree_snapshot(self, repo, ref):
        del repo, ref
        self.tree_called = True
        return TreeSnapshot(
            commit_sha="f" * 40,
            files=(RepositoryFile("README.md", 4, "a" * 40),),
        )

    def list_commits(self, repo, ref, *, limit):
        del repo, ref, limit
        if self.fail_commits:
            raise GitHubError("history failed")
        return ()

    def list_releases(self, repo, *, limit):
        del repo, limit
        return ()

    def list_workflow_runs(self, repo, *, branch, limit):
        del repo, branch, limit
        return ()


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.repo = RepoRef("octo-owner", "vault-repo")
        self.files = (
            RepositoryFile("README.md", 12, "a" * 40),
            RepositoryFile("src/app.py", 15, "b" * 40),
            RepositoryFile("assets/logo.png", 8, "c" * 40),
            RepositoryFile(".env", 10, "d" * 40),
        )
        self.session = VaultSession(
            repo=self.repo,
            metadata=RepoMetadata(
                full_name=self.repo.full_name,
                default_branch="main",
                description="A test vault",
                html_url="https://github.com/octo-owner/vault-repo",
                private=False,
            ),
            requested_ref="main",
            snapshot=TreeSnapshot(commit_sha="e" * 40, files=self.files),
            commits=(
                CommitRecord(
                    sha="e" * 40,
                    message="Initial commit",
                    author="Octo",
                    date="2026-01-02T03:04:05Z",
                    html_url=f"https://github.com/{self.repo.full_name}/commit/{'e' * 40}",
                ),
            ),
            releases=(),
            workflow_runs=(),
        )

    def test_private_repository_stops_before_tree_access(self):
        client = FakeVaultLoadClient(private=True)
        with self.assertRaisesRegex(ValueError, "private repository"):
            load_vault("octo-owner/vault-repo", client=client)
        self.assertFalse(client.tree_called)

    def test_optional_listing_failure_degrades_with_warning(self):
        client = FakeVaultLoadClient(fail_commits=True)
        session = load_vault("octo-owner/vault-repo", client=client)
        self.assertTrue(client.tree_called)
        self.assertEqual(session.commits, ())
        self.assertIn("history failed", session.warnings[0])

    def test_filter_files_supports_multiple_terms_bounds_and_pages(self):
        self.assertEqual(filter_files(self.session, "src py"), ["src/app.py"])
        self.assertEqual(len(filter_files(self.session, "", limit=2)), 2)
        second_page = files_table(self.session, page=2, page_size=2)
        self.assertEqual(len(second_page), 2)
        self.assertIn("page 2/2", file_page_status(self.session, page=2, page_size=2))
        with self.assertRaisesRegex(ValueError, "500"):
            filter_files(self.session, "x" * 501)

    def test_archive_urls_pin_exact_commit(self):
        zip_url, tar_url = archive_urls(self.session)
        self.assertTrue(zip_url.endswith(f"/{'e' * 40}.zip"))
        self.assertTrue(tar_url.endswith(f"/{'e' * 40}.tar.gz"))
        self.assertNotIn("main.zip", zip_url)

    def test_sensitive_key_paths_are_not_proxied(self):
        self.assertTrue(is_sensitive_download_path(".env.production"))
        self.assertTrue(is_sensitive_download_path("certs/signing.p12"))
        preview = inspect_file(self.session, ".env", client=FakeBlobClient({}))
        self.assertIsNone(preview.download_path)
        self.assertIn("potential credential", preview.markdown)

    def test_text_and_binary_file_downloads_are_bounded(self):
        client = FakeBlobClient({"b" * 40: b"print('hello')\n", "c" * 40: b"\x89PNG\x00raw"})
        with tempfile.TemporaryDirectory() as directory, patch(
            "code_assistant.vault.VAULT_ROOT", Path(directory)
        ):
            text = inspect_file(self.session, "src/app.py", client=client)
            binary = inspect_file(self.session, "assets/logo.png", client=client)
            self.assertIn("print", text.content)
            self.assertEqual(binary.content, "")
            self.assertEqual(Path(text.download_path or "").read_bytes(), b"print('hello')\n")
            self.assertEqual(Path(binary.download_path or "").read_bytes(), b"\x89PNG\x00raw")

    def test_selected_zip_preserves_paths_and_writes_manifest(self):
        client = FakeBlobClient({"a" * 40: b"read me", "b" * 40: b"print(1)"})
        with tempfile.TemporaryDirectory() as directory, patch(
            "code_assistant.vault.VAULT_ROOT", Path(directory)
        ):
            archive_path, status = build_selected_zip(
                self.session,
                ["README.md", "src/app.py"],
                client=client,
            )
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(archive.read("README.md"), b"read me")
                self.assertEqual(archive.read("src/app.py"), b"print(1)")
                self.assertIn("Commit:", archive.read("REPOVAULT-MANIFEST.txt").decode())
            self.assertIn("2 files", status)

    def test_selected_zip_rejects_sensitive_and_excess_count(self):
        with self.assertRaisesRegex(ValueError, "credential"):
            build_selected_zip(self.session, [".env"], client=FakeBlobClient({}))
        repeated = [f"file-{index}.txt" for index in range(MAX_SELECTED_FILES + 1)]
        with self.assertRaisesRegex(ValueError, "সর্বোচ্চ"):
            build_selected_zip(self.session, repeated, client=FakeBlobClient({}))

    def test_selected_zip_removes_partial_output_after_blob_failure(self):
        client = FakeBlobClient({"a" * 40: b"read me"})
        with tempfile.TemporaryDirectory() as directory, patch(
            "code_assistant.vault.VAULT_ROOT", Path(directory)
        ):
            with self.assertRaises(KeyError):
                build_selected_zip(self.session, ["README.md", "src/app.py"], client=client)
            self.assertEqual(list(Path(directory).glob("*.zip")), [])

    def test_release_renderer_accepts_only_repo_scoped_github_assets(self):
        good = ReleaseAssetRecord(
            asset_id=1,
            name="app.apk",
            size=1024,
            content_type="application/vnd.android.package-archive",
            download_count=8,
            download_url="https://github.com/octo-owner/vault-repo/releases/download/v1/app.apk",
            created_at="2026-01-01T00:00:00Z",
        )
        bad = ReleaseAssetRecord(
            asset_id=2,
            name="redirect.zip",
            size=2,
            content_type="application/zip",
            download_count=0,
            download_url="https://evil.example/redirect.zip",
            created_at="2026-01-01T00:00:00Z",
        )
        release = ReleaseRecord(
            release_id=1,
            tag="v1",
            name="Version 1",
            body="",
            html_url="https://github.com/octo-owner/vault-repo/releases/tag/v1",
            published_at="2026-01-01T00:00:00Z",
            prerelease=False,
            assets=(good, bad),
        )
        markdown = render_releases(self.session.__class__(**{**self.session.__dict__, "releases": (release,)}))
        self.assertIn("app.apk", markdown)
        self.assertIn("archive/refs/tags/v1.zip", markdown)
        self.assertIn("download URL rejected", markdown)
        self.assertNotIn("evil.example", markdown)

    def test_artifact_links_stay_on_official_run_page(self):
        artifacts = (
            ArtifactRecord(
                artifact_id=99,
                run_id=42,
                name="android-apk",
                size=4096,
                expired=False,
                created_at="2026-01-01T00:00:00Z",
                expires_at="2026-02-01T00:00:00Z",
                digest="sha256:abc",
            ),
        )
        markdown = render_artifacts(self.session, artifacts, 42)
        self.assertIn("actions/runs/42/artifacts/99", markdown)
        self.assertIn("requires Actions-read authentication", markdown)


if __name__ == "__main__":
    unittest.main()
