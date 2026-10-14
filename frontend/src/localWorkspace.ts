import { SCENARIOS, type Assignment, type Mode, type Problem, type Result, type Scenario } from "./types";

// Local content only: provider credentials and server history are never stored here.
export const LOCAL_WORKSPACE_KEY = "atlas.workspace.v1";
export interface LocalWorkspace {
  problem: Problem;
  result: Result | null;
  previous: Assignment[];
  previousProblem?: Problem;
  input: string;
  appliedInput?: string;
  mode: Mode;
  customWeights: Record<string, number> | null;
  reviewed: boolean;
  summary: string[];
  warnings: string[];
  inputTab: "constraints" | "activities";
  view: "calendar" | "resources";
}
export interface WorkspaceStore {
  schema_version: 1;
  active_scenario: Scenario;
  workspaces: Partial<Record<Scenario, LocalWorkspace>>;
}
type RecordValue = Record<string, unknown>;
const record = (value: unknown): value is RecordValue =>
  !!value && typeof value === "object" && !Array.isArray(value);
const number = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string");
const numbers = (value: unknown): value is Record<string, number> =>
  record(value) && Object.values(value).every(number);
const scenario = (value: unknown): value is Scenario =>
  typeof value === "string" && Object.hasOwn(SCENARIOS, value);
const list = (value: unknown, limit: number, check: (item: RecordValue) => boolean) =>
  Array.isArray(value) && value.length <= limit && value.every((item) => record(item) && check(item));

function assignments(value: unknown): value is Assignment[] {
  return list(value, 100, (a) => typeof a.activity_id === "string" &&
    number(a.start) && number(a.end) && a.start >= 0 && a.end > a.start && a.end <= 336 &&
    (a.room_id === null || typeof a.room_id === "string"));
}
function problem(value: unknown, s: Scenario): value is Problem {
  if (!record(value) || value.scenario !== s || typeof value.name !== "string" ||
    typeof value.week_start !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value.week_start) ||
    Number.isNaN(Date.parse(`${value.week_start}T12:00:00`))) return false;
  return list(value.resources, 50, (r) => typeof r.id === "string" && typeof r.name === "string" &&
    typeof r.type === "string" && typeof r.room_type === "string" && number(r.capacity) && r.capacity >= 1 && number(r.seats)) &&
    list(value.activities, 100, (a) => typeof a.id === "string" && typeof a.name === "string" &&
      typeof a.category === "string" && number(a.duration) && a.duration > 0 && a.duration <= 48 &&
      strings(a.resources) && strings(a.room_options) && numbers(a.demands) && number(a.required_seats) &&
      typeof a.room_type === "string" && Array.isArray(a.days) && a.days.length > 0 &&
      a.days.every((d) => number(d) && Number.isInteger(d) && d >= 0 && d <= 6) &&
      number(a.window_start) && number(a.window_end) && a.window_start < a.window_end &&
      typeof a.optional === "boolean" && number(a.priority) && number(a.op_index) &&
      (a.group === null || typeof a.group === "string")) &&
    list(value.constraints, 200, (c) => typeof c.id === "string" && typeof c.label === "string" &&
      ["fixed_time", "time_window", "unavailable", "preferred_window", "deadline", "precedence", "daily_limit", "min_gap", "consecutive"].includes(String(c.type)) &&
      typeof c.target === "string" && ["hard", "soft"].includes(String(c.level)) &&
      (c.day === null || (number(c.day) && Number.isInteger(c.day) && c.day >= 0 && c.day <= 6)) &&
      number(c.start) && number(c.end) && number(c.value) && typeof c.source === "string" &&
      (c.other === null || typeof c.other === "string"));
}
function result(value: unknown, p: Problem): value is Result | null {
  if (value === null) return true;
  if (!record(value) || typeof value.status !== "string" || typeof value.run_id !== "string" ||
    !assignments(value.assignments) || !record(value.metrics)) return false;
  const ids = new Set(p.activities.map((a) => a.id));
  if (value.assignments.some((a) => !ids.has(a.activity_id))) return false;
  const m = value.metrics;
  if (!["solve_time", "activities", "resources", "constraints", "variables", "model_constraints"].every((key) => number(m[key]))) return false;
  if (!Object.entries(m).every(([key, item]) => key === "daily_hours"
    ? Array.isArray(item) && item.length === 7 && item.every(number) : number(item))) return false;
  if (value.objective !== null && (!record(value.objective) || !numbers(value.objective.penalties) ||
    !numbers(value.objective.weights) || !number(value.objective.value) || !number(value.objective.best_bound) ||
    typeof value.objective.stability_applicable !== "boolean")) return false;
  return list(value.conflicts, 200, (c) => typeof c.title === "string" && typeof c.detail === "string" && strings(c.constraint_ids)) &&
    list(value.repairs, 200, (r) => typeof r.constraint_id === "string" && typeof r.label === "string" &&
      typeof r.detail === "string" && typeof r.verified === "boolean");
}
export function isLocalWorkspace(value: unknown, s: Scenario): value is LocalWorkspace {
  return record(value) && problem(value.problem, s) && result(value.result, value.problem) &&
    (value.previousProblem === undefined || problem(value.previousProblem, s)) &&
    assignments(value.previous) && typeof value.input === "string" && (value.appliedInput === undefined || typeof value.appliedInput === "string") &&
    ["efficient", "balanced", "robust"].includes(String(value.mode)) &&
    (value.customWeights === null || numbers(value.customWeights)) && typeof value.reviewed === "boolean" &&
    strings(value.summary) && strings(value.warnings) &&
    ["constraints", "activities"].includes(String(value.inputTab)) && ["calendar", "resources"].includes(String(value.view));
}

