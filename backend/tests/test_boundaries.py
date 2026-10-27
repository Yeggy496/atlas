"""Failure-path tests; mocked model responses are not live API validation."""
from io import BytesIO
import json
from unittest.mock import patch
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from openpyxl import Workbook
import pytest

from app.adapters import ADAPTERS
from app.llm.providers import APIProvider, parse_failure_message
from app.main import app
from app.schemas import Assignment
from app.solver.engine import preference_summary, solve


@pytest.mark.parametrize('provider', ['openai', 'deepseek'])
@pytest.mark.parametrize('envelope', [
    {'choices': []},
    {'choices': None},
    {'choices': [{'message': {'content': None}}]},
    {'choices': [{'message': {'content': '[]'}}]},
    {'choices': [{'message': {'content': 'not JSON'}}]},
    {'choices': [{'message': {'content': '{"summary": []}'}}]},
])
def test_malformed_model_response_is_a_friendly_api_error(monkeypatch, provider, envelope):
    monkeypatch.setenv('LLM_PROVIDER', provider)
    monkeypatch.setenv(provider.upper() + '_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    response = httpx.Response(200, json=envelope, request=httpx.Request('POST', 'https://example.invalid'))
    with patch('app.llm.providers.httpx.Client') as model_client:
        model_client.return_value.__enter__.return_value.post.return_value = response
        with TestClient(app, raise_server_exceptions=False) as client:
            result = client.post('/api/constraints/parse', json={'problem': ADAPTERS['life']().model_dump(), 'text': '新增会议'})
    assert result.status_code == 422
    assert '模型解析未成功' in result.json()['detail']
    assert 'TEST_ONLY_PLACEHOLDER' not in result.text


@pytest.mark.parametrize('provider', ['openai', 'deepseek'])
def test_valid_model_output_still_requires_user_review(monkeypatch, provider):
    monkeypatch.setenv(provider.upper() + '_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    problem = ADAPTERS['life']()
    data = {'problem': problem.model_dump(), 'summary': ['保持原任务'], 'warnings': []}
    response = httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(data)}}]}, request=httpx.Request('POST', 'https://example.invalid'))
    with patch('app.llm.providers.httpx.Client.post', return_value=response) as post:
        result = APIProvider(provider).parse_constraints(problem, '保持原任务')
    assert result['requires_review'] is True
    assert result['provider'] == provider
    assert post.call_args.kwargs['json']['response_format'] == {'type': 'json_object'}
    payload = post.call_args.kwargs['json']
    if provider == 'deepseek':
        assert payload['thinking'] == {'type': 'disabled'}
    else:
        assert 'thinking' not in payload


@pytest.mark.parametrize('failure', ['timeout', 'unauthorized'])
def test_model_network_failure_does_not_crash(monkeypatch, failure):
    monkeypatch.setenv('OPENAI_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    request = httpx.Request('POST', 'https://example.invalid')
    error = httpx.ReadTimeout('timeout', request=request) if failure == 'timeout' else httpx.HTTPStatusError('unauthorized', request=request, response=httpx.Response(401, request=request))
    with patch('app.llm.providers.httpx.Client.post', side_effect=error):
        with pytest.raises(ValueError, match='模型解析未成功'):
            APIProvider('openai').parse_constraints(ADAPTERS['life'](), '新增会议')


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 503])
def test_model_http_errors_identify_status_without_leaking_secrets(status):
    request = httpx.Request('POST', 'https://example.invalid/private?key=SECRET_TEST_VALUE')
    error = httpx.HTTPStatusError('Bearer SECRET_TEST_VALUE', request=request,
                                  response=httpx.Response(status, request=request))
    message = parse_failure_message(error)
    assert f'HTTP {status}' in message
    assert 'SECRET_TEST_VALUE' not in message
    assert 'example.invalid' not in message
    if status >= 500:
        assert '稍后重试' in message and '手工编辑和求解' in message


def test_model_tls_and_timeout_errors_are_distinguishable():
    request = httpx.Request('POST', 'https://example.invalid')
    tls = httpx.ConnectError('CERTIFICATE_VERIFY_FAILED SECRET_TEST_VALUE', request=request)
    timeout = httpx.ReadTimeout('SECRET_TEST_VALUE', request=request)
    assert '证书校验失败' in parse_failure_message(tls)
    assert '请求超时' in parse_failure_message(timeout)
    assert 'SECRET_TEST_VALUE' not in parse_failure_message(tls) + parse_failure_message(timeout)


