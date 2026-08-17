# Architecture

## Goals

Taj GitHub Repository Vault turns a public GitHub repository into a bounded, immutable browsing and download workspace while retaining the existing AI reviewer as a secondary tool.

Primary goals:

1. Read only public GitHub resources.
2. Never execute, clone, install, build, or extract repository-controlled content.
3. Pin every file operation to a commit and exact Git blob ID.
4. Support useful file, history, release, and Actions workflows with explicit limits.
5. Stream complete snapshots only from GitHub's fixed codeload host with disk/byte limits.
6. Never collect visitor credentials or expose protected resources through an owner token.
7. Keep deterministic repository logic independently testable from Gradio and ZeroGPU.

## Primary request flow

```text
Repository URL + optional ref
        │
        ▼
canonical GitHub parser ── reject other hosts/URL forms
        │
        ▼
public metadata check ── reject private repositories
        │
        ▼
recursive tree snapshot ── resolve immutable commit SHA
        │
        ├── recent commits + release assets + Actions runs
        ├── path filtering + file table
        ├── exact blob preview/download
        ├── selected exact blobs → bounded ZIP
        └── immutable GitHub ZIP/TAR links
```

No step invokes a shell, Git client, archive extractor, compiler, package manager, workflow, APK, or repository import.

## Components

### `app.py`

Owns Gradio composition, event wiring, error boundaries, model lifecycle, and ZeroGPU-decorated inference. The repository-first interface has eight workspaces:

1. Browse & select
2. Download everything
3. APKs & releases
4. Commit time travel
5. Actions artifacts
6. AI review
7. 161+ feature catalog
8. Trust & limits

A serial onboarding panel precedes the workspaces: repository validation → branch discovery/selection → immutable workspace launch. The primary explorer uses visible multi-select file cards rather than a single-file dropdown.

The primary load event calls `load_vault_ui`, renders all anonymously available GitHub metadata, and stores an immutable `VaultSession` in Gradio session state. File, ZIP, commit, and artifact events require that state and cannot silently switch repositories.

The AI workspace uses a separate `PreparedAnalysis` state. Its model lifecycle and review/export event chain remain isolated from RepoVault downloads.

### `code_assistant/github_client.py`

The only production component that calls GitHub's REST API. It:

- accepts only canonical GitHub repository identifiers;
- constructs requests beneath fixed `https://api.github.com` routes;
- rejects redirects;
- uses bounded timeouts and retries for idempotent GET requests;
- tracks rate-limit headers;
- maps API failures to user-safe errors;
- caches bounded public metadata for short periods.

Repository-vault operations include:

- repository metadata;
- recursive tree snapshots;
- up to 300 selectable branch records with protection and SHA metadata;
- recent commit records;
- changed-file metadata for a commit;
- published releases and attached assets;
- public workflow runs and retained artifact metadata;
- exact Git blob decoding with caller-provided byte ceilings.

AI-review operations additionally include base/head comparison and bounded Contents API text reads.

The client never follows an API-provided redirect or arbitrary download URL. Browser links are independently constrained or constructed from the validated owner/repository.

### `code_assistant/vault.py`

The repository explorer/download service. It defines immutable `VaultSession` and `FilePreview` records and enforces the public product's limits.

Responsibilities:

- orchestrate metadata → public check → tree → optional history/release/Actions loading;
- search and bound visible paths;
- render repository, commit, release, and workflow information;
- identify potential credential/private-key paths that must not be proxied;
- classify downloaded bytes as text or binary without executing them;
- write individual downloads under randomized private-mode `/tmp` names;
- assemble selected files from exact blob SHAs into a traversal-safe ZIP;
- classify and sort visible file cards into package/code/archive/media/docs/tests/config/data groups;
- stream complete commit-pinned ZIPs from fixed `codeload.github.com` without authorization headers;
- validate ZIP signature and central directory, compressed byte ceiling, retention, count, and total temporary-storage budget;
- validate release assets as repository-scoped HTTPS `github.com` URLs;
- build official GitHub workflow run/artifact links.

Selected ZIPs carry a manifest recording repository, commit, and file count. Input count, individual size, and total uncompressed bytes are checked before and during retrieval.

### `code_assistant/cache.py`

A lock-protected TTL/LRU cache reduces duplicate public GitHub reads. It has hard entry ceilings, monotonic expiration, and deterministic eviction. Private metadata is not cached. Large Git blob byte payloads are deliberately not cached globally.

