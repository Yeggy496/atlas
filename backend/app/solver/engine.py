from collections import defaultdict
from ortools.sat.python import cp_model
from ..schemas import Problem, Assignment
from .constraints import candidates, applies, preference_cost
from .validator import verify

WEIGHTS = {
    'efficient': {'goal':100, 'compact':4, 'balance':0, 'robust':1, 'stability':5},
    'balanced': {'goal':100, 'compact':1, 'balance':2, 'robust':2, 'stability':20},
    'robust': {'goal':100, 'compact':1, 'balance':1, 'robust':8, 'stability':1000},
}


def solve(problem: Problem, mode='balanced', previous=None, seconds=4.0, optimize=True):
    model = cp_model.CpModel()
    occupancy, choices, presences, starts = defaultdict(list), {}, {}, {}
    day_loads, day_choices = defaultdict(list), defaultdict(list)
    terms = {k: [] for k in WEIGHTS['balanced']}
    old = {x.activity_id: x for x in (previous or [])}
    for a in problem.activities:
        options = []
        for i, (start, room) in enumerate(candidates(problem, a)):
            var = model.new_bool_var(f'{a.id}_{i}')
            if a.id in old:
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
                    terms['robust'].append(max(0, 4-(c.end-start-a.duration))*var)
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
        elif c.type == 'daily_limit':
            for day in range(7):
                if c.day is not None and day != c.day:
                    continue
                model.add(sum(v for a in problem.activities for s, room, v in choices[a.id] if s//48 == day and applies(c,a,room)) <= c.value)
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
    if optimize:
        model.minimize(sum(WEIGHTS[mode][k]*sum(v) for k,v in terms.items()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 4
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
    pref_total = sum(1 for c in problem.constraints if c.level == 'soft')
    pref_satisfied = sum(1 for c in problem.constraints if c.level == 'soft' and all(c.start <= x.start%48 and x.start%48+activity_map[x.activity_id].duration <= c.end for x in result if applies(c,activity_map[x.activity_id],x.room_id) and (c.day is None or c.day==x.start//48)))
    base['assignments'] = [x.model_dump() for x in result]
    base['metrics'].update({'hard_violations':0,'scheduled':len(result),'scheduled_hours':sum(x.end-x.start for x in result)/2,'optional_completed':sum(activity_map[x.activity_id].optional for x in result),'preference_total':pref_total,'preference_satisfied':pref_satisfied,'changed':sum(1 for x in result if x.activity_id in old and (x.start!=old[x.activity_id].start or x.room_id!=old[x.activity_id].room_id))+sum(1 for aid in old if aid in activity_map and aid not in {x.activity_id for x in result}),'daily_hours':[sum(x.end-x.start for x in result if x.start//48==day and activity_map[x.activity_id].category!='sleep')/2 for day in range(7)]})
    base['objective'] = {'penalties':penalties,'weights':WEIGHTS[mode],'value':round(solver.objective_value,2),'best_bound':round(solver.best_objective_bound,2),'stability_applicable':bool(old)}
    return base
