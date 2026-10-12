"""Schedule comparison — the data behind MASTER_SPEC §16 / §37.

"Minimal-Perturbation Rescheduling" is only credible if the change is measurable.
This module compares two schedules of the *same* problem and reports exactly which
activities moved, which kept their slot, and the change count the ``stability``
penalty is built from. It is pure data: no model is called and nothing is guessed.
"""
from ..schemas import Assignment, Problem

DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def _clock(slot):
    return f'{slot // 2:02d}:{"30" if slot % 2 else "00"}'


def _normalize(items):
    """Accept either Assignment models or plain dicts, keyed by activity id."""
    out = {}
    for item in items or []:
        if isinstance(item, Assignment):
            out[item.activity_id] = item
        elif isinstance(item, dict):
            out[item['activity_id']] = Assignment(**item)
        else:
            raise TypeError('assignment must be an Assignment or dict')
    return out


def compare_plans(problem: Problem, previous, current):
    """Return a per-activity diff between an old and a new schedule."""
    activities = {a.id: a for a in problem.activities}
    old = _normalize(previous)
    new = _normalize(current)

    moved, kept, added, removed = [], [], [], []
    for aid in sorted(set(old) | set(new)):
        activity = activities.get(aid)
        name = activity.name if activity else aid
        before, after = old.get(aid), new.get(aid)
        if before and after:
            if before.start == after.start and before.room_id == after.room_id:
                kept.append(_entry(aid, name, after))
            else:
                moved.append(_change(aid, name, before, after, activity))
        elif after and not before:
            added.append(_entry(aid, name, after))
        elif before and not after:
            removed.append(_entry(aid, name, before))

    total = len(kept) + len(moved) + len(added) + len(removed)
    return {
        'changed': len(moved) + len(added) + len(removed),
        'total': total,
        'stability': round(len(kept) / total, 3) if total else 1.0,
        'moved': moved,
        'kept': kept,
        'added': added,
        'removed': removed,
    }


def _entry(aid, name, assignment):
    day, local = divmod(assignment.start, 48)
    return {
        'activity_id': aid,
        'name': name,
        'day': day,
        'day_name': DAY_NAMES[day],
        'start': assignment.start,
        'start_clock': _clock(local),
        'end_clock': _clock(local + (assignment.end - assignment.start)),
        'room_id': assignment.room_id,
    }


def _change(aid, name, before, after, activity):
    item = _entry(aid, name, after)
    old_day, old_local = divmod(before.start, 48)
    item.update({
        'from': {'day': old_day, 'day_name': DAY_NAMES[old_day], 'start_clock': _clock(old_local), 'room_id': before.room_id},
        'delta_slots': after.start - before.start,
        'same_day': old_day == item['day'],
        'room_changed': before.room_id != after.room_id,
    })
    return item