### Existing AI intelligence components

The secondary workspace keeps the prior review pipeline:

- `repository.py` — public check, tree limits, evidence selection, sanitization, and immutable analysis construction;
- `ranking.py` — deterministic relevance ranking and architectural diversity;
- `security.py` — request policy, path policy, secret redaction, prompt-injection neutralization, and static leads;
- `inspection.py` — language/profile/symbol extraction without import;
- `dependencies.py` — data-only manifest parsing without installation or registry calls;
- `prompting.py` — trust-separated model prompt and output contract;
- `presentation.py` — bounded deterministic views;
- `reporting.py` — expiring Markdown, validated patch, and JSON exports without raw source.

## Data model

### Vault records

GitHub response records in `github_client.py` are immutable:

- `RepoRef`, `RepoMetadata`, and `TreeSnapshot`
- `CommitRecord`, `CommitFileRecord`, and `CommitDetail`
- `ReleaseAssetRecord` and `ReleaseRecord`
- `WorkflowRunRecord` and `ArtifactRecord`

`VaultSession` combines one repository, requested ref, resolved tree/commit, and bounded listing metadata. Historical browsing replaces only the requested ref and tree snapshot; repository identity remains fixed.

### AI review records

`domain.py` contains immutable repository profile, evidence, dependency, symbol, finding, analysis, and export records. Refinement reuses the original analysis snapshot.

## Download designs

### Individual file

1. Select a path already present in `VaultSession`.
2. Reject sensitive proxy paths and files above 25 MB.
3. Fetch bytes by exact blob SHA.
4. Classify a bounded sample for text preview.
5. Write bytes to a randomized 0600 file in `/tmp/taj-repovault`.
6. Let Gradio serve it as a download.

### Selected-file ZIP

1. Deduplicate and cap the selected paths at 20.
2. Confirm every path exists in the current tree and is archive-safe.
3. Reject credential/key proxy paths and per-file/total size violations.
4. Fetch each exact blob with a shrinking byte budget.
5. Write paths directly into a new ZIP; never extract an archive.
6. Add a non-sensitive provenance manifest.

### Complete repository

1. The active `VaultSession` provides a validated owner/repository and exact commit SHA.
2. `GitHubClient` constructs only `https://codeload.github.com/{owner}/{repo}/zip/{sha}` and sends no authorization header.
3. Redirects and non-success responses are rejected.
4. Content-Length and streamed bytes are limited to 500 MB; the payload must have a ZIP signature and readable central directory.
5. A `.part` file is atomically renamed only after success.
6. The completed file is returned through Gradio, retained for at most two hours, and included in the 2 GB shared temporary budget.

The archive is never extracted or executed.

### Release assets

The API-provided browser URL is accepted only when it is HTTPS on `github.com` and begins with the validated repository's `/releases/download/` path. The visitor downloads directly from GitHub.

### Actions artifacts

RepoVault lists anonymous public metadata. Actual artifact download uses GitHub's protected flow, so the UI links to the official run/artifact page. Visitor tokens never pass through the Space.

## Failure behavior

- Invalid repository/ref/path inputs fail before expensive work.
- Private repositories stop before tree/blob access.
- A tree above 20,000 files or a truncated GitHub tree fails closed.
- Commit, release, or Actions listing failure can degrade that panel while preserving the Explorer.
- Blob and selected-ZIP failures do not mutate session state.
- Expired/missing Actions artifacts remain represented by GitHub status without proxy fallback.
- Model failure does not affect repository browsing or deterministic AI tabs.
- Internal tracebacks are logged but not rendered to visitors.

## Resource model

The design intentionally does not consume all available RAM or disk. Repository trees and bounded metadata live in process/session memory. Large blob payloads are streamed through one bounded operation and not retained in the shared cache. Temporary downloads and AI exports have independent two-hour/120-file cleanup policies.

No database, clone cache, vector database, long-running worker, or persistent user storage is required.

## Extension rules

A new feature must preserve:

- fixed GitHub-only network destinations;
- public repositories only;
- no visitor tokens or private-source confused deputy;
- no repository code or artifact execution;
- no arbitrary redirects, proxying, tunnels, or remote management;
- exact snapshot/blob identity for downloaded files;
- bounded tree, list, file, archive, cache, queue, model, and export operations;
- no owner credential used to anonymously expose protected GitHub content;
- no GitHub write without a separate explicit authorization and confirmation design;
- regression tests for every new trust or resource boundary.
