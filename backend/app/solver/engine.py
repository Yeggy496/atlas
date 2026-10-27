from collections import defaultdict
import os
from ..config import env
from ortools.sat.python import cp_model
from ..schemas import Problem, Assignment
from .constraints import candidates, applies, preference_cost
from .validator import verify

# 三档偏好的目标权重。
#   goal      软目标（时间窗偏好、可选活动的取舍）
#   compact   各资源每日占用区间内的空档
#   balance   每日负载均衡
#   robust    截止任务缓冲
#   lead      截止任务的开始时刻（仅“稳健”档启用，越小越早完成）
#   stability 与上一版计划的差异（仅“稳健”档与冲突修复流程启用）
#   regular   日常作息规律性（同名日常活动尽量每天同一时间）
WEIGHTS = {
    'efficient': {'goal':100, 'compact':4, 'balance':1, 'robust':1, 'lead':0, 'stability':0, 'regular':1},
    'balanced': {'goal':100, 'compact':1, 'balance':2, 'robust':2, 'lead':0, 'stability':0, 'regular':3},
    'robust': {'goal':100, 'compact':1, 'balance':1, 'robust':8, 'lead':2, 'stability':1000, 'regular':3},
}
# 修复流程必须最小化改动，因此无论当前是哪个档位都强制启用稳定性项。
REPAIR_STABILITY = 1000
# “稳健”档要求截止任务至少预留的半小时数（默认 6 小时）。
ROBUST_BUFFER_SLOTS = int(env('OPTIDAY_ROBUST_BUFFER_SLOTS', '12'))


