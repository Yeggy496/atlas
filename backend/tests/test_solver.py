from io import BytesIO
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pydantic import ValidationError
from app.adapters import ADAPTERS
from app.schemas import Activity, Constraint, Problem, Resource, Assignment
from app.solver.engine import solve
from app.solver.validator import verify
from app.solver.diagnosis import add_demo_conflict, diagnose
from app.llm.providers import DemoProvider
from app.importer import import_table
from app.main import app


@pytest.mark.parametrize('scenario',['life','academic','lab','meeting','production'])
def test_each_adapter_produces_legal_schedule(scenario):
    problem=ADAPTERS[scenario]()
    result=solve(problem,seconds=4)
    assert result['status'] in ('OPTIMAL','FEASIBLE')
    assignments=[Assignment(**a) for a in result['assignments']]
    assert verify(problem,assignments)==[]
    assert len(assignments)==len(problem.activities)
    if scenario=='life':
        assert sum(a.duration for a in problem.activities if a.category=='sleep')==7*16
        assert sum(a.duration for a in problem.activities if a.id.startswith('python'))==12
        assert len({a.start//48 for a in assignments if a.activity_id.startswith('run')})==3


def test_actual_infeasibility_and_verified_repair():
    problem=add_demo_conflict(ADAPTERS['lab']())
    assert solve(problem,seconds=.5)['status']=='INFEASIBLE'
    conflicts,repairs=diagnose(problem)
    assert conflicts and repairs
    for repair in repairs:
        changed=problem.model_copy(deep=True)
        changed.constraints=[c for c in changed.constraints if c.id!=repair['constraint_id']]
        assert solve(changed,seconds=.7,optimize=False)['assignments']


def test_parser_keeps_user_review_gate_and_meeting_fixed_time():
    p=ADAPTERS['life']()
    parsed=DemoProvider().parse_constraints(p,'周三19:00有一个临时会议。')
    assert parsed['requires_review']
    changed=Problem.model_validate(parsed['problem'])
    assert len(changed.activities)==len(p.activities)+1
    meeting=next(a for a in changed.activities if a.name=='临时会议')
    fixed=next(c for c in changed.constraints if c.target==meeting.id)
    assert fixed.start==38 and fixed.day==2


def test_unsupported_text_is_disclosed():
    parsed=DemoProvider().parse_constraints(ADAPTERS['life'](),'把量子纠缠任务放在火星时间。')
    assert not parsed['summary']
    assert parsed['warnings']


def test_stability_preserves_prior_feasible_assignments():
    p=ADAPTERS['life']()
    original=solve(p,seconds=4)
    changed=Problem.model_validate(DemoProvider().parse_constraints(p,'周三19:00有一个临时会议。')['problem'])
    previous=[Assignment(**a) for a in original['assignments']]
    updated=solve(changed,mode='robust',previous=previous,seconds=4)
    assert updated['assignments']
    assert updated['metrics']['changed']==0
    assert updated['objective']['stability_applicable']


def test_capacity_two_and_precedence():
    p=Problem(scenario='lab',name='容量与前置校验',resources=[Resource(id='device',name='两台设备',capacity=2)],activities=[Activity(id='a',name='A',duration=2,resources=['device'],days=[0],window_start=16,window_end=20),Activity(id='b',name='B',duration=2,resources=['device'],days=[0],window_start=16,window_end=20)],constraints=[Constraint(id='ca',label='A固定8点',type='fixed_time',target='a',day=0,start=16),Constraint(id='cb',label='B固定8点',type='fixed_time',target='b',day=0,start=16)])
    assert solve(p,seconds=.5)['assignments']
    p.resources[0].capacity=1
    assert solve(p,seconds=.5)['status']=='INFEASIBLE'
    p.resources[0].capacity=2
    p.constraints.append(Constraint(id='precedence',label='A在B前',type='precedence',target='a',other='b'))
    assert solve(p,seconds=.5)['status']=='INFEASIBLE'


def _consecutive_problem():
    return Problem(scenario='academic',name='连排校验',resources=[Resource(id='room',name='教室',type='room',seats=30)],
        activities=[Activity(id='a',name='A',duration=2,resources=['room'],days=[0],window_start=16,window_end=24),
                    Activity(id='b',name='B',duration=2,resources=['room'],days=[0],window_start=16,window_end=24)],
        constraints=[Constraint(id='con',label='A与B连排',type='consecutive',target='a',other='b')])


def test_consecutive_constraint_links_two_activities_back_to_back():
    p=_consecutive_problem()
    result=solve(p,seconds=1)
    assert result['status'] in ('OPTIMAL','FEASIBLE')
    by={x['activity_id']:x for x in result['assignments']}
    assert by['b']['start']==by['a']['end']
    assert verify(p,[Assignment(**x) for x in result['assignments']])==[]


def test_consecutive_requires_a_second_activity():
    with pytest.raises(ValidationError):
        Constraint(id='bad',label='缺后续活动',type='consecutive',target='a')


def test_validator_rejects_non_adjacent_consecutive():
    p=_consecutive_problem()
    broken=[Assignment(activity_id='a',start=16,end=18,room_id='room'),
            Assignment(activity_id='b',start=20,end=22,room_id='room')]
    assert verify(p,broken)


def test_demo_parser_links_two_activities_back_to_back():
    parsed=DemoProvider().parse_constraints(ADAPTERS['academic'](),'机器学习1和机器学习2连排。')
    changed=Problem.model_validate(parsed['problem'])
    demo=[c for c in changed.constraints if c.type=='consecutive' and c.source=='demo_parser']
    assert demo and demo[-1].target=='ml0' and demo[-1].other=='ml1'



def test_validator_rejects_deliberately_corrupted_result():
    p=ADAPTERS['life']()
    result=solve(p,seconds=4)
    assignments=[Assignment(**a) for a in result['assignments']]
    assignments[1].start=assignments[0].start
    assignments[1].end=assignments[0].end
    assert verify(p,assignments)


def test_invalid_entity_reference_is_rejected():
    p=ADAPTERS['life']().model_dump()
    p['constraints'].append({'id':'bad','label':'未知课程','type':'unavailable','target':'does_not_exist','start':18,'end':20})
    with pytest.raises(ValidationError): Problem.model_validate(p)


@pytest.mark.parametrize('format',['csv','xlsx'])
def test_structured_file_import_without_llm(format):
    p=ADAPTERS['life']()
    rows=[['name','duration_minutes','day','start','resources','category'],['测试会议',60,3,'19:00','me','meeting']]
    if format=='csv': content=('\n'.join(','.join(map(str,r)) for r in rows)).encode('utf-8')
    else:
        book=Workbook();sheet=book.active
        for row in rows:sheet.append(row)
        buf=BytesIO();book.save(buf);content=buf.getvalue()
    imported=import_table(p,'data.'+format,content)
    assert len(imported['problem']['activities'])==len(p.activities)+1
    assert imported['requires_review']


def test_review_gate_is_enforced_by_api():
    with TestClient(app) as client:
        response=client.post('/api/solve',json={'problem':ADAPTERS['lab']().model_dump(),'reviewed':False})
        assert response.status_code==409
        assert client.get('/api/health').json()['solver']=='OR-Tools CP-SAT'


def test_production_build_is_served_from_project_directory():
    with TestClient(app) as client:
        response=client.get('/')
        assert response.status_code==200
        assert 'ATLAS' in response.text
        assert 'text/html' in response.headers['content-type']

def test_production_jobs_keep_operation_order():
    problem=ADAPTERS['production']()
    result=solve(problem,mode='balanced',seconds=5)
    assert result['status'] in ('OPTIMAL','FEASIBLE')
    assignments=[Assignment(**a) for a in result['assignments']]
    assert verify(problem,assignments)==[]
    by={a.activity_id:a for a in assignments}
    groups={}
    for a in problem.activities:
        if a.group:
            groups.setdefault(a.group,[]).append(a)
    # 三个工单各自保持 切削 -> 装配 -> 质检 的先后顺序
    assert len(groups)==3
    for members in groups.values():
        members.sort(key=lambda a:a.op_index)
        assert [a.op_index for a in members]==[0,1,2]
        for prev,nxt in zip(members,members[1:]):
            assert by[prev.id].end<=by[nxt.id].start


def test_group_operation_index_must_be_contiguous():
    base={'scenario':'production','name':'工序序号校验','activities':[
        {'id':'j0','name':'切削','duration':2,'category':'operation','room_options':['mill1'],'group':'J','op_index':0,'days':[0],'window_start':16,'window_end':40},
        {'id':'j2','name':'质检','duration':2,'category':'operation','resources':['assembly'],'group':'J','op_index':2,'days':[0],'window_start':16,'window_end':40}]}
    with pytest.raises(ValidationError):
        Problem.model_validate(base)
