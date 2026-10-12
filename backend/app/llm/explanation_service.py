"""LLM explanation service — MASTER_SPEC §18.

The math is never invented here. ``solver/explain.py`` already produces the real,
deterministic facts (which hard constraint pins the slot, how many legal slots
exist, which soft preference was traded off, etc.). This service *only* rephrases
那些已验证的事实 into fluent prose.

Design rules (mirrors the provider boundary in ``providers.py``):
- The LLM receives the explanation facts as read-only data and must not add new
  claims. Reviewer-visible keys are preserved verbatim from the deterministic path.
- ``demo`` provider (or any failure) falls back to the deterministic explanation,
  so the demo never depends on a live model to stay correct.
- Every returned string is length-capped; the model output is data, not code.
"""
import json
import os

import httpx

from ..solver.explain import explain


MAX_HEADLINE = 240
MAX_BULLET = 400


class LLMExplanation:
    """Wraps the deterministic explainer and optionally adds an LLM narrative."""

    def __init__(self, provider: str):
        self.provider = provider

    def build(self, problem, assignments, activity_id, previous=None):
        facts = explain(problem, assignments, activity_id, previous)
        base = {**facts, 'narrative': None, 'narrative_source': 'deterministic'}
        if self.provider not in ('openai', 'deepseek'):
            return base
        try:
            narrative = self._narrate(facts)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            narrative = None
        if narrative:
            base['narrative'] = narrative
            base['narrative_source'] = self.provider
        return base

    def _narrate(self, facts: dict):
        prefix = self.provider.upper()
        key = os.getenv(f'{prefix}_API_KEY', '')
        if not key:
            return None
        default_base = 'https://api.openai.com/v1' if self.provider == 'openai' else 'https://api.deepseek.com'
        base = (os.getenv(f'{prefix}_BASE_URL') or default_base).rstrip('/')
        model = os.getenv(f'{prefix}_MODEL', 'gpt-4.1-mini' if self.provider == 'openai' else 'deepseek-chat')
        timeout = float(os.getenv(f'{prefix}_TIMEOUT', '35'))
        prompt = ('你是调度结果解释助手。下面给出某个活动被安排在此时刻的真实求解事实（JSON）。'
                  '请只依据这些事实，用 1-2 句中文口语化地解释“为什么排在这个时间”。'
                  '不得引入事实之外的任何信息，不得声称唯一性或最优性，除非事实里写明候选时段只有 1 个。'
                  '只返回 JSON 对象 {"headline": "...", "bullets": ["..."]}，不要解释、不要代码。')
        payload = {'activity': facts.get('name'), 'day': facts.get('day_name'),
                   'clock': f"{facts.get('start_clock')}-{facts.get('end_clock')}",
                   'candidate_slots_total': facts.get('candidate_slots_total'),
                   'candidate_slots_same_day': facts.get('candidate_slots_same_day'),
                   'reasons': [{'kind': r.get('kind'), 'title': r.get('title'), 'detail': r.get('detail')}
                               for r in facts.get('reasons', [])]}
        with httpx.Client(timeout=timeout) as client:
            response = client.post(base + '/chat/completions',
                                   headers={'Authorization': f'Bearer {key}'},
                                   json={'model': model, 'temperature': 0,
                                         'response_format': {'type': 'json_object'},
                                         'messages': [{'role': 'system', 'content': prompt},
                                                      {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]})
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
        if not isinstance(content, str):
            return None
        return _validate_narrative(json.loads(content))


def _validate_narrative(data):
    """Keep only well-formed, length-capped narrative strings."""
    if not isinstance(data, dict):
        return None
    headline = data.get('headline')
    if not isinstance(headline, str) or not headline.strip():
        return None
    bullets = data.get('bullets')
    if bullets is None:
        bullets = []
    if not isinstance(bullets, list):
        bullets = []
    clean = [b.strip()[:MAX_BULLET] for b in bullets if isinstance(b, str) and b.strip()][:4]
    return {'headline': headline.strip()[:MAX_HEADLINE], 'bullets': clean}


def get_explanation_service():
    """Pick the service from LLM_PROVIDER; unknown values fall back to demo."""
    name = os.getenv('LLM_PROVIDER', 'demo').lower()
    return LLMExplanation(name if name in ('openai', 'deepseek') else 'demo')