def solve(problem: Problem, mode='balanced', previous=None, seconds=None, optimize=True, keep_previous=False, overrides=None):
    """Solve the problem with CP-SAT.

    ``overrides`` lets the caller adjust individual objective weights on top of the
    chosen preset (MASTER_SPEC §15: five-dimension sliders + custom mode). Only the
    keys present in ``overrides`` are changed; every unchanged key keeps the preset
    value, so a preset with no overrides behaves exactly as before. Unknown keys and
    negative values are ignored rather than trusted.
    """
    if seconds is None:
        seconds = float(env('OPTIDAY_SOLVE_SECONDS', '4'))
    weights = dict(WEIGHTS[mode])
    if overrides:
        for key, value in overrides.items():
            if key in weights and isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                weights[key] = int(value)
        # A profile where every weight is zero carries no signal, so the solver would
        # return an arbitrary first-feasible schedule. Fall back to the preset's goal
        # anchor in that single degenerate case; otherwise honour the user's numbers.
        if not any(weights.values()):
            weights['goal'] = WEIGHTS[mode]['goal']
    if keep_previous and previous:
        weights['stability'] = max(weights['stability'], REPAIR_STABILITY)
    model = cp_model.CpModel()
    occupancy, choices, presences, starts = defaultdict(list), {}, {}, {}
    day_loads, day_choices = defaultdict(list), defaultdict(list)
    terms = {k: [] for k in weights}
    old = {x.activity_id: x for x in (previous or [])}
    for a in problem.activities:
        options = []
        for i, (start, room) in enumerate(candidates(problem, a)):
            var = model.new_bool_var(f'{a.id}_{i}')
            if a.id in old and weights['stability'] > 0:
                model.add_hint(var,int(start==old[a.id].start and room==old[a.id].room_id))
            options.append((start, room, var))
            demand_ids = set(a.resources) | set(a.demands)
            if room:
                demand_ids.add(room)
            for rid in demand_ids:
                for slot in range(start, start+a.duration):
                    occupancy[rid, slot].append(var * a.demands.get(rid, 1))
            pref = preference_cost(problem, a, start, room)
            if pref:
                terms['goal'].append(pref * var)
            if a.id in old:
                if start != old[a.id].start or room != old[a.id].room_id:
                    terms['stability'].append(var)
            for c in problem.constraints:
                if c.type == 'deadline' and applies(c, a, room):
                    terms['robust'].append(max(0, ROBUST_BUFFER_SLOTS-(c.end-start-a.duration))*var)
                    terms['lead'].append(start*var)
            if a.category != 'sleep':
                day_loads[start//48].append(a.duration*var)
                for rid in a.resources:
                    day_choices[rid, start//48].append((start%48, a.duration, var))
        choices[a.id] = options
        present = model.new_bool_var(f'present_{a.id}')
        model.add(sum(v for _, _, v in options) == present)
        if not a.optional:
            model.add(present == 1)
        else:
            terms['goal'].append(a.priority*20*(1-present))
            if a.id in old:
                terms['stability'].append(1-present)
        presences[a.id] = present
        starts[a.id] = sum(s*v for s, _, v in options)
    resource_map = {r.id: r for r in problem.resources}
    for (rid, _), variables in occupancy.items():
        model.add(sum(variables) <= resource_map[rid].capacity)
    activity_map = {a.id: a for a in problem.activities}
    for c in problem.constraints:
        if c.type in ('precedence', 'min_gap'):
            a = activity_map[c.target]
            model.add(starts[a.id] + a.duration + (c.value if c.type == 'min_gap' else 0) <= starts[c.other]).only_enforce_if([presences[a.id], presences[c.other]])
        elif c.type == 'consecutive':
            # 连排：目标活动结束后，另一活动必须紧接其后开始（连续排布）。
            a = activity_map[c.target]; b = activity_map[c.other]
            model.add(starts[a.id] + a.duration == starts[b.id]).only_enforce_if([presences[a.id], presences[b.id]])
        elif c.type == 'daily_limit':
            for day in range(7):
                if c.day is not None and day != c.day:
                    continue
                model.add(sum(v for a in problem.activities for s, room, v in choices[a.id] if s//48 == day and applies(c,a,room)) <= c.value)
    # 工序链：同一工单(group)内按 op_index 顺序执行，前一道结束下一道才能开始。
    groups = defaultdict(list)
    for a in problem.activities:
        if a.group:
            groups[a.group].append(a)
    for members in groups.values():
        members.sort(key=lambda a: a.op_index)
        for prev, nxt in zip(members, members[1:]):
            model.add(starts[prev.id] + prev.duration <= starts[nxt.id]).only_enforce_if([presences[prev.id], presences[nxt.id]])
    # Compactness is the idle space within each resource's occupied daily span.
    for (rid, day), entries in day_choices.items():
        day_starts, day_ends = [], []
        by_activity = defaultdict(list)
        for a in problem.activities:
            if rid in a.resources and a.category != 'sleep':
                for s, _, v in choices[a.id]:
                    if s//48 == day:
                        by_activity[a.id].append((s%48, a.duration, v))
        for aid, xs in by_activity.items():
            on_day = sum(v for _, _, v in xs)
            lo = model.new_int_var(0,48,f'lo_{rid}_{day}_{aid}')
            hi = model.new_int_var(0,48,f'hi_{rid}_{day}_{aid}')
            model.add(lo == sum(s*v for s,_,v in xs)+48*(1-on_day))
            model.add(hi == sum((s+d)*v for s,d,v in xs))
            day_starts.append(lo)
            day_ends.append(hi)
        first = model.new_int_var(0,48,f'first_{rid}_{day}')
        last = model.new_int_var(0,48,f'last_{rid}_{day}')
        model.add_min_equality(first,day_starts)
        model.add_max_equality(last,day_ends)
        gap = model.new_int_var(0,48,f'idle_{rid}_{day}')
        model.add_max_equality(gap,[0,last-first-sum(d*v for _,d,v in entries)])
        terms['compact'].append(gap)
    total_load = sum(a.duration for a in problem.activities if a.category != 'sleep' and not a.optional)
    for day in range(7):
        deviation = model.new_int_var(0,33600,f'balance_{day}')
        model.add_abs_equality(deviation,7*sum(day_loads[day])-total_load)
        terms['balance'].append(deviation)
    # 作息规律性：同名的日常活动（午餐/晚餐等）尽量每天落在同一时间，
    # 否则求解器会在窗口内随机漂移，出现每天 11:30/12:30/13:00 各不相同的课表。
    regular_groups = defaultdict(list)
    for a in problem.activities:
        if a.category == 'meal' and not a.optional:
            regular_groups[a.name].append(a)
    for name, acts in regular_groups.items():
        if len(acts) < 2:
            continue
        target = model.new_int_var(0, 47, f'regular_target_{name}')
        for a in acts:
            local = sum((start % 48) * v for start, _, v in choices[a.id])
            dev = model.new_int_var(0, 47, f'regular_dev_{a.id}')
            model.add_abs_equality(dev, local - target)
            terms['regular'].append(dev)
    # 目标权重：修复流程强制保留原安排，其余情况由档位决定。
    if optimize:
        model.minimize(sum(weights[k]*sum(v) for k,v in terms.items()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = int(env('OPTIDAY_SOLVER_WORKERS', '4'))
    solver.parameters.random_seed = 42
    status = solver.solve(model)
    name = solver.status_name(status)
    base = {'status':name,'assignments':[], 'metrics':{'solve_time':round(solver.wall_time,3),'activities':len(problem.activities),'resources':len(problem.resources),'constraints':len(problem.constraints),'variables':len(model.proto.variables),'model_constraints':len(model.proto.constraints)}, 'objective':None,'conflicts':[],'repairs':[]}
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        return base
    result = []
    for a in problem.activities:
        for s, room, var in choices[a.id]:
            if solver.value(var):
                result.append(Assignment(activity_id=a.id,start=s,end=s+a.duration,room_id=room))
    violations = verify(problem,result)
    if violations:
        raise RuntimeError('结果校验失败：'+'；'.join(violations))
    result.sort(key=lambda x:(x.start,x.activity_id))
    penalties = {k:int(solver.value(sum(v))) if v else 0 for k,v in terms.items()}
    pref_total, pref_satisfied = preference_summary(problem, result, activity_map)
    base['assignments'] = [x.model_dump() for x in result]
    base['metrics'].update({'hard_violations':0,'scheduled':len(result),'scheduled_hours':sum(x.end-x.start for x in result)/2,'optional_completed':sum(activity_map[x.activity_id].optional for x in result),'preference_total':pref_total,'preference_satisfied':pref_satisfied,'changed':sum(1 for x in result if x.activity_id in old and (x.start!=old[x.activity_id].start or x.room_id!=old[x.activity_id].room_id))+sum(1 for aid in old if aid in activity_map and aid not in {x.activity_id for x in result}),'daily_hours':[sum(x.end-x.start for x in result if x.start//48==day and activity_map[x.activity_id].category!='sleep')/2 for day in range(7)]})
    base['objective'] = {'penalties':penalties,'weights':weights,'value':round(solver.objective_value,2),'best_bound':round(solver.best_objective_bound,2),'stability_applicable':bool(old)}
    return base


def preference_summary(problem, result, activity_map):
    """Count soft time preferences and how many the schedule honours.

    Defensive by design: only ``preferred_window`` soft constraints carry a
    day-local ``start``/``end`` window, so any other (future) soft constraint
    type is skipped instead of raising on missing/None bounds. An unsatisfiable
    window (``start >= end``) is ignored rather than miscounted.
    """
    total = 0
    satisfied = 0
    for c in problem.constraints:
        if getattr(c, 'level', None) != 'soft' or getattr(c, 'type', None) != 'preferred_window':
            continue
        start, end = getattr(c, 'start', None), getattr(c, 'end', None)
        if start is None or end is None or start >= end:
            continue
        total += 1
        if all(start <= x.start % 48 and x.start % 48 + activity_map[x.activity_id].duration <= end
               for x in result
               if applies(c, activity_map[x.activity_id], x.room_id)
               and (c.day is None or c.day == x.start // 48)):
            satisfied += 1
    return total, satisfied
