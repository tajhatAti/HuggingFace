---
title: Taj AI Code Assistant Pro
emoji: 🧠
colorFrom: indigo
colorTo: blue
sdk: gradio
app_file: app.py
python_version: 3.12.12
pinned: false
license: apache-2.0
models:
  - Qwen/Qwen2.5-Coder-3B-Instruct
---

# Taj AI Code Assistant Pro

A production-oriented, read-only repository intelligence and AI code-review application for **public GitHub repositories**. It builds a bounded repository map, selects relevant evidence, removes secret-like values, neutralizes source-embedded prompt injection, runs deterministic static review heuristics, and asks a local Qwen coding model for a professional report and focused unified diff.

The interface is optimized for Bangla/Banglish-speaking developers while review requests and reports can also be written in English.

## Product capabilities

### Repository intelligence

- Canonical GitHub repository and branch validation with strict host controls.
- Public metadata, recursive tree, commit snapshot, and bounded source retrieval through the GitHub REST API.
- Optional base→review-branch comparison with commit metadata, changed-file deltas, and automatic changed-file prioritization (no remote patch body is trusted).
- Large-repository protection: 20,000-tree-file ceiling, 14 selected-file ceiling, per-file limits, and depth-based context budgets.
- Deterministic relevance ranking using user terms, common filename abbreviations, review mode, entrypoints, manifests, tests, CI, and explicit path mentions.
- Language inventory, top-level directory map, test/docs/CI counts, framework signals, package managers, and probable entrypoints.
- Symbol extraction for Python, JavaScript/TypeScript, Go, Rust, Java/Kotlin/C#/Scala, PHP, and Ruby without importing source.
- Ten-minute bounded in-process caching for repeated public metadata and source reads.

### Review modes

- Comprehensive review
- Bug hunt
- Defensive security audit
- Performance review
- Architecture review
- Test strategy
- Documentation review

Quick, Standard, and Deep depth profiles control evidence count and context size. The public Space remains intentionally bounded even when Deep mode is selected.

### Deterministic analysis

The scanner reports review leads—not unverified claims of exploitability—for patterns such as:

- hard-coded credential formats and secret assignments;
- dynamic code execution and unsafe shell construction;
- disabled TLS verification;
- unsafe object deserialization;
- SQL interpolation and path-sensitive file operations;
- browser HTML injection sinks and token storage;
- wildcard CORS and production debug flags;
- weak security hashes and container root-user signals;
- broad/unpinned runtime dependency ranges.

Every lead includes severity, rule ID, location, redacted evidence, confidence, and a defensive recommendation. The AI is told to verify each heuristic against supplied context before including it as a material finding.

### Dependency inventory

Safe text parsers support:

- npm-compatible `package.json` files;
- Python `requirements.txt` and `pyproject.toml` (PEP 621 and Poetry sections);
- Rust `Cargo.toml`;
- Go `go.mod`;
- PHP Composer;
- Ruby Gemfile;
- Maven and Gradle;
- Dart/Flutter pubspec.

No dependency is installed and no repository script is run. The inventory does not pretend to be a live vulnerability database; the generated validation plan directs maintainers to current ecosystem advisory tooling.

### AI report and workflow

Qwen2.5-Coder-3B-Instruct runs locally on Hugging Face ZeroGPU and returns a structured report with:

1. Executive summary
2. Prioritized findings
3. Architecture impact
4. Suggested unified diff
5. Validation plan
6. Risks and unknowns

A completed review can be refined using the same immutable repository snapshot. The application exports:

- a complete Markdown report;
- a `.patch` file when the model returns a valid unified diff;
- machine-readable JSON without raw source contents or the full model prompt.

Temporary exports are private-mode files under `/tmp`, are bounded in number, and expire after two hours.

## Deliberate safety boundary

This public Space **does not**:

- clone or execute repository code;
- invoke a shell, compiler, package manager, build, or test command from user input;
- accept arbitrary network hosts or act as a proxy/tunnel;
- read private repositories;
- request a visitor's GitHub or Hugging Face token;
- write, commit, push, open pull requests, merge, or deploy visitor repositories;
- expose raw repository source in exported reports;
- produce clearly malicious, phishing, credential-theft, unauthorized-access, spam, cryptomining, destructive, or evasion tooling.

Repository text is explicitly marked as untrusted evidence. Strong embedded instructions such as “ignore previous instructions” are replaced before inference. Recognized GitHub, Hugging Face, cloud, Slack, JWT, database URI, private-key, and secret-assignment formats are redacted both before inference and after generation.

These constraints preserve the product as a legitimate ML code-review application rather than a public remote-management or arbitrary-code-execution service.

See [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) for trust boundaries and abuse cases.

## Architecture

