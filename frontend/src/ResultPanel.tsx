import {
  CalendarDays,
  Activity as ActivityIcon,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Clock3,
  Workflow,
  Sparkles,
  ArrowRight,
  Settings2,
  ChevronDown,
} from "lucide-react";
import { Calendar } from "./Calendar";
import { type Problem, type Result, type Assignment, DAYS } from "./types";
interface Props {
  problem: Problem | null;
  result: Result | null;
  busy: string;
  view: "calendar" | "resources";
  setView: (v: "calendar" | "resources") => void;
  summary: string[];
  exportPlan: (format: "json" | "xlsx" | "pdf") => void;
  repair: (id: string) => Promise<void>;
  setSelected: (v: Assignment | null) => void;
}
const PENALTIES: Record<string, { label: string; description: string }> = {
  goal: {
    label: "目标与偏好",
    description: "未安排可选活动及偏离时间偏好的惩罚",
  },
  compact: {
    label: "时间紧凑",
    description: "各资源每日占用跨度内的空闲时间，单位为半小时",
  },
  balance: {
    label: "负载均衡",
    description: "每日非睡眠任务量偏离周平均的绝对差",
  },
  robust: { label: "截止缓冲", description: "未给截止任务留足缓冲的惩罚" },
  lead: {
    label: "提前完成",
    description: "截止任务的开始时刻；仅在稳健档启用，越低表示越早完成",
  },
  regular: {
    label: "作息规律",
    description: "同名日常活动（如午餐、晚餐）每天时间不一致的程度",
  },
  stability: {
    label: "方案稳定",
    description: "已有任务的时间或教室发生变动的数量",
  },
};

