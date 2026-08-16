# Architecture

## Goals

Taj AI Code Assistant Pro provides useful repository review while maintaining a narrow and auditable trust boundary. The core is intentionally independent from Gradio, Transformers, and ZeroGPU so repository intelligence can be tested as ordinary Python.

Primary goals:

1. Read only public GitHub repository text.
2. Never execute or install repository-controlled content.
3. Bound every external input and expensive operation.
4. Separate deterministic facts, heuristic leads, and model suggestions.
5. Ensure secret-like values do not reach inference or exports.
6. Produce reports that a maintainer can verify before applying.

## Components

### `app.py`

Owns UI composition, model lifecycle, ZeroGPU-decorated inference, event chaining, and user-facing error boundaries. It delegates all repository logic to the package.

The initial review pipeline is:

1. `inspect_repository_ui` prepares a deterministic snapshot.
2. The UI immediately renders repository, findings, architecture, dependency, and evidence tabs.
3. `generate_review` uses the prepared prompt inside a bounded GPU allocation.
4. `build_exports_ui` writes expiring Markdown, patch, and JSON artifacts.

Static inspection can stop after step 2 and consumes no GPU quota. Refinement reuses the same prepared snapshot and cannot silently read additional files.

### `code_assistant/github_client.py`

The only production component that reads GitHub. It constructs URLs under a fixed `https://api.github.com` root, rejects redirects, applies bounded retries to idempotent GET requests, records rate-limit headers, and maps API failures to user-safe errors.

The client exposes:

- canonical owner/repository parsing;
- branch validation;
- metadata retrieval;
- recursive Git tree snapshots with commit SHA;
- optional base/head compare metadata for changed-file prioritization;
- bounded Base64 file decoding from the Contents API.

The client does not follow `download_url`, raw URLs, submodule links, release assets, Git LFS pointers, webhooks, or user-selected hosts.

### `code_assistant/cache.py`

A lock-protected TTL/LRU cache limits repeat GitHub reads. It uses monotonic time, hard entry ceilings, lazy expiration, and deterministic eviction. Private metadata is never cached, and the orchestrator rejects private repositories before tree or file retrieval.

### `code_assistant/ranking.py`

Ranking operates only on tree metadata. It combines:

- exact user-mentioned paths;
- request terms and explicit filename abbreviations;
- mode-specific path signals;
- project entrypoint and configuration names;
- dependency manifests;
- test, documentation, and CI signals;
- generated/output penalties;
- a small architectural diversity reservation.

Ranking does not use embeddings, execute indexing binaries, or download the entire repository. Final evidence remains capped at 14 files.

### `code_assistant/security.py`

Defines four separate safety layers:

1. Request policy for clearly harmful or unauthorized intent.
2. Path policy excluding credential, binary, generated, dependency-vendor, and build trees.
3. Pre-inference sanitization for recognized credentials, private keys, control characters, and strong source-embedded prompt injection.
4. Post-generation sanitization before display and export.

Static review rules return evidence leads with explicit confidence. They are not treated as proof that a vulnerability is exploitable.

### `code_assistant/inspection.py`

Creates path-derived repository profiles and extracts bounded symbols. Python uses `ast.parse`; other languages use conservative regular expressions. Parsing source text does not import or execute it.

### `code_assistant/dependencies.py`

Parses common manifest formats with standard-library JSON, TOML, XML, and constrained line parsers. YAML support intentionally recognizes only the small dependency mapping needed by `pubspec.yaml`; no object-constructing YAML loader is used.

The inventory never resolves versions or calls a package registry. Broad-version findings recommend lockfiles and advisory scanning in the maintainer's CI.

### `code_assistant/repository.py`

The orchestrator enforces the product's resource and trust invariants:

- request safety before network access;
- public metadata check before tree access;
- branch and tree limits;
- reviewable path/size filtering;
- deterministic ranking;
- per-depth source and total-context budgets;
- static scan of downloaded text;
- sanitization before symbols, dependency parsing, and inference;
- immutable `PreparedAnalysis` creation.

A compatibility `prepare_repository` API remains available for integrations using the original compact response.

### `code_assistant/prompting.py`

Builds a prompt with explicit sections for trusted configuration, user request, deterministic metadata, heuristic leads, and untrusted repository files. Each file is wrapped as evidence and the model is repeatedly instructed not to treat repository text as commands.

The output contract requires a full professional report and forbids claims that code, tests, package managers, or vulnerability databases were run.

### `code_assistant/reporting.py`

Creates three optional artifacts:

- Markdown with the complete deterministic and AI report;
- patch only when a fenced block has old/new headers and a hunk marker;
- JSON with structured metadata, symbols, dependencies, findings, and review.

Raw source content and the full model prompt are excluded. Files are atomically written with restrictive permissions under an ephemeral directory and cleaned by age/count.

## Data model

`code_assistant/domain.py` contains immutable dataclasses and enums:

- `AnalysisMode` and `ReviewDepth`
- `Severity`
- `RepositoryFile`, `RepositorySnapshot`, and `RepositoryProfile`
- `CodeSymbol`, `DependencyRecord`, and `Finding`
- `SourceDocument`
- `PreparedAnalysis`
- `ReviewArtifacts`

Immutability ensures that the branch/commit/evidence set used by a refinement remains the same as its initial review.

## Failure behavior

Network, parser, model, and export failures are isolated:

- Invalid user/network conditions return localized actionable messages.
- One unavailable selected file is skipped and reported as a warning.
- If all selected files fail, preparation stops rather than fabricating context.
- An unavailable model does not disable deterministic repository intelligence.
- A model failure does not erase static tabs.
- Export failure does not erase an already generated report.

Internal tracebacks are logged server-side and are not rendered to public visitors.

## Resource model

The Space runtime has finite CPU/RAM/disk and ZeroGPU quota. The implementation therefore avoids repository clones, vector databases, background workers, and persistent multi-user state. Model weights are loaded once through ZeroGPU's root-level CUDA emulation path. Public sessions store only their prepared analysis and temporary export references in Gradio state.

## Extension rules

A new feature must preserve these invariants:

- no repository-controlled code execution;
- no arbitrary network destination;
- no visitor credential collection;
- no private source exposure through owner credentials;
- no unbounded tree, file, prompt, output, cache, queue, or artifact;
- no unverified security claim presented as fact;
- no write operation without a separate, explicit product and authorization design.
