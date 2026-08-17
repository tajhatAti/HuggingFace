---
title: Taj GitHub Repository Vault
emoji: 🗃️
colorFrom: green
colorTo: yellow
sdk: gradio
app_file: app.py
python_version: 3.12.12
pinned: false
license: apache-2.0
models:
  - Qwen/Qwen2.5-Coder-3B-Instruct
---

# Taj GitHub Repository Vault

A production-oriented, repository-first explorer and downloader for **public GitHub repositories**. Paste a repository URL to browse an immutable file snapshot, preview or download a file, package selected files, download the full source archive, inspect commit history, browse any commit, collect published release assets, and discover GitHub Actions artifacts.

The previous Qwen-powered AI repository reviewer remains available as a secondary specialist workspace.

## Product capabilities

### Repository explorer

- Canonical `owner/repository` and `https://github.com/owner/repository` validation.
- Branch, tag, or commit selection; a blank ref resolves to the default branch.
- Recursive Git tree index pinned to the commit SHA returned by GitHub.
- Searchable path list and paginated file table across the complete bounded tree, with type, size, blob SHA, and proxy status.
- Safe text preview for supported files and metadata-only treatment for binary files.
- Individual-file preparation from the exact Git blob ID.
- Potential credential/private-key files are listed but not previewed or proxied.

### Downloads

- Individual files up to 25 MB through an ephemeral Gradio download.
- Selected-file ZIP generation for up to 20 files and 50 MB of uncompressed content.
- Archive paths are validated against traversal and exact blob IDs are used.
- Complete snapshot ZIP and TAR.GZ links point directly to GitHub and are pinned to an immutable commit.
- Temporary files use randomized names, restrictive permissions, two-hour expiry, and a count ceiling.

### History and historical snapshots

- Latest 50 commits with SHA, author, time, message, and signature-verification status.
- Changed-file metadata for a selected commit, including status and addition/deletion counts.
- One-click replacement of the active Explorer with the selected historical commit.
- Individual, selected, and complete archive downloads continue to work for that historical snapshot.
- Any known commit SHA can also be entered directly in the top ref field.

### Releases, APKs, and attached files

- Up to 20 published releases and 100 assets per release.
- APK, AAB, ZIP, TAR, and other release assets with name, MIME type, size, and download count.
- Asset links are accepted only when they are HTTPS URLs on `github.com` under the selected repository's release-download path.
- Downloads are served directly by GitHub; the Space does not copy large release binaries.

### GitHub Actions

- Latest 40 public workflow runs with status, conclusion, branch, event, and official run link.
- Retained artifact metadata with name, ZIP size, expiry, and official artifact/run page.
- Public artifact metadata can be listed anonymously. GitHub requires Actions-read authentication for artifact download, so RepoVault opens GitHub's official page and lets GitHub enforce sign-in.
- The Space never asks visitors for a personal access token and never uses an owner credential to anonymously expose protected artifacts.

### AI review workspace

The original production review engine remains available in tab 06:

- comprehensive, bug, defensive security, performance, architecture, testing, and documentation modes;
- optional base→review-branch comparison;
- deterministic architecture, symbol, dependency, test/docs/CI, and static-review intelligence;
- bounded, relevance-ranked source evidence;
- secret redaction and source prompt-injection neutralization;
- local Qwen Coder inference on ZeroGPU;
- Markdown, validated patch, and machine-readable JSON exports.

## Deliberate safety boundary

RepoVault is a public, read-only data viewer. It does **not**:

- clone, import, compile, build, test, install, execute, or extract repository-controlled content;
- execute APKs, workflow jobs, release files, or Actions artifacts;
- accept arbitrary network hosts, follow API redirects, or operate as a proxy/tunnel;
- read private repositories or request visitor credentials;
- write, commit, push, open pull requests, merge, publish releases, or trigger workflows;
- proxy common credential/private-key filenames;
- use an owner token to grant anonymous visitors access to protected GitHub content.

