"""Reusable verification pipeline for CLI and Prompt Lab runners.

This module owns the product ReviewPack -> ReviewResult orchestration. Adapters
such as the CLI should handle file/config I/O, then call this core path instead
of duplicating ReviewResult construction.
"""

from __future__ import annotations

from .adjudicator import determine_advisory_verdict, determine_intent_coverage
from .budget import apply_budget_gate
from .normalizer import normalize_review_output
from .pack import compute_pack_completeness
from .reviewer import ReviewerBackend, ReviewerError, resolve_reviewer_backend
from .schema import (
    AdvisoryVerdict,
    BudgetStatus,
    ReviewPack,
    ReviewerConfig,
    ReviewerFailureReason,
    ReviewerMeta,
    ResultBudget,
    ReviewResult,
    ReviewStatus,
    SCHEMA_VERSION,
    Verdict,
)


def _build_result(
    *,
    pack: ReviewPack,
    reviewer_model: str,
    budget_status: BudgetStatus,
    files_reviewed: int,
    files_total: int,
    chars_consumed: int,
    chars_limit: int | None,
    review_status: ReviewStatus,
    raw_findings: list | None = None,
    findings=None,
    raw_analysis: str | None = None,
    prompt_source: str | None = None,
    prompt_version: str | None = None,
    latency_sec: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    failure_reason: ReviewerFailureReason | None = None,
    advisory_verdict: AdvisoryVerdict | None = None,
    quality_metrics=None,
    intent_coverage=None,
) -> ReviewResult:
    return ReviewResult(
        schema_version=SCHEMA_VERSION,
        artifact_fingerprint=pack.artifact_fingerprint,
        pack_fingerprint=pack.pack_fingerprint,
        review_status=review_status,
        intent_coverage=intent_coverage or determine_intent_coverage(pack, findings or []),
        raw_findings=raw_findings or [],
        findings=findings or [],
        evidence=list(pack.evidence or []),
        advisory_verdict=advisory_verdict or AdvisoryVerdict(
            verdict=Verdict.INCONCLUSIVE,
            rationale="review did not produce a final advisory verdict",
        ),
        quality_metrics=quality_metrics or ReviewResult().quality_metrics,
        reviewer=ReviewerMeta(
            model=reviewer_model,
            raw_analysis=raw_analysis,
            prompt_source=prompt_source,
            prompt_version=prompt_version,
            latency_sec=latency_sec,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            failure_reason=failure_reason,
        ),
        budget=ResultBudget(
            status=budget_status,
            files_reviewed=files_reviewed,
            files_total=files_total,
            chars_consumed=chars_consumed,
            chars_limit=chars_limit,
        ),
    )


def run_verify_pack(
    pack: ReviewPack,
    reviewer_config: ReviewerConfig,
    *,
    backend: ReviewerBackend | None = None,
) -> ReviewResult:
    """Run the standalone verification pipeline for an already-valid pack.

    Caller responsibilities:
    - load/validate the ReviewPack before calling;
    - resolve ReviewerConfig from the adapter-specific sources;
    - serialize or persist the returned ReviewResult.

    The optional backend seam is intentionally narrow so tests and Prompt Lab
    utilities can inject an API-only or fake backend without bypassing budget,
    normalization, adjudication, and result construction.
    """
    budget_result = apply_budget_gate(pack)
    pack_completeness = compute_pack_completeness(pack)

    if budget_result.status == BudgetStatus.REJECTED:
        return _build_result(
            pack=pack,
            reviewer_model=reviewer_config.model,
            budget_status=budget_result.status,
            files_reviewed=budget_result.files_reviewed,
            files_total=budget_result.files_total,
            chars_consumed=budget_result.chars_consumed,
            chars_limit=budget_result.chars_limit,
            review_status=ReviewStatus.REJECTED,
            failure_reason=budget_result.failure_reason,
            advisory_verdict=AdvisoryVerdict(
                verdict=Verdict.INCONCLUSIVE,
                rationale="review input was rejected by the budget gate",
            ),
        )

    if budget_result.effective_pack is None:
        raise RuntimeError("budget gate passed but effective_pack is None")

    try:
        active_backend = backend or resolve_reviewer_backend(reviewer_config)
        review = active_backend.review(budget_result.effective_pack, reviewer_config)
    except ReviewerError as exc:
        return _build_result(
            pack=pack,
            reviewer_model=reviewer_config.model,
            budget_status=budget_result.status,
            files_reviewed=budget_result.files_reviewed,
            files_total=budget_result.files_total,
            chars_consumed=budget_result.chars_consumed,
            chars_limit=budget_result.chars_limit,
            review_status=ReviewStatus.FAILED,
            failure_reason=exc.failure_reason,
            advisory_verdict=AdvisoryVerdict(
                verdict=Verdict.INCONCLUSIVE,
                rationale=str(exc),
            ),
        )

    normalization = normalize_review_output(
        review.raw_analysis,
        budget_result.effective_pack,
        pack_completeness=pack_completeness,
    )
    advisory_verdict = determine_advisory_verdict(
        findings=normalization.findings,
        pack=pack,
        budget_status=budget_result.status,
        pack_completeness=pack_completeness,
        speculative_ratio=normalization.quality_metrics.speculative_ratio,
    )
    review_status = (
        ReviewStatus.TRUNCATED
        if budget_result.status == BudgetStatus.TRUNCATED
        else ReviewStatus.COMPLETE
    )
    return _build_result(
        pack=pack,
        reviewer_model=review.model,
        budget_status=budget_result.status,
        files_reviewed=budget_result.files_reviewed,
        files_total=budget_result.files_total,
        chars_consumed=budget_result.chars_consumed,
        chars_limit=budget_result.chars_limit,
        review_status=review_status,
        findings=normalization.findings,
        raw_findings=normalization.raw_findings,
        raw_analysis=review.raw_analysis,
        prompt_source=getattr(review, "prompt_source", None),
        prompt_version=getattr(review, "prompt_version", None),
        latency_sec=review.latency_sec,
        input_tokens=review.input_tokens,
        output_tokens=review.output_tokens,
        advisory_verdict=advisory_verdict,
        quality_metrics=normalization.quality_metrics,
    )
