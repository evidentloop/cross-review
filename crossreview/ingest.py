"""Host-integrated ingest pipeline: raw analysis → ReviewResult.

This module owns the post-reviewer path for host-integrated mode.
The host executes the canonical prompt in an isolated context and passes
the raw analysis text back. This module runs normalizer + adjudicator
to produce a standard ReviewResult — no LLM call, no budget gate.
"""

from __future__ import annotations

from .adjudicator import determine_advisory_verdict
from .normalizer import normalize_review_output
from .pack import compute_pack_completeness
from .schema import (
    BudgetStatus,
    ReviewPack,
    ReviewResult,
    ReviewStatus,
    ReviewerMeta,
    ResultBudget,
)
from .verify import build_review_result


def run_ingest(
    pack: ReviewPack,
    raw_analysis: str,
    *,
    model: str,
    prompt_source: str | None = None,
    prompt_version: str | None = None,
    latency_sec: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> ReviewResult:
    """Run the ingest pipeline for host-integrated review.

    The host has already executed the canonical prompt in an isolated context.
    This function takes the raw analysis text and produces a ReviewResult
    by running normalizer + adjudicator. No LLM call is made.

    Budget gate is skipped — the host manages its own context window.
    Budget fields are populated as:
      - status = COMPLETE
      - files_reviewed = files_total = len(pack.changed_files)
      - chars_consumed = len(pack.diff)
      - chars_limit = pack.budget.max_chars_total
    """
    pack_completeness = compute_pack_completeness(pack)
    files_total = len(pack.changed_files)

    normalization = normalize_review_output(
        raw_analysis,
        pack,
        pack_completeness=pack_completeness,
    )
    advisory_verdict = determine_advisory_verdict(
        findings=normalization.findings,
        pack=pack,
        budget_status=BudgetStatus.COMPLETE,
        pack_completeness=pack_completeness,
        speculative_ratio=normalization.quality_metrics.speculative_ratio,
    )
    reviewer = ReviewerMeta(
        model=model,
        raw_analysis=raw_analysis,
        prompt_source=prompt_source,
        prompt_version=prompt_version,
        latency_sec=latency_sec,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    result_budget = ResultBudget(
        status=BudgetStatus.COMPLETE,
        files_reviewed=files_total,
        files_total=files_total,
        chars_consumed=len(pack.diff),
        chars_limit=pack.budget.max_chars_total,
    )

    return build_review_result(
        pack=pack,
        reviewer=reviewer,
        budget=result_budget,
        review_status=ReviewStatus.COMPLETE,
        findings=normalization.findings,
        raw_findings=normalization.raw_findings,
        advisory_verdict=advisory_verdict,
        quality_metrics=normalization.quality_metrics,
    )
