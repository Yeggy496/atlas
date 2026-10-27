"""Repair suggestions are accepted only after a real solver verifies the change."""
import os
from ..config import env
from ..schemas import Problem, Constraint
from .engine import solve
from .constraints import candidates


def diagnose(problem: Problem, proved_infeasible: bool = True, max_relaxations: int = 20):
    conflicts, repairs = [], []
    for a in problem.activities:
        if not a.optional and not list(candidates(problem,a)):
            conflicts.append({'title':f'{a.name} 没有可用时间或合适资源','detail':'当前时间域、硬约束、教室类型和容量筛选后，没有合法候选。','constraint_ids':[c.id for c in problem.constraints if c.target in (a.id,a.category,*a.resources)]})
    # Each suggested relaxation comes with a feasibility witness, not LLM speculation.
    for c in [c for c in problem.constraints if c.level=='hard'][:max_relaxations]:
        changed = problem.model_copy(deep=True)
        changed.constraints = [x for x in changed.constraints if x.id != c.id]
        witness = solve(changed,seconds=float(env('OPTIDAY_DIAGNOSIS_SECONDS', '.45')),optimize=False)
        if witness['status'] in ('FEASIBLE','OPTIMAL'):
            repairs.append({'constraint_id':c.id,'label':f'放宽「{c.label}」','detail':'已重新求解验证：移除此条限制后存在合法方案。需你确认后应用。','verified':True})
            if len(repairs)>=3:
                break
    if repairs:
        if proved_infeasible:
            conflicts.append({'title':'硬约束与资源容量共同导致冲突','detail':'下列放宽方案分别经过 CP-SAT 验证；它们是可行修复候选，不代表全局最小冲突核心。','constraint_ids':[r['constraint_id'] for r in repairs]})
        else:
            conflicts.append({'title':'超时情况下仍能恢复可行的放宽候选','detail':'本次求解超时（UNKNOWN），并未证明无解。下列放宽方案各自经过 CP-SAT 重求解验证存在合法方案，可作为排查方向；它们不代表全局最小冲突核心。','constraint_ids':[r['constraint_id'] for r in repairs]})
    if not conflicts:
        if proved_infeasible:
            conflicts.append({'title':'当前硬约束集合不可行','detail':'求解器已证明无解，但限时诊断没有找到单条放宽即可恢复可行的方案。请检查活动时间域、资源容量和组合限制。','constraint_ids':[]})
        else:
            conflicts.append({'title':'求解在时限内未得出可行解','detail':'本次求解达到时间上限（状态 UNKNOWN），尚未证明无解。可先提高求解时限或放宽部分硬约束后重试。','constraint_ids':[]})
    return conflicts, repairs


def add_demo_conflict(problem: Problem):
    p=problem.model_copy(deep=True)
    if p.scenario=='lab':
        ids=['expA','expB']
    elif p.scenario=='academic':
        ids=['ml0','math0']
    elif p.scenario=='meeting':
        ids=['review','interview']
    elif p.scenario=='production':
        ids=['jobA_asm','jobB_asm']
    else:
        ids=['python0','run0']
    names={a.id:a.name for a in p.activities}
    if not set(ids).issubset(names):
        raise ValueError('当前活动已修改，无法建立此场景的冲突示例。请恢复示例后重试。')
    day=1 if p.scenario=='production' else 2
    day_label='周二' if day==1 else '周三'
    for i,aid in enumerate(ids):
        p.constraints.append(Constraint(id=f'demo_conflict_{i}',label=f'{names[aid]} · {day_label} 14:00 固定开始',type='fixed_time',target=aid,day=day,start=28,source='demo'))
    return Problem.model_validate(p.model_dump())
