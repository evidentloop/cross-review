"""Human-readable output formatter for ReviewResult.

Implements the output format specified in v0-scope.md §9 (输出示例 human-readable).
"""

from __future__ import annotations

from .schema import (
    ReviewResult,
    ReviewPack,
    SCHEMA_VERSION,
    Severity,
)

# v0-scope.md §9 output example uses abbreviated severity labels (e.g. "MED" not "MEDIUM").
_SEV_LABEL = {
    Severity.HIGH: "HIGH",
    Severity.MEDIUM: "MED",
    Severity.LOW: "LOW",
    Severity.NOTE: "NOTE",
}


def format_human(result: ReviewResult, pack: ReviewPack) -> str:
    """Render *result* as a human-readable terminal string.

    *pack* is accepted alongside *result* because some display fields
    (e.g. intent) live on the pack, not the result.  Currently only
    ``pack.intent`` is used; the signature takes the full pack so future
    sections (e.g. changed-file list) can be added without API churn.

    The format mirrors v0-scope.md §9::

        CrossReview v0-alpha | artifact: <short> | review_status: <status>
        Intent: ...
        ...
        Advisory Verdict: ...
    """
    lines: list[str] = []

    # --- header ---
    artifact_short = result.artifact_fingerprint[:12] if result.artifact_fingerprint else "n/a"
    lines.append(
        f"CrossReview {SCHEMA_VERSION} | artifact: {artifact_short} "
        f"| review_status: {result.review_status.value}"
    )
    lines.append("")

    # --- intent ---
    intent_text = pack.intent or "(not provided)"
    lines.append(f"Intent: {intent_text}")
    lines.append(f"Intent Coverage: {result.intent_coverage.value}")
    lines.append(f"Pack Completeness: {result.quality_metrics.pack_completeness:.2f}")
    lines.append("")

    # --- findings ---
    findings = result.findings
    lines.append(f"Findings ({len(findings)}):")
    if not findings:
        lines.append("  (none)")
    for f in findings:
        sev = _SEV_LABEL[f.severity]
        loc = f.file or "(no file)"
        if f.line is not None:
            loc += f":{f.line}"
        lines.append(f"  [{sev}]  {loc} — {f.summary}")

        # Attribute line: locatability | confidence [| actionable] [| evidence: related_file]
        attrs = [f.locatability.value, f.confidence.value]
        if f.actionable:
            attrs.append("actionable")
        if f.evidence_related_file:
            attrs.append("evidence: related_file")
        lines.append(f"          {' | '.join(attrs)}")

        if f.diff_hunk:
            lines.append(f"          Diff hunk: {f.diff_hunk}")

        lines.append("")

    # --- evidence ---
    if result.evidence:
        lines.append("Evidence:")
        for ev in result.evidence:
            status_label = ev.status.value
            lines.append(f"  {ev.source}: {ev.summary} ({status_label})")
        lines.append("")

    # --- diagnostics ---
    qm = result.quality_metrics
    lines.append("Diagnostics:")
    spec_pct = int(qm.speculative_ratio * 100)
    lines.append(f"  Speculative: {spec_pct}% | Noise: {qm.noise_count}")
    lines.append("")

    # --- advisory verdict ---
    av = result.advisory_verdict
    lines.append(f"Advisory Verdict: {av.verdict.value}")
    lines.append(f"  Rationale: {av.rationale}")
    lines.append("")

    # --- fingerprint ---
    pack_short = result.pack_fingerprint[:12] if result.pack_fingerprint else "n/a"
    reviewer_type = result.reviewer.type
    model = result.reviewer.model or "unknown"
    lines.append(
        f"Fingerprint: diff:{artifact_short} | pack:{pack_short} "
        f"| reviewer:{reviewer_type}({model})"
    )

    return "\n".join(lines)
