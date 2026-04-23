"""Reviewer backend abstraction and standalone Anthropic backend."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol

from .core.prompt import (
    PRODUCT_REVIEWER_PROMPT_SOURCE,
    PRODUCT_REVIEWER_PROMPT_VERSION,
    get_default_reviewer_template,
    render_reviewer_prompt,
)
from .schema import ReviewPack, ReviewerConfig, ReviewerFailureReason


class ReviewerError(Exception):
    """Base class for reviewer invocation failures."""

    failure_reason = ReviewerFailureReason.MODEL_ERROR


class UnsupportedReviewerProviderError(ReviewerError):
    """Provider is not supported by the current standalone runtime."""


class ReviewerDependencyError(ReviewerError):
    """Optional dependency required by a provider backend is missing."""


class ReviewerConfigurationError(ReviewerError):
    """Standalone backend configuration is incomplete."""

    failure_reason = ReviewerFailureReason.INPUT_INVALID


class ReviewerOutputMalformedError(ReviewerError):
    """Reviewer returned no usable text."""

    failure_reason = ReviewerFailureReason.OUTPUT_MALFORMED


@dataclass
class ReviewResponse:
    """Normalized response from a reviewer backend."""

    raw_analysis: str
    model: str
    latency_sec: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    prompt_source: str | None = None
    prompt_version: str | None = None


class ReviewerBackend(Protocol):
    """Backend contract for isolated review execution."""

    def review(self, pack: ReviewPack, config: ReviewerConfig) -> ReviewResponse:
        """Run review and return raw analysis plus metadata."""


class AnthropicReviewerBackend:
    """Standalone Anthropic backend.

    The import is intentionally lazy so host-integrated use cases do not need
    the dependency installed.
    """

    def __init__(self, *, max_output_tokens: int = 4096):
        self.max_output_tokens = max_output_tokens

    def review(self, pack: ReviewPack, config: ReviewerConfig) -> ReviewResponse:
        if not config.api_key_env:
            raise ReviewerConfigurationError(
                "Standalone Anthropic review requires api_key_env to be configured."
            )

        api_key = os.environ.get(config.api_key_env)
        if not api_key:
            raise ReviewerConfigurationError(
                f"Environment variable {config.api_key_env} is not set."
            )

        try:
            import anthropic
        except ImportError as exc:
            raise ReviewerDependencyError(
                "Anthropic backend is not installed. Install crossreview[anthropic] "
                "for standalone verify mode."
            ) from exc

        template = get_default_reviewer_template()
        prompt = render_reviewer_prompt(template, pack)

        client = anthropic.Anthropic(api_key=api_key)
        started = time.monotonic()
        response = client.messages.create(
            model=config.model,
            max_tokens=self.max_output_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_sec = time.monotonic() - started

        raw_parts: list[str] = []
        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                raw_parts.append(block.text)

        raw_analysis = "\n".join(raw_parts).strip()
        if not raw_analysis:
            raise ReviewerOutputMalformedError("Reviewer returned empty text output.")

        usage = getattr(response, "usage", None)
        return ReviewResponse(
            raw_analysis=raw_analysis,
            model=config.model,
            prompt_source=PRODUCT_REVIEWER_PROMPT_SOURCE,
            prompt_version=PRODUCT_REVIEWER_PROMPT_VERSION,
            latency_sec=latency_sec,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )


def resolve_reviewer_backend(config: ReviewerConfig) -> ReviewerBackend:
    """Resolve the first standalone backend for a provider."""
    provider = config.provider.lower()
    if provider == "anthropic":
        return AnthropicReviewerBackend()
    raise UnsupportedReviewerProviderError(
        f"Unsupported standalone reviewer provider: {config.provider}"
    )
