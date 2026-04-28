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
    Finding,
    IntentCoverage,
    QualityMetrics,
    ReviewPack,
    ReviewerConfig,
    ReviewerMeta,
    ResultBudget,
    ReviewResult,
    ReviewStatus,
    SCHEMA_VERSION,
    Verdict,
)


def build_review_result(
    *,
    pack: ReviewPack,
    reviewer: ReviewerMeta,
    budget: ResultBudget,
    review_status: ReviewStatus,
    raw_findings: list[Finding] | None = None,
    findings: list[Finding] | None = None,
    advisory_verdict: AdvisoryVerdict | None = None,
    quality_metrics: QualityMetrics | None = None,
    intent_coverage: IntentCoverage | None = None,
) -> ReviewResult:
    resolved_raw_findings = raw_findings or []
    resolved_findings = findings or []
    return ReviewResult(
        schema_version=SCHEMA_VERSION,
        artifact_fingerprint=pack.artifact_fingerprint,
        pack_fingerprint=pack.pack_fingerprint,
        review_status=review_status,
        intent_coverage=intent_coverage or determine_intent_coverage(pack, resolved_findings),
        raw_findings=resolved_raw_findings,
        findings=resolved_findings,
        evidence=list(pack.evidence or []),
        advisory_verdict=advisory_verdict or AdvisoryVerdict(
            verdict=Verdict.INCONCLUSIVE,
            rationale="review did not produce a final advisory verdict",
        ),
        quality_metrics=quality_metrics or ReviewResult().quality_metrics,
        reviewer=reviewer,
        budget=budget,
    )


# Internal alias so existing tests that reference _build_result keep working.
_build_result = build_review_result


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
    result_budget = ResultBudget(
        status=budget_result.status,
        files_reviewed=budget_result.files_reviewed,
        files_total=budget_result.files_total,
        chars_consumed=budget_result.chars_consumed,
        chars_limit=budget_result.chars_limit,
    )

    if budget_result.status == BudgetStatus.REJECTED:
        return _build_result(
            pack=pack,
            reviewer=ReviewerMeta(
                model=reviewer_config.model,
                failure_reason=budget_result.failure_reason,
            ),
            budget=result_budget,
            review_status=ReviewStatus.REJECTED,
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
            reviewer=ReviewerMeta(
                model=reviewer_config.model,
                failure_reason=exc.failure_reason,
            ),
            budget=result_budget,
            review_status=ReviewStatus.FAILED,
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
        reviewer=ReviewerMeta(
            model=review.model,
            raw_analysis=review.raw_analysis,
            prompt_source=getattr(review, "prompt_source", None),
            prompt_version=getattr(review, "prompt_version", None),
            latency_sec=review.latency_sec,
            input_tokens=review.input_tokens,
            output_tokens=review.output_tokens,
        ),
        budget=result_budget,
        review_status=review_status,
        findings=normalization.findings,
        raw_findings=normalization.raw_findings,
        advisory_verdict=advisory_verdict,
        quality_metrics=normalization.quality_metrics,
    )
