"""Flag meeting participants that were not explicit in the meeting's sentence."""
import re


def meeting_participant_warnings(problem, text):
    if problem.scenario != 'meeting':
        return []
    sentences = [s for s in re.split(r'[。；;\n]', text) if s.strip()]
    people = {r.id: r.name for r in problem.resources if r.type == 'person'}
    warnings = []
    for activity in problem.activities:
        matching = [s for s in sentences if activity.name and activity.name in s]
        if len(matching) != 1:
            continue
        sentence = matching[0]
        inferred = [people[rid] for rid in activity.resources if rid in people and people[rid] not in sentence]
        if inferred:
            names = '、'.join(inferred)
            warnings.append(f'“{activity.name}”关联的参会人（{names}）未在该会议的描述中直接列出，可能根据上下文推断，请核对。')
    return warnings


def constrained_preference_warnings(problem):
    names = []
    for activity in problem.activities:
        for rule in problem.constraints:
            targets = {'*', activity.id, activity.category, *activity.resources, *activity.demands}
            if (rule.type == 'preferred_window' and rule.target in targets and
                (rule.day is None or rule.day in activity.days) and (rule.start, rule.end) != (0, 48) and
                activity.window_start >= rule.start and activity.window_end <= rule.end):
                names.append(activity.name)
                break
    if not names:
        return []
    display = '、'.join(names[:5]) + ('等' if len(names) > 5 else '')
    return [f'以下活动的允许时间已限制在偏好时段内：{display}。如果只是“尽量”而非必须，请检查活动时间范围。']
