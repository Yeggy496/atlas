"""Deterministic candidate compilation. Never executes model-generated code."""
from ..schemas import Activity, Constraint, Problem


def applies(c: Constraint, a: Activity, room=None):
    return c.target in ('*', a.id, a.category, *a.resources, *a.demands, room)


def allowed(c: Constraint, a: Activity, start: int, room=None):
    if c.level != 'hard' or not applies(c, a, room):
        return True
    day, local = divmod(start, 48)
    if c.type == 'fixed_time':
        return start == c.day * 48 + c.start
    if c.type == 'deadline':
        return start + a.duration <= c.end
    if c.day is not None and day != c.day:
        return c.type != 'time_window'
    if c.type == 'time_window':
        return local >= c.start and local + a.duration <= c.end
    if c.type == 'unavailable':
        return local + a.duration <= c.start or local >= c.end
    return True


def candidates(problem: Problem, activity: Activity):
    rooms = {r.id: r for r in problem.resources}
    choices = activity.room_options or [None]
    for room in choices:
        if room and (rooms[room].seats < activity.required_seats or (activity.room_type and rooms[room].room_type != activity.room_type)):
            continue
        for day in sorted(set(activity.days)):
            for local in range(activity.window_start, activity.window_end - activity.duration + 1):
                start = day * 48 + local
                if all(allowed(c, activity, start, room) for c in problem.constraints):
                    yield start, room


def preference_cost(problem, activity, start, room):
    local = start % 48
    return sum(max(0, c.start - local) + max(0, local + activity.duration - c.end)
               for c in problem.constraints if c.type == 'preferred_window' and applies(c, activity, room)
               and (c.day is None or start // 48 == c.day))
