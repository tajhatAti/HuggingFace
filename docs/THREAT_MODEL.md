# Threat model

## Scope

This document covers the public Hugging Face Space, its GitHub read path, model prompt, UI state, and downloadable reports. It does not claim to secure a future self-hosted execution agent or GitHub write integration.

## Assets

- Availability of the public Space and its ZeroGPU quota.
- Confidentiality of Space-owner deployment credentials.
- Integrity of review output and safety boundaries.
- Visitor trust that repository code is not executed.
- Public GitHub API quota.
- Ephemeral report files.

The application is not designed to receive private source, production credentials, personal data, or proprietary artifacts.

## Trust zones

### Trusted application code

The checked-in Python package, deployment workflow, fixed model identifier, and owner-configured Space settings are trusted subject to normal supply-chain review.

### Partially trusted user request

A visitor controls repository identifier, branch, task, mode, depth, and evidence limit. Inputs are length- and format-bounded. Requests with clear malicious intent are refused, while defensive security work remains allowed.

### Untrusted repository

Names, paths, metadata, manifests, source, documentation, comments, and embedded instructions are hostile data. They can attempt prompt injection, contain credentials, be syntactically invalid, or be extremely large.

### Probabilistic model output

The model can be incorrect, omit context, produce malformed patches, or echo dangerous patterns. Output is a suggestion, not an executed change. Final secret redaction and bounded export validation apply.

### External services

GitHub and Hugging Face are external dependencies. Their failures, rate limits, and response changes must fail safely.

## Primary threats and controls

### Server-side request forgery

**Threat:** A repository or branch input redirects the server to an internal/arbitrary host.

**Controls:** Canonical full-match GitHub parser, hard-coded API root, percent-encoded path components, redirect rejection, and no use of repository-provided download URLs.

### Repository code execution

**Threat:** Malicious source triggers import hooks, package scripts, builds, tests, shells, or deserialization.

**Controls:** Contents API text only; no clone, import, package install, compiler, shell, subprocess, archive extraction, or runtime execution. Python symbol inspection uses `ast.parse`, not import. Manifest parsers use data-only standard-library operations.

### Prompt injection

**Threat:** Source comments/docs instruct the model to reveal prompts, ignore policy, or change roles.

**Controls:** Strong injection lines are replaced; prompt trust boundaries mark every file as untrusted; system and user instructions repeat non-compliance requirements; files cannot invoke tools; output receives final sanitization.

### Credential exposure

**Threat:** Public repositories accidentally contain live credentials that appear in prompts, logs, findings, model output, or reports.

**Controls:** Sensitive filenames and extensions are not read; known token/private-key/URI/assignment patterns are redacted before model use; evidence rendering is redacted; model output is redacted again; reports exclude raw source and full prompts. Logs do not print source or tokens.

Redaction is defense in depth, not a guarantee. Public-repository owners must revoke any committed credential and remove it from history.

### Private repository confused deputy

**Threat:** An owner-configured GitHub token allows an anonymous visitor to read private source through the Space.

**Controls:** Metadata is checked first and any repository marked private is rejected before tree/file access. Private metadata is not shared through the public cache. Visitors are never asked for tokens.

### Resource exhaustion

**Threat:** Huge repositories/files, expensive repeated analysis, dependency explosions, report accumulation, or GPU queue abuse exhaust resources.

**Controls:** Hard tree/file/context/output/finding/dependency bounds; queue limit; ZeroGPU duration; TTL/LRU cache; expiring/count-bounded report directory; no persistent vector index or repository clone.

### Malicious model request

**Threat:** A visitor asks for credential theft, malware, phishing, unauthorized access, destructive automation, or evasion.

**Controls:** Deterministic intent screening, model safety policy, defensive-only security framing, no execution/write tools, and no arbitrary network access.

### Misleading security claims

**Threat:** Regex findings or model text are presented as confirmed vulnerabilities or successful tests.

**Controls:** UI and prompt label findings as heuristic leads; output contract requires confidence and evidence; static inventory states it is not an advisory lookup; model is told never to claim execution; exported verification notice repeats limitations.

### Patch misuse

**Threat:** A generated patch is automatically applied or contains unrelated/destructive changes.

**Controls:** No write integration. Patch export requires plausible unified-diff structure, is bounded, and carries a review warning. A maintainer must inspect and test it separately.

### Cross-user report access

**Threat:** One visitor guesses another visitor's report filename.

**Controls:** Randomized names, restrictive directory/file modes, Gradio-managed file delivery, no index, short retention, and no raw source. For stronger tenancy guarantees, deploy a dedicated authenticated service rather than a shared public Space.

## Abuse cases intentionally unsupported

- Public shell or remote desktop.
- Arbitrary command, test, build, or package execution.
- Visitor-provided tokens or private repository proxying.
- Automatic commit, push, merge, release, or deployment.
- Tunnels, generic proxies, botnet control, credential collection, spam, cryptomining, or security bypass.

## Residual risks

- Novel credential formats may evade regex redaction.
- Prompt injection can influence a language model despite layered instructions.
- Static heuristics can produce false positives and false negatives.
- Public GitHub data can contain personal or copyrighted material.
- Model output can be incorrect or insecure.
- Shared public infrastructure can experience queue and rate-limit contention.

The residual-risk response is bounded evidence, no execution/write authority, transparent limitations, output review, and rapid rollback through Git/Hugging Face revisions.
