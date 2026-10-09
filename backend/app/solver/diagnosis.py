"""Repair suggestions are accepted only after a real solver verifies the change."""
from ..schemas import Problem, Constraint
from .engine import solve
from .constraints import candidates


def diagnose(problem: Problem):
    conflicts, repairs = [], []
    for a in problem.activities:
        if not a.optional and not list(candidates(problem,a)):
            conflicts.append({'title':f'{a.name} 没有可用时间或合适资源','detail':'当前时间域、硬约束、教室类型和容量筛选后，没有合法候选。','constraint_ids':[c.id for c in problem.constraints if c.target in (a.id,a.category,*a.resources)]})
    # Each suggested relaxation comes with a feasibility witness, not LLM speculation.
    for c in [c for c in problem.constraints if c.level=='hard'][:20]:
        changed = problem.model_copy(deep=True)
        changed.constraints = [x for x in changed.constraints if x.id != c.id]
        witness = solve(changed,seconds=.45,optimize=False)
        if witness['status'] in ('FEASIBLE','OPTIMAL'):
            repairs.append({'constraint_id':c.id,'label':f'放宽「{c.label}」','detail':'已重新求解验证：移除此条限制后存在合法方案。需你确认后应用。','verified':True})
            if len(repairs)>=3:
                break
    if repairs:
        conflicts.append({'title':'硬约束与资源容量共同导致冲突','detail':'下列放宽方案分别经过 CP-SAT 验证；它们是可行修复候选，不代表全局最小冲突核心。','constraint_ids':[r['constraint_id'] for r in repairs]})
    if not conflicts:
        conflicts.append({'title':'当前硬约束集合不可行','detail':'求解器已证明无解，但限时诊断没有找到单条放宽即可恢复可行的方案。请检查活动时间域、资源容量和组合限制。','constraint_ids':[]})
    return conflicts, repairs


def add_demo_conflict(problem: Problem):
    p=problem.model_copy(deep=True)
    if p.scenario=='lab':
        ids=['expA','expB']
    elif p.scenario=='academic':
        ids=['ml0','math0']
    else:
        ids=['python0','run0']
    for i,aid in enumerate(ids):
        p.constraints.append(Constraint(id=f'demo_conflict_{i}',label=f'{next(a.name for a in p.activities if a.id==aid)} · 周三 14:00 固定开始',type='fixed_time',target=aid,day=2,start=28,source='demo'))
    return Problem.model_validate(p.model_dump())
