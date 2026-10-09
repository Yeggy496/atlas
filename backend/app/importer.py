"""Strict CSV/XLSX template import; structured files are not sent to a model."""
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
    if len(content)>2_000_000: raise ValueError('演示版文件最大为 2 MB。')
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
    else: raise ValueError('此 Demo 支持 CSV 和 XLSX 模板。')
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
