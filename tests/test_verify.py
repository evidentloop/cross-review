"""Tests for the reusable ReviewPack -> ReviewResult verify pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from crossreview.core.prompt import PRODUCT_REVIEWER_PROMPT_SOURCE, PRODUCT_REVIEWER_PROMPT_VERSION
from crossreview.reviewer import ReviewResponse
from crossreview.schema import FileMeta, ReviewerConfig
from crossreview.budget import ABSOLUTE_MAX_FIRST_FILE_CHARS
from crossreview.pack import assemble_pack
from crossreview.verify import run_verify_pack


SAMPLE_DIFF = """\
diff --git a/hello.py b/hello.py
--- a/hello.py
+++ b/hello.py
@@ -1 +1,2 @@
 print("hello")
+print("world")
"""


@dataclass
class FakeBackend:
    raw_analysis: str
    prompt_source: str | None = PRODUCT_REVIEWER_PROMPT_SOURCE
    prompt_version: str | None = PRODUCT_REVIEWER_PROMPT_VERSION

    def review(self, _pack, config: ReviewerConfig) -> ReviewResponse:
        return ReviewResponse(
            raw_analysis=self.raw_analysis,
            model=config.model,
            prompt_source=self.prompt_source,
            prompt_version=self.prompt_version,
            latency_sec=0.1,
            input_tokens=10,
            output_tokens=20,
        )


def _pack():
    return assemble_pack(
        SAMPLE_DIFF,
        changed_files=[FileMeta(path="hello.py", language="python")],
        intent="fix greeting",
    )


def _config():
    return ReviewerConfig(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
    )


class TestRunVerifyPack:
    def test_success_builds_canonical_review_result(self):
        result = run_verify_pack(
            _pack(),
            _config(),
            backend=FakeBackend(
                """## Section 1: Findings

### f-001
- **Where**: `hello.py`, line 2
- **What**: The new print changes behavior.
- **Why**: The diff now prints an extra line.
- **Severity estimate**: LOW
- **Category**: spec_mismatch

## Section 2: Observations
"""
            ),
        )

        assert result.review_status.value == "complete"
        assert result.reviewer.model == "claude-sonnet-4-20250514"
        assert result.reviewer.prompt_source == PRODUCT_REVIEWER_PROMPT_SOURCE
        assert result.reviewer.prompt_version == PRODUCT_REVIEWER_PROMPT_VERSION
        assert result.reviewer.raw_analysis
        assert result.raw_findings[0].id == "f-001"
        assert result.findings[0].category == "spec_mismatch"
        assert result.quality_metrics.raw_findings_count == 1
        assert result.intent_coverage.value == "partial"

    def test_rejected_budget_still_returns_review_result(self):
        oversized_diff = (
            "diff --git a/huge.py b/huge.py\n"
            "--- a/huge.py\n"
            "+++ b/huge.py\n"
            "@@ -1 +1 @@\n"
            + "+" + ("x" * (ABSOLUTE_MAX_FIRST_FILE_CHARS + 1))
        )
        pack = assemble_pack(
            oversized_diff,
            changed_files=[FileMeta(path="huge.py", language="python")],
        )

        result = run_verify_pack(
            pack,
            _config(),
            backend=FakeBackend("should not be called"),
        )

        assert result.review_status.value == "rejected"
        assert result.reviewer.failure_reason is not None
        assert result.raw_findings == []