@pytest.mark.parametrize('filetype', ['csv', 'xlsx'])
def test_missing_duration_returns_422_not_server_error(filetype):
    if filetype == 'csv':
        content = b'name,duration_minutes\nMeeting\n'
    else:
        workbook = Workbook()
        workbook.active.append(['name', 'duration_minutes'])
        workbook.active.append(['Meeting', None])
        output = BytesIO()
        workbook.save(output)
        content = output.getvalue()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/api/import', data={'problem_json': ADAPTERS['life']().model_dump_json()}, files={'file': ('missing.' + filetype, content)})
    assert response.status_code == 422
    assert '时长' in response.json()['detail']


def test_fractional_xlsx_minutes_are_not_silently_truncated():
    workbook = Workbook()
    workbook.active.append(['name', 'duration_minutes'])
    workbook.active.append(['Meeting', 60.5])
    output = BytesIO()
    workbook.save(output)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/api/import', data={'problem_json': ADAPTERS['life']().model_dump_json()}, files={'file': ('fraction.xlsx', output.getvalue())})
    assert response.status_code == 422
def test_unknown_timeout_still_returns_a_diagnosis(monkeypatch):
    """A timeout (UNKNOWN) is not proven infeasible, but /api/solve must still
    return an actionable diagnosis instead of a bare status."""
    monkeypatch.setenv('OPTIDAY_DIAGNOSIS_SECONDS', '0.3')
    problem = ADAPTERS['lab']()
    unknown = {
        'status': 'UNKNOWN',
        'assignments': [],
        'metrics': {'solve_time': 0.01, 'activities': len(problem.activities), 'resources': len(problem.resources), 'constraints': len(problem.constraints), 'variables': 0, 'model_constraints': 0},
        'objective': None,
        'conflicts': [],
        'repairs': [],
    }
    with patch('app.main.solve', return_value=unknown):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post('/api/solve', json={'problem': problem.model_dump(), 'reviewed': True, 'mode': 'balanced', 'previous': []})
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'UNKNOWN'
    assert body['conflicts'], 'a timeout must still surface a diagnosis'
    joined = ' '.join(c['title'] + c['detail'] for c in body['conflicts'])
    assert '未证明无解' in joined or '时限' in joined

def test_preference_summary_is_defensive_against_non_window_soft_constraints():
    """A5 regression guard: the soft-preference metric must count only
    preferred_window constraints and must degrade gracefully (no crash, no
    miscount) when a future soft constraint type has no day-local window."""
    problem = ADAPTERS['life']()
    activity_map = {a.id: a for a in problem.activities}
    result = [Assignment(**row) for row in solve(problem, seconds=2)['assignments']]
    soft = [c for c in problem.constraints if c.level == 'soft']
    assert soft, 'the life adapter is expected to declare soft preferences'
    total, satisfied = preference_summary(problem, result, activity_map)
    assert total == len(soft)
    assert 0 <= satisfied <= total

    # A soft constraint without a usable window (a future non-window type, or an
    # inverted window) must be skipped rather than raising or being counted.
    future = problem.model_copy(deep=True)
    future.constraints = problem.constraints + [
        SimpleNamespace(level='soft', type='recurrence', day=None),
        SimpleNamespace(level='soft', type='preferred_window', day=None, start=10, end=4),
    ]
    assert preference_summary(future, result, activity_map) == (total, satisfied)

def test_api_provider_honours_base_url_and_timeout_overrides(monkeypatch):
    """Real gateways need a custom base URL and a longer timeout than the 35s
    default; both must be read from the *_BASE_URL / *_TIMEOUT environment."""
    monkeypatch.setenv('OPENAI_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://gateway.example/v1/')
    monkeypatch.setenv('OPENAI_TIMEOUT', '120')
    problem = ADAPTERS['life']()
    data = {'problem': problem.model_dump(), 'summary': ['保持原任务'], 'warnings': []}
    response = httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(data)}}]}, request=httpx.Request('POST', 'https://example.invalid'))
    with patch('app.llm.providers.httpx.Client') as model_client:
        client = model_client.return_value.__enter__.return_value
        client.post.return_value = response
        APIProvider('openai').parse_constraints(problem, '保持原任务')
    configured = model_client.call_args.kwargs['timeout']
    assert configured.read == 120.0
    assert configured.connect == 10
    posted_url = client.post.call_args.args[0]
    assert posted_url == 'https://gateway.example/v1/chat/completions'
