"""A timed-out optimizer must never erase a real, validated feasible solution."""
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from ortools.sat.python import cp_model
import pytest

from app.schemas import Activity, Assignment, Constraint, Problem, Resource
from app.solver.engine import solve
from app.solver.search import search
from app.solver.validator import verify


def test_optimizer_timeout_keeps_real_solution_with_original_objective():
    model = cp_model.CpModel()
    x = model.new_int_var(1, 3, 'x')
    objective = 7 * x + 5
    model.minimize(objective)
    actual = cp_model.CpSolver()
    timed_out = SimpleNamespace(parameters=SimpleNamespace(), wall_time=0.01, best_objective_bound=12.0,
                                solve=lambda model: cp_model.UNKNOWN)
    with patch('app.solver.search.cp_model.CpSolver', side_effect=[actual, timed_out]), \
            patch('app.solver.search.monotonic', side_effect=[100.0, 100.6]):
        result = search(model, 3, 1, objective)
    assert result.status == cp_model.FEASIBLE
    assert 1 <= result.solver.value(x) <= 3
    assert result.objective == 7 * result.solver.value(x) + 5
    assert result.best_bound <= result.objective
    assert result.source == 'feasibility'
    assert timed_out.parameters.max_time_in_seconds == pytest.approx(2.4)


def test_timeout_without_a_real_incumbent_stays_unknown():
    model = cp_model.CpModel()
    x = model.new_bool_var('x')
    model.minimize(x)
    exhausted = SimpleNamespace(parameters=SimpleNamespace(), wall_time=0.01, best_objective_bound=0.0,
                               solve=lambda model: cp_model.UNKNOWN)
    with patch('app.solver.search.cp_model.CpSolver', return_value=exhausted):
        result = search(model, 0.1, 1, x)
    assert result.status == cp_model.UNKNOWN


def test_optimized_result_can_still_prove_optimality():
    model = cp_model.CpModel()
    x = model.new_int_var(1, 10, 'x')
    model.minimize(x)
    result = search(model, 2, 1, x)
    assert result.status == cp_model.OPTIMAL
    assert result.solver.value(x) == result.objective == result.best_bound == 1


def test_impossible_model_is_not_returned_as_feasible():
    model = cp_model.CpModel()
    x = model.new_bool_var('x')
    model.add(x == 0)
    model.add(x == 1)
    model.minimize(x)
    assert search(model, 2, 1, x).status == cp_model.INFEASIBLE


def test_fallback_still_passes_independent_checks_and_reports_real_penalties():
    problem = Problem(scenario='life', name='超时保留合法计划', resources=[Resource(id='me', name='我')],
                      activities=[Activity(id='a', name='任务', resources=['me'], days=[0], window_start=16, window_end=20)],
                      constraints=[Constraint(id='early', label='优先早上', type='preferred_window', target='a',
                                              level='soft', start=16, end=18)])
    actual = cp_model.CpSolver()
    timed_out = SimpleNamespace(parameters=SimpleNamespace(), wall_time=0.01, best_objective_bound=0,
                                solve=lambda model: cp_model.UNKNOWN)
    with patch('app.solver.search.cp_model.CpSolver', side_effect=[actual, timed_out]):
        result = solve(problem, seconds=2)
    assert result['status'] == 'FEASIBLE'
    assert verify(problem, [Assignment.model_validate(x) for x in result['assignments']]) == []
    objective = result['objective']
    assert objective['value'] == sum(objective['weights'][k] * v for k, v in objective['penalties'].items())
    assert result['metrics']['feasibility_fallback'] == 1


def test_long_weekly_plan_remains_usable_with_one_search_worker(monkeypatch):
    monkeypatch.setenv('OPTIDAY_SOLVER_WORKERS', '1')
    problem = Problem.model_validate_json((Path(__file__).parent / 'fixtures/weekly_47.json').read_text(encoding='utf-8'))
    result = solve(problem, seconds=4)
    assert result['status'] in ('FEASIBLE', 'OPTIMAL')
    assignments = [Assignment.model_validate(x) for x in result['assignments']]
    assert not verify(problem, assignments)
    assert {a.id for a in problem.activities if not a.optional}.issubset({a.activity_id for a in assignments})
