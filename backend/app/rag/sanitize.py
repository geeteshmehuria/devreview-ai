"""
What may be indexed, and secret redaction.

Repository content is untrusted and ends up in two external services (the embedding API and the
chat LLM), so files that usually hold secrets are never read, and secret-looking strings are
replaced before anything is stored or sent.
"""

import re
from pathlib import PurePosixPath

from app.services.repository_service import ANALYZED_EXTENSIONS

# Docs and config often answer "how do I run / configure this?" questions.
EXTRA_EXTENSIONS = {
    ".md", ".mdx", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg",
    ".sql", ".sh", ".html", ".css", ".scss", ".prisma", ".graphql",
}
EXTRA_FILENAMES = {"Dockerfile", "Makefile", "Procfile"}
INDEXED_EXTENSIONS = ANALYZED_EXTENSIONS | EXTRA_EXTENSIONS

SECRET_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".crt", ".cer", ".der", ".jks", ".keystore"}
LOCK_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock", "uv.lock",
    "Cargo.lock", "composer.lock", "Gemfile.lock", "go.sum", "bun.lockb",
}
MAX_LINE_CHARS = 1_000  # a line this long means minified/generated code


def should_index_path(rel_path: str) -> bool:
    """Decide from the path alone. Deny rules run before allow rules."""
    p = PurePosixPath(rel_path)
    name = p.name
    if name.startswith(".env") or name.startswith("id_rsa") or name.startswith("id_ed25519"):
        return False
    if p.suffix.lower() in SECRET_EXTENSIONS or name in LOCK_FILES:
        return False
    if ".min." in name or name.endswith(".map"):
        return False
    return name in EXTRA_FILENAMES or p.suffix.lower() in INDEXED_EXTENSIONS


def should_index_content(text: str, max_chars: int) -> bool:
    """Reject binaries, oversized files and minified files after reading."""
    if not text.strip() or len(text) > max_chars or "\x00" in text:
        return False
    return max(map(len, text.splitlines()), default=0) <= MAX_LINE_CHARS


REDACTED = "[REDACTED]"

_SECRET_PATTERNS = [
    # PEM private key blocks (multi-line)
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                          # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),                # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),              # GitHub fine-grained PAT
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),                    # Google API key
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}"),       # OpenAI / Anthropic keys
    re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}\b"),      # Stripe keys
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"),             # Slack tokens
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWTs
]
# password = "hunter2hunter2" → keep the name, hide the quoted literal (calls like get_password() stay).
_SECRET_NAME = r"[\w.-]*(?:secret|password|passwd|pwd|token|api[_-]?key|access[_-]?key|private[_-]?key|credentials?)[\w.-]*"
_ASSIGNMENT = re.compile(
    rf"""(?ix)
    (\b{_SECRET_NAME}
     ["']?\s*[:=]\s*)
    (["'])([^"'\s]{{8,}})\2
    """
)
# Config files rarely quote values: `db_password: hunter2hunter2`. Only applied to these file
# types, because in code an unquoted right-hand side is an expression (token = get_token()).
CONFIG_EXTENSIONS = {".yaml", ".yml", ".ini", ".cfg", ".toml"}
_CONFIG_ASSIGNMENT = re.compile(
    rf"""(?imx)
    ^(\s*-?\s*{_SECRET_NAME}\s*[:=]\s*)
    ([^\s"'${{<|>\#\[][^\s\#]{{7,}})   # not quoted, not a ${{VAR}} / {{{{template}}}} / block scalar / list
    """
)
_URL_CREDENTIALS = re.compile(r"(\b[a-z][a-z0-9+.\-]*://)[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)


def _keep_newlines(match: re.Match) -> str:
    # Same number of lines in and out, so chunk line numbers still match the real file.
    return REDACTED + "\n" * match.group(0).count("\n")


def _redact_assignment(match: re.Match) -> str:
    name, quote, value = match.groups()
    # GITHUB_TOKEN_URL = "https://…" is an endpoint, not a secret; URL credentials are handled below.
    if value.lower().startswith(("http://", "https://")):
        return match.group(0)
    return f"{name}{quote}{REDACTED}{quote}"


def _redact_config_assignment(match: re.Match) -> str:
    name, value = match.groups()
    if value.lower().startswith(("http://", "https://")):
        return match.group(0)
    return f"{name}{REDACTED}"


def redact_secrets(text: str, path: str = "") -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_keep_newlines, text)
    text = _ASSIGNMENT.sub(_redact_assignment, text)
    if PurePosixPath(path).suffix.lower() in CONFIG_EXTENSIONS:
        text = _CONFIG_ASSIGNMENT.sub(_redact_config_assignment, text)
    return _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}{REDACTED}@", text)
