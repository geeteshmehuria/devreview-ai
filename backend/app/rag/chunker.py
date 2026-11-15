"""
Code-aware chunking: split a file into pieces that each mean one thing (a function, a class,
a method, a block of imports) so a retrieved chunk is a complete, citable unit.

- Python: the `ast` module gives exact start/end lines for top-level functions and classes.
- JS/TS: a top-level declaration starts at column 0 (`function`, `class`, `const x =`, `export …`)
  and runs until the next one starts. No brace matching, so strings, regexes and JSX can't confuse
  it. Its limit: it relies on conventional formatting (Prettier) and nested declarations stay
  inside their parent.
- Everything else, and any piece too big to embed well: a sliding window over lines.

Every line of the file lands in exactly one chunk (plus window overlap), so nothing is lost.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

# Rough token estimate: ~4 characters per token for code and English.
# shortcut: a char-based estimate, not a real tokenizer; switch to the model's token counter if
# chunks start hitting the 2048-token embedding limit.
CHARS_PER_TOKEN = 4
WINDOW_TOKENS = 400
OVERLAP_TOKENS = 50
MAX_CHUNK_TOKENS = 1_200  # bigger symbols are windowed; gemini-embedding-001 accepts 2048 tokens

LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".go": "go", ".rs": "rust", ".cs": "csharp",
    ".cpp": "cpp", ".c": "c", ".rb": "ruby", ".php": "php", ".swift": "swift", ".kt": "kotlin",
    ".scala": "scala", ".vue": "vue", ".svelte": "svelte", ".md": "markdown", ".mdx": "markdown",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".sql": "sql", ".sh": "shell",
    ".html": "html", ".css": "css", ".scss": "scss",
}
JS_LANGS = {"javascript", "typescript"}


@dataclass
class Chunk:
    file_path: str
    start_line: int   # 1-based, inclusive
    end_line: int     # 1-based, inclusive
    symbol_name: str | None
    language: str
    content: str

    def embed_text(self) -> str:
        """What gets embedded: a header gives the vector the file/symbol context the code lacks."""
        return f"File: {self.file_path} | Symbol: {self.symbol_name or '-'} | Language: {self.language}\n{self.content}"


def detect_language(path: str) -> str:
    p = PurePosixPath(path)
    if p.name in ("Dockerfile", "Makefile", "Procfile"):
        return p.name.lower()
    return LANGUAGES.get(p.suffix.lower(), "text")


def chunk_file(path: str, text: str) -> list[Chunk]:
    language = detect_language(path)
    lines = text.splitlines()
    if language == "python":
        spans = _python_spans(text, len(lines))
    elif language in JS_LANGS:
        spans = _js_spans(lines)
    else:
        spans = None
    structured = spans is not None
    if not structured:  # unsupported language or unparsable file → windows over the whole file
        spans = [(1, len(lines), None)]

    chunks: list[Chunk] = []
    for start, end, symbol in spans:
        body = lines[start - 1:end]
        if not "".join(body).strip():
            continue
        if structured and _tokens(body) <= MAX_CHUNK_TOKENS:
            chunks.append(Chunk(path, start, end, symbol, language, "\n".join(body)))
        else:
            chunks.extend(_window(path, lines, start, end, symbol, language))
    return chunks


# ── Python ────────────────────────────────────────────────────────────────────

_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _node_start(node: ast.AST) -> int:
    # Decorators belong to the function they decorate.
    return min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])


def _python_spans(text: str, n_lines: int) -> list[tuple[int, int, str | None]] | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    return _split_nodes(tree.body, 1, n_lines, prefix="", text_lines=text.splitlines())


def _split_nodes(body, start: int, end: int, prefix: str, text_lines: list[str]):
    """Spans for each def/class in `body`, plus spans for the code between them (imports, constants)."""
    spans: list[tuple[int, int, str | None]] = []
    cursor = start
    gap_symbol = prefix.rstrip(".") or None  # module-level gaps have no symbol; class-level gaps get the class name
    for node in body:
        if not isinstance(node, _DEFS):
            continue
        n_start, n_end = _node_start(node), node.end_lineno
        if n_start > cursor:
            spans.append((cursor, n_start - 1, gap_symbol))
        name = f"{prefix}{node.name}"
        too_big = _tokens(text_lines[n_start - 1:n_end]) > MAX_CHUNK_TOKENS
        if isinstance(node, ast.ClassDef) and too_big and any(isinstance(c, _DEFS) for c in node.body):
            spans.extend(_split_nodes(node.body, n_start, n_end, f"{name}.", text_lines))
        else:
            spans.append((n_start, n_end, name))
        cursor = n_end + 1
    if cursor <= end:
        spans.append((cursor, end, gap_symbol))
    return spans


# ── JavaScript / TypeScript ───────────────────────────────────────────────────

_JS_DECL = re.compile(
    r"""^(?:export\s+(?:default\s+)?)?(?:declare\s+)?(?:async\s+)?(?:abstract\s+)?
        (?:function\s*\*?\s*(?P<fn>[\w$]+)
          |class\s+(?P<cls>[\w$]+)
          |(?:const|let|var)\s+(?P<var>[\w$]+)
          |(?:interface|type|enum)\s+(?P<type>[\w$]+))""",
    re.VERBOSE,
)
_JS_DEFAULT = re.compile(r"^export\s+default\b")
_JS_LEADING = re.compile(r"^\s*(?://|/\*|\*|@)")  # comments / JSDoc / decorators above a declaration


def _js_spans(lines: list[str]) -> list[tuple[int, int, str | None]]:
    starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        m = _JS_DECL.match(line)
        if m:
            starts.append((i, next(v for v in m.groupdict().values() if v)))
        elif _JS_DEFAULT.match(line):
            starts.append((i, "default"))

    # Pull comments/decorators directly above a declaration into it.
    adjusted = []
    for line_no, name in starts:
        s = line_no
        while s > 1 and _JS_LEADING.match(lines[s - 2]) and (not adjusted or s - 1 > adjusted[-1][0]):
            s -= 1
        adjusted.append((s, name))

    spans: list[tuple[int, int, str | None]] = []
    if not adjusted or adjusted[0][0] > 1:
        spans.append((1, (adjusted[0][0] - 1) if adjusted else len(lines), None))  # imports / preamble
    for idx, (s, name) in enumerate(adjusted):
        e = adjusted[idx + 1][0] - 1 if idx + 1 < len(adjusted) else len(lines)
        spans.append((s, e, name))
    return spans


# ── Fallback window ───────────────────────────────────────────────────────────

def _tokens(lines: list[str]) -> int:
    return sum(len(line) + 1 for line in lines) // CHARS_PER_TOKEN


def _window(path, lines, start, end, symbol, language) -> list[Chunk]:
    """~400-token windows over whole lines, each overlapping the previous one by ~50 tokens."""
    max_chars, overlap_chars = WINDOW_TOKENS * CHARS_PER_TOKEN, OVERLAP_TOKENS * CHARS_PER_TOKEN
    chunks, i = [], start
    while i <= end:
        j, size = i, 0
        while j <= end and (size == 0 or size + len(lines[j - 1]) + 1 <= max_chars):
            size += len(lines[j - 1]) + 1
            j += 1
        body = lines[i - 1:j - 1]
        if "".join(body).strip():
            chunks.append(Chunk(path, i, j - 1, symbol, language, "\n".join(body)))
        if j > end:
            break
        # Step back over whole lines until ~overlap_chars are repeated, but always move forward.
        back, k = 0, j - 1
        while k > i and back + len(lines[k - 1]) + 1 <= overlap_chars:
            back += len(lines[k - 1]) + 1
            k -= 1
        i = max(k + 1, i + 1)
    return chunks