export function ResultPanel({
  problem,
  result,
  busy,
  view,
  setView,
  summary,
  exportPlan,
  repair,
  setSelected,
}: Props) {
  const metric = result?.metrics;
  return (
    <section className="result-panel panel" aria-busy={!!busy}>
      <div className="result-heading">
        <div>
          <div className="result-title">
            <h2>{problem?.name ?? "我的一周"}</h2>
            <span className="sample-label">
              {result ? "已求解" : summary.length ? "待确认变更" : "待生成计划"}
            </span>
          </div>
          <p>
            {problem?.week_start.replaceAll("-", ".")} —{" "}
            {problem
              ? new Date(
                  new Date(`${problem.week_start}T12:00:00`).getTime() +
                    6 * 86400000,
                ).toLocaleDateString("zh-CN", {
                  month: "2-digit",
                  day: "2-digit",
                })
              : ""}
          </p>
        </div>
        <div className="result-actions">
          <div className="view-switch">
            <button
              aria-label="周日历"
              className={view === "calendar" ? "active" : ""}
              onClick={() => setView("calendar")}
            >
              <CalendarDays size={15} />
              <span>周日历</span>
            </button>
            <button
              aria-label="资源视图"
              className={view === "resources" ? "active" : ""}
              onClick={() => setView("resources")}
            >
              <ActivityIcon size={15} />
              <span>资源</span>
            </button>
          </div>
          <div className="export-group" role="group" aria-label="导出方案">
            <button
              title="导出 Excel（含完整中文课表）"
              aria-label="导出 Excel"
              className="icon-button"
              disabled={!result?.assignments.length}
              onClick={() => exportPlan("xlsx")}
            >
              <FileSpreadsheet size={17} />
            </button>
            <button
              title="导出 PDF（中文计划）"
              aria-label="导出 PDF"
              className="icon-button"
              disabled={!result?.assignments.length}
              onClick={() => exportPlan("pdf")}
            >
              <FileText size={17} />
            </button>
            <button
              title="下载当前计划 JSON"
              aria-label="下载计划 JSON"
              className="icon-button"
              disabled={!result?.assignments.length}
              onClick={() => exportPlan("json")}
            >
              <Download size={17} />
            </button>
          </div>
        </div>
      </div>
      <div
        className={`solver-strip ${["INFEASIBLE", "UNKNOWN"].includes(result?.status ?? "") ? "infeasible" : ""}`}
      >
        <div>
          {busy ? (
            <Loader2 size={14} className="spin" />
          ) : result?.assignments.length ? (
            <CheckCircle2 size={15} />
          ) : result?.status === "INFEASIBLE" ? (
            <AlertTriangle size={15} />
          ) : (
            <Clock3 size={15} />
          )}
          <strong>
            {busy ? busy : (result?.status ?? "等待确认")}
          </strong>
          {metric?.scheduled !== undefined && (
            <span>{metric.scheduled} 项活动已安排</span>
          )}
          {result?.objective?.stability_applicable && metric?.changed !== undefined && (
            <span className="change-count" title="与上一版相比，当前任务中移动或取消安排的原活动数量。新增和已删除任务不计入。">
              原活动调整 {metric.changed} 项
            </span>
          )}
        </div>
        <span>
          {result ? `${metric?.solve_time}s · CP-SAT` : "确认约束后开始优化"}
        </span>
      </div>
      {result && ["INFEASIBLE", "UNKNOWN"].includes(result.status) ? (
        <div className="conflict-view">
          <div className="conflict-illustration">
            <Workflow size={40} />
            <span>!</span>
          </div>
          <h2>
            {result.status === "INFEASIBLE"
              ? "有些要求，暂时无法同时满足。"
              : "本次求解在时限内没有得出可行解。"}
          </h2>
          <p>
            {result.status === "INFEASIBLE"
              ? "求解器已证明当前模型无解。你可以选择放宽一条限制，再重新优化。"
              : "这通常是任务规模较大或约束较紧导致超时，并不代表问题一定无解。下面给出经重求解验证的排查方向。"}
          </p>
          {result.conflicts.map((c, i) => (
            <article className="conflict-item" key={i}>
              <AlertTriangle size={17} />
              <div>
                <strong>{c.title}</strong>
                <p>{c.detail}</p>
                {c.constraint_ids.map((cid) => (
                  <span className="conflict-chip" key={cid}>
                    {problem?.constraints.find((x) => x.id === cid)?.label ??
                      cid}
                  </span>
                ))}
              </div>
            </article>
          ))}
          {result.repairs.length > 0 && (
            <div className="repair-list">
              <h3>
                <Sparkles size={16} />
                已验证的修复候选
              </h3>
              {result.repairs.map((r) => (
                <article key={r.constraint_id}>
                  <div>
                    <strong>{r.label}</strong>
                    <p>{r.detail}</p>
                  </div>
                  <button
                    disabled={!!busy}
                    className="secondary"
                    onClick={() => repair(r.constraint_id)}
                  >
                    应用并求解
                    <ArrowRight size={14} />
                  </button>
                </article>
              ))}
            </div>
          )}
        </div>
      ) : problem && view === "calendar" ? (
        <Calendar problem={problem} result={result} onSelect={setSelected} />
      ) : problem ? (
        <div className="resource-view">
          <h3>资源占用</h3>
          <p className="muted">
            按完整一周 168 小时 × 资源数量计算。教室座位数独立校验。
          </p>
          {problem.resources.map((r) => {
            const used =
              result?.assignments
                .filter((x) => {
                  const a = problem.activities.find(
                    (a) => a.id === x.activity_id,
                  );
                  return (
                    a &&
                    (a.resources.includes(r.id) ||
                      r.id in a.demands ||
                      x.room_id === r.id)
                  );
                })
                .reduce(
                  (s, x) =>
                    s +
                    ((x.end - x.start) / 2) *
                      (problem.activities.find((a) => a.id === x.activity_id)
                        ?.demands[r.id] ?? 1),
                  0,
                ) ?? 0;
            return (
              <div className="resource-row" key={r.id}>
                <div>
                  <strong>{r.name}</strong>
                  <small>
                    {r.type} · 并发容量 {r.capacity}
                    {r.seats ? ` · ${r.seats} 座` : ""}
                  </small>
                </div>
                <div className="resource-bar">
                  <span
                    style={{
                      width: `${Math.min(100, (used / (168 * r.capacity)) * 100)}%`,
                    }}
                  />
                </div>
                <strong>
                  {used} <small>小时</small>
                </strong>
              </div>
            );
          })}
          <h3 className="daily-title">每日任务负载</h3>
          <div className="bar-chart">
            {DAYS.map((d, i) => {
              const h = metric?.daily_hours?.[i] ?? 0;
              return (
                <div key={d}>
                  <span>{h}h</span>
                  <div>
                    <i
                      style={{
                        height: `${Math.max(2, (h / Math.max(1, ...(metric?.daily_hours ?? []))) * 120)}px`,
                      }}
                    />
                  </div>
                  <small>{d}</small>
                </div>
              );
            })}
          </div>
          <p className="muted">每日负载不计睡眠，数值来自当前实际求解结果。</p>
        </div>
      ) : null}
      {result?.objective && (
        <details className="objective-details">
          <summary>
            <Settings2 size={14} />
            <span>优化指标明细</span>
            <small>原始惩罚值 · 越低越好</small>
            <ChevronDown size={13} />
          </summary>
          <div>
            {Object.entries(PENALTIES).map(([key, p]) => (
              <section title={p.description} key={key}>
                <span>{p.label}</span>
                <strong>
                  {key === "stability" &&
                  !result.objective?.stability_applicable
                    ? "—"
                    : result.objective?.penalties[key]}
                </strong>
                <small>权重 {result.objective?.weights[key]}</small>
              </section>
            ))}
          </div>
          <p>
            目标值 {result.objective.value} · 最佳界{" "}
            {result.objective.best_bound} · {metric?.variables} 个变量 /{" "}
            {metric?.model_constraints} 条模型约束
          </p>
        </details>
      )}
    </section>
  );
}
