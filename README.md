# CrossReview

English | [简体中文](README.zh-CN.md)

> Automated cross-review for AI coding assistants — a fresh, isolated LLM session verifies what your assistant produced.

## What is Cross-Review?

In human code review, a change is typically inspected by **someone who did not directly implement it**, which reduces author bias. CrossReview applies the same principle to AI-generated code by separating generation and review into two isolated contexts.

An AI coding assistant (Claude, Copilot, Cursor, etc.) first produces the change in its original session. CrossReview then packages the diff, stated intent, focus areas, and optional context into a `ReviewPack` and hands it to a **separate reviewer session** for verification. That reviewer does not inherit the original conversation, reasoning trace, or tool history; it evaluates the change only from the minimum necessary inputs.

The key insight: **you don't need a different model, just a different context.** Same model, clean session, real findings.

## Why It Works

The mechanism is not model diversity; it is **input isolation**.

The author session accumulates local assumptions, discarded alternatives, retries, and tool-side trial-and-error. If the review step reuses that context, the reviewer is likely to preserve the author's framing instead of independently re-deriving whether the change is correct.

CrossReview avoids that by constraining reviewer input to the review artifact itself:

| Reviewer receives | Reviewer does not receive |
|-------------------|---------------------------|
| Diff / changed files | Original conversation |
| Stated intent | Planning or reasoning trace |
| Focus areas | Tool call history |
| Optional context files | Retries, failed attempts, intermediate drafts |

This separation has two practical effects:

- It increases reviewer independence, because the second pass must justify findings from the artifact rather than from inherited session state.
- It improves auditability, because reviewer claims can be checked against `ReviewPack` contents, emitted findings, and deterministic normalization rules.

## Early Results

Preliminary evaluation across 4 real-world fixtures (tool-assisted isolated reviewer, claude-opus-4.6):

- **Precision 1.00** — zero false positives (improved from 0.45 in Round 1 after introducing Findings/Observations split)
- **Recall 0.75** — one baseline finding missed (bash multiline continuation semantics)
- **Invalid findings per run: 0.00**

These results validate the direction but are too small to be conclusive. A full eval harness with 13+ fixtures and [8 release gate metrics](docs/v0-scope.md) is in progress.

## Quick Start

```bash
pip install -e .                    # full CLI (pack + verify commands)
pip install -e '.[anthropic]'       # + Anthropic standalone reviewer backend

# configure standalone verify via flags, crossreview.yaml, or env vars
# example:
#   export CROSSREVIEW_PROVIDER=anthropic
#   export CROSSREVIEW_MODEL=claude-sonnet-4-20250514
#   export CROSSREVIEW_API_KEY_ENV=ANTHROPIC_API_KEY
#   export ANTHROPIC_API_KEY=...

crossreview pack --diff HEAD~1 --intent "fix auth token refresh" > pack.json
crossreview verify --pack pack.json
```

`crossreview verify` outputs `ReviewResult` JSON to stdout:

```jsonc
{
  "schema_version": "0.1-alpha",
  "artifact_fingerprint": "diff:abc123",
  "pack_fingerprint": "pack:def456",
  "review_status": "complete",
  "intent_coverage": "covered",
  "findings": [
    {
      "id": "f-001",
      "severity": "high",
      "summary": "Token refresh silently succeeds when refresh_token is expired",
      "detail": "The try/except on line 42 catches TokenExpiredError but returns the old token instead of raising.",
      "category": "logic_error",
      "locatability": "exact",
      "confidence": "plausible",
      "evidence_related_file": false,
      "actionable": true,
      "file": "src/auth.py",
      "line": 42
    }
  ],
  "advisory_verdict": {
    "verdict": "concerns",
    "rationale": "review found medium/high-severity issues"
  },
  "quality_metrics": {
    "pack_completeness": 0.85,
    "noise_count": 0,
    "raw_findings_count": 1,
    "emitted_findings_count": 1,
    "locatability_distribution": {
      "exact_pct": 1.0,
      "file_only_pct": 0.0,
      "none_pct": 0.0
    },
    "speculative_ratio": 0.0
  },
  "reviewer": {
    "type": "fresh_llm",
    "model": "claude-sonnet-4-20250514",
    "session_isolated": true,
    "failure_reason": null,
    "prompt_source": "product",
    "prompt_version": "v0.1"
  },
  "budget": {
    "status": "complete",
    "files_reviewed": 1,
    "files_total": 1,
    "chars_consumed": 842,
    "chars_limit": 12000
  }
}
```

## Architecture

