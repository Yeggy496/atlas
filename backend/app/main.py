from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
import json
import os
from .config import env
from zipfile import BadZipFile
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
# Small .env loader: values are configuration data, never shell commands.
env_file=Path(__file__).resolve().parents[2]/'.env'
if env_file.exists():
    for line in env_file.read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key,value=line.split('=',1)
            if key.strip().replace('_','').isalnum():
                os.environ.setdefault(key.strip(),value.strip().strip('\"').strip("'"))
from .schemas import Problem, SolveRequest, ParseRequest, RepairRequest, ExplainRequest, CompareRequest, ExportRequest, Scenario
from .adapters import ADAPTERS
from .solver.engine import solve, WEIGHTS, REPAIR_STABILITY
from .solver.diagnosis import diagnose, add_demo_conflict
from .solver.compare import compare_plans
from .llm.providers import get_provider
from .llm.explanation_service import get_explanation_service
from .importer import import_table, extract_text
from .workload import admitted, SOLVER_SLOTS, MODEL_SLOTS
from .exporters import build_xlsx, build_pdf
from .storage import init_db, save_run, recent_runs, server_history_enabled


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


# Single source of truth for the release version: the repository VERSION file.
# Reading it here keeps /openapi.json, /docs and the health payload in step with
# VERSION/package.json instead of drifting from a stale hard-coded string.
def _read_version() -> str:
    try:
        return (Path(__file__).resolve().parents[2]/'VERSION').read_text(encoding='utf-8').strip() or '0.0.0'
    except OSError:
        return '0.0.0'


APP_VERSION=_read_version()

app=FastAPI(title='OptiDay',version=APP_VERSION,lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['GET','POST'],allow_headers=['Content-Type'])


@app.get('/api/health')
def health():
    provider = os.getenv('LLM_PROVIDER', 'demo').strip().lower()
    configured = provider in ('deepseek', 'openai') and bool(os.getenv(f'{provider.upper()}_API_KEY', '').strip())
    return {'status':'ok','product':'OptiDay','version':APP_VERSION,'solver':'OR-Tools CP-SAT','provider':provider,'slot_minutes':30,
            'model_configured':configured,'parser_type':'model' if provider in ('deepseek','openai') else 'rules',
            'history_scope':'server' if server_history_enabled() else 'browser'}


@app.get('/api/weights')
def weights_meta():
    """Expose the objective dimensions and preset values (MASTER_SPEC §15).

    The frontend uses this to render the custom-weight sliders, so the UI never
    hard-codes the solver's objective names or default magnitudes.
    """
    dimensions=[
        {'key':'goal','label':'目标达成','hint':'满足时间窗偏好与可选任务的取舍'},
        {'key':'compact','label':'时间紧凑','hint':'减少每日占用区间内的空档'},
        {'key':'balance','label':'负载均衡','hint':'各天任务量尽量平均'},
        {'key':'robust','label':'缓冲余量','hint':'截止任务预留更多提前量'},
        {'key':'lead','label':'尽早完成','hint':'截止任务越早开始越好'},
        {'key':'stability','label':'最小扰动','hint':'尽量保留上一版安排'},
        {'key':'regular','label':'作息规律','hint':'日常活动尽量每天同一时间'},
    ]
    return {'dimensions':dimensions,'presets':WEIGHTS,'repair_stability':REPAIR_STABILITY}


@app.get('/api/templates/{scenario}')
def template(scenario:Scenario):
    return ADAPTERS[scenario]().model_dump()


def run(request:SolveRequest,keep_previous=False):
    if not request.reviewed: raise HTTPException(409,'请先检查并确认任务和约束，再开始求解。')
    with admitted(SOLVER_SLOTS, '求解服务'):
        return run_admitted(request, keep_previous)


def run_admitted(request:SolveRequest,keep_previous=False):
    result=solve(request.problem,request.mode,request.previous,keep_previous=keep_previous,overrides=request.weights)
    if result['status']=='INFEASIBLE': result['conflicts'],result['repairs']=diagnose(request.problem)
    elif result['status']=='UNKNOWN': result['conflicts'],result['repairs']=diagnose(request.problem,proved_infeasible=False,max_relaxations=6)
    result['run_id']=uuid4().hex[:12]
    save_run(result['run_id'],request.problem.model_dump(),result)
    return result


@app.post('/api/solve')
def optimize(request:SolveRequest):
    return run(request)


@app.post('/api/constraints/parse')
def parse(request:ParseRequest):
    try:
        with admitted(MODEL_SLOTS, '需求识别服务'):
            return get_provider().parse_constraints(request.problem,request.text)
    except (ValueError,KeyError,ValidationError) as exc:
        raise HTTPException(422,str(exc)[:500]) from exc


# MASTER_SPEC §23 names this endpoint ``/api/parse-constraints``. The canonical
# route above is kept for the existing frontend; this alias serves the documented
# contract without changing either behaviour.
@app.post('/api/parse-constraints')
def parse_constraints_alias(request:ParseRequest):
    return parse(request)


@app.post('/api/constraints/validate')
def validate(problem:Problem):
    return {'valid':True,'constraints':len(problem.constraints)}


@app.post('/api/explain')
def explain_assignment(request:ExplainRequest):
    """Deterministic explanation, optionally rephrased by the configured LLM.

    The deterministic facts from ``solver/explain.py`` are always returned; when a
    real provider is configured the same facts are also narrated (MASTER_SPEC §18).
    ``demo``/failure keeps the response fully offline and correct.
    """
    try:
        service = get_explanation_service()
        if not request.include_narrative:
            return service.build(request.problem,request.assignments,request.activity_id,request.previous,include_narrative=False)
        with admitted(MODEL_SLOTS, 'AI 说明服务'):
            return service.build(request.problem,request.assignments,request.activity_id,request.previous)
    except KeyError as exc:
        raise HTTPException(404,str(exc)[:500]) from exc


