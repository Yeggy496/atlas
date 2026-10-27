"""Export the displayed schedule to XLSX or a readable Chinese PDF.

Both exporters read the *same* solved result the UI already shows, so an export
can never disagree with what the user saw. Nothing here re-solves or re-orders
assignments.

XLSX uses openpyxl. PDF uses ReportLab's built-in Chinese CID font, avoiding
external font downloads and keeping the same schedule in both formats.
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


def _fmt_slot_time(slot: int, *, end: bool = False) -> str:
    _, within = divmod(int(slot), 48)
    # An activity ending at the boundary belongs to the preceding day. Showing
    # 00:00 beside its 23:00 start would look like a negative duration.
    if end and int(slot) > 0 and within == 0:
        return '24:00'
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
            _fmt_slot_time(r['end'], end=True) if r['end'] is not None else '-',
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

    # Excel must treat user-supplied names and descriptions as text, even when
    # they start with '='. Setting the cell type preserves the exact displayed
    # value without inserting a visible apostrophe or exporting a formula.
    for sheet in wb:
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'

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

def build_pdf(problem: Problem, result: dict) -> bytes:
    """A4 schedule with Chinese text, wrapping cells and repeated table headers."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font = 'STSong-Light'
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font))

    rows = _rows(problem, result.get('assignments') or [])
    objective = result.get('objective') or {}
    metrics = result.get('metrics') or {}
    blue = colors.HexColor('#3158D5')
    ink = colors.HexColor('#1E293B')
    muted = colors.HexColor('#64748B')
    border = colors.HexColor('#E2E8F0')

    text_style = ParagraphStyle('schedule-text', fontName=font, fontSize=9,
                                leading=13, textColor=ink, wordWrap='CJK')
    heading_style = ParagraphStyle('schedule-title', parent=text_style,
                                   fontSize=19, leading=26, textColor=blue)
    small_style = ParagraphStyle('schedule-note', parent=text_style,
                                 fontSize=8, leading=12, textColor=muted)
    header_style = ParagraphStyle('schedule-header', parent=text_style,
                                  textColor=colors.white, alignment=TA_CENTER)

    def para(value, style=text_style):
        # Paragraph interprets XML-like markup. User text must stay literal.
        text = ''.join(ch for ch in str(value) if ch >= ' ' or ch in '\n\t')
        return Paragraph(escape(text).replace('\n', '<br/>'), style)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=32, leftMargin=32,
                            topMargin=32, bottomMargin=38,
                            title=f'OptiDay - {problem.name}', author='OptiDay',
                            # Repeated downloads of the same data are byte stable.
                            invariant=1)
    story = [para('OptiDay 周计划', heading_style), Spacer(1, 6),
             para(problem.name),
             para(f'起始日期：{problem.week_start}　时间粒度：30 分钟', small_style),
             Spacer(1, 14)]
    status = result.get('status', '-')
    summary = (f'求解状态：{status}　已安排：{len(rows)} / {len(problem.activities)} 项　'
               f'资源：{len(problem.resources)}　显式约束：{len(problem.constraints)}')
    story += [para(summary), Spacer(1, 5)]
    details = []
    if metrics.get('hard_violations') is not None:
        details.append(f'硬约束违反：{metrics["hard_violations"]}')
    if metrics.get('solve_time') is not None:
        details.append(f'求解耗时：{metrics["solve_time"]} 秒')
    if objective.get('value') is not None:
        details.append(f'目标值：{objective["value"]}')
    if details:
        story += [para('　'.join(details), small_style), Spacer(1, 10)]

    columns = ['序号', '任务', '星期', '开始', '结束', '小时', '资源']
    table_rows = [[para(label, header_style) for label in columns]]
    for i, row in enumerate(rows, start=1):
        table_rows.append([
            para(i), para(row['name']),
            para(DAY_NAMES[row['day']] if row['day'] is not None else '-'),
            para(_fmt_slot_time(row['start']) if row['start'] is not None else '未安排'),
            para(_fmt_slot_time(row['end'], end=True) if row['end'] is not None else '-'),
            para(f'{row["duration"] / 2:g}'), para(row['resources']),
        ])
    if rows:
        table = Table(table_rows, colWidths=[30, 155, 42, 44, 44, 35, 181],
                      repeatRows=1, splitInRow=1, hAlign='LEFT')
        # Column widths sum to the usable A4 width (531 points).
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), blue),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, 0), 0.6, blue),
            ('LINEBELOW', (0, 1), (-1, -1), 0.3, border),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(table)
    else:
        story.append(para('此方案暂未安排任务。', small_style))
    story += [Spacer(1, 12), para('导出内容与当前显示的求解结果一致；每日负载与完整求解指标可在 Excel 中查看。', small_style)]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(muted)
        canvas.drawString(32, 21, 'OptiDay')
        canvas.drawRightString(A4[0] - 32, 21, f'第 {document.page} 页')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
