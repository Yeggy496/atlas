"""Failure-path tests; mocked model responses are not live API validation."""
from io import BytesIO
import json
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from openpyxl import Workbook
import pytest

from app.adapters import ADAPTERS
from app.llm.providers import APIProvider
from app.main import app


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


@pytest.mark.parametrize('failure', ['timeout', 'unauthorized'])
def test_model_network_failure_does_not_crash(monkeypatch, failure):
    monkeypatch.setenv('OPENAI_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    request = httpx.Request('POST', 'https://example.invalid')
    error = httpx.ReadTimeout('timeout', request=request) if failure == 'timeout' else httpx.HTTPStatusError('unauthorized', request=request, response=httpx.Response(401, request=request))
    with patch('app.llm.providers.httpx.Client.post', side_effect=error):
        with pytest.raises(ValueError, match='模型解析未成功'):
            APIProvider('openai').parse_constraints(ADAPTERS['life'](), '新增会议')


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