export function readLocalWorkspaces(): { store: WorkspaceStore; warning: string } {
  const empty: WorkspaceStore = { schema_version: 1, active_scenario: "life", workspaces: {} };
  try {
    const raw = localStorage.getItem(LOCAL_WORKSPACE_KEY);
    if (!raw) return { store: empty, warning: "" };
    const data: unknown = JSON.parse(raw);
    if (!record(data) || data.schema_version !== 1 || !scenario(data.active_scenario) || !record(data.workspaces)) {
      return { store: empty, warning: "本地保存的数据无法恢复，已打开预置方案。" };
    }
    const store: WorkspaceStore = { ...empty, active_scenario: data.active_scenario };
    let damaged = false;
    for (const s of Object.keys(SCENARIOS) as Scenario[]) {
      if (!Object.hasOwn(data.workspaces, s)) continue;
      const saved = data.workspaces[s];
      if (isLocalWorkspace(saved, s)) store.workspaces[s] = saved;
      else damaged = true;
    }
    return { store, warning: damaged ? "部分本地数据无法恢复，已忽略损坏的内容。" : "" };
  } catch {
    return { store: empty, warning: "无法读取本地保存，已打开预置方案。" };
  }
}

/** Backups are data, not executable configuration; validate again on the server before use. */
export function readWorkspaceBackup(raw: string): LocalWorkspace {
  if (raw.length > 2_000_000) throw new Error("备份文件不能超过 2 MB。");
  let data: unknown;
  try { data = JSON.parse(raw); } catch { throw new Error("文件不是有效的 JSON 备份。"); }
  if (record(data) && record(data.problem) && scenario(data.problem.scenario) && problem(data.problem, data.problem.scenario)) {
    const p = data.problem;
    // A plan export can restore editable data, but cannot establish approval or correctness.
    return { problem: p, result: null, previous: record(data.result) && assignments(data.result.assignments) ? data.result.assignments : [],
      previousProblem: p, input: "", appliedInput: "", mode: "balanced", customWeights: null,
      reviewed: false, summary: [], warnings: [], inputTab: "activities", view: "calendar" };
  }
  if (!record(data) || data.format !== "atlas-workspace" || data.version !== 1 ||
    !record(data.workspace) || !record(data.workspace.problem) ||
    !scenario(data.workspace.problem.scenario) ||
    !isLocalWorkspace(data.workspace, data.workspace.problem.scenario)) {
    throw new Error("请选择由“备份工作空间”下载的 ATLAS 文件，原有内容未改变。");
  }
  return data.workspace;
}

/** Stable comparison allows safe autosave even for old backups with differently ordered keys. */
export function workspaceKey(value: LocalWorkspace | undefined): string {
  const ordered = (item: unknown): unknown => Array.isArray(item) ? item.map(ordered) :
    record(item) ? Object.fromEntries(Object.keys(item).sort().map((key) => [key, ordered(item[key])])) : item;
  return value ? JSON.stringify(ordered(value)) : "";
}

export function writeLocalWorkspaces(store: WorkspaceStore): string {
  try {
    localStorage.setItem(LOCAL_WORKSPACE_KEY, JSON.stringify(store));
    return "";
  } catch {
    return "浏览器未能保存当前内容，请检查网站存储权限或可用空间，关闭前请备份输入。";
  }
}