GitHub source archives and release assets remain first-party GitHub downloads. This prevents the Space from becoming an unbounded large-file relay while preserving complete-repository and release download functionality.

See [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) for trust boundaries and abuse cases.

## Architecture

```text
Gradio repository-first UI
  │
  ├── strict public GitHub repository + ref validation
  │
  ├── bounded GitHub REST client ── short TTL/LRU cache
  │       ├── metadata + recursive tree snapshot
  │       ├── commits + changed-file details
  │       ├── releases + attached assets
  │       ├── workflow runs + artifact metadata
  │       └── exact Git blob bytes
  │
  ├── RepoVault service
  │       ├── path search + file metadata
  │       ├── safe text/binary preview decision
  │       ├── individual ephemeral download
  │       ├── bounded selected-file ZIP
  │       └── immutable GitHub archive/release/run links
  │
  └── secondary AI review workspace
          ├── sanitized repository intelligence
          ├── Qwen Coder inside @spaces.GPU
          └── expiring report/patch/JSON exports
```

Detailed component responsibilities are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Runtime limits

| Control | Current bound |
|---|---:|
| Recursive tree | 20,000 files |
| File paths displayed per search | 1,000 |
| File table rows per search | 500 |
| Text preview | 300,000 bytes |
| Individual proxied file | 25,000,000 bytes |
| Selected files per ZIP | 20 |
| Selected ZIP uncompressed input | 50,000,000 bytes |
| Recent commits | 50 |
| Changed files per commit detail | 300 |
| Published releases | 20 |
| Assets per release | 100 |
| Workflow runs | 40 |
| Artifacts per run | 100 |
| Vault temporary download retention | 2 hours / 120 files |
| AI evidence | 3–14 files |
| AI context | 22,000–48,000 characters |
| AI model output | 256–2,000 tokens |
| ZeroGPU allocation | 55 seconds per generation |

GitHub API quotas and GitHub's own retention/authentication rules still apply.

## Runtime configuration

No visitor API key is required.

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_ID` | `Qwen/Qwen2.5-Coder-3B-Instruct` | Secondary AI workspace model |
| `MAX_INPUT_TOKENS` | `15000` | AI model input ceiling |
| `MAX_NEW_TOKENS` | `1200` | AI model output ceiling |
| `GITHUB_TOKEN` | unset | Optional owner-configured read-only token for higher public API quota |
| `VAULT_DIRECTORY` | `/tmp/taj-repovault` | Ephemeral individual/selected downloads |
| `REPORT_DIRECTORY` | `/tmp/taj-ai-reports` | Ephemeral AI exports |

If `GITHUB_TOKEN` is configured by the Space owner, it must be a fine-grained read-only Space secret. The application checks repository visibility and rejects private repositories before tree or blob access.

## Local validation

Core tests need only Requests and the standard library:

```bash
python -m venv .venv
.venv/bin/pip install "requests>=2.32,<3" "ruff>=0.11,<1"
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check app.py code_assistant tests scripts
python -m compileall -q app.py code_assistant scripts tests
```

The Hugging Face runtime manages Gradio, PyTorch, Spaces, and `huggingface_hub`. Application dependencies are listed in `requirements.txt`.

## Automatic deployment

`.github/workflows/sync-to-huggingface.yml` validates every push to `main` or `arena/01a00b5b-huggingface`, mirrors the exact revision to `madarauchihagmailcom/My` with the official Hub Sync action, and requests ZeroGPU.

The only deployment credential is the GitHub Actions secret `HF_TOKEN`, scoped to the target Space. It is never stored in source or shown to visitors.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components, data flow, and extension rules
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) — trust zones, abuse cases, and controls
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — deployment, verification, troubleshooting, and rollback
- [`SECURITY.md`](SECURITY.md) — vulnerability reporting and security commitments
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — change and validation requirements

## License

Apache-2.0. See [`LICENSE`](LICENSE).
