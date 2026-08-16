# Contributing

## Principles

1. Preserve the read-only, non-executing product boundary.
2. Prefer a small explicit parser/rule over a broad dependency.
3. Bound all visitor-controlled work.
4. Treat repository text and model output as untrusted.
5. Add regression tests for every safety, parser, ranking, or export change.
6. Never add credentials or private repository fixtures.

## Development workflow

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install "requests>=2.32.0,<3.0.0"
python -m unittest discover -s tests -v
python -m compileall -q app.py code_assistant scripts tests
git diff --check
```

Install full runtime requirements only when testing the Gradio/model integration.

## Adding a language

- Add extension/name detection in `inspection.py`.
- Add symbol extraction only if it is bounded and cannot execute source.
- Extend path tests, language tests, malformed-input tests, and profile tests.
- Do not invoke a repository-provided compiler, language server, formatter, or build tool in the public Space.

## Adding a dependency parser

- Parse data text only.
- Avoid loaders with object construction or code hooks.
- Cap records and field sizes.
- Fail closed to an empty inventory on malformed input.
- State clearly that inventory is not live vulnerability intelligence.
- Add valid, malformed, grouping, pinning, and deduplication tests.

## Adding a static rule

A rule must include stable ID, severity, category, title, defensive recommendation, confidence, and optional language scope.

Rules are review leads. Keep patterns narrow enough to avoid flooding reports, redact evidence, and cap matches. Add positive, negative, language-scope, and secret-evidence tests.

## Changing ranking

Ranking must remain deterministic. Test task relevance, explicit paths, mode signals, architectural diversity, blocked paths, stable ordering, and hard limits. Do not make the public Space clone and embed every repository file.

## UI changes

Maintain responsive behavior, Bangla/Banglish usability, clear progress/error states, static-only access without GPU, and transparent safety limitations. Verify all tabs and export outputs after deployment.

## Deployment-sensitive files

Changes under `.github/workflows/` may require GitHub App workflow permission and manual owner review. Never place the `HF_TOKEN` value in YAML. Hugging Face front matter uses a restricted color vocabulary and must retain Python 3.12.12 for ZeroGPU compatibility.

## Definition of done

- Unit suite passes.
- Compilation and whitespace checks pass.
- No token/private key is present in the diff.
- Dependency resolution remains compatible with the managed runtime.
- GitHub Action passes.
- Hugging Face build reaches `RUNNING` on `zero-a10g`.
- Live UI and one bounded public-repository inspection are verified.
- Documentation and threat model reflect any changed trust boundary.
