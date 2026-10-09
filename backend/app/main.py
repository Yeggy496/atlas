from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
import json
import os
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
from .schemas import Problem, SolveRequest, ParseRequest, RepairRequest, Scenario
from .adapters import ADAPTERS
from .solver.engine import solve
from .solver.diagnosis import diagnose, add_demo_conflict
from .llm.providers import get_provider
from .importer import import_table
from .storage import init_db, save_run, recent_runs


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app=FastAPI(title='ATLAS-Σ',version='0.1.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['GET','POST'],allow_headers=['Content-Type'])


@app.get('/api/health')
def health():
    return {'status':'ok','solver':'OR-Tools CP-SAT','provider':os.getenv('LLM_PROVIDER','demo'),'slot_minutes':30}


@app.get('/api/templates/{scenario}')
def template(scenario:Scenario):
    return ADAPTERS[scenario]().model_dump()


def run(request:SolveRequest):
    if not request.reviewed: raise HTTPException(409,'请先检查并确认任务和约束，再开始求解。')
    result=solve(request.problem,request.mode,request.previous)
    if result['status']=='INFEASIBLE': result['conflicts'],result['repairs']=diagnose(request.problem)
    result['run_id']=uuid4().hex[:12]
    save_run(result['run_id'],request.problem.model_dump(),result)
    return result


@app.post('/api/solve')
def optimize(request:SolveRequest):
    return run(request)


@app.post('/api/constraints/parse')
def parse(request:ParseRequest):
    try: return get_provider().parse_constraints(request.problem,request.text)
    except (ValueError,KeyError,ValidationError) as exc:
        raise HTTPException(422,str(exc)[:500]) from exc


@app.post('/api/constraints/validate')
def validate(problem:Problem):
    return {'valid':True,'constraints':len(problem.constraints)}


@app.post('/api/demo/conflict')
def demo_conflict(problem:Problem):
    return add_demo_conflict(problem).model_dump()


@app.post('/api/repair')
def repair(request:RepairRequest):
    c=next((x for x in request.problem.constraints if x.id==request.constraint_id),None)
    if not c: raise HTTPException(404,'这条约束已不存在，请重新求解。')
    p=request.problem.model_copy(deep=True)
    p.constraints=[x for x in p.constraints if x.id!=c.id]
    result=run(SolveRequest(problem=p,reviewed=request.reviewed,mode=request.mode,previous=request.previous))
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
    resource={'life':'me','academic':'class','lab':'teamA'}[scenario]
    content=f'name,duration_minutes,day,start,resources,category\n临时会议,60,3,19:00,{resource},meeting\n数据复习,90,,,{resource},study\n'
    return Response('\ufeff'+content,media_type='text/csv',headers={'Content-Disposition':'attachment; filename=atlas-template.csv'})


@app.get('/api/history')
def history():
    return recent_runs()


# A production build can be served by FastAPI as one local/deployable application.
dist=Path(__file__).resolve().parents[2]/'frontend'/'dist'
if dist.exists(): app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