@app.post('/api/demo/conflict')
def demo_conflict(problem:Problem):
    try:
        return add_demo_conflict(problem).model_dump()
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@app.post('/api/diagnose')
def diagnose_conflicts(request:SolveRequest):
    """Standalone conflict diagnosis (MASTER_SPEC §14, §23).

    Unlike ``/api/solve`` (which inlines conflicts only when its own solve comes
    back INFEASIBLE/UNKNOWN), this endpoint re-solves the given problem first and
    only then diagnoses — so calling it on a healthy, solvable problem correctly
    reports ``infeasible: false`` instead of inventing a conflict. Every suggested
    relaxation still carries a CP-SAT feasibility witness, never an LLM guess.
    """
    if not request.reviewed:
        raise HTTPException(409,'请先检查并确认任务和约束，再开始求解。')
    with admitted(SOLVER_SLOTS, '求解服务'):
        return diagnose_admitted(request)


def diagnose_admitted(request:SolveRequest):
    probe=solve(request.problem,request.mode,seconds=float(env('OPTIDAY_DIAGNOSIS_SECONDS','2')),previous=request.previous,overrides=request.weights)
    status=probe['status']
    if status in ('OPTIMAL','FEASIBLE'):
        return {'status':status,'infeasible':False,'conflicts':[],'repairs':[]}
    conflicts,repairs=diagnose(request.problem,proved_infeasible=(status=='INFEASIBLE'))
    return {'status':status,'infeasible':status=='INFEASIBLE','conflicts':conflicts,'repairs':repairs}


@app.post('/api/compare')
def compare(request:CompareRequest):
    """Diff two schedules of the same problem (Minimal-Perturbation evidence)."""
    return compare_plans(request.problem,request.previous,request.current)


@app.post('/api/repair')
def repair(request:RepairRequest):
    c=next((x for x in request.problem.constraints if x.id==request.constraint_id),None)
    if not c: raise HTTPException(404,'这条约束已不存在，请重新求解。')
    p=request.problem.model_copy(deep=True)
    p.constraints=[x for x in p.constraints if x.id!=c.id]
    # 修复必须最小化对现有课表的改动，因此强制启用稳定性项。
    result=run(SolveRequest(problem=p,reviewed=request.reviewed,mode=request.mode,previous=request.previous,weights=request.weights),keep_previous=True)
    return {'problem':p.model_dump(),'result':result}


@app.post('/api/import')
def import_file(file:UploadFile=File(...),problem_json:str=Form(...)):
    try:
        p=Problem.model_validate_json(problem_json)
        return import_table(p,file.filename or '',file.file.read(2_000_001))
    except (ValueError,KeyError,StopIteration,ValidationError,BadZipFile) as exc:
        raise HTTPException(422,str(exc)[:500]) from exc


@app.get('/api/import/template.csv')
def csv_template(scenario:Scenario='life'):
    resource={'life':'me','academic':'class','lab':'teamA','meeting':'room_m','production':'mill1'}[scenario]
    content=f'name,duration_minutes,day,start,resources,category\n临时会议,60,3,19:00,{resource},meeting\n数据复习,90,,,{resource},study\n'
    return Response('\ufeff'+content,media_type='text/csv',headers={'Content-Disposition':'attachment; filename=optiday-template.csv'})


@app.post('/api/import/text')
def import_text(file:UploadFile=File(...)):
    """Extract plain text from TXT/PDF and hand it to the NL constraint pipeline.

    Deterministic extraction first (MASTER_SPEC §11); the reviewed parser then
    turns the text into structured constraints. This endpoint never writes a
    problem directly — it returns extracted text for the user to review.
    """
    try:
        extracted=extract_text(file.filename or '',file.file.read(2_000_001))
    except (ValueError,KeyError) as exc:
        raise HTTPException(422,str(exc)[:500]) from exc
    return extracted


@app.get('/api/history')
def history():
    """Compatibility route; public deployments keep history in each browser."""
    return recent_runs()


@app.post('/api/export/{fmt}')
def export_plan(fmt:str,request:ExportRequest):
    """Export a solved schedule as XLSX or PDF (MASTER_SPEC §25 P2).

    The export is built from the same solved result the UI displayed, so the file
    can never disagree with the screen. Both formats carry the Chinese schedule.
    """
    fmt=fmt.lower()
    if fmt not in ('xlsx','pdf'):
        raise HTTPException(404,'仅支持导出 xlsx 或 pdf。')
    try:
        if fmt=='xlsx':
            payload=build_xlsx(request.problem,request.result)
            media='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            payload=build_pdf(request.problem,request.result)
            media='application/pdf'
    except (ValueError,KeyError,TypeError,AttributeError,IndexError) as exc:
        raise HTTPException(422,f'导出失败：{str(exc)[:400]}') from exc
    name=f'optiday-{request.problem.scenario}-{request.result.get("run_id","plan")}'
    return Response(payload,media_type=media,headers={'Content-Disposition':f'attachment; filename={name}.{fmt}'})


# A production build can be served by FastAPI as one local/deployable application.
# `app/webapp` ships a copy of the build so the service stays self-contained when
# only the backend tree is uploaded; `frontend/dist` (repo layout) is preferred.
for dist in (Path(__file__).resolve().parents[2]/'frontend'/'dist',Path(__file__).resolve().parent/'webapp'):
    if (dist/'index.html').exists():
        app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
        break
