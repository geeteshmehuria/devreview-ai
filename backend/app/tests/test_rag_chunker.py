"""Chunker: exact line numbers, symbols never split in half, complete coverage, window fallback."""

import textwrap

from app.rag import chunker
from app.rag.chunker import chunk_file

PY = textwrap.dedent('''\
    """Module docstring."""
    import os
    from x import y

    LIMIT = 10


    @decorator
    def first(a):
        return a + 1


    class Service:
        """A service."""

        def run(self):
            return first(1)


    async def last():
        pass
''')


def _by_symbol(chunks):
    return {c.symbol_name: c for c in chunks}


def test_python_splits_by_top_level_symbol_with_exact_lines():
    chunks = chunk_file("app/mod.py", PY)
    by = _by_symbol(chunks)

    assert (by["first"].start_line, by["first"].end_line) == (8, 10)  # decorator included
    assert by["first"].content.startswith("@decorator")
    assert (by["Service"].start_line, by["Service"].end_line) == (13, 17)  # small class stays whole
    assert (by["last"].start_line, by["last"].end_line) == (20, 21)
    # Docstring + imports + constants are their own chunk, without a symbol.
    preamble = chunks[0]
    assert preamble.symbol_name is None and preamble.start_line == 1
    assert "import os" in preamble.content and "LIMIT = 10" in preamble.content
    assert all(c.language == "python" for c in chunks)


def test_every_non_blank_line_is_in_a_chunk_and_content_matches_lines():
    lines = PY.splitlines()
    chunks = chunk_file("app/mod.py", PY)
    covered = {n for c in chunks for n in range(c.start_line, c.end_line + 1)}
    assert {i for i, line in enumerate(lines, 1) if line.strip()} <= covered
    for c in chunks:
        assert c.content == "\n".join(lines[c.start_line - 1:c.end_line])


def test_large_python_class_is_split_by_method(monkeypatch):
    monkeypatch.setattr(chunker, "MAX_CHUNK_TOKENS", 10)
    by = _by_symbol(chunk_file("app/mod.py", PY))
    assert "Service.run" in by
    assert (by["Service.run"].start_line, by["Service.run"].end_line) == (16, 17)
    assert by["Service"].start_line == 13  # class header + docstring kept under the class name


def test_huge_function_falls_back_to_windows_that_keep_the_symbol_name():
    body = "\n".join(f"    x{i} = {i}  # some padding text here" for i in range(400))
    src = f"def huge():\n{body}\n"
    chunks = chunk_file("big.py", src)
    assert len(chunks) > 1
    assert all(c.symbol_name == "huge" for c in chunks)
    assert chunks[0].start_line == 1 and chunks[-1].end_line == 401


def test_invalid_python_uses_the_window_fallback():
    chunks = chunk_file("broken.py", "def broken(:\n    pass\n")
    assert len(chunks) == 1 and chunks[0].symbol_name is None
    assert (chunks[0].start_line, chunks[0].end_line) == (1, 2)


TS = textwrap.dedent('''\
    import { api } from "./api";

    /**
     * Fetch a user.
     */
    export async function getUser(id: string) {
      const url = `/users/${id}`;
      return api.get(url);
    }

    export const useThing = () => {
      return 1;
    };

    export default class Store {
      items = [];
    }

    interface Props { a: number }
''')


def test_typescript_splits_by_declaration_and_keeps_jsdoc():
    by = _by_symbol(chunk_file("lib/user.ts", TS))
    assert by[None].start_line == 1 and "import" in by[None].content
    assert (by["getUser"].start_line, by["getUser"].end_line) == (3, 10)  # JSDoc pulled in
    assert by["getUser"].content.rstrip().endswith("}")
    assert by["useThing"].start_line == 11
    assert by["Store"].start_line == 15
    assert by["Props"].start_line == 19
    assert by["getUser"].language == "typescript"


def test_window_fallback_has_bounded_size_and_overlap():
    text = "\n".join(f"Line number {i} of a long markdown document with words." for i in range(1, 301))
    chunks = chunk_file("docs/guide.md", text)
    assert len(chunks) > 1 and chunks[0].language == "markdown"
    max_chars = chunker.WINDOW_TOKENS * chunker.CHARS_PER_TOKEN
    assert all(len(c.content) <= max_chars for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt.start_line <= prev.end_line          # windows overlap
        assert nxt.start_line > prev.start_line         # and always move forward
    assert chunks[0].start_line == 1 and chunks[-1].end_line == 300


def test_embed_text_has_header():
    c = chunk_file("app/mod.py", PY)[1]
    assert c.embed_text().startswith(f"File: app/mod.py | Symbol: {c.symbol_name} | Language: python\n")


def test_empty_file_gives_no_chunks():
    assert chunk_file("a.py", "") == []
    assert chunk_file("a.ts", "\n\n") == []
