from threading import BoundedSemaphore

from fastapi.testclient import TestClient
import pytest

from app import main
from app.llm.providers import DemoProvider
from app.schemas import Activity, Problem, Resource
from app.solver.engine import solve
from app.workload import _limit


def small_problem():
    return Problem(scenario='life', name='并发检查', week_start='2026-10-12',
                   resources=[Resource(id='me', name='我')],
                   activities=[Activity(id='a', name='任务', resources=['me'], duration=2,
                                        days=[0], window_start=16, window_end=20)])


def test_solver_admission_rejects_overload_and_recovers(monkeypatch):
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(main, 'SOLVER_SLOTS', slots)
    payload = {'problem': small_problem().model_dump(), 'reviewed': True}
    with TestClient(main.app) as client:
        slots.acquire()
        try:
            for route in ['/api/solve', '/api/diagnose']:
                response = client.post(route, json=payload)
                assert response.status_code == 429
                assert response.headers['Retry-After'] == '3'
                assert '保留' in response.json()['detail']
        finally:
            slots.release()
        result = client.post('/api/solve', json=payload)
    assert result.status_code == 200
    assert result.json()['metrics']['hard_violations'] == 0


def test_solver_exception_releases_admission(monkeypatch):
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(main, 'SOLVER_SLOTS', slots)

    def failure(*args, **kwargs):
        raise RuntimeError('simulated solver failure')

    monkeypatch.setattr(main, 'solve', failure)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert client.post('/api/solve', json={'problem': small_problem().model_dump(), 'reviewed': True}).status_code == 500
    assert slots.acquire(blocking=False), 'A failed request must not occupy the slot forever'
    slots.release()


def test_model_admission_keeps_facts_available(monkeypatch):
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(main, 'MODEL_SLOTS', slots)
    monkeypatch.setattr(main, 'get_provider', lambda: DemoProvider())
    problem = small_problem()
    result = solve(problem, seconds=2)
    with TestClient(main.app) as client:
        slots.acquire()
        try:
            parsed = client.post('/api/constraints/parse', json={'problem': problem.model_dump(), 'text': '周三19:00有一个会议'})
            assert parsed.status_code == 429
            body = {'problem': problem.model_dump(), 'assignments': result['assignments'], 'activity_id': 'a'}
            assert client.post('/api/explain', json=body).status_code == 429
            facts = client.post('/api/explain', json={**body, 'include_narrative': False})
            assert facts.status_code == 200 and facts.json()['narrative'] is None
        finally:
            slots.release()
        assert client.post('/api/constraints/parse', json={'problem': problem.model_dump(), 'text': '周三19:00有一个会议'}).status_code == 200


def test_optional_priority_changes_the_real_solver_choice():
    problem = small_problem()
    low = problem.activities[0].model_copy(update={'id': 'low', 'optional': True, 'priority': 2, 'window_end': 18})
    high = low.model_copy(update={'id': 'high', 'name': '更重要的任务', 'priority': 9})
    problem.activities = [low, high]
    result = solve(problem, seconds=2)
    assert result['status'] == 'OPTIMAL'
    assert [a['activity_id'] for a in result['assignments']] == ['high']
    assert result['metrics']['hard_violations'] == 0


@pytest.mark.parametrize('value,expected', [('invalid', 2), ('0', 1), ('99', 8)])
def test_admission_setting_has_safe_bounds(monkeypatch, value, expected):
    monkeypatch.setenv('OPTIDAY_TEST_LIMIT', value)
    assert _limit('OPTIDAY_TEST_LIMIT') == expected
