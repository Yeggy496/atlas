"""Independent post-solve checks, including resource occupancy and user rules."""
from collections import defaultdict
from ..schemas import Problem, Assignment


def verify(problem: Problem, assignments: list[Assignment]):
    errors, occupancy = [], defaultdict(int)
    activities = {a.id: a for a in problem.activities}
    resources = {r.id: r for r in problem.resources}
    chosen = {x.activity_id: x for x in assignments}
    if len(chosen) != len(assignments):
        errors.append('重复安排同一活动')
    for a in problem.activities:
        if a.id not in chosen and not a.optional:
            errors.append(f'{a.name} 未安排')
    for x in assignments:
        if x.activity_id not in activities:
            errors.append('结果包含未知任务')
            continue
        a = activities[x.activity_id]
        day, local = divmod(x.start, 48)
        if x.end-x.start != a.duration or day not in a.days or not (a.window_start <= local and local+a.duration <= a.window_end):
            errors.append(f'{a.name} 的持续时间或时间域不合法')
        if a.room_options:
            room = resources.get(x.room_id)
            if not room or room.id not in a.room_options or room.seats < a.required_seats or (a.room_type and room.room_type != a.room_type):
                errors.append(f'{a.name} 的教室不符合要求')
        used = set(a.resources) | set(a.demands)
        if x.room_id:
            used.add(x.room_id)
        for rid in used:
            for slot in range(x.start, x.end):
                occupancy[rid, slot] += a.demands.get(rid, 1)
        for c in problem.constraints:
            if c.level == 'soft' or c.target not in {'*', a.id, a.category, *used}:
                continue
            bad = False
            if c.type == 'fixed_time':
                bad = x.start != c.day*48+c.start
            elif c.type == 'deadline':
                bad = x.end > c.end
            elif c.type == 'time_window':
                bad = (c.day is not None and day != c.day) or local < c.start or local+a.duration > c.end
            elif c.type == 'unavailable' and (c.day is None or c.day == day):
                bad = local < c.end and local+a.duration > c.start
            elif c.type in ('precedence', 'min_gap') and c.other in chosen:
                bad = x.end + (c.value if c.type == 'min_gap' else 0) > chosen[c.other].start
            if bad:
                errors.append(c.label)
    for (rid, _), demand in occupancy.items():
        if demand > resources[rid].capacity:
            errors.append(f'{resources[rid].name} 容量超限')
    for c in problem.constraints:
        if c.type == 'daily_limit':
            for day in range(7):
                count = sum(1 for x in assignments if x.start//48 == day and c.target in {'*', activities[x.activity_id].id, activities[x.activity_id].category, *activities[x.activity_id].resources, *activities[x.activity_id].demands, x.room_id})
                if (c.day is None or c.day == day) and count > c.value:
                    errors.append(c.label)
    return sorted(set(errors))
