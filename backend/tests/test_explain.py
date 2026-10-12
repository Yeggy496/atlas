"""The "why this time?" explanation must be derived from the real solution."""
from fastapi.testclient import TestClient

from app.adapters import ADAPTERS
from app.main import app
from app.schemas import Activity, Assignment, Constraint, Problem, Resource
from app.solver.engine import solve
from app.solver.explain import explain


def _solved(scenario):
    problem = ADAPTERS[scenario]()
    result = solve(problem, seconds=4)
    assert result['status'] in ('OPTIMAL', 'FEASIBLE')
    return problem, [Assignment(**a) for a in result['assignments']]


def test_every_scheduled_activity_has_data_only_reasons():
    problem, assignments = _solved('life')
    assert assignments
    for chosen in assignments:
        data = explain(problem, assignments, chosen.activity_id)
        assert data['activity_id'] == chosen.activity_id
        assert data['start'] == chosen.start and data['end'] == chosen.end
        assert data['candidate_slots_total'] >= 1
        assert data['reasons'], 'an explanation must never be empty'


def test_life_running_preference_is_explained_with_its_window():
    problem, assignments = _solved('life')
    run = next(a for a in problem.activities if a.category == 'exercise')
    data = explain(problem, assignments, run.id)
    preference = [r for r in data['reasons'] if r['kind'] == 'preference']
    assert preference, 'the life adapter declares a running time preference'
    assert any('17:00' in r['detail'] or '偏好' in r['title'] for r in preference)


def test_fixed_time_constraint_is_reported():
    problem = Problem(
        scenario='life',
        name='fixed',
        activities=[Activity(id='m', name='临时会议', duration=2, category='meeting', days=[2], window_start=30, window_end=44)],
        resources=[Resource(id='me', name='我')],
        constraints=[Constraint(id='f', label='周三 19:00 临时会议', type='fixed_time', target='m', day=2, start=38)],
    )
    result = solve(problem, seconds=3)
    assert result['status'] in ('OPTIMAL', 'FEASIBLE')
    assignments = [Assignment(**a) for a in result['assignments']]
    data = explain(problem, assignments, 'm')
    assert any(r['kind'] == 'fixed' for r in data['reasons'])
    assert data['candidate_slots_total'] == 1
    candidate = next(r for r in data['reasons'] if r['kind'] == 'candidates')
    assert '只有 1 个候选开始时段' in candidate['detail']
    assert '未检查其他活动' in candidate['detail']
    assert not any(r['kind'] == 'boundary' for r in data['reasons'])


def test_explain_endpoint_returns_reasons_and_404_for_unknown_activity():
    problem, assignments = _solved('life')
    payload = {'problem': problem.model_dump(), 'assignments': [a.model_dump() for a in assignments]}
    with TestClient(app, raise_server_exceptions=False) as client:
        ok = client.post('/api/explain', json={**payload, 'activity_id': assignments[0].activity_id})
        assert ok.status_code == 200
        assert ok.json()['reasons']
        missing = client.post('/api/explain', json={**payload, 'activity_id': 'does-not-exist'})
        assert missing.status_code == 404
