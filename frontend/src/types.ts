export type Scenario = "life" | "academic" | "lab";
export type Mode = "efficient" | "balanced" | "robust";
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
}
export type ConstraintType =
  | "fixed_time"
  | "time_window"
  | "unavailable"
  | "preferred_window"
  | "deadline"
  | "precedence"
  | "daily_limit"
  | "min_gap";
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
export interface HistoryRun {
  id: string;
  created_at: string;
  problem: Problem;
  result: Result;
}
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
};
export const CATEGORIES: Record<string, { label: string; color: string }> = {
  course: { label: "固定课程", color: "blue" },
  study: { label: "学习", color: "purple" },
  homework: { label: "作业", color: "teal" },
  exercise: { label: "运动", color: "orange" },
  meal: { label: "用餐", color: "slate" },
  sleep: { label: "睡眠", color: "slate" },
  leisure: { label: "自由活动", color: "pink" },
  meeting: { label: "会议", color: "pink" },
  experiment: { label: "实验", color: "teal" },
  lab: { label: "实验课", color: "teal" },
};
export const clock = (slot: number) =>
  `${String(Math.floor((slot % 48) / 2)).padStart(2, "0")}:${slot % 2 ? "30" : "00"}`;
export const id = () => crypto.randomUUID().slice(0, 8);
