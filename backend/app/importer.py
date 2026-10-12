"""Strict CSV/XLSX template import; structured files are not sent to a model.

TXT/PDF are handled by a separate, clearly-scoped path: they carry unstructured
text, so we only extract plain text deterministically and hand it to the existing
natural-language constraint pipeline (``/api/constraints/parse``). Per MASTER_SPEC
§11, "能用确定性程序解决的，不交给大模型猜" — extraction is deterministic; only
the already-existing NL understanding step sees a model.
"""
import csv
from decimal import Decimal, InvalidOperation
from io import StringIO, BytesIO
from uuid import uuid4
from openpyxl import load_workbook
from .schemas import Activity, Constraint, Problem


def parse_clock(value):
    h,m=map(int,str(value).strip().split(':'))
    if not 0<=h<=23 or m not in (0,30): raise ValueError('时间请使用 HH:00 或 HH:30。')
    return h*2+m//30


def parse_integer(value, label):
    try:
        number=Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f'{label}须填写整数。') from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError(f'{label}须填写整数。')
    return int(number)


def import_table(problem:Problem, filename:str, content:bytes):
    if len(content)>2_000_000: raise ValueError('上传文件最大为 2 MB。')
    if filename.lower().endswith('.csv'):
        try: raw=content.decode('utf-8-sig')
        except UnicodeDecodeError: raw=content.decode('gb18030')
        rows=list(csv.DictReader(StringIO(raw)))
    elif filename.lower().endswith('.xlsx'):
        book=load_workbook(BytesIO(content),read_only=True,data_only=True)
        try:
            sheet=book.active
            iterator=sheet.iter_rows(values_only=True)
            first=next(iterator,None)
            if first is None: raise ValueError('文件为空，请下载模板并填写活动。')
            headers=[str(x).strip() for x in first]
            rows=[dict(zip(headers,line)) for line in iterator if any(v is not None for v in line)]
        finally: book.close()
    else: raise ValueError('任务表支持 CSV 和 XLSX 模板。')
    if not rows or len(rows)>100: raise ValueError('文件须包含 1–100 行活动。')
    p=problem.model_copy(deep=True)
    resource_ids={r.id for r in p.resources}
    summary=[]
    for index,row in enumerate(rows,2):
        if not {'name','duration_minutes'}.issubset(row): raise ValueError('文件缺少 name 或 duration_minutes 列，请下载模板。')
        name=str(row['name'] or '').strip()
        minutes=parse_integer(row['duration_minutes'],f'第 {index} 行时长')
        if minutes<=0 or minutes%30: raise ValueError(f'第 {index} 行时长须为正数且为 30 分钟整数倍。')
        rid_text=str(row.get('resources') or ('me' if p.scenario=='life' else ('class' if p.scenario=='academic' else 'teamA')))
        ids=[x.strip() for x in rid_text.split('|') if x.strip()]
        if not ids or not set(ids).issubset(resource_ids): raise ValueError(f'第 {index} 行引用未知资源 ID。')
        aid='import_'+uuid4().hex[:10]
        a=Activity(id=aid,name=name,duration=minutes//30,category=str(row.get('category') or 'study'),resources=ids)
        day=row.get('day'); start=row.get('start')
        if day is not None and str(day).strip()!='':
            a.days=[parse_integer(day,f'第 {index} 行日期')-1]
        if start is not None and str(start).strip()!='':
            if len(a.days)!=1: raise ValueError(f'第 {index} 行固定时间必须同时指定 day (1–7)。')
            p.constraints.append(Constraint(id='fixed_'+aid,label=f'{name} · 导入固定日程',type='fixed_time',target=aid,day=a.days[0],start=parse_clock(start),source='file'))
            a.window_start=0; a.window_end=48
        p.activities.append(a)
        summary.append(f'导入 {name} · {minutes} 分钟')
    return {'problem':Problem.model_validate(p.model_dump()).model_dump(),'summary':summary,'requires_review':True}


# --------------------------------------------------------------------------- #
# Unstructured text import (TXT / PDF) — MASTER_SPEC §11.
# These only extract plain text; they never add activities or constraints.
# The extracted text is returned to the caller, which forwards it to the
# existing natural-language constraint pipeline for user review.
# --------------------------------------------------------------------------- #

MAX_TEXT_CHARS = 20_000
TEXT_SUFFIXES = ('.txt',)
PDF_SUFFIXES = ('.pdf',)


def extract_text(filename: str, content: bytes) -> dict:
    """Extract plain text from a .txt or .pdf file without interpreting it.

    Deterministic by design: TXT is decoded (UTF-8/GB18030 fallback), PDF text is
    read page by page with pypdf when it is installed. Nothing here guesses at
    tasks or constraints — that is the job of the reviewed NL pipeline.
    """
    if len(content) > 2_000_000:
        raise ValueError('上传文件最大为 2 MB。')
    name = filename.lower()
    if name.endswith(TEXT_SUFFIXES):
        text = _decode_text(content)
        kind = 'txt'
    elif name.endswith(PDF_SUFFIXES):
        text = _extract_pdf(content)
        kind = 'pdf'
    else:
        raise ValueError('文本导入支持 TXT 和 PDF；结构化数据请使用 CSV / XLSX 模板。')
    text = text.strip()
    if not text:
        raise ValueError('未能从文件中提取到文字。扫描版 PDF 需要先做 OCR。')
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
    return {'kind': kind, 'text': text, 'chars': len(text)}


def _decode_text(content: bytes) -> str:
    for encoding in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('无法识别文本编码，请另存为 UTF-8。')


def _extract_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError('服务器未安装 PDF 解析组件（pypdf）。请改用 TXT，或让管理员安装依赖。') from exc
    try:
        reader = PdfReader(BytesIO(content))
        pages = [(page.extract_text() or '').strip() for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - surface any pdf parse failure as a friendly 422
        raise ValueError('PDF 解析失败，请确认文件未加密且非扫描件。') from exc
    return '\n'.join(page for page in pages if page)
