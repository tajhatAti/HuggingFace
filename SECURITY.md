# Security policy

## Supported version

The current `arena/01a00b5b-huggingface` deployment branch and the revision running on the public Hugging Face Space receive security fixes during active development.

## Reporting a vulnerability

Do not publish live credentials, private repository source, personal data, or a weaponized proof of concept in a public GitHub issue.

Use GitHub's private vulnerability reporting feature for `tajhatAti/HuggingFace` when available. Include:

- affected commit and component;
- impact and required attacker access;
- minimal non-destructive reproduction using synthetic data;
- whether the public Space is currently affected;
- suggested mitigation if known.

Never send a GitHub or Hugging Face token. If a token was exposed, revoke it immediately before reporting.

## Security design commitments

The public product will preserve:

- canonical GitHub-only network access;
- public repositories only;
- no repository, APK, archive, release asset, or workflow execution;
- no shell, package installation, build, archive extraction, or clone;
- no visitor credential collection or owner-token proxying of protected GitHub content;
- no repository write/commit/push/workflow authority;
- immutable commit/blob identity for proxied files and selected ZIPs;
- repository-scoped official links for full archives, releases, and Actions;
- bounded trees, lists, files, selected ZIPs, prompts, outputs, caches, queues, and artifacts;
- credential/key path blocking in RepoVault and pre/post secret redaction in AI review;
- explicit untrusted-source prompt boundaries;
- transparent distinction between metadata, heuristics, and confirmed facts.

Changes that weaken one of these commitments require an explicit threat-model update and dedicated regression tests.

## Out of scope

- Findings that only reproduce after an operator intentionally removes documented safety limits.
- Model quality disagreements without a concrete safety or integrity impact.
- Public information already visible in the selected public GitHub repository.
- Denial of service requiring control of Hugging Face or GitHub infrastructure.
- Automated scanner reports without a validated affected path.