```
         git diff + intent + focus + context
                      │
                      ▼
              ┌────────────────┐
              │      Pack      │  Assemble ReviewPack
              └───────┬────────┘
                      │
                      ▼
              ┌────────────────┐
              │  Budget Gate   │  Focus-priority, size cap
              └───────┬────────┘
                      │
   ╔══════════════════╪═══════════════════════════╗
   ║                  ▼  Isolation Boundary       ║
   ║          ┌────────────────┐                  ║
   ║          │ Reviewer (LLM) │  Fresh session,  ║
   ║          │                │  zero shared ctx ║
   ║          └───────┬────────┘                  ║
   ╚══════════════════╪═══════════════════════════╝
                      │
                      ▼
              ┌────────────────┐
              │  Normalizer    │  Extract findings from text
              └───────┬────────┘
                      │
                      ▼
              ┌────────────────┐
              │  Adjudicator   │  Apply rules → verdict
              └───────┬────────┘
                      │
                      ▼
              ┌────────────────┐
              │ ReviewResult   │  Findings + verdict
              │ (JSON)         │  + quality metrics
              └────────────────┘
```

Only the Reviewer calls an LLM. Everything else is rule-based — no AI in the loop.

## Installation

```bash
pip install -e .                    # full CLI (pack + verify commands)
pip install -e '.[anthropic]'       # + Anthropic standalone reviewer backend
pip install -e '.[dev]'             # dev dependencies (pytest + ruff)
```

Two reviewer backend modes:

| Mode | Description | Dependency |
|------|-------------|------------|
| **Host-integrated** *(planned)* | Host provides an isolated reviewer backend; CrossReview only consumes the result | No extra SDK on the CrossReview side |
| **Standalone** *(implemented)* | CLI calls the LLM API directly | `crossreview[anthropic]` + reviewer config + API key |

Host-integrated is the planned default product path. The current main branch ships standalone verify only.

## Commands

### `crossreview pack`

```bash
crossreview pack --diff HEAD~1 > pack.json
crossreview pack --diff main..feat --intent "add caching" --focus cache --context ./plan.md > pack.json
```

| Flag | Description |
|------|-------------|
| `--diff REF` | Git ref (`HEAD~1`) or range (`main..feat`) |
| `--intent TEXT` | Task intent (background claim, not ground truth) |
| `--task FILE` | Full task description file |
| `--focus TERM` | Focus review area (repeatable) |
| `--context FILE` | Extra context file (repeatable) |

### `crossreview verify`

```bash
crossreview verify --pack pack.json
crossreview verify --pack pack.json --model claude-sonnet-4-20250514 --provider anthropic
```

`crossreview verify` also requires reviewer configuration to resolve successfully:

- `--model / --provider / --api-key-env`
- or `crossreview.yaml`
- or `~/.crossreview/config.yaml`
- or `CROSSREVIEW_MODEL / CROSSREVIEW_PROVIDER / CROSSREVIEW_API_KEY_ENV`

| Flag | Description |
|------|-------------|
| `--pack FILE` | Path to ReviewPack JSON |
| `--model TEXT` | Override reviewer model |
| `--provider TEXT` | Override provider (currently `anthropic` only) |
| `--api-key-env VAR` | Override API key env variable name |

## Status

| Component | Status | Notes |
|-----------|--------|-------|
| Schema | ✅ Done | ReviewPack / Finding / ReviewResult / Config |
| Pack CLI | ✅ Done | `crossreview pack` |
| Budget Gate | ✅ Done | Focus priority + soft/hard truncation |
| Reviewer | ✅ Done | ReviewerBackend protocol + Anthropic standalone |
| Normalizer | ✅ Done | Rule-based finding extraction |
| Adjudicator | ✅ Done | Rule-based advisory verdict |
| Verify CLI | ✅ Done | `crossreview verify --pack` |
| Evidence Collector | 🔜 Next | ReviewPack.evidence path exists, empty evidence works |
| Eval Harness | 🔜 Planned | Release gate validation with fixtures |
| Human-readable Output | 🔜 Next | `--format human` |
| One-stop Verify | 🔜 Next | `crossreview verify --diff` (pack + review in one step) |

## v0 Scope

**Supported**: `code_diff` artifact only · advisory verdict · single `fresh_llm` reviewer · deterministic adjudicator and normalizer (no LLM fallback)

**Out of scope (v0)**: Python SDK · MCP Server · Agent Skill · CI/CD Action · cross-model reviewer · verdict = block

**Release gate**: v0 must pass [8 blocking metrics](docs/v0-scope.md) (§12), including manual_recall ≥ 0.80, precision ≥ 0.70, fixture_count ≥ 20, invalid_findings_per_run ≤ 2, and 4 others. Fail → revert to prompt pattern, no standalone product.

## License

MIT
