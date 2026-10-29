from app.adapters import meeting
from app.llm.grounding import meeting_participant_warnings, constrained_preference_warnings
from app.schemas import Activity, Resource, Constraint


def test_unnamed_meeting_participants_are_flagged_without_changing_the_plan():
    p = meeting().model_copy(update={'activities': [Activity(id='weekly', name='部门周例会',
        resources=['designer'])], 'resources': [Resource(id='designer', name='设计师', type='person')],
        'constraints': []})
    warnings = meeting_participant_warnings(p, '周一10:00有部门周例会，6人参加。设计师参与其他会议。')
    assert len(warnings) == 1 and '设计师' in warnings[0] and '请核对' in warnings[0]
    assert p.activities[0].resources == ['designer']
    assert not meeting_participant_warnings(p, '部门周例会由设计师参加。')


def test_activity_window_may_accidentally_make_preference_mandatory():
    p = meeting().model_copy(update={'activities': [Activity(id='run', name='跑步',
        category='exercise', window_start=34, window_end=44)], 'resources': [],
        'constraints': [Constraint(id='p', label='尽量17点以后', type='preferred_window',
            target='exercise', level='soft', start=34, end=44)]})
    assert '跑步' in constrained_preference_warnings(p)[0]
    assert not constrained_preference_warnings(p.model_copy(update={'constraints': []}))
