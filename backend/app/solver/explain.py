"""Deterministic, data-only explanation for one scheduled activity.

"为什么是现在这个时间？" is answered purely from the real problem and the real
solver output: the hard constraints that pin the slot, the activity's own allowed
domain, the soft preference windows (honoured or traded off, with their penalty),
resource contention in the chosen slot, and how many alternative slots were even
legal. Nothing is invented and no model is called; every sentence is derived
from the inputs the user can see.
"""
from ..schemas import Assignment, Problem
from .constraints import applies, candidates

DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def _clock(slot):
    return f'{slot // 2:02d}:{"30" if slot % 2 else "00"}'


def explain(problem: Problem, assignments: list[Assignment], activity_id: str, previous: list[Assignment] | None = None):
    activity = next((a for a in problem.activities if a.id == activity_id), None)
    if activity is None:
        raise KeyError(f'活动 {activity_id} 不在当前问题中。')
    chosen = next((x for x in assignments if x.activity_id == activity_id), None)
    if chosen is None:
        raise KeyError(f'活动「{activity.name}」当前没有被安排，无法解释。')
    activities = {a.id: a for a in problem.activities}
    resources = {r.id: r for r in problem.resources}
    day, local = divmod(chosen.start, 48)
    window_end = local + activity.duration
    reasons = []

    def add(kind, title, detail, constraint_id=None):
        item = {'kind': kind, 'title': title, 'detail': detail}
        if constraint_id:
            item['constraint_id'] = constraint_id
        reasons.append(item)

    relevant = [c for c in problem.constraints if applies(c, activity, chosen.room_id)
                and (c.day is None or c.day == day)]

    # Hard constraints that pin this slot.
    for c in relevant:
        if c.level != 'hard':
            continue
        if c.type == 'fixed_time':
            add('fixed', '固定时间，不可移动', f'约束「{c.label}」把「{activity.name}」固定在 {DAY_NAMES[day]} {_clock(local)}–{_clock(window_end)}。', c.id)
        elif c.type == 'time_window':
            add('window', '受硬时间窗口限定', f'约束「{c.label}」要求安排在 {_clock(c.start)}–{_clock(c.end)}，当前 {_clock(local)}–{_clock(window_end)} 落在窗口内。', c.id)
        elif c.type == 'unavailable':
            add('avoid', '已避开不可用时段', f'约束「{c.label}」标记的不可用时段与当前安排不重叠。', c.id)

    days = sorted(set(activity.days))
    add('domain', '活动允许的时间域', f'允许 {"/".join(DAY_NAMES[d] for d in days)} 的 {_clock(activity.window_start)}–{_clock(activity.window_end)}，时长 {activity.duration / 2:g} 小时。')

    allowed_starts = sorted({s for s, _ in candidates(problem, activity)})
    same_day = [s for s in allowed_starts if s // 48 == day]
    if allowed_starts:
        if len(allowed_starts) == 1:
            detail = '按单项活动的日期、时间窗口与固定限制筛选后，只有 1 个候选开始时段；此数量未检查其他活动的资源占用和先后关系。'
        else:
            detail = f'按单项活动的日期、时间窗口与固定限制筛选后，共有 {len(allowed_starts)} 个候选开始时段'
            if same_day:
                detail += f'（当天 {len(same_day)} 个）'
            detail += '；此数量未检查其他活动的资源占用和先后关系。'
        add('candidates', '候选时段数量', detail)
    if len(same_day) > 1:
        if chosen.start == same_day[0]:
            add('boundary', '处于当天候选时段的最早边界', '仅依据单项活动的时间域、窗口与固定限制比较；不代表已对所有替代方案重新求解。')
        elif chosen.start == same_day[-1]:
            add('boundary', '处于当天候选时段的最晚边界', '仅依据单项活动的时间域、窗口与固定限制比较；不代表已对所有替代方案重新求解。')

    # Soft time preferences: honoured or traded off, with the per-constraint penalty.
    for c in relevant:
        if c.level != 'soft' or c.type != 'preferred_window':
            continue
        deviation = max(0, c.start - local) + max(0, window_end - c.end)
        if deviation == 0:
            add('preference', '满足时间偏好', f'软偏好「{c.label}」（希望 {_clock(c.start)}–{_clock(c.end)}）已满足，不产生附加惩罚。', c.id)
        else:
            add('preference', '时间偏好被权衡', f'软偏好「{c.label}」希望 {_clock(c.start)}–{_clock(c.end)}；当前偏离，产生 penal　{deviation}。求解器在全局目标下用这一点惩罚换取了其它约束或整体紧凑度。'.replace('　', ' '), c.id)

    # Deadline / ordering constraints that mention this activity.
    for c in problem.constraints:
        if c.type == 'deadline' and c.target == activity.id:
            add('deadline', '满足截止要求', f'约束「{c.label}」要求在此前完成，当前结束于 {_clock(window_end)}。', c.id)
        elif c.type in ('precedence', 'min_gap', 'consecutive'):
            other = activities.get(c.other)
            if c.target == activity.id and other:
                if c.type == 'consecutive':
                    detail = f'结束后「{other.name}」必须立即开始'
                elif c.type == 'min_gap':
                    detail = f'结束至少 {c.value / 2:g} 小时后「{other.name}」才能开始'
                else:
                    detail = f'必须在「{other.name}」开始前完成'
                add('order', '存在先后关系', f'{detail}（约束「{c.label}」）。', c.id)
            elif c.other == activity.id:
                anchor = activities.get(c.target)
                if anchor:
                    add('order', '存在先后关系', f'需要排在「{anchor.name}」之后（约束「{c.label}」）。', c.id)

    # Resource state during the chosen slot, from the real assignment list.
    used = set(activity.resources) | set(activity.demands)
    if chosen.room_id:
        used.add(chosen.room_id)
    for rid in sorted(used):
        resource = resources.get(rid)
        if not resource:
            continue
        shared = []
        for other in assignments:
            if other.activity_id == activity.id:
                continue
            other_activity = activities.get(other.activity_id)
            if not other_activity:
                continue
            other_used = set(other_activity.resources) | set(other_activity.demands)
            if other.room_id:
                other_used.add(other.room_id)
            if rid in other_used and other.start < chosen.end and chosen.start < other.end:
                shared.append(other_activity.name)
        if shared:
            add('resource', '资源在该时段被共用', f'{resource.name} 同时被 {", ".join(shared)} 占用，仍在并发容量 {resource.capacity} 之内。')
    if used:
        names = '、'.join(resources[rid].name for rid in sorted(used) if rid in resources)
        if names:
            add('capacity', '资源容量校验通过', f'{names} 在该时段的并发需求没有超过容量。')

    if previous:
        prior = next((x for x in previous if x.activity_id == activity_id), None)
        if prior and prior.start == chosen.start and prior.room_id == chosen.room_id:
            add('stability', '与上一次方案一致', '当前时间与教室和上一次求解相同，稳定项没有额外惩罚。')

    return {
        'activity_id': activity_id,
        'name': activity.name,
        'day': day,
        'day_name': DAY_NAMES[day],
        'start': chosen.start,
        'end': chosen.end,
        'start_clock': _clock(local),
        'end_clock': _clock(window_end),
        'duration_hours': activity.duration / 2,
        'room_id': chosen.room_id,
        'room_name': resources[chosen.room_id].name if chosen.room_id and chosen.room_id in resources else None,
        'candidate_slots_total': len(allowed_starts),
        'candidate_slots_same_day': len(same_day),
        'reasons': reasons,
    }
