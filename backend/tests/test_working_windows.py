from app.adapters import meeting
from app.llm.working_windows import normalize_explicit_working_windows
from app.schemas import Problem, Assignment
from app.solver.engine import solve
from app.solver.validator import verify
from app.llm.providers import APIProvider
from unittest.mock import patch
import httpx
import json


def payload():
    problem = meeting().model_copy(update={'activities': [], 'constraints': []})
    data = {'problem': problem.model_dump(), 'warnings': []}
    data['problem']['activities'] = [{'id': 'm', 'name': '会议', 'duration': 4,
        'days': [0], 'window_start': 18, 'window_end': 36}]
    data['problem']['constraints'] = [
        {'id': 'morning', 'type': 'time_window', 'label': '上午', 'target': '*', 'start': 18, 'end': 24},
        {'id': 'afternoon', 'type': 'time_window', 'label': '下午', 'target': '*', 'start': 26, 'end': 36},
    ]
    return problem, data


def test_explicit_alternative_windows_remain_hard_but_allow_either_period():
    expected, data = payload()
    output = normalize_explicit_working_windows(data, expected,
        '会议可以安排在周一至周五9:00到12:00、13:00到18:00。')
    assert data['problem']['constraints'][0]['end'] == 24
    problem = Problem.model_validate(output['problem'])
    assert {(c.type, c.start, c.end) for c in problem.constraints} == {
        ('time_window', 18, 36), ('unavailable', 24, 26)}
    result = solve(problem, seconds=2)
    assert result['status'] in ('FEASIBLE', 'OPTIMAL')
    chosen = [Assignment.model_validate(a) for a in result['assignments']]
    assert not verify(problem, chosen)
    assert chosen[0].end <= 24 or chosen[0].start >= 26
    assert '两个可用时段' in output['warnings'][-1]


def test_preexisting_or_unrelated_windows_are_not_rewritten():
    expected, data = payload()
    assert normalize_explicit_working_windows(data, expected, '两个日期时间不同。') == data
    expected = expected.model_copy(update={'constraints': Problem.model_validate(data['problem']).constraints})
    out = normalize_explicit_working_windows(data, expected, '会议可安排在9:00到12:00、13:00到18:00。')
    assert out['problem']['constraints'] == data['problem']['constraints']


def test_existing_unavailable_gap_is_not_duplicated():
    expected, data = payload()
    data['problem']['constraints'].append({'id': 'lunch', 'type': 'unavailable',
        'label': '午休', 'target': '*', 'start': 24, 'end': 26})
    out = normalize_explicit_working_windows(data, expected, '会议可安排在9:00到12:00和13:00到18:00。')
    assert sum(c['type'] == 'unavailable' for c in out['problem']['constraints']) == 1


def test_activity_restricted_to_only_one_period_is_flagged():
    expected, data = payload()
    data['problem']['activities'][0].update(window_start=18, window_end=24)
    data['problem']['constraints'] = []
    out = normalize_explicit_working_windows(data, expected, '会议可安排在9:00到12:00、13:00到18:00。')
    assert '仅允许' in out['warnings'][-1]


def test_provider_applies_window_fix_and_reports_unsupported_soft_deadline(monkeypatch):
    expected, data = payload()
    data['summary'] = []
    data['problem']['constraints'].append({'id': 'soft', 'type': 'deadline', 'label': '尽量周五完成',
                                           'target': '*', 'end': 226, 'level': 'soft'})
    response = httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
        'content': json.dumps(data, ensure_ascii=False)}}]}, request=httpx.Request('POST', 'https://example.invalid'))
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'TEST_ONLY_PLACEHOLDER')
    with patch('app.llm.providers.httpx.Client.post', return_value=response):
        parsed = APIProvider('deepseek').parse_constraints(expected, '会议可安排在9:00到12:00、13:00到18:00。')
    problem = Problem.model_validate(parsed['problem'])
    assert {(c.type, c.start, c.end) for c in problem.constraints} == {
        ('time_window', 18, 36), ('unavailable', 24, 26)}
    assert any('未纳入本次求解' in w for w in parsed['warnings'])
    assert parsed['requires_review']
