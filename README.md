---
title: Taj AI Code Assistant
emoji: 🧠
colorFrom: indigo
colorTo: cyan
sdk: gradio
app_file: app.py
python_version: 3.12.12
pinned: false
license: apache-2.0
models:
  - Qwen/Qwen2.5-Coder-3B-Instruct
---

# Taj AI Code Assistant

A safe, read-only AI assistant for reviewing **public GitHub repositories**. Give it a repository and a change request; it selects likely relevant files, removes secret-like values, and uses Qwen2.5-Coder-3B-Instruct to produce a diagnosis, plan, suggested diff, tests, and risks.

The interface and errors are written for a Bangla/Banglish-speaking beginner.

## What it does

- Reads public repository metadata and source through GitHub HTTPS APIs.
- Selects up to eight relevant text/source files without cloning the repository.
- Refuses `.env`, private-key, binary, generated, lock, and oversized files.
- Redacts common token formats and secret assignments before model inference.
- Generates a review and proposed patch on Hugging Face ZeroGPU.
- Supports Bangla, Banglish, or English requests.

## Deliberate safety boundaries

This public Space does **not**:

- execute repository code or shell commands;
- accept arbitrary URLs or act as a network proxy;
- write to GitHub, commit, merge, or deploy user repositories;
- request a user's GitHub/Hugging Face credentials;
- produce clearly malicious, phishing, credential-theft, unauthorized-access, spam, cryptomining, or evasion tooling.

These boundaries keep it an ML code-review demo rather than a remote-management or arbitrary-code-execution service.

## Automatic deployment

`.github/workflows/sync-to-huggingface.yml` uses Hugging Face's official `huggingface/hub-sync` action. A push to `main` or the Arena work branch mirrors this repository to:

- **Space:** `madarauchihagmailcom/My`
- **SDK:** Gradio
- **Hardware requested after sync:** ZeroGPU (`zero-a10g`)

The workflow expects a repository secret named `HF_TOKEN` containing a **fine-grained Hugging Face token with write access only to that Space**. No token is stored in this repository.

## Runtime configuration

The app needs no API key for public repositories or for the bundled local model. Optional variables:

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_ID` | `Qwen/Qwen2.5-Coder-3B-Instruct` | Public Transformers model |
| `MAX_INPUT_TOKENS` | `14000` | Maximum prompt tokens |
| `MAX_NEW_TOKENS` | `900` | Maximum generated tokens |
| `GITHUB_TOKEN` | unset | Optional read-only token for higher GitHub API limits |

If `GITHUB_TOKEN` is used, make it a fine-grained read-only Space secret. It is not needed for light usage.

## Local checks

The core safety and repository-selection logic has no model dependency:

```bash
python -m unittest discover -s tests -v
python -m compileall -q app.py code_assistant scripts tests
```

Running the full UI locally additionally requires Gradio, PyTorch, `spaces`, and the packages in `requirements.txt`.
