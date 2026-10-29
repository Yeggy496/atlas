"""Correct a narrow, explicit two-window extraction before user review.

The solver intersects time_window constraints. When the user explicitly lists
two alternative operating periods, the model sometimes emits two incompatible
windows for the same target. Replace only that identifiable new pair with its
bounding interval and an unavailable gap; retain all other constraints.
"""
from copy import deepcopy
import re


_PAIR = re.compile(
    r'(\d{1,2}):(00|30)\s*(?:到|至|[-–—])\s*(\d{1,2}):(00|30)\s*'
    r'[、，,和与或及]\s*(\d{1,2}):(00|30)\s*(?:到|至|[-–—])\s*(\d{1,2}):(00|30)'
)


def _slot(hour, minute):
    return int(hour) * 2 + int(minute) // 30


def normalize_explicit_working_windows(data, expected, text):
    if not isinstance(data, dict) or not isinstance(data.get('problem'), dict):
        return data
    constraints = data['problem'].get('constraints')
    warnings = data.get('warnings', [])
    if not isinstance(constraints, list) or not isinstance(warnings, list):
        return data
    intervals = set()
    for match in _PAIR.finditer(text):
        surrounding = text[max(0, match.start() - 40):min(len(text), match.end() + 18)]
        if not re.search(r'可安排|可以安排|安排在|可用|工作|可以上课|上课的时间', surrounding):
            continue
        g = match.groups()
        a, b, c, d = (_slot(g[i], g[i + 1]) for i in range(0, 8, 2))
        if 0 <= a < b < c < d <= 48:
            intervals.add((a, b, c, d))
    if not intervals:
        return data
    out = deepcopy(data)
    result = out['problem']['constraints']
    old_ids = {c.id for c in expected.constraints} if expected is not None else set()
    old_activity_ids = {a.id for a in expected.activities} if expected is not None else set()
    used_ids = {c['id'] for c in result if isinstance(c, dict) and isinstance(c.get('id'), str)}
    for a, b, c, d in sorted(intervals):
        first = [x for x in result if isinstance(x, dict) and x.get('type') == 'time_window'
                 and x.get('level', 'hard') == 'hard' and x.get('start', 0) == a and x.get('end', 48) == b
                 and isinstance(x.get('id'), str) and x['id'] not in old_ids]
        second = [x for x in result if isinstance(x, dict) and x.get('type') == 'time_window'
                  and x.get('level', 'hard') == 'hard' and x.get('start', 0) == c and x.get('end', 48) == d
                  and isinstance(x.get('id'), str) and x['id'] not in old_ids]
        for left in first:
            matches = [right for right in second if right in result and
                       right.get('target', '*') == left.get('target', '*') and right.get('day') == left.get('day')]
            if len(matches) != 1 or left not in result:
                continue
            right = matches[0]
            # Preserve the first window's identity, and re-express the second
            # using an exact exclusion of the gap. Do not change a constraint
            # referenced by another model constraint.
            if any(isinstance(x, dict) and isinstance(x.get('other'), str) and
                   x['other'] in {left['id'], right['id']} for x in result):
                continue
            left['end'] = d
            left['label'] = '可用时间范围（已排除中间空档）'
            result.remove(right)
            if not any(isinstance(x, dict) and x.get('type') == 'unavailable' and
                       x.get('target', '*') == left.get('target', '*') and x.get('day') == left.get('day') and
                       x.get('start', 0) == b and x.get('end', 48) == c and x.get('level', 'hard') == 'hard'
                       for x in result):
                new_id = f'window_gap_{left.get("id", "rule")}'
                while new_id in used_ids:
                    new_id += '_x'
                used_ids.add(new_id)
                result.append({'id': new_id, 'label': '两个可用时段之间不可用', 'type': 'unavailable',
                               'target': left.get('target', '*'), 'day': left.get('day'),
                               'start': b, 'end': c, 'level': 'hard', 'source': 'model_normalizer'})
            out.setdefault('warnings', []).append('已将原文中两个可用时段按“任一时段可安排”处理，中间时段不可用；请检查。')
    fixed_ids = {x['target'] for x in result if isinstance(x, dict) and x.get('type') == 'fixed_time'
                 and isinstance(x.get('target'), str)}
    narrow = []
    activities = out['problem'].get('activities', [])
    for activity in activities if isinstance(activities, list) else []:
        if not isinstance(activity, dict) or not isinstance(activity.get('id'), str) or activity['id'] in old_activity_ids | fixed_ids:
            continue
        start, end = activity.get('window_start', 16), activity.get('window_end', 44)
        if any((start, end) in ((a, b), (c, d)) for a, b, c, d in intervals):
            narrow.append(str(activity.get('name', '未命名活动')))
    if narrow:
        names = '、'.join(narrow[:5]) + ('等' if len(narrow) > 5 else '')
        out.setdefault('warnings', []).append(f'以下活动仅允许在原文两个时段中的一段安排：{names}。如果两段都可用，请检查活动时间范围。')
    return out
