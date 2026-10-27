"""The comparison harness must stay real: no number may drift from a live run.

These tests pin the behaviour the competition report relies on -- OptiDay
passes every hard constraint and the baselines do not -- and cover the parsing
of a Direct-LLM schedule, so the report's "killer table" cannot silently become
a fabricated one.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_benchmark():
    spec = importlib.util.spec_from_file_location('optiday_benchmark', ROOT / 'scripts' / 'benchmark.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = load_benchmark()


def test_optiday_passes_every_hard_constraint_where_baselines_do_not():
    problem = bench.ADAPTERS['academic']()
    optiday_assignments = bench._as_assignments(bench.solve(problem, 'balanced', seconds=3.0)['assignments'])
    optiday_metrics = bench.compute_metrics(problem, optiday_assignments, 0.0)
    assert optiday_metrics['hard_violations'] == 0
    assert optiday_metrics['valid'] is True

    random_metrics = bench.compute_metrics(problem, bench.random_schedule(problem, seed=0), 0.0)
    greedy_metrics = bench.compute_metrics(problem, bench.greedy_schedule(problem), 0.0)
    assert random_metrics['hard_violations'] > 0
    assert greedy_metrics['hard_violations'] > 0


def test_llm_proxy_is_deterministic_and_offline():
    problem = bench.ADAPTERS['lab']()
    first = bench.llm_proxy_schedule(problem)
    second = bench.llm_proxy_schedule(problem)
    assert [(x.activity_id, x.start, x.room_id) for x in first] == \
           [(x.activity_id, x.start, x.room_id) for x in second]
    assert len(first) == len(problem.activities)


def test_run_benchmark_records_real_solver_scale():
    problem = bench.ADAPTERS['lab']()
    rows = bench.run_benchmark([('lab', problem)], ['optiday'], 0, 'demo', 3.0)
    solver = rows[0]['solver']
    assert solver['variables'] > 0
    assert solver['model_constraints'] > 0
    assert rows[0]['hard_violations'] == 0


def test_validate_schedule_keeps_only_known_activities():
    from app.llm.providers import validate_schedule
    from app.schemas import Activity, Problem, Resource

    problem = Problem(scenario='life', name='t', activities=[
        Activity(id='a', name='A', duration=2, resources=['me']),
        Activity(id='b', name='B', duration=2, resources=['me'])],
        resources=[Resource(id='me', name='我的时间')])
    data = {'assignments': [
        {'activity_id': 'a', 'start': 0, 'end': 2, 'room_id': None},
        {'activity_id': 'ghost', 'start': 0, 'end': 2},
        {'activity_id': 'b', 'start': 'oops', 'end': 4},
        'not-a-dict']}
    kept = validate_schedule(data, problem)
    assert [x.activity_id for x in kept] == ['a']
    assert kept[0].start == 0 and kept[0].end == 2


def test_render_markdown_has_table4():
    meta = {'generated_at': 'now', 'provider': 'demo', 'seed': 0, 'optiday_seconds': 4.0, 'methods': ['optiday']}
    rows = [{'instance': 'lab', 'method': 'optiday', 'hard_violations': 0, 'valid': True,
             'preference_score': 1.0, 'fragmentation_slots': 0, 'daily_load_span_hours': 2.0,
             'solve_time': 1.0, 'activities': 6, 'solver': {'variables': 10, 'model_constraints': 12,
                                                            'status': 'OPTIMAL'}}]
    summary = bench.aggregate(rows, ['lab'])
    md = bench.render_markdown(rows, summary, meta)
    assert 'Hard Violations' in md and 'Preference Score' in md and 'optiday' in md
