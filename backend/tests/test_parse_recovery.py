"""Regression coverage for long-output failures and accidental scenario selection."""
from copy import deepcopy
import json
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
import pytest

from app import main
from app.adapters import ADAPTERS
from app.llm.parse_support import completion_content, IncompleteParse, parse_token_limit, suggested_scenario
from app.llm.providers import APIProvider


def envelope(data, reason='stop'):
    content = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return httpx.Response(200, json={'choices': [{'finish_reason': reason, 'message': {'content': content}}]},
                          request=httpx.Request('POST', 'https://example.invalid'))


def parsed_problem():
    return {'problem': ADAPTERS['life']().model_dump(), 'summary': ['完整识别'], 'warnings': []}


def test_truncated_response_is_regenerated_even_if_its_json_is_balanced(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    monkeypatch.delenv('DEEPSEEK_MAX_TOKENS', raising=False)
    expected = parsed_problem()
    partial = deepcopy(expected)
    partial['problem']['activities'] = []
    partial['problem']['constraints'] = []
    with patch('app.llm.providers.httpx.Client.post', side_effect=[envelope(partial, 'length'), envelope(expected)]) as post:
        result = APIProvider('deepseek').parse_constraints(ADAPTERS['life'](), '安排完整个人周计划')
    assert result['parse_attempts'] == 2 and result['requires_review'] is True
    assert len(result['problem']['activities']) == len(expected['problem']['activities'])
    assert post.call_args_list[0].kwargs['json']['max_tokens'] == 24576
    assert post.call_args_list[1].kwargs['json']['max_tokens'] == 32768


def test_invalid_resource_reference_is_repaired_once_and_input_is_unchanged(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    problem = ADAPTERS['life']()
    before = problem.model_dump()
    invalid = parsed_problem()
    invalid['problem']['activities'][0]['resources'] = ['unknown_person']
    with patch('app.llm.providers.httpx.Client.post', side_effect=[envelope(invalid), envelope(parsed_problem())]) as post:
        result = APIProvider('openai').parse_constraints(problem, '保留任务')
    assert post.call_count == 2 and result['parse_attempts'] == 2
    messages = post.call_args.kwargs['json']['messages']
    assert messages[-2]['role'] == 'assistant'
    assert 'unknown_person' in messages[-2]['content']
    assert '校验' in messages[-1]['content']
    assert problem.model_dump() == before


@pytest.mark.parametrize('field,value', [('scenario', 'lab'), ('week_start', '2026-10-19')])
def test_model_cannot_silently_change_workspace_scope(monkeypatch, field, value):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    invalid = parsed_problem()
    invalid['problem'][field] = value
    with patch('app.llm.providers.httpx.Client.post', return_value=envelope(invalid)) as post:
        with pytest.raises(ValueError, match='模型解析未成功'):
            APIProvider('deepseek').parse_constraints(ADAPTERS['life'](), '保留任务')
    assert post.call_count == 2


def test_failed_repair_is_not_partially_accepted(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    with patch('app.llm.providers.httpx.Client.post', return_value=envelope('{"problem":', 'length')) as post:
        with pytest.raises(ValueError, match='截断'):
            APIProvider('deepseek').parse_constraints(ADAPTERS['life'](), '很多任务')
    assert post.call_count == 2


def test_transient_http_error_is_not_retried_as_json_repair(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    response = httpx.Response(503, request=httpx.Request('POST', 'https://example.invalid'))
    with patch('app.llm.providers.httpx.Client.post', return_value=response) as post:
        with pytest.raises(ValueError, match='HTTP 503'):
            APIProvider('openai').parse_constraints(ADAPTERS['life'](), '新增任务')
    assert post.call_count == 1


@pytest.mark.parametrize('reason', ['content_filter', 'insufficient_system_resource', 'tool_calls', 'aborted'])
def test_provider_stops_are_not_retried_as_format_repair(monkeypatch, reason):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    with patch('app.llm.providers.httpx.Client.post', return_value=envelope('{}', reason)) as post:
        with pytest.raises(ValueError, match='没有完成此次识别'):
            APIProvider('deepseek').parse_constraints(ADAPTERS['life'](), '保持任务')
    assert post.call_count == 1


def test_scenario_suggestion_never_calls_model_or_mutates_input(monkeypatch):
    problem = ADAPTERS['production']()
    original = problem.model_dump()
    with patch.object(main, 'get_provider') as provider, TestClient(main.app) as client:
        response = client.post('/api/constraints/parse', json={'problem': original,
            'text': '安排我的个人周计划，每天睡8小时，午饭半小时，每周跑步3次。'})
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'scenario_mismatch'
    assert response.json()['detail']['suggested_scenario'] == 'life'
    provider.assert_not_called()
    assert problem.model_dump() == original


def test_user_can_explicitly_keep_the_current_scenario(monkeypatch):
    problem = ADAPTERS['production']()
    with patch.object(main, 'get_provider') as provider, TestClient(main.app) as client:
        provider.return_value.parse_constraints.return_value = {'problem': problem.model_dump(), 'requires_review': True}
        response = client.post('/api/constraints/parse', json={'problem': problem.model_dump(),
            'text': '个人计划，包括睡眠和午饭', 'allow_scenario_mismatch': True})
    assert response.status_code == 200
    provider.return_value.parse_constraints.assert_called_once()


def test_simple_factory_meal_break_is_not_forced_to_a_personal_plan():
    assert suggested_scenario(ADAPTERS['production'](), '午饭期间所有机床停工半小时') is None
    assert suggested_scenario(ADAPTERS['life'](), '个人周计划，睡眠和跑步') is None


@pytest.mark.parametrize('value,expected', [('bad', 24576), ('0', 1024), ('999999', 32768)])
def test_output_budget_has_safe_bounds(monkeypatch, value, expected):
    monkeypatch.setenv('DEEPSEEK_MAX_TOKENS', value)
    assert parse_token_limit('deepseek') == expected


def test_only_a_single_complete_json_fence_is_unwrapped():
    assert completion_content({'choices': [{'message': {'content': '```json\n{"ok":true}\n```'}}]}) == '{"ok":true}'
    with pytest.raises(IncompleteParse):
        completion_content({'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]})
