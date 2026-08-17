# Threat model

## Scope

This document covers the public Hugging Face Space, repository explorer/download path, GitHub API client, temporary files, release and Actions links, and the secondary AI review workspace. It does not claim to secure a future private-repository service, execution sandbox, GitHub write integration, or generic file proxy.

## Assets

- Visitor trust that repository files, APKs, archives, and workflows are never executed.
- Confidentiality of Space-owner deployment/API credentials.
- Isolation and short lifetime of generated individual/selected downloads.
- Integrity of repository/ref/blob identity shown to a visitor.
- Availability of CPU, RAM, disk, public GitHub quota, and ZeroGPU quota.
- Integrity and confidentiality controls around AI review prompts and exports.

The application is not designed to receive private source, visitor tokens, production credentials, personal data, or proprietary artifacts.

## Trust zones

### Trusted application

Checked-in Python, fixed GitHub API roots, deployment workflow, fixed model identifier, and owner-configured Space settings are trusted subject to normal review.

### User-controlled identifiers

A visitor controls repository, ref, file search, selected paths from a server-provided list, commit selection, workflow-run selection, and AI review request. All remain untrusted and format/resource bounded.

### Untrusted repository and artifacts

Paths, names, metadata, source bytes, binary files, release names/assets, workflow names, commit messages, manifests, comments, and embedded instructions are hostile data. They can be malformed, huge, misleading, secret-bearing, prompt-injecting, or executable on another system.

### GitHub

GitHub is the sole repository data provider and an external dependency. API output is mapped into bounded records. Redirects are rejected. Large source archives, release assets, and protected artifact downloads remain on official GitHub pages.

### Probabilistic model

AI output can be wrong, incomplete, insecure, or malformed. It is a suggestion and has no execution/write tool. Final redaction and export validation still apply.

## Primary threats and controls

### Server-side request forgery and open proxying

**Threat:** Input causes the Space to request an internal/arbitrary host or relay arbitrary large data.

**Controls:** Full-match GitHub parser, fixed API root, encoded path/query values, redirect rejection, no visitor URL fetch, no generic download endpoint, bounded blob reads, and first-party links for full archives/releases/Actions.

### Private-repository confused deputy

**Threat:** An owner-configured token lets anonymous visitors read private source.

**Controls:** Repository metadata is checked first and any repository reported private is rejected before tree/blob access. Visitors cannot supply tokens. Private metadata is not placed in the public cache. Protected artifact downloads are never proxied with an owner token.

### Repository, APK, or workflow execution

**Threat:** Malicious content triggers an import, build, package script, archive extraction, shell, workflow, APK, parser gadget, or executable preview.

**Controls:** No clone, checkout, subprocess, import, compiler, package manager, test runner, workflow dispatch, APK runner, archive extraction, or object-deserializing parser. Binary files have metadata-only preview. ZIP creation writes bytes without interpreting them. The AI symbol parser never imports source.

### Path traversal in selected archives

**Threat:** A crafted Git path writes outside the ZIP namespace or collides with a server path.

**Controls:** Selections must exist in the immutable tree map. Empty/dot/dot-dot/absolute/backslash/NUL paths are rejected before `writestr`. The ZIP is newly created under a randomized server path and is never extracted server-side.

### Commit/ref confusion

**Threat:** The UI claims to show one ref while downloading another moving branch state.

**Controls:** The recursive tree response resolves an exact commit SHA. Individual files use tree-provided blob SHAs. Complete archives use the exact commit, not the branch. Historical browsing replaces session snapshot atomically. UI surfaces requested ref and exact SHA.

### Credential exposure from public source

**Threat:** A public repository accidentally contains active credentials that RepoVault previews, packages, logs, caches, or sends to the model.

**Controls:** Common secret/key filenames and extensions are listed but not previewed or included in selected ZIPs. Large blob bytes are not globally cached. Logs contain no source bytes. The AI path applies stronger path exclusion and pre/post secret redaction. Full GitHub archives are clearly identified as direct, uninspected first-party downloads.

These controls are defense in depth, not a guarantee. Repository owners must revoke committed credentials and remove them from history.

### Malicious browser links

**Threat:** Repository metadata injects a phishing/external download link.

**Controls:** Repository, commit, archive, run, artifact, and release-note links are built from the validated owner/repository. Release asset links are allowed only for HTTPS `github.com` URLs under that repository's release-download path. Markdown labels are escaped and length bounded.

### Temporary-file cross-user access

**Threat:** One visitor guesses another generated file or old files accumulate.

**Controls:** Random names, 0700 directory, 0600 files where supported, no index, Gradio-managed file delivery, two-hour expiry, 120-file cap, no persistent storage, and no raw AI prompt/source export. Stronger tenancy would require authenticated isolated storage.

### Resource exhaustion

**Threat:** Huge trees/files, many selected blobs, compression, repeated API calls, excessive sessions, or AI queue use exhausts resources.

**Controls:** 20,000-file tree ceiling; 500/1,000 display bounds; 25 MB individual file; 20-file/50 MB selected ZIP; bounded commit/release/run/artifact lists; shrinking per-ZIP byte budget; TTL/LRU metadata cache; queue limit; expiring files; and bounded ZeroGPU duration. Full repositories/releases are not proxied.

### Actions authentication bypass

**Threat:** The Space uses an owner token to make protected Actions artifacts anonymously downloadable.

**Controls:** Only artifact metadata is read through the public client. UI links to official GitHub run/artifact pages. GitHub enforces its own sign-in and permissions. No visitor or owner token is added to browser links or responses.

### Prompt injection

**Threat:** Source tells the AI to reveal prompts, ignore policy, or act on embedded instructions.

**Controls:** AI evidence excludes sensitive paths, recognized injection lines are replaced, every file is marked untrusted, the model has no tools, and output is sanitized. RepoVault preview itself does not invoke the model.

### Misleading analysis

**Threat:** Static or model output is presented as executed/confirmed.

**Controls:** UI and prompt call deterministic findings heuristic leads; the model contract forbids claims of execution; reports include verification guidance; no patch is auto-applied.

## Abuse cases intentionally unsupported

- Public shells, remote desktops, tunnels, generic proxies, or remote management.
- Arbitrary commands, builds, tests, package installs, APK execution, or workflow dispatch.
- Private repository access or visitor token collection.
- Owner-token proxying of protected Actions artifacts.
- Automatic commit, push, PR, merge, release, or deployment.
- Credential collection, phishing, malware delivery, destructive tooling, cryptomining, spam, or security restriction bypass.

## Residual risks

- Novel credential filenames may evade sensitive-path checks.
- Direct GitHub archives can contain accidentally committed credentials because RepoVault does not inspect them.
- Public repositories/assets can contain unlawful, malicious, copyrighted, or personal material.
- A visitor can choose to run a downloaded file elsewhere; the Space cannot secure that external environment.
- GitHub API/URL behavior can change.
- Markdown or browser download behavior can have upstream vulnerabilities.
- Shared infrastructure can experience quota and denial-of-service contention.
- Static and model review can produce false positives/negatives.

The response is a narrow GitHub-only boundary, immutable identity, no execution/write authority, strict limits, first-party large downloads, transparent warnings, tests, and rollback through versioned deployment.
