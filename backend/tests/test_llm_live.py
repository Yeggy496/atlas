"""Opt-in live end-to-end check for the real LLM provider path.

This is deliberately NOT a mocked-model test: it makes a real HTTP call to a
configured OpenAI-compatible endpoint and asserts the full path
APIProvider -> HTTP -> validate_parse -> Pydantic Problem validation succeeds.

It only runs when OPTIDAY_LLM_LIVE_TEST=1 and a key is present, so the offline
suite (and CI) stays green without credentials.

Run, for example:
    LLM_PROVIDER=deepseek
    DEEPSEEK_BASE_URL=https://api.deepseek.com
    DEEPSEEK_API_KEY=...
    DEEPSEEK_MODEL=deepseek-flash
    DEEPSEEK_TIMEOUT=90
    OPTIDAY_LLM_LIVE_TEST=1
    python -m pytest backend/tests/test_llm_live.py -q
"""
import os

import pytest

from app.llm.providers import APIProvider
from app.schemas import Activity, Problem, Resource

_has_key = bool(os.getenv('OPENAI_API_KEY') or os.getenv('DEEPSEEK_API_KEY'))

pytestmark = pytest.mark.skipif(
    os.getenv('OPTIDAY_LLM_LIVE_TEST') != '1' or not _has_key,
    reason='set OPTIDAY_LLM_LIVE_TEST=1 and an API key to run the live provider check',
)


def test_live_provider_returns_a_validated_parse():
    provider = os.getenv('LLM_PROVIDER', 'openai').lower()
    assert provider in ('openai', 'deepseek'), 'live check needs a real (non-demo) provider'

    problem = Problem(
        scenario='life',
        name='live-e2e',
        activities=[Activity(id='a1', name='Python 学习', duration=4, category='study')],
        resources=[Resource(id='me', name='我')],
    )
    out = APIProvider(provider).parse_constraints(problem, '把 Python 学习改到周二下午14:00以后，共3小时')

    assert out['provider'] == provider
    assert out['requires_review'] is True
    assert isinstance(out['summary'], list) and out['summary']

    # The model output must still round-trip through the same schema the API serves.
    echoed = Problem.model_validate(out['problem'])
    assert any(a.id == 'a1' for a in echoed.activities)
