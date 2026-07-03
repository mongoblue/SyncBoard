"""Shared log sanitization for all CI pipeline clients.

Provides `sanitize_logs(text) -> str` — a single function that redacts
tokens, secrets, and sensitive headers from free-text CI log output.
Used by GitHubActionsClient, JenkinsClient, GitLabClient, and the
PipelineRunLogsView.
"""

from __future__ import annotations

import re

# ── compiled patterns ──────────────────────────────────────────────────

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 1. HTTP header-style tokens — capture multi-word values until end of line
    (
        re.compile(
            r'(?i)^\s*(authorization|private-token|x-ci-token|'
            r'x-jenkins-token|x-gitlab-token|x-hub-signature-256):\s*\S.*$',
            re.MULTILINE,
        ),
        r'\1: [redacted]',
    ),
    # 2. GitHub classic personal access token (ghp_ prefix, >= 36 chars)
    (
        re.compile(r'\bghp_[A-Za-z0-9_]{36,}\b'),
        '[redacted]',
    ),
    # 3. GitHub fine-grained PAT (github_pat_ prefix, >= 22 chars)
    (
        re.compile(r'\bgithub_pat_[A-Za-z0-9_]{22,}\b'),
        '[redacted]',
    ),
    # 4. GitLab personal access token (glpat- prefix)
    (
        re.compile(r'\bglpat-[A-Za-z0-9\-_]{20,}\b'),
        '[redacted]',
    ),
    # 5. Generic key=value secrets in free text
    (
        re.compile(
            r'(?i)(api[_-]?key|api[_-]?secret|access[_-]?key|'
            r'secret[_-]?key|private[_-]?key)\s*[:=]\s*\S+'
        ),
        r'\1: [redacted]',
    ),
    # 6. Standalone Bearer token (not inside an Authorization header — catch stray refs)
    (
        re.compile(r'(?i)bearer\s+[\w\-\.+/=]{20,}'),
        'Bearer [redacted]',
    ),
]


def sanitize_logs(text: str) -> str:
    """Apply all sanitization patterns to a log string.

    Returns the text with sensitive tokens, headers, and secrets redacted.
    """
    if not text:
        return text
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
