from copy import deepcopy

from app.adapters import life
from app.llm.overnight import expand_fixed_daily_sleep
from app.llm.providers import validate_parse
from app.schemas import Assignment
from app.solver.engine import solve
from app.solver.validator import verify


TEXT = '每天晚上23:00到第二天早上7:00睡觉。'


def blank():
    return life().model_copy(update={'activities': [], 'constraints': []})


def test_explicit_overnight_sleep_is_split_into_week_bounded_fixed_segments():
    expected = blank()
    # This is the malformed cross-midnight result we have to handle before
    # Pydantic validation; it is synthetic, not a captured model response.
    data = {'problem': expected.model_dump(), 'summary': [], 'warnings': []}
    data['problem']['activities'] = [{'id': 's', 'name': '睡眠', 'category': 'sleep',
        'resources': ['me'], 'days': [0], 'duration': 16, 'window_start': 46, 'window_end': 14}]
    original = deepcopy(data)
    output = expand_fixed_daily_sleep(data, expected, TEXT)
    assert data == original
    problem = validate_parse(output, 'deepseek', expected=expected)['problem']
    from app.schemas import Problem
    p = Problem.model_validate(problem)
    assert len(p.activities) == 14
    result = solve(p, seconds=2)
    assert result['status'] in ('OPTIMAL', 'FEASIBLE')
    assignments = [Assignment.model_validate(x) for x in result['assignments']]
    assert not verify(p, assignments)
    assert {(a.start, a.end) for a in assignments} == {
        interval for d in range(7) for interval in ((d * 48, d * 48 + 14), (d * 48 + 46, d * 48 + 48))
    }
    assert '周一凌晨' in output['warnings'][-1]


def test_existing_sleep_or_negated_input_is_not_rewritten():
    existing = life()
    data = {'problem': existing.model_dump(), 'summary': [], 'warnings': []}
    assert expand_fixed_daily_sleep(data, existing, TEXT) is data
    empty = blank()
    data = {'problem': empty.model_dump(), 'summary': [], 'warnings': []}
    assert expand_fixed_daily_sleep(data, empty, '不需要' + TEXT) is data


def test_unrelated_sleep_relationship_is_not_discarded():
    expected = blank()
    data = {'problem': expected.model_dump(), 'summary': [], 'warnings': []}
    data['problem']['activities'] = [{'id': 'sleep', 'name': '睡眠', 'category': 'sleep'}]
    data['problem']['constraints'] = [{'id': 'x', 'type': 'precedence', 'target': 'sleep', 'other': 'study'}]
    assert expand_fixed_daily_sleep(data, expected, TEXT) is data
