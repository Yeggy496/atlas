"""Handle an explicitly fixed daily overnight sleep interval at week boundaries.

The solver's activities occupy a single calendar day. This narrow rule expands
only an unambiguous daily 24-hour-clock interval, and leaves other sleep input
to the model and user review. It does not change pre-existing sleep activities.
"""
from copy import deepcopy
import re


_DAILY_SLEEP = re.compile(
    r'每天晚上\s*(\d{1,2}):(00|30)\s*(?:到|至|[-–—])\s*'
    r'(?:第二天|次日)(?:早上|上午|凌晨)?\s*(\d{1,2}):(00|30)\s*(?:睡觉|睡眠|休息)'
)


def expand_fixed_daily_sleep(data, expected, text):
    match = _DAILY_SLEEP.search(text)
    if not match or any(word in text[max(0, match.start() - 8):match.start()] for word in ('不用', '不要', '不需要', '取消')):
        return data
    if expected is None or expected.scenario != 'life' or any(a.category == 'sleep' for a in expected.activities):
        return data
    start_hour, start_min, end_hour, end_min = match.groups()
    start = int(start_hour) * 2 + int(start_min) // 30
    end = int(end_hour) * 2 + int(end_min) // 30
    if not (0 <= end < start < 48):
        return data
    if not isinstance(data, dict) or not isinstance(data.get('problem'), dict):
        return data
    out = deepcopy(data)
    problem = out['problem']
    activities, constraints, resources = (problem.get(k) for k in ('activities', 'constraints', 'resources'))
    if not all(isinstance(x, list) for x in (activities, constraints, resources)):
        return data
    people = [r.get('id') for r in resources if isinstance(r, dict) and r.get('type', 'person') == 'person']
    expected_people = [r.id for r in expected.resources if r.type == 'person']
    if len(expected_people) != 1 or expected_people[0] not in people:
        return data
    sleep = [a for a in activities if isinstance(a, dict) and (a.get('category') == 'sleep' or re.search(r'睡眠|睡觉', str(a.get('name', ''))))]
    old_ids = {a.get('id') for a in sleep if isinstance(a.get('id'), str)}
    # Do not discard unfamiliar relationships or rules the model associated
    # with sleep: these need user/model review instead of automatic rewriting.
    targeted = [c for c in constraints if isinstance(c, dict) and (c.get('target') in old_ids or c.get('target') == 'sleep' or c.get('other') in old_ids)]
    if any(c.get('type') not in ('fixed_time', 'time_window') or c.get('other') in old_ids for c in targeted):
        return data
    existing_ids = {a.get('id') for a in activities if isinstance(a, dict)}
    existing_ids |= {r.get('id') for r in resources if isinstance(r, dict)}
    existing_ids |= {c.get('id') for c in constraints if isinstance(c, dict)}
    prefix = 'daily_overnight_sleep'
    while any(f'{prefix}_{day}_{part}' in existing_ids for day in range(7) for part in ('early', 'late')):
        prefix += '_x'
    problem['activities'] = [a for a in activities if a not in sleep]
    problem['constraints'] = [c for c in constraints if c not in targeted]
    for day in range(7):
        for part, begin, finish in (('early', 0, end), ('late', start, 48)):
            if begin == finish:
                continue
            problem['activities'].append({'id': f'{prefix}_{day}_{part}', 'name': '睡眠', 'category': 'sleep',
                'resources': expected_people, 'days': [day], 'window_start': begin, 'window_end': finish,
                'duration': finish - begin})
    if isinstance(out.get('warnings'), list):
        out['warnings'].append('跨午夜睡眠按自然日拆成两段；周一凌晨对应上周日夜间，周日夜间只显示到本周结束。')
    return out
