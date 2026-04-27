"""Tests for crossreview.formatter — v0-05 human-readable output."""

from __future__ import annotations

from crossreview.formatter import format_human
from crossreview.schema import (
    AdvisoryVerdict,
    Confidence,
    Evidence,
    EvidenceStatus,
    Finding,
    IntentCoverage,
    LocalizabilityDistribution,
    Locatability,
    QualityMetrics,
    ReviewerMeta,
    ReviewPack,
    ReviewResult,
    ReviewStatus,
    Severity,
    Verdict,
)


def _minimal_result(**overrides) -> ReviewResult:
    defaults = dict(
        artifact_fingerprint="a3f2b1c4d5e6f7890123",
        pack_fingerprint="e7d4a2f0b1c3d5e67890",
        review_status=ReviewStatus.COMPLETE,
        intent_coverage=IntentCoverage.COVERED,
    )
    defaults.update(overrides)
    return ReviewResult(**defaults)


def _minimal_pack(**overrides) -> ReviewPack:
    defaults = dict(intent="fix auth refresh logic")
    defaults.update(overrides)
    return ReviewPack(**defaults)


class TestFormatHumanHeader:
    def test_header_contains_version_artifact_status(self):
        result = _minimal_result()
        pack = _minimal_pack()
        out = format_human(result, pack)
        assert "CrossReview 0.1-alpha" in out
        assert "artifact: a3f2b1c4d5e6" in out
        assert "review_status: complete" in out

    def test_intent_displayed(self):
        out = format_human(_minimal_result(), _minimal_pack())
        assert "Intent: fix auth refresh logic" in out

    def test_intent_not_provided(self):
        out = format_human(_minimal_result(), _minimal_pack(intent=None))
        assert "Intent: (not provided)" in out

    def test_intent_coverage(self):
        out = format_human(_minimal_result(), _minimal_pack())
        assert "Intent Coverage: covered" in out


class TestFormatHumanFindings:
    def test_no_findings(self):
        out = format_human(_minimal_result(), _minimal_pack())
        assert "Findings (0):" in out
        assert "(none)" in out

    def test_finding_with_line(self):
        f = Finding(
            id="f-001",
            severity=Severity.HIGH,
            summary="Token expiry off-by-one",
            detail="Off-by-one causes premature refresh failure",
            category="logic_error",
            locatability=Locatability.EXACT,
            confidence=Confidence.PLAUSIBLE,
            actionable=True,
            file="src/auth/refresh.ts",
            line=42,
            diff_hunk="@@ -40,3 +40,3 @@",
        )
        result = _minimal_result(findings=[f])
        out = format_human(result, _minimal_pack())
        assert "Findings (1):" in out
        assert "[HIGH]  src/auth/refresh.ts:42" in out
        assert "Token expiry off-by-one" in out
        assert "exact | plausible | actionable" in out
        assert "Diff hunk: @@ -40,3 +40,3 @@" in out

    def test_finding_file_only_no_line(self):
        f = Finding(
            id="f-002",
            severity=Severity.LOW,
            summary="Missing docs",
            detail="No doc",
            category="documentation",
            locatability=Locatability.FILE_ONLY,
            confidence=Confidence.PLAUSIBLE,
            file="src/types.ts",
        )
        result = _minimal_result(findings=[f])
        out = format_human(result, _minimal_pack())
        assert "[LOW]  src/types.ts —" in out
        assert "file_only | plausible | actionable" in out

    def test_finding_evidence_related(self):
        f = Finding(
            id="f-001",
            severity=Severity.HIGH,
            summary="Bug",
            detail="Detail",
            category="logic_error",
            locatability=Locatability.EXACT,
            confidence=Confidence.PLAUSIBLE,
            evidence_related_file=True,
            file="a.py",
            line=1,
        )
        result = _minimal_result(findings=[f])
        out = format_human(result, _minimal_pack())
        assert "evidence: related_file" in out

    def test_speculative_finding(self):
        f = Finding(
            id="f-001",
            severity=Severity.MEDIUM,
            summary="Maybe issue",
            detail="Detail",
            category="possible_bug",
            locatability=Locatability.NONE,
            confidence=Confidence.SPECULATIVE,
            actionable=False,
            file=None,
        )
        result = _minimal_result(findings=[f])
        out = format_human(result, _minimal_pack())
        assert "[MED]" in out
        assert "none | speculative" in out
        assert "actionable" not in out.split("none | speculative")[1].split("\n")[0]


class TestFormatHumanEvidence:
    def test_evidence_displayed(self):
        ev = Evidence(
            source="npm test",
            status=EvidenceStatus.PASS,
            summary="47 passed, 0 failed",
        )
        result = _minimal_result(evidence=[ev])
        out = format_human(result, _minimal_pack())
        assert "Evidence:" in out
        assert "npm test: 47 passed, 0 failed (pass)" in out

    def test_no_evidence_section_when_empty(self):
        result = _minimal_result(evidence=[])
        out = format_human(result, _minimal_pack())
        assert "Evidence:" not in out


class TestFormatHumanDiagnostics:
    def test_diagnostics(self):
        qm = QualityMetrics(
            pack_completeness=0.85,
            noise_count=2,
            raw_findings_count=5,
            emitted_findings_count=3,
            locatability_distribution=LocalizabilityDistribution(0.6, 0.3, 0.1),
            speculative_ratio=0.33,
        )
        result = _minimal_result(quality_metrics=qm)
        out = format_human(result, _minimal_pack())
        assert "Diagnostics:" in out
        assert "Speculative: 33%" in out
        assert "Noise: 2" in out
        assert "Pack Completeness: 0.85" in out


class TestFormatHumanVerdict:
    def test_verdict_displayed(self):
        av = AdvisoryVerdict(
            verdict=Verdict.CONCERNS,
            rationale="1 high-severity off-by-one in core auth logic",
        )
        result = _minimal_result(advisory_verdict=av)
        out = format_human(result, _minimal_pack())
        assert "Advisory Verdict: concerns" in out
        assert "Rationale: 1 high-severity off-by-one" in out

    def test_pass_candidate_verdict(self):
        av = AdvisoryVerdict(
            verdict=Verdict.PASS_CANDIDATE,
            rationale="No findings, evidence passes",
        )
        result = _minimal_result(advisory_verdict=av)
        out = format_human(result, _minimal_pack())
        assert "Advisory Verdict: pass_candidate" in out


class TestFormatHumanFingerprint:
    def test_fingerprint_line(self):
        result = _minimal_result(
            reviewer=ReviewerMeta(model="claude-sonnet-4-20250514"),
        )
        out = format_human(result, _minimal_pack())
        assert "Fingerprint:" in out
        assert "diff:a3f2b1c4d5e6" in out
        assert "pack:e7d4a2f0b1c3" in out
        assert "fresh_llm(claude-sonnet-4-20250514)" in out
