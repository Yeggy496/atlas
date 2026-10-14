from app.adapters import ADAPTERS
from app.llm.explanation_service import LLMExplanation
from app.schemas import Assignment


def test_facts_only_never_calls_model(monkeypatch):
    problem = ADAPTERS['life']()
    activity = problem.activities[0]
    assignment = Assignment(activity_id=activity.id, start=0, end=activity.duration)
    service = LLMExplanation('deepseek')

    def unexpected_call(_facts):
        raise AssertionError('Facts-only requests must not call the paid model')

    monkeypatch.setattr(service, '_narrate', unexpected_call)
    facts = service.build(problem, [assignment], activity.id, include_narrative=False)
    assert facts['activity_id'] == activity.id
    assert facts['narrative'] is None
    assert facts['narrative_source'] == 'deterministic'
    assert facts['reasons']
