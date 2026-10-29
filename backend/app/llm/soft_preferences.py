"""Translate only explicitly soft model output without strengthening it."""
from copy import deepcopy
import re


def normalize_soft_preferences(data):
    if not isinstance(data, dict) or not isinstance(data.get('problem'), dict):
        return data
    constraints = data['problem'].get('constraints')
    warnings = data.get('warnings', [])
    if not isinstance(constraints, list) or not isinstance(warnings, list):
        return data
    out = deepcopy(data)
    normalized = []
    extra = []
    for item in out['problem']['constraints']:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        kind, level = item.get('type'), item.get('level')
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
    out['warnings'] = warnings + extra
    return out
