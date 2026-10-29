"""Translate only explicitly soft model output without strengthening it."""
from copy import deepcopy
import re

_SOFT_JOB_DEADLINE = re.compile(
    r'(工单\s*[A-Za-z0-9]+)\s*(?:希望|尽量|最好)\s*(?:在|于)?\s*'
    r'周([一二三四五六日天])\s*(\d{1,2}):(00|30)\s*(?:之前|以前|前)\s*(?:完成|完工)'
)


def normalize_soft_preferences(data, expected=None, text=''):
    if not isinstance(data, dict) or not isinstance(data.get('problem'), dict):
        return data
    constraints = data['problem'].get('constraints')
    warnings = data.get('warnings', [])
    if not isinstance(constraints, list) or not isinstance(warnings, list):
        return data
    out = deepcopy(data)
    normalized = []
    extra = []
    old_ids = {c.id for c in expected.constraints} if expected is not None else set()
    activities = out['problem'].get('activities', [])
    names = {a['id']: str(a.get('name', '')) for a in activities
             if isinstance(a, dict) and isinstance(a.get('id'), str)} if isinstance(activities, list) else {}
    soft_deadlines = []
    for match in _SOFT_JOB_DEADLINE.finditer(text):
        job, day, hour, minute = match.groups()
        if re.search(re.escape(job) + r'[^，。；;]{0,40}(?:必须|最晚|不得晚于|不能晚于)', text):
            continue
        slot = '一二三四五六日'.index(day.replace('天', '日')) * 48 + int(hour) * 2 + int(minute) // 30
        if int(hour) <= 23:
            soft_deadlines.append((re.sub(r'\s+', '', job).lower(), slot))
    for item in out['problem']['constraints']:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        kind, level = item.get('type'), item.get('level')
        if kind == 'deadline' and level in (None, 'hard') and isinstance(item.get('id'), str) and item['id'] not in old_ids:
            target = item.get('target')
            identity = re.sub(r'\s+', '', names.get(target, '') if isinstance(target, str) else '').lower()
            label_identity = re.sub(r'\s+', '', str(item.get('label', ''))).lower()
            if any((job in identity or job in label_identity) and item.get('end') == slot
                   for job, slot in soft_deadlines):
                extra.append(f'“{item.get("label", "工单截止") }”在原文中是希望而非硬截止；软截止暂不支持，未纳入求解，请检查。')
                continue
        if kind == 'preferred_window' and level is None:
            item['level'] = 'soft'
        elif kind == 'time_window' and level == 'soft':
            item['type'] = 'preferred_window'
            extra.append(f'“{item.get("label", "时间窗口")}”作为软时间偏好处理，请检查。')
        elif kind not in ('preferred_window', 'time_window') and level == 'soft':
            # There is no generic soft deadline/order/daily limit in this
            # model. Dropping with an explicit warning is safer than silently
            # making a preference hard or pretending it was optimized.
            extra.append(f'“{item.get("label", "未命名偏好")}”属于暂不支持的软偏好，未纳入本次求解，请检查并手动调整。')
            continue
        if item.get('type') == 'preferred_window' and item.get('level') == 'soft':
            label = str(item.get('label', ''))
            if re.search(r'尽量少|尽量不|最好不|避免|少安排|少排课|不要安排', label):
                extra.append(f'“{label}”是减少某时段安排的偏好，当前无法可靠表达，未纳入本次求解，请检查并手动调整。')
                continue
            start, end = item.get('start', 0), item.get('end', 48)
            if isinstance(start, int) and isinstance(end, int) and not 0 <= start < end <= 48:
                extra.append(f'“{item.get("label", "时间偏好")}”不能表示为单日时间偏好，未纳入本次求解，请检查并手动调整。')
                continue
        normalized.append(item)
    out['problem']['constraints'] = normalized
    out['warnings'] = warnings + (['系统已校正部分模型偏好处理；如模型说明与下列系统校正冲突，以系统校正为准。'] if extra else []) + extra
    return out
