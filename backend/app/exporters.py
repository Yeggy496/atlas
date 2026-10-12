"""Export a solved schedule to XLSX or PDF (MASTER_SPEC §25 P2).

Both exporters read the *same* solved result the UI already shows, so an export
can never disagree with what the user saw. Nothing here re-solves or re-orders
assignments.

XLSX uses openpyxl (already a declared dependency for import). PDF is written
with the standard library only: the spec only lists ``pypdf`` for parsing, and
adding a heavyweight layout engine for a one-page summary would be exactly the
"over-development" §26 warns against.
"""
from __future__ import annotations

import io
import json
from datetime import datetime

from .schemas import Problem

SLOT_MINUTES = 30
DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def _slot_label(slot: int) -> str:
    """Convert a 30-minute slot index (0 = Monday 00:00) into ``周X HH:MM``."""
    day, within = divmod(int(slot), 48)
    hour, half = divmod(within, 2)
    return f'{DAY_NAMES[day % 7]} {hour:02d}:{half * 30:02d}'


def _fmt_slot_time(slot: int) -> str:
    _, within = divmod(int(slot), 48)
    hour, half = divmod(within, 2)
    return f'{hour:02d}:{half * 30:02d}'


def _as_slot(value) -> int | None:
    """Coerce a solver slot index; anything unusable becomes None."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resource_label(raw, fallback) -> str:
    """Join a resource list defensively — the result is caller-supplied data."""
    if isinstance(raw, str):
        return raw or '-'
    if isinstance(raw, (list, tuple)):
        parts = [str(x) for x in raw if x not in (None, '')]
        return ', '.join(parts) or '-'
    return ', '.join(str(x) for x in fallback) or '-'


def _rows(problem: Problem, assignments) -> list[dict]:
    """Normalise assignments into report rows, keeping solver order intact.

    ``assignments`` arrives from the client, so every element is treated as
    untrusted: non-dict entries are skipped and unparseable slots fall back to
    ``None`` rather than raising (an export must not 500 on odd input).
    """
    by_id = {a.id: a for a in problem.activities}
    resources = {r.id: r.name for r in problem.resources}
    if not isinstance(assignments, (list, tuple)):
        return []
    out = []
    for a in assignments:
        if not isinstance(a, dict):
            continue
        act = by_id.get(a.get('activity_id'))
        if act is None:
            continue
        start = _as_slot(a.get('start'))
        day = _as_slot(a.get('day'))
        if day is None and start is not None:
            day = start // 48
        if day is not None and not 0 <= day <= 6:
            day = None
        used = list(dict.fromkeys(act.resources + list(act.demands)))
        room_id = a.get('room_id')
        if room_id and room_id not in used:
            used.append(room_id)
        resource_names = [resources.get(rid, rid) +
                          (f' × {act.demands[rid]}' if act.demands.get(rid, 1) > 1 else '')
                          for rid in used]
        out.append({
            'name': act.name,
            'category': act.category,
            'priority': act.priority,
            'day': day,
            'start': start,
            'end': None if start is None else start + act.duration,
            'duration': act.duration,
            'resources': ', '.join(resource_names) or '-',
            'optional': act.optional,
        })
    out.sort(key=lambda r: (r['start'] if r['start'] is not None else 10 ** 6))
    return out


# --------------------------------------------------------------------------- XLSX


def build_xlsx(problem: Problem, result: dict) -> bytes:
    """Workbook: 调度明细 / 每日负载 / 求解概况."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    assignments = result.get('assignments') or []
    rows = _rows(problem, assignments)

    wb = Workbook()
    head_font = Font(bold=True, color='FFFFFF')
    head_fill = PatternFill('solid', fgColor='3158D5')
    center = Alignment(horizontal='center')

    def style_header(ws, count):
        for cell in ws[1][:count]:
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = center

    # Sheet 1 — schedule detail
    ws = wb.active
    ws.title = '调度明细'
    ws.append(['任务', '类别', '优先级', '星期', '开始', '结束', '时长(小时)', '资源', '可选'])
    for r in rows:
        ws.append([
            r['name'],
            r['category'],
            r['priority'],
            DAY_NAMES[r['day']] if r['day'] is not None else '-',
            _fmt_slot_time(r['start']) if r['start'] is not None else '未安排',
            _fmt_slot_time(r['end']) if r['end'] is not None else '-',
            round(r['duration'] / 2, 1),
            r['resources'],
            '是' if r['optional'] else '否',
        ])
    style_header(ws, 9)
    for column, width in zip('ABCDEFGHI', (24, 12, 8, 8, 9, 9, 11, 22, 6)):
        ws.column_dimensions[column].width = width
    ws.freeze_panes = 'A2'

    # Sheet 2 — per-day load (excludes sleep, mirroring the UI note)
    ws2 = wb.create_sheet('每日负载')
    ws2.append(['星期', '任务数(不含睡眠)', '占用时长(小时，不含睡眠)'])
    totals = [0.0] * 7
    counts = [0] * 7
    for r in rows:
        if r['day'] is None or r['category'] == 'sleep':
            continue
        totals[r['day']] += r['duration'] / 2
        counts[r['day']] += 1
    for i in range(7):
        ws2.append([DAY_NAMES[i], counts[i], round(totals[i], 1)])
    style_header(ws2, 3)
    for column, width in zip('ABC', (10, 14, 16)):
        ws2.column_dimensions[column].width = width

    # Sheet 3 — solver summary
    ws3 = wb.create_sheet('求解概况')
    ws3.append(['指标', '数值'])
    objective = result.get('objective') or {}
    metrics = result.get('metrics') or {}
    ws3.append(['场景', problem.name])
    ws3.append(['求解状态', result.get('status', '-')])
    ws3.append(['目标值', objective.get('value', '-')])
    ws3.append(['最优界', objective.get('best_bound', '-')])
    ws3.append(['任务总数', len(problem.activities)])
    ws3.append(['已安排', len(rows)])
    ws3.append(['资源总数', len(problem.resources)])
    ws3.append(['约束总数', len(problem.constraints)])
    for key, value in metrics.items():
        ws3.append([key, _cell_value(value)])
    ws3.append(['导出于', datetime.now().strftime('%Y-%m-%d %H:%M')])
    style_header(ws3, 2)
    ws3.column_dimensions['A'].width = 18
    ws3.column_dimensions['B'].width = 30

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _cell_value(value):
    """OpenPyXL only accepts scalars; summarise anything structured."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        if not value:
            return ''
        if all(isinstance(v, (int, float)) for v in value):
            return ', '.join(str(v) for v in value)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


# ---------------------------------------------------------------------------- PDF

# Deliberate constraint: the PDF is generated with the standard library and the
# built-in Helvetica font only. CJK glyphs cannot be drawn without embedding a
# ~10-20 MB font (or adding reportlab + pillow as new dependencies), and MASTER_SPEC
# §26 forbids that kind of over-development for a one-page export. So the PDF is an
# English/ASCII summary and the XLSX export carries the full Chinese schedule.
# The UI states this next to the two export buttons.
EN_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _pdf_escape(text: str) -> str:
    return text.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')


def _ascii(text: str) -> str:
    """Replace characters the built-in PDF fonts cannot draw with '?'."""
    return ''.join(ch if 32 <= ord(ch) < 127 else '?' for ch in text)


def build_pdf(problem: Problem, result: dict) -> bytes:
    rows = _rows(problem, result.get('assignments') or [])
    objective = result.get('objective') or {}
    penalties = (objective.get('penalties') or {})

    lines: list[tuple[int, str]] = []
    lines.append((16, 'ATLAS-Sigma Weekly Schedule'))
    lines.append((9, f'Problem  : {_ascii(problem.name)}'))
    lines.append((9, f'Status   : {result.get("status", "-")}   '
                    f'Objective: {objective.get("value", "-")}'))
    lines.append((9, f'Scheduled: {len(rows)} / {len(problem.activities)} activities   '
                    f'Resources: {len(problem.resources)}   Constraints: {len(problem.constraints)}'))
    lines.append((9, '-' * 96))
    lines.append((9, 'No   Task                          Day   Start  End    Hrs   Resources'))
    lines.append((9, '-' * 96))
    for i, r in enumerate(rows, start=1):
        name = _ascii(r['name'])[:28].ljust(28)
        day_en = EN_DAYS[r['day']] if r['day'] is not None else '--'
        start = _fmt_slot_time(r['start']) if r['start'] is not None else '--:--'
        end = _fmt_slot_time(r['end']) if r['end'] is not None else '--:--'
        res = _ascii(r['resources'])[:20]
        lines.append((9, f'{i:<4} {name} {day_en:<5} {start}  {end}  '
                         f'{r["duration"] / 2:>4.1f}  {res}'))
    lines.append((9, '-' * 96))
    if penalties:
        summary = '   '.join(f'{_ascii(k)}={v}' for k, v in penalties.items())
        lines.append((8, f'Penalties: {summary[:96]}'))
    lines.append((8, f'Generated by ATLAS-Sigma . {datetime.now().strftime("%Y-%m-%d %H:%M")}'))
    lines.append((8, 'Note: PDF uses the built-in font and is ASCII-only. '
                     'Use the XLSX export for the full Chinese schedule.'))

    return _pdf_from_lines(lines)


def _pdf_from_lines(lines: list[tuple[int, str]]) -> bytes:
    """Lay text lines out on A4 pages and emit a valid PDF byte string."""
    page_w, page_h = 595, 842          # A4 in points
    margin_x, top, bottom = 40, 800, 50
    content_pages: list[bytes] = []
    buffer: list[str] = []
    y = top

    def flush_page():
        nonlocal buffer, y
        if buffer:
            content_pages.append('\n'.join(buffer).encode('latin-1', 'replace'))
        buffer = []
        y = top

    for size, text in lines:
        if y < bottom:
            flush_page()
        buffer.append(f'BT /F1 {size} Tf {margin_x} {y} Td ({_pdf_escape(text)}) Tj ET')
        y -= size + 4
    flush_page()
    if not content_pages:
        content_pages.append(b'')

    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font_id = add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    page_ids: list[int] = []
    content_ids: list[int] = []
    for content in content_pages:
        cid = add(b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n'
                  + content + b'\nendstream')
        content_ids.append(cid)
        page_ids.append(0)  # placeholder, patched after the parent is known

    pages_id_placeholder = len(objects) + 1 + len(content_pages)
    for i, cid in enumerate(content_ids):
        page_ids[i] = add(
            f'<< /Type /Page /Parent {pages_id_placeholder} 0 R /MediaBox [0 0 {page_w} {page_h}] '
            f'/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {cid} 0 R >>'.encode()
        )
    kids = ' '.join(f'{pid} 0 R' for pid in page_ids)
    pages_id = add(f'<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>'.encode())
    assert pages_id == pages_id_placeholder, 'page tree id drifted'
    catalog_id = add(f'<< /Type /Catalog /Pages {pages_id} 0 R >>'.encode())

    out = io.BytesIO()
    out.write(b'%PDF-1.4\n')
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f'{i} 0 obj\n'.encode())
        out.write(obj)
        out.write(b'\nendobj\n')
    xref_at = out.tell()
    out.write(f'xref\n0 {len(objects) + 1}\n'.encode())
    out.write(b'0000000000 65535 f \n')
    for off in offsets[1:]:
        out.write(f'{off:010d} 00000 n \n'.encode())
    out.write(f'trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n'
              f'startxref\n{xref_at}\n%%EOF\n'.encode())
    return out.getvalue()
