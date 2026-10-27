"""Public-product privacy and date/time boundary regression checks."""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import storage
from app.main import app


def small_problem():
    return {
        'scenario': 'life', 'name': '我的个人计划', 'week_start': '2026-10-12',
        'resources': [{'id': 'me', 'name': '我'}],
        'activities': [{'id': 'study', 'name': '学习', 'duration': 2,
                        'resources': ['me'], 'days': [0]}],
        'constraints': [],
    }


def test_public_history_hides_old_rows_and_does_not_store_new_content(monkeypatch):
    """Turning off shared history also protects rows from an older release."""
    memory = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    monkeypatch.setattr(storage, 'engine', memory)
    monkeypatch.setenv('OPTIDAY_SERVER_HISTORY', 'true')
    storage.init_db()
    storage.save_run('old-private-run', {'name': '旧访客的私人内容'}, {'status': 'OPTIMAL'})
    assert len(storage.recent_runs()) == 1

    monkeypatch.delenv('OPTIDAY_SERVER_HISTORY')
    with TestClient(app) as client:
        assert client.get('/api/history').json() == []
        assert client.get('/api/health').json()['history_scope'] == 'browser'
        solved = client.post('/api/solve', json={'problem': small_problem(), 'reviewed': True})
        assert solved.status_code == 200
        assert solved.json()['status'] in ('OPTIMAL', 'FEASIBLE')
        assert client.get('/api/history').json() == []

    # The real solve above must not have added a second database row.
    monkeypatch.setenv('OPTIDAY_SERVER_HISTORY', 'true')
    rows = storage.recent_runs()
    assert [row['id'] for row in rows] == ['old-private-run']
    memory.dispose()


@pytest.mark.parametrize('week_start', ['2026-02-30', 'not-a-date', '20261012', '2026-10-14'])
def test_invalid_or_non_monday_week_is_rejected_before_solver(week_start):
    problem = small_problem()
    problem['week_start'] = week_start
    with TestClient(app) as client:
        response = client.post('/api/solve', json={'problem': problem, 'reviewed': True})
    assert response.status_code == 422
    assert '周' in response.text


@pytest.mark.parametrize('interval', [(-1, 1), (0, 337), (336, 337), (20, 20), (20, 18)])
def test_bad_previous_time_interval_is_rejected(interval):
    with TestClient(app) as client:
        response = client.post('/api/solve', json={
            'problem': small_problem(), 'reviewed': True,
            'previous': [{'activity_id': 'study', 'start': interval[0], 'end': interval[1]}],
        })
    assert response.status_code == 422


def test_last_half_hour_of_sunday_remains_a_legal_assignment():
    problem = small_problem()
    activity = problem['activities'][0]
    activity.update(duration=1, days=[6], window_start=47, window_end=48)
    with TestClient(app) as client:
        response = client.post('/api/solve', json={'problem': problem, 'reviewed': True,
            'previous': [{'activity_id': 'study', 'start': 335, 'end': 336}]})
    assert response.status_code == 200
    assert response.json()['assignments'][0]['end'] == 336
    assert response.json()['metrics']['hard_violations'] == 0


def test_valid_new_week_date_survives_validation_without_reinterpretation():
    problem = small_problem()
    problem['week_start'] = '2026-10-19'
    with TestClient(app) as client:
        response = client.post('/api/constraints/validate', json=problem)
    assert response.status_code == 200
    assert response.json()['valid'] is True
