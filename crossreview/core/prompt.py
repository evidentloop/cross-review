"""Canonical reviewer prompt seam for product and eval usage."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from crossreview.schema import to_serializable


PRODUCT_REVIEWER_PROMPT_SOURCE = "product"
PRODUCT_REVIEWER_PROMPT_VERSION = "v0.1"


DEFAULT_REVIEWER_TEMPLATE = """# CrossReview Reviewer Prompt Template (product/v0.1)

You are an independent code reviewer. You have NO access to the original development session, conversation history, or the author's reasoning process. You are seeing this code change for the first time.

## Your Input

**Task Intent** (background claim — NOT verified truth):
{intent}

**Task Description** (background claim — NOT verified truth):
{task_file}

**Focus Areas** (author's suggestion — verify independently):
{focus}

**Context Files**:
{context_files}

**Changed Files**:
{changed_files}

**Evidence** (deterministic tool output):
{evidence}

**Code Diff**:
```diff
{diff}
```

## Critical Instructions

1. The intent, focus, task description, and context files are background claims, not verified truth. Prioritize what the raw diff shows over what these materials say should happen.
2. Do NOT assume the change is correct. Your job is to find what might be wrong, not to confirm it works.
3. Be specific. Every issue you raise must point to a concrete location in the diff when possible.
4. Do NOT rationalize. If something looks off, report it.
5. Only report findings you can verify from the diff. If your analysis requires assumptions about unseen code or runtime behavior, move it to Observations.
6. If the diff rewrites or transforms code, check semantic equivalence instead of only syntax.
7. For shell, command, or parser rewrites, check statement-boundary and continuation semantics. For example, shell `&&` or `||` at line end can continue across a newline; do not assume every newline terminates the statement unless the diff proves that behavior.

## Your Output

Analyze the diff thoroughly. Separate your output into two sections: Findings (issues verifiable from the diff) and Observations (notes that require assumptions about unseen code or context).

## Section 1: Findings

Number each finding as f-001, f-002, etc. For each finding provide:
- **Where**: file path and line number if identifiable
- **What**: one-sentence summary
- **Why**: brief technical explanation grounded in the diff
- **Severity estimate**: HIGH / MEDIUM / LOW
- **Category**: logic_error / missing_test / spec_mismatch / security / performance / missing_validation / semantic_equivalence / other

## Section 2: Observations

Use this section for context-dependent concerns that are not verifiable from the diff alone.

## Section 3: Overall Assessment

Provide a short overall assessment of the diff quality. If there are no findings, say so explicitly.
"""


def get_default_reviewer_template() -> str:
    """Return the built-in product prompt template."""
    return DEFAULT_REVIEWER_TEMPLATE


def _normalize_pack(pack: Any) -> dict[str, Any]:
    if is_dataclass(pack):
        return to_serializable(pack)
    if isinstance(pack, dict):
        return pack
    return asdict(pack)


def _render_changed_files(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "(no changed files provided)"
    rendered: list[str] = []
    for item in value:
        if isinstance(item, dict):
            path = item.get("path", "<unknown>")
            language = item.get("language")
            suffix = f" ({language})" if language else ""
            rendered.append(f"- {path}{suffix}")
        else:
            rendered.append(f"- {item}")
    return "\n".join(rendered)


def _render_context_files(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "(no context files provided)"
    chunks: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            chunks.append(str(item))
            continue
        title = item.get("path", "<unknown>")
        role = item.get("role")
        role_suffix = f" [{role}]" if role else ""
        content = item.get("content", "")
        chunks.append(f"### {title}{role_suffix}\n```text\n{content}\n```")
    return "\n\n".join(chunks)


def render_reviewer_prompt(template: str, pack: Any) -> str:
    """Render the canonical reviewer prompt from a ReviewPack-like object."""
    normalized = _normalize_pack(pack)
    return template.format(
        intent=normalized.get("intent") or "(no intent provided)",
        task_file=normalized.get("task_file") or "(no task file provided)",
        focus=", ".join(normalized.get("focus") or []) or "(no focus specified)",
        context_files=_render_context_files(normalized.get("context_files")),
        changed_files=_render_changed_files(normalized.get("changed_files")),
        evidence=json.dumps(normalized.get("evidence") or [], indent=2, ensure_ascii=False),
        diff=normalized.get("diff", ""),
    )
