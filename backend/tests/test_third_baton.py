"""Third-baton coverage: text/PDF import, LLM explanation boundary, plan compare.

These tests protect the MASTER_SPEC §11/§16/§18 behaviours added on top of the
already-stable first two batons. They must not require a live model, and they must
not change any existing module's contract.
"""
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.adapters import ADAPTERS
from app.importer import extract_text
from app.llm.explanation_service import LLMExplanation, get_explanation_service
from app.main import app
from app.schemas import Assignment
from app.solver.compare import compare_plans
from app.solver.engine import solve


# --------------------------------------------------------------------------- #
# TXT / PDF extraction (MASTER_SPEC §11)
# --------------------------------------------------------------------------- #

def test_txt_extraction_decodes_utf8_and_gb18030():
    assert extract_text('req.txt', '每天睡眠8小时'.encode('utf-8'))['text'] == '每天睡眠8小时'
    assert extract_text('req.txt', '每天睡眠8小时'.encode('gb18030'))['text'] == '每天睡眠8小时'


def test_unsupported_extension_is_rejected():
    with pytest.raises(ValueError, match='TXT 和 PDF'):
        extract_text('data.docx', b'x')


def test_empty_text_is_rejected():
    with pytest.raises(ValueError, match='提取到文字'):
        extract_text('req.txt', b'   \n  ')


def test_pdf_without_library_degrades_gracefully(monkeypatch):
    """Missing pypdf must be a friendly error, never a crash."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == 'pypdf':
            raise ImportError('no pypdf')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', fake_import)
    with pytest.raises(ValueError, match='pypdf'):
        extract_text('report.pdf', b'%PDF-1.4 fake')


def test_text_import_endpoint_returns_extracted_text_without_mutating_problem():
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            '/api/import/text',
            files={'file': ('req.txt', '周三19:00有一个临时会议。'.encode('utf-8'))},
        )
    assert response.status_code == 200
    body = response.json()
    assert body['kind'] == 'txt'
    assert '临时会议' in body['text']
    # The endpoint returns text only; it must not fabricate a problem or constraints.
    assert 'problem' not in body and 'constraints' not in body


# --------------------------------------------------------------------------- #
# LLM explanation boundary (MASTER_SPEC §18)
# --------------------------------------------------------------------------- #

def _solved(scenario):
    problem = ADAPTERS[scenario]()
    result = solve(problem, seconds=4)
    assert result['status'] in ('OPTIMAL', 'FEASIBLE')
    return problem, [Assignment(**a) for a in result['assignments']]


def test_demo_provider_keeps_explanation_deterministic():
    problem, assignments = _solved('life')
    data = get_explanation_service().build(problem, assignments, assignments[0].activity_id)
    assert data['narrative_source'] == 'deterministic'
    assert data['narrative'] is None
    assert data['reasons']


def test_provider_failure_falls_back_to_deterministic_facts(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    problem, assignments = _solved('life')
    boom = httpx.ReadTimeout('slow', request=httpx.Request('POST', 'https://example.invalid'))
    with patch('app.llm.explanation_service.httpx.Client.post', side_effect=boom):
        data = LLMExplanation('openai').build(problem, assignments, assignments[0].activity_id)
    assert data['narrative_source'] == 'deterministic'
    assert data['reasons'], 'deterministic facts must survive a model failure'


def test_valid_model_narrative_is_attached_but_facts_unchanged(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    problem, assignments = _solved('life')
    payload = {'headline': '因为它不与固定课程冲突。', 'bullets': ['符合 17:00 后的偏好']}
    response = httpx.Response(
        200,
        json={'choices': [{'message': {'content': __import__('json').dumps(payload, ensure_ascii=False)}}]},
        request=httpx.Request('POST', 'https://example.invalid'),
    )
    with patch('app.llm.explanation_service.httpx.Client.post', return_value=response):
        data = LLMExplanation('openai').build(problem, assignments, assignments[0].activity_id)
    assert data['narrative_source'] == 'openai'
    assert data['narrative']['headline'] == payload['headline']
    assert data['candidate_slots_total'] >= 1  # facts still present and intact


def test_malformed_narrative_is_discarded(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    problem, assignments = _solved('life')
    for bad in ({'headline': ''}, {'bullets': ['x']}, ['not', 'a', 'dict']):
        response = httpx.Response(
            200,
            json={'choices': [{'message': {'content': __import__('json').dumps(bad)}}]},
            request=httpx.Request('POST', 'https://example.invalid'),
        )
        with patch('app.llm.explanation_service.httpx.Client.post', return_value=response):
            data = LLMExplanation('openai').build(problem, assignments, assignments[0].activity_id)
        assert data['narrative'] is None, f'{bad!r} must be rejected'


def test_explain_endpoint_still_404s_for_unknown_activity():
    problem, assignments = _solved('life')
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/api/explain', json={
            'problem': problem.model_dump(),
            'assignments': [a.model_dump() for a in assignments],
            'activity_id': 'nope',
        })
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Plan comparison (MASTER_SPEC §16 / §37)
# --------------------------------------------------------------------------- #

def test_identical_schedules_report_no_change():
    problem, assignments = _solved('lab')
    diff = compare_plans(problem, assignments, assignments)
    assert diff['changed'] == 0
    assert diff['stability'] == 1.0
    assert len(diff['kept']) == len(assignments)


def test_moved_activity_is_reported_with_delta_and_same_day_flag():
    problem, assignments = _solved('lab')
    before = [a.model_dump() for a in assignments]
    moved_id = assignments[0].activity_id
    after = []
    for a in assignments:
        item = a.model_dump()
        if a.activity_id == moved_id:
            item['start'] += 2
            item['end'] += 2
        after.append(item)
    diff = compare_plans(problem, before, after)
    assert diff['changed'] == 1
    moved = diff['moved'][0]
    assert moved['activity_id'] == moved_id
    assert moved['delta_slots'] == 2
    assert 'from' in moved and 'day_name' in moved


def test_compare_endpoint_classifies_added_and_removed():
    problem, assignments = _solved('lab')
    subset = [a.model_dump() for a in assignments[1:]]
    with TestClient(app, raise_server_exceptions=False) as client:
        diff = client.post('/api/compare', json={
            'problem': problem.model_dump(),
            'previous': [a.model_dump() for a in assignments],
            'current': subset,
        }).json()
    assert diff['changed'] == 1
    assert len(diff['removed']) == 1
    assert 0 <= diff['stability'] <= 1
