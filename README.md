---
title: RepoVault 3D
emoji: 💎
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

A production-oriented, mobile-first **3D glass repository command center** for public GitHub repositories. The interface now follows a serial flow: connect a repository, discover/select its branches, open an immutable snapshot, tap visible file cards, then preview or download without navigating a wall of dropdowns.

RepoVault includes **160 auditable capabilities** across branch discovery, smart file groups, APK/release access, website-hosted complete ZIPs, commit time travel, Actions metadata, security controls, accessibility, and the preserved Qwen AI reviewer.

## Product capabilities

### Repository explorer

- Canonical `owner/repository` and `https://github.com/owner/repository` validation.
- Two-step onboarding with up to 300 discovered branches, default-branch priority, protected badges, and commit-SHA preview.
- Searchable branch selector plus custom tag/commit support.
- Recursive Git tree index pinned to the exact commit returned by GitHub.
- 160 visible tap-to-select file cards per page instead of an individual-file dropdown.
- Package-first sorting and filters for APK/AAB/installers, code, archives, media, docs, tests, config/CI, data, and other files.
- Complete-tree path search, paginated technical table, smart category counts, and largest-file insights.
- Safe text preview, binary metadata, exact-blob individual download, and multi-select ZIP actions.
- Potential credential/private-key files are listed but not individually previewed or repackaged.

### Downloads

- Individual files up to 25 MB through an ephemeral Gradio download.
- Selected-file ZIP generation for up to 20 files and 50 MB of uncompressed content.
- Archive paths are validated against traversal and exact blob IDs are used.
- **Download every repository file** streams the commit-pinned ZIP from the fixed GitHub codeload host into RepoVault and returns it directly on the website.
- Complete ZIPs have a 500 MB compressed ceiling; the shared temporary directory has a 2 GB budget.
- Temporary files use randomized names, restrictive permissions, two-hour expiry, count cleanup, and byte-budget cleanup.
- Archives are never cloned, extracted, imported, built, or executed.

### Mobile glass and mandatory 3D experience

- Generated cinematic 3D vault artwork in mobile-optimized `assets/repovault-3d.webp`.
- CSS perspective depth, hover tilt, floating vault motion, orbiting particles, glow, and animated glass surfaces.
- Mobile stacking, large touch targets, sticky selection actions, compact preview, horizontally scrollable navigation, and one-hand controls.
- Operating-system `prefers-reduced-motion` support disables non-essential animation for accessibility.

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

Complete source ZIPs are streamed only from the fixed `codeload.github.com` host with redirect rejection, ZIP-signature and central-directory validation, a 500 MB ceiling, and a 2 GB temporary-storage budget. Release assets remain repository-scoped first-party GitHub downloads; protected Actions downloads remain on GitHub's authorization flow.

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
  │       └── website-hosted complete ZIP + scoped release/run links
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
| Discovered branches | 300 |
| Recursive tree | 20,000 files |
| File cards per page | 160 |
| File table rows per page | 500 |
| Text preview | 300,000 bytes |
| Individual proxied file | 25,000,000 bytes |
| Selected files per ZIP | 20 |
| Selected ZIP uncompressed input | 50,000,000 bytes |
| Complete snapshot ZIP | 500,000,000 bytes |
| Vault temporary storage budget | 2,000,000,000 bytes |
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
- [`docs/POLICY_COMPATIBILITY.md`](docs/POLICY_COMPATIBILITY.md) — 50 restricted-use examples, 150 policy-compatible examples, and the RepoVault deployment decision
- [`SECURITY.md`](SECURITY.md) — vulnerability reporting and security commitments
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — change and validation requirements

## License

Apache-2.0. See [`LICENSE`](LICENSE).
