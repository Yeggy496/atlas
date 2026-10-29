from app.llm.soft_preferences import normalize_soft_preferences
from app.llm.providers import validate_parse
from app.adapters import life


def data_with_constraints(constraints):
    problem = life().model_copy(update={'activities': [], 'constraints': []}).model_dump()
    return {'problem': {**problem, 'constraints': constraints}, 'summary': [], 'warnings': []}


def test_unsupported_soft_deadline_is_not_made_hard_and_user_is_warned():
    data = data_with_constraints([{'id': 'p', 'label': '尽量周五完成', 'type': 'deadline',
                                   'target': '*', 'level': 'soft', 'end': 226}])
    out = normalize_soft_preferences(data)
    assert len(data['problem']['constraints']) == 1
    assert out['problem']['constraints'] == []
    assert '未纳入本次求解' in out['warnings'][0]
    assert validate_parse(out, 'deepseek')['requires_review']


def test_soft_time_window_becomes_preference_not_hard_constraint():
    data = data_with_constraints([{'id': 'p', 'label': '尽量上午', 'type': 'time_window',
                                   'target': '*', 'level': 'soft', 'start': 18, 'end': 24}])
    out = normalize_soft_preferences(data)
    c = out['problem']['constraints'][0]
    assert c['type'] == 'preferred_window' and c['level'] == 'soft'
    assert validate_parse(out, 'deepseek')['requires_review']


def test_hard_conditions_are_never_weakened():
    data = data_with_constraints([{'id': 'p', 'label': '必须周五完成', 'type': 'deadline',
                                   'target': '*', 'level': 'hard', 'end': 226}])
    out = normalize_soft_preferences(data)
    assert out['problem']['constraints'] == data['problem']['constraints']
    assert not out['warnings']


def test_week_wide_soft_window_is_not_misread_as_a_daily_window():
    data = data_with_constraints([{'id': 'p', 'label': '尽量周五前完成', 'type': 'preferred_window',
                                   'target': '*', 'level': 'soft', 'start': 0, 'end': 226}])
    out = normalize_soft_preferences(data)
    assert not out['problem']['constraints']
    assert '未纳入本次求解' in out['warnings'][-1]


def test_avoid_period_is_not_treated_as_a_preferred_period():
    data = data_with_constraints([{'id': 'p', 'label': '周五下午尽量少排课', 'type': 'preferred_window',
                                   'target': '*', 'level': 'soft', 'day': 4, 'start': 28, 'end': 36}])
    out = normalize_soft_preferences(data)
    assert not out['problem']['constraints']
    assert '未纳入本次求解' in out['warnings'][-1]
