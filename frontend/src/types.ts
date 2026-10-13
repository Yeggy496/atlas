export type Scenario =
  | "life"
  | "academic"
  | "lab"
  | "meeting"
  | "production";
export type Mode = "efficient" | "balanced" | "robust";
// "custom" is a UI-only pseudo-mode: it keeps the last chosen preset as a base and
// applies the user's slider values on top (MASTER_SPEC §15).
export type ModeSelection = Mode | "custom";
export interface WeightDimension {
  key: string;
  label: string;
  hint: string;
}
export interface WeightsMeta {
  dimensions: WeightDimension[];
  presets: Record<Mode, Record<string, number>>;
  repair_stability: number;
}
export interface Resource {
  id: string;
  name: string;
  type: string;
  capacity: number;
  seats: number;
  room_type: string;
}
export interface Activity {
  id: string;
  name: string;
  duration: number;
  category: string;
  resources: string[];
  demands: Record<string, number>;
  room_options: string[];
  required_seats: number;
  room_type: string;
  days: number[];
  window_start: number;
  window_end: number;
  optional: boolean;
  priority: number;
  group: string | null;
  op_index: number;
}
export type ConstraintType =
  | "fixed_time"
  | "time_window"
  | "unavailable"
  | "preferred_window"
  | "deadline"
  | "precedence"
  | "daily_limit"
  | "min_gap"
  | "consecutive";
export interface Constraint {
  id: string;
  label: string;
  type: ConstraintType;
  target: string;
  level: "hard" | "soft";
  day: number | null;
  start: number;
  end: number;
  other: string | null;
  value: number;
  source: string;
}
export interface Problem {
  scenario: Scenario;
  name: string;
  week_start: string;
  activities: Activity[];
  resources: Resource[];
  constraints: Constraint[];
}
export interface Assignment {
  activity_id: string;
  start: number;
  end: number;
  room_id: string | null;
}
export interface Result {
  status: string;
  run_id: string;
  assignments: Assignment[];
  metrics: {
    solve_time: number;
    activities: number;
    resources: number;
    constraints: number;
    variables: number;
    model_constraints: number;
    hard_violations?: number;
    scheduled?: number;
    scheduled_hours?: number;
    optional_completed?: number;
    preference_total?: number;
    preference_satisfied?: number;
    changed?: number;
    daily_hours?: number[];
  };
  objective: null | {
    penalties: Record<string, number>;
    weights: Record<string, number>;
    value: number;
    best_bound: number;
    stability_applicable: boolean;
  };
  conflicts: { title: string; detail: string; constraint_ids: string[] }[];
  repairs: {
    constraint_id: string;
    label: string;
    detail: string;
    verified: boolean;
  }[];
}
export interface ExplanationReason {
  kind: string;
  title: string;
  detail: string;
  constraint_id?: string;
}
export interface Explanation {
  activity_id: string;
  name: string;
  day: number;
  day_name: string;
  start: number;
  end: number;
  start_clock: string;
  end_clock: string;
  duration_hours: number;
  room_id: string | null;
  room_name: string | null;
  candidate_slots_total: number;
  candidate_slots_same_day: number;
  reasons: ExplanationReason[];
  narrative: { headline: string; bullets: string[] } | null;
  narrative_source: string;
}
export interface HistoryRun {
  id: string;
  created_at: string;
  problem: Problem;
  result: Result;
}
export const MAX_INPUT_CHARS = 4000;
export const DAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
export const SCENARIOS: Record<
  Scenario,
  { title: string; en: string; description: string; input: string }
> = {
  life: {
    title: "个人周计划",
    en: "LifeGrid",
    description: "在固定日程之外，为学习、运动与生活找到合适的位置。",
    input:
      "每天睡眠不少于8小时，每周跑步3次，每次1小时，最好17点以后。本周安排6小时Python学习，高数作业周三之前完成。",
  },
  academic: {
    title: "智能排课",
    en: "Academic",
    description: "协调一个班的课程、教师与教室，让每节课各就其位。",
    input:
      "张老师周五下午不能上课，机器学习课程必须连续两节，数据库实验只能安排在计算机实验室。",
  },
  lab: {
    title: "实验室调度",
    en: "LabFlow",
    description: "协调实验团队、仪器与实验室，满足连续使用和前置关系。",
    input: "实验团队 A 周三下午不可用。",
  },
  meeting: {
    title: "会议室预订",
    en: "RoomBook",
    description: "为会议、参会人与共享会议室找到互不冲突的时段。",
    input: "部门周例会固定周一 10 点，12:00–13:00 不安排会议，会议尽量安排在上午。",
  },
  production: {
    title: "生产排程",
    en: "JobShop",
    description: "把带多道工序的工单排到共享机台，先加工、再装配、最后质检。",
    input: "工单 A 需在第 2 天结束前完工，切削工序可在两台数控机床中任选。",
  },
};

export const CATEGORIES: Record<string, { label: string; color: string }> = {
  course: { label: "课程", color: "blue" },
  study: { label: "学习", color: "purple" },
  homework: { label: "作业", color: "teal" },
  exercise: { label: "运动", color: "orange" },
  meal: { label: "用餐", color: "slate" },
  sleep: { label: "睡眠", color: "slate" },
  leisure: { label: "自由活动", color: "pink" },
  meeting: { label: "会议", color: "pink" },
  operation: { label: "工序", color: "orange" },
  experiment: { label: "实验", color: "teal" },
  lab: { label: "实验课", color: "teal" },
};
export const clock = (slot: number) =>
  `${String(Math.floor((slot % 48) / 2)).padStart(2, "0")}:${slot % 2 ? "30" : "00"}`;
export const id = () => crypto.randomUUID().slice(0, 8);
