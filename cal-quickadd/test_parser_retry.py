"""Unit tests for ai_parser retry/backoff and fallback model behaviour.

These mock google.generativeai so they don't need a real Gemini key or quota.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from app import ai_parser
from app.ai_parser import QuotaExceeded


class FakeQuotaError(Exception):
    """Mimics google.api_core.exceptions.ResourceExhausted-style 429 error."""

    def __str__(self):
        return "429 Resource exhausted. Please try again later."


def _make_response(text: str):
    r = MagicMock()
    r.text = text
    return r


def _patch_models(*, primary_side_effects, fallback_side_effects=None):
    """Return a patch context that swaps GenerativeModel to a factory whose generate_content
    yields side-effects depending on which model name was requested."""
    primary = ai_parser.config.GEMINI_MODEL_PRIMARY
    fallback = ai_parser.config.GEMINI_MODEL_FALLBACK

    primary_iter = iter(primary_side_effects)
    fallback_iter = iter(fallback_side_effects or [])

    def factory(name, system_instruction=None):
        m = MagicMock()

        def gen(*args, **kwargs):
            target = primary_iter if name == primary else fallback_iter
            try:
                eff = next(target)
            except StopIteration:
                raise AssertionError(f"unexpected extra call to {name}")
            if isinstance(eff, Exception):
                raise eff
            return _make_response(eff)

        m.generate_content.side_effect = gen
        return m

    return patch("app.ai_parser.genai.GenerativeModel", side_effect=factory)


@pytest.mark.asyncio
async def test_retry_succeeds_after_two_429s():
    """Transient 429s should retry up to 3 times; success on attempt 3 returns parsed JSON."""
    ai_parser.quota_state = "ok"
    good_json = '{"title": "x", "date": "2026-04-28", "confidence": "high"}'

    with _patch_models(primary_side_effects=[FakeQuotaError(), FakeQuotaError(), good_json]):
        # Skip the real sleep so the test is fast.
        with patch("app.ai_parser.asyncio.sleep", new=_noop_sleep):
            result = await ai_parser.parse("anything")

    assert result["title"] == "x"
    assert ai_parser.quota_state == "ok"


@pytest.mark.asyncio
async def test_falls_back_on_primary_exhaustion():
    """If primary 429s on all 3 attempts, fall back to GEMINI_MODEL_FALLBACK."""
    ai_parser.quota_state = "ok"
    good_json = '{"title": "from-fallback", "date": "2026-04-28", "confidence": "high"}'

    with _patch_models(
        primary_side_effects=[FakeQuotaError(), FakeQuotaError(), FakeQuotaError()],
        fallback_side_effects=[good_json],
    ):
        with patch("app.ai_parser.asyncio.sleep", new=_noop_sleep):
            result = await ai_parser.parse("anything")

    assert result["title"] == "from-fallback"
    assert ai_parser.quota_state == "throttled"


@pytest.mark.asyncio
async def test_quota_exceeded_raised_when_all_models_fail():
    """If both primary and fallback 429, parser raises QuotaExceeded."""
    ai_parser.quota_state = "ok"

    with _patch_models(
        primary_side_effects=[FakeQuotaError(), FakeQuotaError(), FakeQuotaError()],
        fallback_side_effects=[FakeQuotaError()],
    ):
        with patch("app.ai_parser.asyncio.sleep", new=_noop_sleep):
            with pytest.raises(QuotaExceeded):
                await ai_parser.parse("anything")

    assert ai_parser.quota_state == "exhausted"


async def _noop_sleep(*_args, **_kwargs):
    return None
