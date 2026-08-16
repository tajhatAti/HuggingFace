"""Safety policy, secret redaction, prompt-injection neutralization, and static review rules.

All checks are deterministic and operate on text only.  They never import,
execute, compile, install, or otherwise trust repository code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from .domain import Finding, Severity
from .inspection import detect_language

MAX_TASK_CHARS = 6_000
MAX_STATIC_FINDINGS_PER_FILE = 8
MAX_STATIC_FINDINGS_TOTAL = 50

TEXT_EXTENSIONS = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cxx",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".dart",
    ".scala",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".ps1",
    ".sql",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
    ".astro",
    ".json",
    ".jsonc",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".graphql",
    ".gql",
    ".proto",
    ".md",
    ".mdx",
    ".rst",
    ".txt",
}

SPECIAL_TEXT_FILENAMES = {
    "dockerfile",
    "makefile",
    "justfile",
    "gemfile",
    "rakefile",
    "procfile",
    "jenkinsfile",
}

BLOCKED_PATH_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".env",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".next",
    ".nuxt",
    ".output",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".cache",
    "target",
}

BLOCKED_FILENAMES = {
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials.json",
    "service-account.json",
    "secrets.json",
    "master.key",
    "keystore",
}

LOW_VALUE_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "bun.lockb",
    "poetry.lock",
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "packages.lock.json",
    "go.sum",
}

MALICIOUS_PATTERNS = (
    r"\bransomware\b",
    r"\bcredential\s*(?:stealer|harvester)\b",
    r"\bsteal\s+(?:passwords?|tokens?|cookies?|credentials?|wallets?)\b",
    r"\bphishing\s+(?:page|kit|site|campaign|template)\b",
    r"\bkeylogger\b",
    r"\bbotnet\b",
    r"\bcrypto\s*miner\b",
    r"\bcryptominer\b",
    r"\breverse\s+shell\b",
    r"\bremote\s+access\s+trojan\b",
    r"\bdisable\s+(?:antivirus|defender|edr|firewall)\b",
    r"\bbypass\s+(?:authentication|2fa|mfa|captcha|rate.?limit)\b",
    r"\bexfiltrat(?:e|ion)\s+(?:data|secrets?|tokens?|credentials?|cookies?)\b",
    r"\bmalware\b",
    r"\btrojan\b",
    r"\bddos\b",
    r"\bspam\s+(?:bot|campaign|sender)\b",
    r"\bচুরি\s*(?:কর|করা|করে)",
    r"\bপাসওয়ার্ড\s*চুরি\b",
)

DEFENSIVE_TERMS = re.compile(
    r"\b(?:fix|patch|prevent|detect|remove|block|secure|audit|review|mitigat|protect|defen[cs]e|"
    r"hardening|incident|forensic|sanitize|validate)\w*\b|"
    r"(?:নিরাপত্তা|প্রতিরোধ|বন্ধ|সমাধান|ঠিক|রিভিউ|অডিট|সুরক্ষিত)",
    re.IGNORECASE,
)

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(?:sk|rk|pk)-(?:live|test|proj)?-?[A-Za-z0-9_-]{18,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s'\"<>]{8,}"),
)

PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----.*?"
    r"-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
    re.DOTALL,
)

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:export\s+)?[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|"
    r"PRIVATE_KEY|CLIENT_SECRET|ACCESS_KEY)[A-Z0-9_]*\s*[=:]\s*)"
    r"(?P<quote>['\"]?)(?P<value>[^\s,'\"}]{8,})(?P=quote)"
)

PROMPT_INJECTION_RE = re.compile(
    r"(?i)(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|above|system)\s+"
    r"(?:instructions?|prompts?|rules?)|"
    r"(?:system|developer)\s+message\s*:|"
    r"you\s+are\s+now\s+(?:dan|unrestricted|an?\s+assistant)|"
    r"reveal\s+(?:the\s+)?(?:system\s+prompt|hidden\s+instructions?)|"
    r"do\s+not\s+follow\s+(?:the\s+)?user"
)

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class UnsafeRequestError(ValueError):
    """Raised when a request clearly asks for harmful or unauthorized tooling."""


def is_safe_path(path: str) -> bool:
    """Allow bounded source/documentation paths while excluding secrets and generated trees."""

    if not path or "\x00" in path or "\\" in path:
        return False
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return False
    lower_parts = {part.casefold() for part in pure.parts}
    name = pure.name.casefold()

    if lower_parts & BLOCKED_PATH_PARTS:
        return False
    if name in BLOCKED_FILENAMES or name in LOW_VALUE_FILENAMES:
        return False
    if name.startswith(".env") or name.endswith(
        (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".der", ".crt", ".cer")
    ):
        return False
    return pure.suffix.casefold() in TEXT_EXTENSIONS or name in SPECIAL_TEXT_FILENAMES


def ensure_safe_request(task: str) -> None:
    normalized = (task or "").strip()
    if len(normalized) < 8:
        raise ValueError("কী পরিবর্তন চান, অন্তত এক বাক্যে লিখুন।")
    if len(normalized) > MAX_TASK_CHARS:
        raise ValueError(f"Request অনেক বড়; {MAX_TASK_CHARS:,} অক্ষরের মধ্যে লিখুন।")
    if CONTROL_CHARS_RE.search(normalized):
        raise ValueError("Request-এ invalid control character আছে।")

    hits = [pattern for pattern in MALICIOUS_PATTERNS if re.search(pattern, normalized, re.IGNORECASE)]
    if hits and not DEFENSIVE_TERMS.search(normalized):
        raise UnsafeRequestError(
            "এই request malicious বা unauthorized tooling তৈরি করতে পারে, তাই process করা হবে না। "
            "Defensive security review বা নিরাপদ fix চাইলে সেটি পরিষ্কারভাবে লিখুন।"
        )


def count_secret_matches(content: str) -> int:
    count = sum(len(pattern.findall(content)) for pattern in SECRET_VALUE_PATTERNS)
    count += len(PRIVATE_KEY_BLOCK_RE.findall(content))
    count += len(SECRET_ASSIGNMENT_RE.findall(content))
    return count


def redact_secrets(content: str) -> str:
    """Remove recognized credentials while preserving enough syntax for review."""

    redacted = PRIVATE_KEY_BLOCK_RE.sub("<REDACTED_PRIVATE_KEY>", content)
    for pattern in SECRET_VALUE_PATTERNS:
        redacted = pattern.sub("<REDACTED_SECRET>", redacted)

    def replace_assignment(match: re.Match[str]) -> str:
        quote = match.group("quote") or ""
        return f"{match.group('prefix')}{quote}<REDACTED_SECRET>{quote}"

    return SECRET_ASSIGNMENT_RE.sub(replace_assignment, redacted)


def neutralize_prompt_injection(content: str) -> tuple[str, int]:
    """Replace strong repository-embedded instruction attacks line by line."""

    output: list[str] = []
    count = 0
    for line in content.splitlines(keepends=True):
        if PROMPT_INJECTION_RE.search(line):
            newline = "\n" if line.endswith("\n") else ""
            output.append("<POTENTIAL_PROMPT_INJECTION_REDACTED>" + newline)
            count += 1
        else:
            output.append(line)
    return "".join(output), count


def sanitize_repository_content(content: str) -> tuple[str, int, int]:
    secret_count = count_secret_matches(content)
    redacted = redact_secrets(content)
    neutralized, injection_count = neutralize_prompt_injection(redacted)
    neutralized = CONTROL_CHARS_RE.sub("", neutralized)
    return neutralized, secret_count, injection_count


def sanitize_evidence(value: str, limit: int = 220) -> str:
    clean = redact_secrets(CONTROL_CHARS_RE.sub("", value)).strip()
    clean = " ".join(clean.split())
    if len(clean) > limit:
        clean = clean[: limit - 1] + "…"
    return clean


@dataclass(frozen=True)
class StaticRule:
    rule_id: str
    pattern: re.Pattern[str]
    severity: Severity
    category: str
    title: str
    recommendation: str
    languages: frozenset[str] = frozenset()
    confidence: str = "medium"


STATIC_RULES: tuple[StaticRule, ...] = (
    StaticRule(
        "PY-SHELL-TRUE",
        re.compile(r"\b(?:subprocess\.(?:run|call|Popen)|check_(?:call|output))\s*\([^\n]*shell\s*=\s*True"),
        Severity.HIGH,
        "Command execution",
        "Shell command construction requires review",
        "Pass an argument list without shell=True and strictly validate any user-controlled values.",
        frozenset({"Python"}),
        "high",
    ),
    StaticRule(
        "PY-EVAL-EXEC",
        re.compile(r"(?<![A-Za-z0-9_])(?:eval|exec)\s*\("),
        Severity.HIGH,
        "Code execution",
        "Dynamic code execution detected",
        "Replace eval/exec with a typed parser or a small explicit dispatch table.",
        frozenset({"Python"}),
    ),
    StaticRule(
        "PY-PICKLE-LOAD",
        re.compile(r"\b(?:pickle|dill)\.loads?\s*\("),
        Severity.HIGH,
        "Deserialization",
        "Potentially unsafe object deserialization",
        "Do not deserialize untrusted bytes; prefer a schema-validated data format such as JSON.",
        frozenset({"Python"}),
    ),
    StaticRule(
        "PY-YAML-LOAD",
        re.compile(r"\byaml\.load\s*\([^\n]*(?!Loader\s*=\s*(?:SafeLoader|CSafeLoader))"),
        Severity.MEDIUM,
        "Deserialization",
        "YAML loading may construct unsafe objects",
        "Use yaml.safe_load for untrusted or user-supplied YAML.",
        frozenset({"Python"}),
    ),
    StaticRule(
        "TLS-VERIFY-DISABLED",
        re.compile(r"\bverify\s*=\s*False\b|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0"),
        Severity.HIGH,
        "Transport security",
        "TLS certificate verification appears disabled",
        "Restore certificate verification and configure the correct CA bundle instead.",
        confidence="high",
    ),
    StaticRule(
        "WEAK-HASH",
        re.compile(r"\b(?:hashlib\.)?(?:md5|sha1)\s*\("),
        Severity.LOW,
        "Cryptography",
        "Legacy hash algorithm used",
        "For security-sensitive hashing use SHA-256 or a purpose-built password KDF; document non-security uses.",
        frozenset({"Python"}),
    ),
    StaticRule(
        "WEB-INNERHTML",
        re.compile(r"\.(?:innerHTML|outerHTML)\s*=|dangerouslySetInnerHTML\s*="),
        Severity.MEDIUM,
        "Browser security",
        "HTML injection sink requires review",
        "Render text through framework escaping or sanitize trusted markup with a maintained allowlist sanitizer.",
        frozenset({"JavaScript", "TypeScript", "Vue", "Svelte"}),
    ),
    StaticRule(
        "JS-DYNAMIC-EVAL",
        re.compile(r"(?<![A-Za-z0-9_])(?:eval|Function)\s*\("),
        Severity.HIGH,
        "Code execution",
        "Dynamic JavaScript execution detected",
        "Replace dynamic execution with explicit parsing and a constrained operation map.",
        frozenset({"JavaScript", "TypeScript", "Vue", "Svelte"}),
    ),
    StaticRule(
        "CORS-WILDCARD",
        re.compile(r"(?:allow_origins|Access-Control-Allow-Origin|origin)\s*[:=]\s*[\[\(]?\s*['\"]\*['\"]"),
        Severity.MEDIUM,
        "Access control",
        "Wildcard CORS policy requires review",
        "Allow only the exact trusted browser origins and review credential handling.",
    ),
    StaticRule(
        "DEBUG-ENABLED",
        re.compile(r"\b(?:DEBUG|debug)\s*[:=]\s*(?:True|true|1)\b"),
        Severity.LOW,
        "Configuration",
        "Debug mode appears enabled",
        "Disable debug mode in production and keep environment-specific settings outside source.",
    ),
    StaticRule(
        "SQL-INTERPOLATION",
        re.compile(
            r"(?i)(?:execute|query)\s*\(\s*(?:f['\"]|['\"][^'\"]*(?:SELECT|INSERT|UPDATE|DELETE)[^'\"]*%|`[^`]*\$\{)"
        ),
        Severity.HIGH,
        "Injection",
        "SQL appears to be assembled with string interpolation",
        "Use parameterized statements and validate identifiers through an explicit allowlist.",
    ),
    StaticRule(
        "PATH-TRAVERSAL-SINK",
        re.compile(r"\b(?:open|readFile|writeFile|send_file|sendFile)\s*\([^\n]*(?:request|req\.|params|query|form)"),
        Severity.MEDIUM,
        "File access",
        "User-controlled path may reach a file operation",
        "Resolve against a fixed base directory and reject traversal, absolute paths, and symlink escapes.",
    ),
    StaticRule(
        "TOKEN-LOCALSTORAGE",
        re.compile(r"localStorage\.(?:setItem|getItem)\s*\(\s*['\"][^'\"]*(?:token|jwt|session)"),
        Severity.MEDIUM,
        "Session security",
        "Authentication material appears stored in localStorage",
        "Prefer short-lived server sessions in Secure, HttpOnly, SameSite cookies when the architecture allows it.",
        frozenset({"JavaScript", "TypeScript", "Vue", "Svelte"}),
    ),
    StaticRule(
        "DOCKER-ROOT-USER",
        re.compile(r"(?i)^\s*USER\s+(?:root|0)\s*$"),
        Severity.LOW,
        "Container hardening",
        "Container explicitly runs as root",
        "Create and switch to a dedicated unprivileged runtime user.",
        frozenset({"Dockerfile"}),
    ),
)


def _secret_finding(path: str, line_number: int, line: str) -> Finding | None:
    if not any(pattern.search(line) for pattern in SECRET_VALUE_PATTERNS) and not SECRET_ASSIGNMENT_RE.search(line):
        return None
    return Finding(
        rule_id="SECRET-HARDCODED",
        severity=Severity.CRITICAL,
        category="Secrets",
        title="Potential hard-coded credential",
        path=path,
        line=line_number,
        evidence=sanitize_evidence(line),
        recommendation="Revoke exposed credentials, remove them from history, and load replacements from a secret store.",
        confidence="high",
    )


def scan_static_findings(path: str, content: str) -> tuple[Finding, ...]:
    """Return bounded heuristic findings; these are leads, not claims of exploitability."""

    language = detect_language(path)
    findings: list[Finding] = []
    seen_rules: set[tuple[str, int]] = set()

    for line_number, line in enumerate(content.splitlines(), 1):
        secret = _secret_finding(path, line_number, line)
        if secret:
            key = (secret.rule_id, line_number)
            if key not in seen_rules:
                findings.append(secret)
                seen_rules.add(key)

        for rule in STATIC_RULES:
            if rule.languages and language not in rule.languages:
                continue
            if not rule.pattern.search(line):
                continue
            key = (rule.rule_id, line_number)
            if key in seen_rules:
                continue
            findings.append(
                Finding(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    category=rule.category,
                    title=rule.title,
                    path=path,
                    line=line_number,
                    evidence=sanitize_evidence(line),
                    recommendation=rule.recommendation,
                    confidence=rule.confidence,
                )
            )
            seen_rules.add(key)
            if len(findings) >= MAX_STATIC_FINDINGS_PER_FILE:
                return tuple(findings)
    return tuple(findings)


def sanitize_model_output(value: str, max_chars: int = 60_000) -> str:
    """Apply final credential and control-character filtering to model text."""

    clean = redact_secrets(CONTROL_CHARS_RE.sub("", value or ""))
    if len(clean) > max_chars:
        clean = clean[:max_chars].rstrip() + "\n\n_Output truncated at the safety limit._"
    return clean.strip()