```text
Gradio UI
  │
  ├── canonical input + request safety policy
  │
  ├── read-only GitHub REST client ── bounded TTL cache
  │       ├── repository metadata
  │       ├── commit/tree snapshot
  │       └── selected Contents API blobs
  │
  ├── repository intelligence pipeline
  │       ├── path safety + relevance ranking
  │       ├── secret and prompt-injection sanitization
  │       ├── language/profile/symbol extraction
  │       ├── dependency manifest parsing
  │       └── deterministic static review leads
  │
  ├── trust-separated professional prompt
  │
  ├── Qwen Coder generation inside @spaces.GPU
  │
  └── final redaction + Markdown/patch/JSON exports
```

Detailed component responsibilities and data flow are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Runtime limits

| Control | Current bound |
|---|---:|
| Recursive tree | 20,000 files |
| Branch comparison metadata | 300 changed files |
| Selectable evidence | 3–14 files |
| Source read per file | 24,000 bytes |
| Quick context | 22,000 characters |
| Standard context | 36,000 characters |
| Deep context | 48,000 characters |
| User request | 6,000 characters |
| Model input | 15,000 tokens by default |
| Model output | 1,200 tokens by default |
| Static findings | 50 per analysis |
| Dependency records | 800 per analysis |
| ZeroGPU allocation | 55 seconds per generation |
| Export retention | 2 hours, up to 120 files |

These are safety and reliability ceilings, not billing promises. Public GitHub API and ZeroGPU account quotas still apply.

## Runtime configuration

The application requires no visitor API key for public repositories or for the local model.

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_ID` | `Qwen/Qwen2.5-Coder-3B-Instruct` | Public Transformers model |
| `MAX_INPUT_TOKENS` | `15000` | Model input ceiling; clamped to 4,096–24,000 |
| `MAX_NEW_TOKENS` | `1200` | Generated token ceiling; clamped to 256–2,000 |
| `GITHUB_TOKEN` | unset | Optional owner-configured read-only token for a higher public GitHub API limit |
| `REPORT_DIRECTORY` | `/tmp/taj-ai-reports` | Ephemeral export directory |

If `GITHUB_TOKEN` is configured by the Space owner, it should be a fine-grained **read-only** Space secret. The product still rejects repositories reported as private so a public visitor can never use an owner credential to expose private source.

## Automatic deployment

`.github/workflows/sync-to-huggingface.yml` validates the source, mirrors GitHub to Hugging Face with the official `huggingface/hub-sync` action, and requests ZeroGPU after each push to `main` or `arena/01a00b5b-huggingface`.

- **Space:** [`madarauchihagmailcom/My`](https://huggingface.co/spaces/madarauchihagmailcom/My)
- **SDK:** Gradio
- **Hardware:** ZeroGPU (`zero-a10g`)

The workflow authenticates with the GitHub Actions secret `HF_TOKEN`. It must remain a fine-grained Hugging Face token restricted to read/write access for this one Space. Never commit it, print it, paste it into chat, or expose it as a Space variable.

Operational checks and rollback guidance are in [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## Local development

Python 3.12.12 matches the Space runtime.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

The core intelligence test suite requires only Requests and standard-library modules:

```bash
python -m pip install "requests>=2.32.0,<3.0.0"
python -m unittest discover -s tests -v
python -m compileall -q app.py code_assistant scripts tests
```

The test suite covers canonical repository parsing, network failure handling, cache expiration and eviction, path policy, request safety, secret redaction, prompt-injection neutralization, static rules, language and symbol extraction, relevance ranking, dependency parsers, context budgets, prompt trust boundaries, and safe report exports.

## Project structure

```text
app.py                              Gradio Pro UI and ZeroGPU generation
code_assistant/cache.py             Bounded thread-safe TTL/LRU cache
code_assistant/dependencies.py      Non-executing manifest parsers
code_assistant/domain.py            Typed immutable domain models
code_assistant/github_client.py     Hardened read-only GitHub REST client
code_assistant/inspection.py        Languages, profile, symbols, architecture
code_assistant/presentation.py      UI/report Markdown renderers
code_assistant/prompting.py         Trust-separated review/refinement prompts
code_assistant/ranking.py           Deterministic evidence ranking
code_assistant/reporting.py         Expiring Markdown/patch/JSON exports
code_assistant/repository.py        End-to-end preparation orchestrator
code_assistant/security.py          Policy, sanitization, static review rules
scripts/configure_space.py          ZeroGPU configuration after deployment
tests/                              Unit and pipeline regression tests
docs/                               Architecture, threat model, operations
```

## Contributing and security

See [`CONTRIBUTING.md`](CONTRIBUTING.md) before changing review rules or trust boundaries. Report security issues using the process in [`SECURITY.md`](SECURITY.md); do not place credentials, private repository source, or exploitable details in a public issue.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
