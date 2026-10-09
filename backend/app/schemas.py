"""The shared representation consumed by all scenario adapters and the solver."""
from typing import Literal
from pydantic import BaseModel, Field, model_validator

Scenario = Literal['life', 'academic', 'lab']
ConstraintType = Literal['fixed_time', 'time_window', 'unavailable', 'preferred_window', 'deadline', 'precedence', 'daily_limit', 'min_gap']


class Resource(BaseModel):
    id: str
    name: str
    type: str = 'person'
    capacity: int = Field(default=1, ge=1, le=100)
    seats: int = Field(default=0, ge=0)
    room_type: str = ''


class Activity(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=100)
    duration: int = Field(default=2, ge=1, le=48, description='30-minute slots')
    category: str = 'study'
    resources: list[str] = Field(default_factory=list)
    demands: dict[str, int] = Field(default_factory=dict)
    room_options: list[str] = Field(default_factory=list)
    required_seats: int = Field(default=0, ge=0)
    room_type: str = ''
    days: list[int] = Field(default_factory=lambda: list(range(7)))
    window_start: int = Field(default=16, ge=0, le=47)
    window_end: int = Field(default=44, ge=1, le=48)
    optional: bool = False
    priority: int = Field(default=5, ge=1, le=10)

    @model_validator(mode='after')
    def validate_days(self):
        if not self.days or any(d < 0 or d > 6 for d in self.days):
            raise ValueError('活动必须指定周一至周日内的有效日期。')
        if self.window_start >= self.window_end:
            raise ValueError('开始时间必须早于结束时间。')
        if any(v < 1 for v in self.demands.values()):
            raise ValueError('资源需求数量必须为正整数。')
        return self


class Constraint(BaseModel):
    id: str
    label: str = Field(min_length=1, max_length=160)
    type: ConstraintType
    target: str = '*'
    level: Literal['hard', 'soft'] = 'hard'
    day: int | None = Field(default=None, ge=0, le=6)
    start: int = Field(default=0, ge=0, le=336)
    end: int = Field(default=48, ge=0, le=336)
    other: str | None = None
    value: int = Field(default=0, ge=0, le=336)
    source: str = 'manual'

    @model_validator(mode='after')
    def validate_semantics(self):
        if self.type == 'preferred_window' and self.level != 'soft':
            raise ValueError('时间偏好必须是软约束。')
        if self.type != 'preferred_window' and self.level == 'soft':
            raise ValueError('此 Demo 仅将时间偏好编译为软约束。')
        if self.type in ('time_window', 'unavailable', 'preferred_window'):
            if not (0 <= self.start < self.end <= 48):
                raise ValueError('时间窗口必须在一天内且起点早于终点。')
        if self.type == 'fixed_time' and (self.day is None or self.start >= 48):
            raise ValueError('固定时间必须包含日期和当天的开始时刻。')
        if self.type in ('precedence', 'min_gap') and not self.other:
            raise ValueError('前置关系或间隔约束必须指定第二项活动。')
        return self


class Problem(BaseModel):
    scenario: Scenario
    name: str
    week_start: str = '2026-10-12'
    activities: list[Activity] = Field(max_length=100)
    resources: list[Resource] = Field(max_length=50)
    constraints: list[Constraint] = Field(default_factory=list, max_length=200)

    @model_validator(mode='after')
    def validate_references(self):
        acts = {a.id for a in self.activities}
        resources = {r.id for r in self.resources}
        if len(acts) != len(self.activities) or len(resources) != len(self.resources):
            raise ValueError('任务或资源 ID 重复。')
        if len({c.id for c in self.constraints}) != len(self.constraints):
            raise ValueError('约束 ID 重复。')
        for a in self.activities:
            if not set(a.resources + a.room_options + list(a.demands)).issubset(resources):
                raise ValueError(f'{a.name} 引用了不存在的资源。')
        categories = {a.category for a in self.activities}
        for c in self.constraints:
            if c.target not in acts | resources | categories | {'*'}:
                raise ValueError(f'约束「{c.label}」的目标不存在。')
            if c.other is not None and c.other not in acts:
                raise ValueError('关联任务不存在。')
            if c.type in ('fixed_time', 'precedence', 'min_gap') and c.target not in acts:
                raise ValueError('固定时间、前置关系与间隔约束必须指向具体活动。')
        return self


class Assignment(BaseModel):
    activity_id: str
    start: int
    end: int
    room_id: str | None = None


class SolveRequest(BaseModel):
    problem: Problem
    reviewed: bool = False
    mode: Literal['efficient', 'balanced', 'robust'] = 'balanced'
    previous: list[Assignment] = Field(default_factory=list, max_length=100)


class ParseRequest(BaseModel):
    problem: Problem
    text: str = Field(min_length=1, max_length=4000)


class RepairRequest(SolveRequest):
    constraint_id: str
