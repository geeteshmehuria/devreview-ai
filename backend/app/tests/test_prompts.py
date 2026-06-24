"""Tests for the prompt builder."""

import pytest
from app.ai.base import ReviewRequest
from app.ai.prompts import build_prompt, SYSTEM_PROMPT


class TestPromptBuilder:
    def test_system_prompt_present(self):
        request = ReviewRequest(review_type="code_snippet", content="print('hello')", language="python")
        system, user = build_prompt(request)
        assert "DevReview AI" in system
        assert "JSON" in system

    def test_code_snippet_prompt_contains_code(self):
        code = "def foo():\n    return 42"
        request = ReviewRequest(review_type="code_snippet", content=code, language="python")
        _, user = build_prompt(request)
        assert code in user
        assert "python" in user

    def test_pr_prompt_includes_context(self):
        request = ReviewRequest(
            review_type="pull_request",
            content="diff --git a/foo.py ...",
            language="python",
            context={
                "pr_number": 42,
                "pr_title": "Fix auth bug",
                "author": "dev1",
                "base_branch": "main",
                "head_branch": "fix/auth",
                "additions": 10,
                "deletions": 5,
                "changed_files": 2,
            },
        )
        _, user = build_prompt(request)
        assert "#42" in user
        assert "Fix auth bug" in user
        assert "diff --git" in user

    def test_repo_prompt_mentions_structure(self):
        request = ReviewRequest(
            review_type="repository",
            content="=== README.md ===\n# My Project",
            language="python",
            context={"repo_name": "owner/myrepo"},
        )
        _, user = build_prompt(request)
        assert "README.md" in user

    def test_file_upload_uses_code_review_prompt(self):
        """file_upload should use the same builder as code_snippet."""
        request = ReviewRequest(review_type="file_upload", content="const x = 1;", language="javascript")
        _, user = build_prompt(request)
        assert "javascript" in user

    def test_detail_level_brief_in_prompt(self):
        request = ReviewRequest(
            review_type="code_snippet",
            content="x = 1",
            language="python",
            detail_level="brief",
        )
        _, user = build_prompt(request)
        assert "concise" in user.lower() or "brief" in user.lower()
