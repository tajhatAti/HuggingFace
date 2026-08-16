# Operations runbook

## Deployment path

A push to `main` or `arena/01a00b5b-huggingface` triggers `.github/workflows/sync-to-huggingface.yml`.

The workflow:

1. checks out the exact GitHub commit;
2. installs only Requests for core tests;
3. runs the unit suite and bytecode compilation;
4. installs the current Hugging Face CLI;
5. mirrors repository files to `madarauchihagmailcom/My` as a Gradio Space;
6. requests `zero-a10g` through `scripts/configure_space.py`.

Authentication is the repository Actions secret `HF_TOKEN`, restricted to this one Space. Never copy the token into a log, issue, commit, Space variable, or support conversation.

## Post-deployment verification

Verify in this order:

1. GitHub Action conclusion is green.
2. `Validate source and safety tests` passed.
3. `Mirror files to Hugging Face` passed.
4. `Request free ZeroGPU hardware` passed.
5. Space metadata reports SDK `gradio` and requested/current hardware `zero-a10g`.
6. Runtime stage reaches `RUNNING`.
7. Space homepage renders the Pro header and review controls.
8. Static inspection of a small known public repository populates all deterministic tabs.
9. One Standard AI review returns a structured report.
10. Markdown and JSON download; patch appears only when the report contains a valid unified diff.

Do not call deployment successful solely because GitHub Actions is green: Hugging Face build and startup are separate stages.

## Common failure modes

### GitHub Action: invalid token or forbidden

- Confirm the secret is named exactly `HF_TOKEN`.
- Confirm the token has read/write permission only for `madarauchihagmailcom/My`.
- Rotate the token if it may have been exposed.
- Never paste the value into diagnostics.

### Hub sync: invalid README metadata

Hugging Face restricts `colorFrom` and `colorTo` to documented values. Run tests/metadata checks before pushing and inspect the first YAML front matter block.

### Space build: dependency resolution conflict

The managed Gradio runtime and Transformers must agree on `huggingface_hub`. Current Gradio 6 uses Hub 1.x, so the application requires Transformers 5.x. Reproduce with a clean pip resolver before changing bounds.

### Space build: package/version unavailable

- Use Python 3.12.12, matching ZeroGPU compatibility.
- Avoid pinning managed Gradio, Torch, Spaces, or `huggingface_hub` in `requirements.txt`.
- Keep application dependencies bounded to supported major versions.

### Runtime: model unavailable

The deterministic tabs should remain usable. Check container logs for model download, architecture, dtype, or CUDA emulation errors. Keep model placement at module initialization for ZeroGPU's optimized transfer path.

### Runtime: GitHub rate limit

Anonymous GitHub REST usage is limited. Wait for reset or configure an owner-controlled fine-grained read-only token. The application must continue rejecting private repositories even if the token can see them.

### Runtime: long queue

Use Quick or Standard depth and keep one generation focused. The 55-second declared duration influences ZeroGPU scheduling. Avoid increasing it without measuring actual generation.

### No patch download

This is expected when the model recommends no code change or returns a malformed/non-unified diff. Markdown and JSON should still be available. Do not weaken patch validation merely to force a file.

## Monitoring signals

Without adding invasive telemetry, watch:

- GitHub Action conclusions and duration;
- Hugging Face build/runtime stage;
- startup/model initialization errors;
- GitHub 403/429 frequency;
- queue saturation and GPU timeout errors;
- report export errors;
- unexpected secret-redaction or prompt-injection counts in user-visible pipeline notes.

The application disables Gradio analytics and does not intentionally persist visitor prompts or source.

## Rollback

1. Identify the last known-good GitHub commit.
2. Revert the breaking commit on the fixed deployment branch; do not force-push shared history.
3. Let automatic sync deploy the revert.
4. Verify Action, Space build, runtime, UI, and one static inspection.
5. Document the root cause and add a regression test before reintroducing the change.

If the Space is actively exposing sensitive output, pause the Space from Hugging Face settings while preparing the revert. Rotate any credential that may have been disclosed.

## Credential rotation

1. Create a new fine-grained Hugging Face token scoped only to the target Space.
2. Replace the GitHub Actions `HF_TOKEN` secret.
3. Trigger a workflow dispatch or safe documentation commit.
4. Confirm sync and hardware steps pass.
5. Revoke the old token.

Do not maintain two long-lived active deployment tokens longer than necessary.

## Capacity and storage

- Model weights are managed by the Hugging Face runtime/cache.
- Repository source is held only in bounded process memory and Gradio session state.
- Public metadata/source cache has finite entries and TTL.
- Exports use `/tmp/taj-ai-reports`, 0600 files, two-hour retention, and a 120-file cap.
- No database, vector store, repository clone, or long-lived worker is required.

The design should not attempt to consume all available RAM or disk. Production reliability requires headroom for the runtime, model, concurrent sessions, dependency installation, and build layers.
