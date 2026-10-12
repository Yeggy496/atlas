"""Smoke-check the configured LLM parser with one small real request.

Run this after setting LLM_PROVIDER and the matching credentials (locally, or in
the Render dashboard) to prove the server can actually reach the model before
the demo is shown. The credential value is never printed. The exit status is
non-zero when the provider is missing, misconfigured, or unreachable, so this can
gate a deploy or a pre-demo check.

    python scripts/check_llm.py
    python scripts/check_llm.py --scenario academic

Never commit a key: pass it through the environment only.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))

from app.llm.providers import get_provider  # noqa: E402
from app.schemas import Problem  # noqa: E402

REQUESTS = {
    'life': '周六下午想安排两小时跑步，晚上11点后不要安排任何活动。',
    'academic': '周三下午不要排课。',
    'lab': '周四下午两点到四点设备占用。',
}
DEFAULT_MODEL = {'openai': 'gpt-4.1-mini', 'deepseek': 'deepseek-flash'}
DEFAULT_BASE = {'openai': 'https://api.openai.com/v1', 'deepseek': 'https://api.deepseek.com'}


def main() -> int:
    parser = argparse.ArgumentParser(description='Check the configured ATLAS-Sigma LLM provider.')
    parser.add_argument('--scenario', choices=sorted(REQUESTS), default='life')
    args = parser.parse_args()

    provider_name = os.getenv('LLM_PROVIDER', 'demo').lower()
    if provider_name == 'demo':
        print('LLM_PROVIDER=demo: the offline rule parser needs no key, nothing to check.')
        print('Set LLM_PROVIDER=openai or deepseek (plus a key) to check a real provider.')
        return 0
    if provider_name not in DEFAULT_MODEL:
        print(f'FAIL: LLM_PROVIDER={provider_name!r} is not demo, openai, or deepseek.', file=sys.stderr)
        return 2

    prefix = provider_name.upper()
    key = os.getenv(f'{prefix}_API_KEY', '')
    base = os.getenv(f'{prefix}_BASE_URL') or DEFAULT_BASE[provider_name]
    model = os.getenv(f'{prefix}_MODEL') or DEFAULT_MODEL[provider_name]
    timeout = os.getenv(f'{prefix}_TIMEOUT', '90' if provider_name == 'deepseek' else '35')

    print(f'provider = {provider_name}')
    print(f'model    = {model}')
    print(f'base_url = {base}')
    print(f'timeout  = {timeout}s')
    print(f'key      = {"set" if key else "MISSING"} (value hidden)')
    if not key:
        print(f'FAIL: {prefix}_API_KEY is not set.', file=sys.stderr)
        return 2

    sample = json.loads((ROOT / 'sample_data' / f'{args.scenario}.json').read_text(encoding='utf-8'))
    problem = Problem.model_validate(sample)

    started = time.perf_counter()
    try:
        result = get_provider().parse_constraints(problem, REQUESTS[args.scenario])
    except Exception as exc:  # noqa: BLE001 - surface whatever the provider raised
        print(f'FAIL after {time.perf_counter() - started:.1f}s: {exc}', file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    if not result.get('requires_review'):
        print('WARN: the result is not flagged for user review.', file=sys.stderr)
    parsed = result['problem']
    print(f'OK in {elapsed:.1f}s: provider={result.get("provider")} '
          f'activities={len(parsed["activities"])} constraints={len(parsed["constraints"])}')
    print(f'     summary={result.get("summary")}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
