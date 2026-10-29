import { InputPanel } from "./InputPanel";
import { ResultPanel } from "./ResultPanel";
import { BusyStatus } from "./BusyStatus";
import { BrandMark } from "./BrandMark";
import { PlanChanges, type PlanBaseline } from "./PlanChanges";
import { ResourceManager } from "./ResourceManager";
import { useEffect, useRef, useState } from "react";
import {
  Activity as ActivityIcon,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  Clock3,
  Factory,
  FlaskConical,
  GraduationCap,
  History,
  Layers3,
  LayoutDashboard,
  Loader2,
  LockKeyhole,
  PanelLeftClose,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Upload,
  UserRound,
  Users,
  Workflow,
  X,
  Zap,
  AlertTriangle,
  Download,
  CheckCircle2,
} from "lucide-react";
import { api, ApiError, exportPlan as exportPlanRequest, upload } from "./api";
import { Calendar } from "./Calendar";
import { occurrenceNames } from "./occurrenceNames";
import { ActivityEditor, ConstraintEditor, Dialog } from "./Editors";
import { readLocalWorkspaces, writeLocalWorkspaces, readWorkspaceBackup, workspaceKey, LOCAL_WORKSPACE_KEY, type LocalWorkspace } from "./localWorkspace";
import { readLocalHistory, saveLocalRun, deleteLocalRun, type LocalRun } from "./localHistory";
import { describeConstraint } from "./constraintDescription";
import { RepeatActivity } from "./RepeatActivity";
import "./styles/product-polish.css";
import {
  type Activity,
  type Assignment,
  type Constraint,
  type Explanation,
  type Mode,
  type Problem,
  type Result,
  type Scenario,
  type WeightsMeta,
  CATEGORIES,
  DAYS,
  SCENARIOS,
  clock,
  MAX_INPUT_CHARS,
} from "./types";

const SCENARIO_ICONS: Record<Scenario, typeof CalendarDays> = {
  life: CalendarDays,
  academic: GraduationCap,
  lab: FlaskConical,
  meeting: Users,
  production: Factory,
};
type ReplacementAction = "preset" | "blank" | "clear-all" | "clear-constraints" | "clear-activities";
type ParseMode = "keep" | "replace";

function mondayOf(date: string): string {
  const day = new Date(`${date}T12:00:00Z`);
  day.setUTCDate(day.getUTCDate() - (day.getUTCDay() + 6) % 7);
  return day.toISOString().slice(0, 10);
}
function modelChanges(before: Problem, after: Problem): string {
  const count = (key: "activities" | "constraints" | "resources") => {
    const old = new Map(before[key].map((item) => [item.id, JSON.stringify(item)]));
    const next = new Map(after[key].map((item) => [item.id, JSON.stringify(item)]));
    const added = [...next.keys()].filter((id) => !old.has(id)).length;
    const removed = [...old.keys()].filter((id) => !next.has(id)).length;
    const changed = [...next].filter(([id, data]) => old.has(id) && old.get(id) !== data).length;
    return `${key === "activities" ? "活动" : key === "constraints" ? "约束" : "资源"}：新增 ${added} / 修改 ${changed} / 移除 ${removed}`;
  };
  return [count("activities"), count("constraints"), count("resources")].join("；");
}

function unmentionedNewActivities(before: Problem, after: Problem, input: string): string[] {
  const normalize = (value: string) => value.toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  const existing = new Map(before.activities.map((activity) => [activity.id, normalize(activity.name)]));
  const source = normalize(input);
  const names = after.activities.filter((activity) => existing.get(activity.id) !== normalize(activity.name)).filter((activity) => {
    const base = activity.name.replace(/[（(][^）)]*[）)]/g, "")
      .replace(/(?:周[一二三四五六日天]|第?[一二三四五六七八九十0-9]+(?:次|节|课时)?)\s*$/, "").trim();
    const key = normalize(base);
    return key.length > 0 && !source.includes(key);
  }).map((activity) => activity.name);
  return [...new Set(names)];
}

export default function App() {
  const [local] = useState(readLocalWorkspaces);
  const initial = local.store.workspaces[local.store.active_scenario];
  const localStore = useRef(local.store);
  const [localReady, setLocalReady] = useState(!!initial);
  const [saveWarning, setSaveWarning] = useState("");
  const [historyWarning, setHistoryWarning] = useState("");
  const [locallySaved, setLocallySaved] = useState(!!initial);
  const knownCopies = useRef(Object.fromEntries(Object.entries(local.store.workspaces).map(([s, saved]) => [s, workspaceKey(saved)])));
  const unsavedWorkspaces = useRef<Partial<Record<Scenario, LocalWorkspace>>>({});
  const [unsavedScenes, setUnsavedScenes] = useState<Scenario[]>([]);
  const [storageConflict, setStorageConflict] = useState<{ latest: LocalWorkspace | null } | null>(null);
  const [onboarding, setOnboarding] = useState(!initial);
  const [repeatActivity, setRepeatActivity] = useState<Activity | null>(null);
  const [appliedInput, setAppliedInput] = useState(initial?.appliedInput ?? (initial?.input === SCENARIOS[local.store.active_scenario].input ? initial.input : ""));
  const modelEpoch = useRef(0);
  const validationCounter = useRef(0);
  const [connectionFailed, setConnectionFailed] = useState(false);
  const [retryAction, setRetryAction] = useState<"parse" | "solve" | null>(null);
  const [pendingText, setPendingText] = useState<{ kind: string; text: string; chars: number; filename: string } | null>(null);
  const [scenarioHint, setScenarioHint] = useState<{ target: Scenario; input: string; mode: ParseMode } | null>(null);
  const [chooseParseMode, setChooseParseMode] = useState(false);
  const lastParseMode = useRef<ParseMode>("keep");
  const [weightsFailed, setWeightsFailed] = useState(false);
  const explanationCache = useRef(new Map<string, Explanation>());
  const selectedKey = useRef("");
  const [problem, setProblem] = useState<Problem | null>(initial?.problem ?? null),
    [result, setResult] = useState<Result | null>(initial?.result ?? null);
  const [scenario, setScenario] = useState<Scenario>(local.store.active_scenario),
    [mode, setMode] = useState<Mode>(initial?.mode ?? "balanced");
  // Custom weight profile (MASTER_SPEC §15). null means "use the preset as-is";
  // the slider panel populates it when the user switches to 自定义.
  const [customWeights, setCustomWeights] = useState<Record<string, number> | null>(
      initial?.customWeights ?? null,
    ),
    [weightsMeta, setWeightsMeta] = useState<WeightsMeta | null>(null);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [input, setInput] = useState(initial?.input ?? SCENARIOS[local.store.active_scenario].input),
    [provider, setProvider] = useState("demo");
  const [version, setVersion] = useState("");
  const [modelConfigured, setModelConfigured] = useState(true);
  const [connected, setConnected] = useState(false);
  const [reviewed, setReviewed] = useState(initial?.reviewed ?? true),
    [summary, setSummary] = useState<string[]>(initial?.summary ?? []),
    [warnings, setWarnings] = useState<string[]>(initial?.warnings ?? []);
  const [inputTab, setInputTab] = useState<"constraints" | "activities">(
      initial?.inputTab ?? "constraints",
    ),
    [view, setView] = useState<"calendar" | "resources">(initial?.view ?? "calendar");
  const [page, setPage] = useState<"workspace" | "history">("workspace"),
    [history, setHistory] = useState<LocalRun[]>([]);
  const [resourcesOpen, setResourcesOpen] = useState(false);
  const [confirmation, setConfirmation] = useState<ReplacementAction | LocalWorkspace | null>(null);
  type UndoEntry = { restore: LocalWorkspace; removeScenario?: Scenario };
  const [undoStack, setUndoStack] = useState<UndoEntry[]>([]);
  const undo = undoStack.at(-1) ?? null;
  function setUndo(entry: UndoEntry | null) {
    setUndoStack((current) => !entry ? [] : current.at(-1)?.restore === entry.restore && current.at(-1)?.removeScenario === entry.removeScenario ? current : [...current, entry].slice(-10));
  }
  const [baseline, setBaseline] = useState<PlanBaseline | null>(null);
  const [constraintEditor, setConstraintEditor] = useState<
      Constraint | "new" | null
    >(null),
    [addingActivity, setAddingActivity] = useState(false),
    [editingActivity, setEditingActivity] = useState<Activity | null>(null),
    [selected, setSelected] = useState<Assignment | null>(null),
    [explanation, setExplanation] = useState<Explanation | null>(null),
    [explainBusy, setExplainBusy] = useState(false),
    [help, setHelp] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null),
    backupFileRef = useRef<HTMLInputElement>(null),
    textFileRef = useRef<HTMLInputElement>(null),
    previous = useRef<Assignment[]>(initial?.previous ?? []),
    previousProblem = useRef<Problem | null>(initial?.previousProblem ?? initial?.problem ?? null),
    loadCounter = useRef(0);

  const snapshot = useRef<LocalWorkspace | null>(null);
  const canSave = useRef(false);
  snapshot.current = problem && problem.scenario === scenario ? {
    problem, result, previous: previous.current, input, appliedInput, mode, customWeights,
    reviewed, summary, warnings, inputTab, view,
    ...(previousProblem.current ? { previousProblem: previousProblem.current } : {}),
  } : null;
  canSave.current = localReady;
  selectedKey.current = result && selected ? `${result.run_id}:${selected.activity_id}` : "";

  function updateUnsavedScenes() {
    const scenes = Object.keys(unsavedWorkspaces.current) as Scenario[];
    setUnsavedScenes((current) => current.join() === scenes.join() ? current : scenes);
  }
  function saveLocal(): boolean {
    const current = snapshot.current;
    if (!canSave.current || !current) return true;
    const s = current.problem.scenario;
    // Another tab may have edited a different scenario since this tab opened.
    // Only replace this workspace; keep the latest stored copies of the others.
    const latestStore = readLocalWorkspaces().store;
    const latest = latestStore.workspaces;
    const savedKey = workspaceKey(latest[s]);
    const knownKey = knownCopies.current[s] ?? "";
    if (savedKey !== knownKey && savedKey !== workspaceKey(current)) {
      setStorageConflict({ latest: latest[s] ?? null });
      setLocallySaved(false);
      setSaveWarning("另一个标签页更新了此计划，当前编辑尚未覆盖它。请选择保留哪一份，或先备份当前内容。");
      return false;
    }
    if (savedKey === workspaceKey(current)) {
      knownCopies.current[s] = savedKey;
      localStore.current = { ...latestStore, active_scenario: s };
      const warning = latestStore.active_scenario !== s ? writeLocalWorkspaces(localStore.current) : "";
      delete unsavedWorkspaces.current[s]; updateUnsavedScenes();
      setSaveWarning(warning); setLocallySaved(!warning); return !warning;
    }
    localStore.current = {
      ...latestStore, active_scenario: s,
      workspaces: { ...latest, [s]: current },
    };
    const warning = writeLocalWorkspaces(localStore.current);
    if (!warning) { knownCopies.current[s] = workspaceKey(current); delete unsavedWorkspaces.current[s]; }
    else unsavedWorkspaces.current[s] = current;
    updateUnsavedScenes();
    setSaveWarning(warning);
    setLocallySaved(!warning);
    return !warning;
  }
  function restoreLocal(saved: LocalWorkspace) {
    modelEpoch.current += 1;
    setProblem(saved.problem);
    setResult(saved.result);
    previous.current = saved.previous;
    previousProblem.current = saved.previousProblem ?? saved.problem;
    setScenario(saved.problem.scenario);
    setInput(saved.input);
    setAppliedInput(saved.appliedInput ?? (saved.input === SCENARIOS[saved.problem.scenario].input ? saved.input : ""));
    setMode(saved.mode);
    setCustomWeights(saved.customWeights);
    setReviewed(saved.reviewed);
    setSummary(saved.summary);
    setWarnings(saved.warnings);
    setInputTab(saved.inputTab);
    setView(saved.view);
    setLocalReady(true);
    setBaseline(null);
  }
  function resolveStorageConflict(useLatest: boolean) {
    if (!snapshot.current) return;
    const s = snapshot.current.problem.scenario;
    const latest = readLocalWorkspaces().store.workspaces[s];
    knownCopies.current[s] = workspaceKey(latest);
    setStorageConflict(null); setSaveWarning("");
    if (useLatest && latest) { restoreLocal(latest); setNotice("已打开另一个标签页保存的最新内容。"); }
    else { const saved = saveLocal(); setNotice(saved ? "已用当前内容保存。另一个标签页会收到更新提示。" : "当前编辑仍保留在页面中，尚未写入浏览器，请先下载备份。"); }
  }
  function rememberRun(p: Problem, r: Result, selectedMode: Mode = mode, weights = customWeights) {
    const saved = snapshot.current;
    if (!saved) return;
    const warning = saveLocalRun({ ...saved, problem: p, result: r, previous: r.assignments.length ? r.assignments : saved.previous,
      previousProblem: r.assignments.length ? p : saved.previousProblem ?? saved.problem,
      mode: selectedMode, customWeights: weights, reviewed: true });
    setHistoryWarning(warning);
  }
  function rememberReplacement(target: Scenario) {
    const current = snapshot.current;
    const old = target === scenario ? current : readLocalWorkspaces().store.workspaces[target];
    if (old) setUndo({ restore: old });
    else if (current) setUndo({ restore: current, removeScenario: target });
  }
  function undoChange() {
    if (!undo) return;
    saveLocal();
    if (undo.removeScenario) {
      const store = readLocalWorkspaces().store;
      if (workspaceKey(store.workspaces[undo.removeScenario]) !== (knownCopies.current[undo.removeScenario] ?? "")) {
        setError("另一标签页已更新这个场景，请先处理更新提示；本次撤销没有删除任何内容。"); return;
      }
      delete store.workspaces[undo.removeScenario];
      delete unsavedWorkspaces.current[undo.removeScenario]; updateUnsavedScenes();
      store.active_scenario = undo.restore.problem.scenario;
      localStore.current = store;
      setSaveWarning(writeLocalWorkspaces(store));
    }
    restoreLocal(undo.restore); setUndoStack((current) => current.slice(0, -1)); setError("");
    setNotice("已撤销上一次内容修改。");
  }
  // Save edits, including unparsed text and unconfirmed drafts. Do not save a
  // half-switched template or overwrite another scenario's workspace.
  useEffect(() => { saveLocal(); }, [localReady, scenario, problem, result, input, mode,
    customWeights, reviewed, summary, warnings, inputTab, view, appliedInput]);
  useEffect(() => {
    const flush = () => saveLocal();
    const hidden = () => { if (document.visibilityState === "hidden") flush(); };
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", hidden);
    return () => {
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, []);
  useEffect(() => {
    const protectUnsaved = (event: BeforeUnloadEvent) => {
      if (!Object.keys(unsavedWorkspaces.current).length) return;
      event.preventDefault(); event.returnValue = "";
    };
    window.addEventListener("beforeunload", protectUnsaved);
    return () => window.removeEventListener("beforeunload", protectUnsaved);
  }, []);
  useEffect(() => {
    const changed = (event: StorageEvent) => {
      if ((event.key !== LOCAL_WORKSPACE_KEY && event.key !== null) || !snapshot.current) return;
      const s = snapshot.current.problem.scenario;
      const latest = readLocalWorkspaces().store.workspaces[s];
      if (workspaceKey(latest) !== (knownCopies.current[s] ?? "") && workspaceKey(latest) !== workspaceKey(snapshot.current)) {
        setStorageConflict({ latest: latest ?? null }); setLocallySaved(false);
        setSaveWarning("另一个标签页更新了此计划，当前编辑尚未覆盖它。请选择保留哪一份，或先备份当前内容。");
      }
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, []);

  async function load(s: Scenario, reset = false, carriedInput?: string) {
    if (storageConflict) { setError("请先处理多标签页更新提示，再切换场景；可先下载当前备份。"); return; }
    saveLocal();
    modelEpoch.current += 1;
    setStorageConflict(null); setSaveWarning("");
    setConstraintEditor(null); setAddingActivity(false); setEditingActivity(null); setResourcesOpen(false);
    if (!reset) setUndo(null);
    const version = ++loadCounter.current;
    setSelected(null);
    setPage("workspace");
    setError("");
    const latest = readLocalWorkspaces().store;
    localStore.current = latest;
    const memory = !reset && unsavedWorkspaces.current[s];
    const saved = !reset && (memory || latest.workspaces[s]);
    if (!memory) knownCopies.current[s] = workspaceKey(latest.workspaces[s]);
    if (saved) {
      restoreLocal(saved);
      if (carriedInput !== undefined) {
        setUndo({ restore: saved }); setInput(carriedInput); setAppliedInput(""); setReviewed(false); setInputTab("constraints");
        setNotice("已切换并带入需求，已有任务仍保留。请点击“识别约束”，原输入可撤销恢复。");
        return;
      }
      setNotice(memory ? "已恢复本次打开期间的未保存草稿，请先备份，关闭页面后内存草稿会丢失。" : "已恢复此浏览器上次保存的内容。");
      return;
    }
    setLocalReady(false);
    setBusy(reset ? "正在生成预置方案" : "正在准备工作空间");
    setNotice("");
    try {
      const p = await api<Problem>(`/templates/${s}`);
      if (version !== loadCounter.current) return;
      p.week_start = mondayOf(new Date().toLocaleDateString("sv-SE"));
      if (!reset) {
        restoreLocal({ problem: { ...p, name: `我的${SCENARIOS[s].title}`, activities: [], constraints: [] },
          result: null, previous: [], input: carriedInput ?? "", appliedInput: "", mode: "balanced", customWeights: null,
          reviewed: false, summary: [], warnings: [], inputTab: "activities", view: "calendar" });
        setNotice(carriedInput !== undefined ? "已切换并带入需求。请点击“识别约束”，再检查生成的任务。" : "从自己的任务开始，或点击“恢复预置方案”体验完整示例。");
        return;
      }
      restoreLocal({
        problem: p, result: null, previous: [], input: SCENARIOS[s].input,
        appliedInput: SCENARIOS[s].input,
        mode: "balanced", customWeights: null, reviewed: true,
        summary: [], warnings: [], inputTab: "constraints", view: "calendar",
      });
      const r = await api<Result>("/solve", {
        problem: p,
        reviewed: true,
        mode: "balanced",
      });
      if (version !== loadCounter.current) return;
      setMode("balanced");
      setResult(r);
      previous.current = r.assignments;
      previousProblem.current = p;
      // Template loading updates React state asynchronously, so use its actual data.
      const warning = saveLocalRun({ problem: p, result: r, previous: r.assignments,
        input: SCENARIOS[s].input, mode: "balanced", customWeights: null,
        reviewed: true, summary: [], warnings: [], inputTab: "constraints", view: "calendar" });
      setHistoryWarning(warning);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (version === loadCounter.current) { setBusy(""); setLocalReady(true); }
    }
  }
  useEffect(() => {
    api<{ provider: string; version: string; model_configured?: boolean }>("/health")
      .then((x) => { setProvider(x.provider); setModelConfigured(x.model_configured !== false); setVersion(x.version); setConnected(true); })
      .catch(() => { setConnectionFailed(true); setError("暂时无法连接后端，请稍后点击重试连接。"); });
    // Weight dimensions come from the solver so the UI never hard-codes them.
    api<WeightsMeta>("/weights")
      .then((x) => setWeightsMeta(x))
      .catch(() => { setWeightsMeta(null); setWeightsFailed(true); });
    if (initial) setNotice(local.warning || "已恢复此浏览器上次保存的内容。");
    else void load(local.store.active_scenario).then(() => {
      if (local.warning) setNotice(local.warning);
    });
  }, []);
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(() => {
    if (
      !selected ||
      !problem ||
      !result ||
      !["FEASIBLE", "OPTIMAL"].includes(result.status)
    ) {
      setExplanation(null);
      setExplainBusy(false);
      return;
    }
    let cancelled = false;
    const cacheKey = `${result.run_id}:${selected.activity_id}`;
    const cached = explanationCache.current.get(cacheKey);
    if (cached) { setExplanation(cached); setExplainBusy(false); return; }
    setExplainBusy(true);
    setExplanation(null);
    api<Explanation>("/explain", {
      problem,
      assignments: result.assignments,
      activity_id: selected.activity_id,
      previous: [],
      include_narrative: false,
    })
      .then((data) => {
        if (!cancelled) { setExplanation(data); explanationCache.current.set(cacheKey, data); }
      })
      .catch(() => {
        if (!cancelled) setExplanation(null);
      })
      .finally(() => {
        if (!cancelled) setExplainBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, problem, result]);
  function draft(p: Problem | ((current: Problem | null) => Problem | null)) {
    modelEpoch.current += 1;
    if (snapshot.current) setUndo({ restore: snapshot.current });
    setProblem(p);
    setResult(null);
    setReviewed(false);
    setError("");
    setRetryAction(null);
    setSelected(null);
    setBaseline(null);
  }
  async function narrateSelected() {
    if (!selected || !problem || !result || explainBusy) return;
    const cacheKey = `${result.run_id}:${selected.activity_id}`;
    const epoch = modelEpoch.current;
    setExplainBusy(true);
    try {
      const data = await api<Explanation>("/explain", { problem, assignments: result.assignments, activity_id: selected.activity_id, previous: previous.current });
      explanationCache.current.set(cacheKey, data);
      if (epoch === modelEpoch.current && selectedKey.current === cacheKey) setExplanation(data);
      if (!data.narrative) setNotice("AI 说明暂不可用，已保留真实约束与求解依据。");
    } catch { setNotice("AI 说明暂不可用，当前计划与求解依据仍可查看。"); }
    finally { if (selectedKey.current === cacheKey) setExplainBusy(false); }
  }
  async function validateDraft(p: Problem): Promise<boolean> {
    const request = ++validationCounter.current;
    const epoch = modelEpoch.current;
    setBusy("正在保存修改");
    try {
      await api("/constraints/validate", p);
      if (request !== validationCounter.current || epoch !== modelEpoch.current) return false;
      draft(p); return true;
    } finally { if (request === validationCounter.current) setBusy(""); }
  }
  const inputPending = !!input.trim() && input !== appliedInput;
  function clearInput() {
    if (snapshot.current) setUndo({ restore: snapshot.current });
    setInput("");
  }
  async function reconnect() {
    setConnectionFailed(false);
    try {
      const [health, weights] = await Promise.all([api<{ provider: string; version: string; model_configured?: boolean }>("/health"), api<WeightsMeta>("/weights")]);
      setProvider(health.provider); setModelConfigured(health.model_configured !== false); setVersion(health.version); setWeightsMeta(weights);
      setConnected(true); setWeightsFailed(false); setError("");
    } catch (e) { setConnected(false); setConnectionFailed(true); setError((e as Error).message); }
  }
  async function optimize(
    selectedMode: Mode = mode,
    fresh = false,
    // Explicit weight profile for this call. React state updates are async, so a
    // caller that has just changed the profile (e.g. a preset switch clearing the
    // custom weights) must pass it here instead of relying on the closure.
    weightsOverride?: Record<string, number> | null,
  ) {
    if (storageConflict) { setError("请先处理另一个标签页的更新提示，再生成计划。"); return; }
    if (!problem || !reviewed || !problem.activities.length || inputPending || busy) return;
    const epoch = modelEpoch.current;
    const effectiveWeights =
      weightsOverride === undefined ? customWeights : weightsOverride;
    setBusy("正在组合优化");
    setRetryAction(null);
    setError("");
    setSelected(null);
    try {
      const before = { problem: previousProblem.current ?? problem, assignments: fresh ? [] : [...previous.current] };
      const r = await api<Result>("/solve", {
        problem,
        reviewed,
        mode: selectedMode,
        previous: fresh ? [] : previous.current,
        ...(effectiveWeights ? { weights: effectiveWeights } : {}),
      });
      if (epoch !== modelEpoch.current) return;
      setResult(r);
      setBaseline(before);
      if (window.matchMedia("(max-width: 760px)").matches) requestAnimationFrame(() => document.querySelector(".result-column")?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }));
      rememberRun(problem, r, selectedMode, effectiveWeights);
      if (r.assignments.length) { previous.current = r.assignments; previousProblem.current = problem; }
      if (r.status === "INFEASIBLE")
        setNotice("检测到约束冲突，已生成诊断结果。");
      else if (r.status === "UNKNOWN")
        setNotice("求解达到时限，已给出可诊断的方向与放宽候选。");
      else if (!["FEASIBLE", "OPTIMAL"].includes(r.status))
        setError("限时内未获得合法解，请减少任务或放宽时间域后重试。");
      else setNotice(`已生成合法计划 · ${r.assignments.length} 项活动`);
    } catch (e) {
      setError((e as Error).message);
      setRetryAction("solve");
    } finally {
      setBusy("");
    }
  }
  async function startParse() {
    if (!problem || busy || !input.trim()) return;
    if (problem.activities.length || problem.constraints.length) { setChooseParseMode(true); return; }
    await parse("keep");
  }
  async function parse(parseMode: ParseMode = "keep", allowScenarioMismatch = false) {
    if (!problem || busy) return;
    lastParseMode.current = parseMode;
    const epoch = modelEpoch.current;
    let splitAt = Math.min(input.length, MAX_INPUT_CHARS);
    if (input.length > MAX_INPUT_CHARS) {
      const newline = input.lastIndexOf("\n", splitAt - 1);
      if (newline > MAX_INPUT_CHARS / 2) splitAt = newline + 1;
    }
    if (splitAt < input.length && /[\uD800-\uDBFF]/.test(input[splitAt - 1])) splitAt -= 1;
    const segment = input.slice(0, splitAt);
    const remainder = input.slice(splitAt);
    setBusy("正在识别约束");
    setRetryAction(null);
    setError("");
    try {
      const data = await api<{
        problem: Problem;
        summary: string[];
        warnings: string[];
        provider: string;
      }>("/constraints/parse", { problem: parseMode === "replace" ? { ...problem, activities: [], constraints: [] } : problem,
        text: segment, ...(allowScenarioMismatch ? { allow_scenario_mismatch: true } : {}) });
      if (epoch !== modelEpoch.current) return;
      if (parseMode === "replace" && (problem.activities.length || problem.constraints.length) && !data.problem.activities.length)
        throw new Error("没有识别出活动，原计划未改变。请补充具体活动后重试；如需清空，请使用“清空当前内容”。");
      const changes = modelChanges(problem, data.problem);
      const namesToCheck = unmentionedNewActivities(parseMode === "replace" ? { ...problem, activities: [] } : problem, data.problem, segment);
      draft(data.problem);
      if (parseMode === "replace") { previous.current = []; previousProblem.current = data.problem; }
      setAppliedInput(segment);
      if (remainder.trim()) { setInput(remainder); setAppliedInput(""); }
      setSummary([parseMode === "replace" ? "已仅按本次描述建立任务；原计划可通过撤销恢复。" :
        problem.activities.length || problem.constraints.length ? "已保留并更新现有计划中的任务。" : "已从本次描述识别任务。",
        changes, ...(remainder.trim() ? [`本段已识别 ${segment.length} 字，剩余 ${remainder.length} 字仍在输入框中，请继续识别。`] : []), ...data.summary]);
      setWarnings([...data.warnings, ...(namesToCheck.length ? [`以下新增或改名活动的名称未直接出现在原文中，可能是对原文的归纳，请核对：${namesToCheck.slice(0, 8).join("、")}${namesToCheck.length > 8 ? ` 等 ${namesToCheck.length} 项` : ""}。`] : [])]);
      setProvider(data.provider);
      setInputTab("activities");
      setNotice("请检查全部活动和约束，确认后再生成计划。");
    } catch (e) {
      if (epoch !== modelEpoch.current) return;
      if (e instanceof ApiError && e.code === "scenario_mismatch" && e.suggestedScenario && Object.hasOwn(SCENARIOS, e.suggestedScenario)) {
        setScenarioHint({ target: e.suggestedScenario as Scenario, input, mode: parseMode });
        setRetryAction(null); return;
      }
      setError((e as Error).message);
      setRetryAction("parse");
    } finally {
      setBusy("");
    }
  }
  async function importFile(file: File) {
    if (!problem) return;
    const epoch = modelEpoch.current;
    setBusy("正在读取文件");
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("problem_json", JSON.stringify(problem));
      const data = await upload<{ problem: Problem; summary: string[]; duplicate_candidates?: number; warnings?: string[] }>("/import", form);
      if (epoch !== modelEpoch.current) return;
      draft(data.problem);
      setSummary([modelChanges(problem, data.problem), "文件中的活动已追加到当前计划，原有活动已保留。", ...data.summary]);
      setWarnings(data.warnings ?? (data.duplicate_candidates ? [`发现 ${data.duplicate_candidates} 行与已有活动可能重复，请检查后删除不需要的条目。`] : []));
      setNotice("已追加导入，请检查并确认新活动。");
      setInputTab("activities");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
      if (fileRef.current) fileRef.current.value = "";
    }
  }
  async function importText(file: File) {
    if (!problem) return;
    setBusy("正在读取文本");
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await upload<{ kind: string; text: string; chars: number }>("/import/text", form);
      setPendingText({ ...data, filename: file.name });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
      if (textFileRef.current) textFileRef.current.value = "";
    }
  }
  function applyTextImport(append: boolean) {
    if (!pendingText) return;
    if (snapshot.current) setUndo({ restore: snapshot.current });
    setInput(append && input.trim() ? `${input.trimEnd()}\n\n${pendingText.text}` : pendingText.text);
    setAppliedInput(""); setInputTab("constraints"); setPendingText(null); setRetryAction(null);
    setNotice("文字已放入输入框，尚未修改任务。点击识别约束后再确认；此操作可撤销。");
  }
  async function repair(constraint_id: string) {
    if (!problem) return;
    setBusy("正在验证并应用修复");
    setError("");
    try {
      const data = await api<{ problem: Problem; result: Result }>("/repair", {
        problem,
        reviewed: true,
        mode,
        ...(customWeights ? { weights: customWeights } : {}),
        previous: previous.current,
        constraint_id,
      });
      if (snapshot.current) setUndo({ restore: snapshot.current });
      modelEpoch.current += 1;
      setProblem(data.problem);
      setResult(data.result);
      setBaseline({ problem: previousProblem.current ?? problem, assignments: [...previous.current] });
      rememberRun(data.problem, data.result);
      setReviewed(true);
      if (data.result.assignments.length) {
        previous.current = data.result.assignments;
        previousProblem.current = data.problem;
      }
      setNotice("已应用你选择的约束放宽方案并重新求解。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function openHistory() {
    setError("");
    saveLocal();
    setHistory(readLocalHistory());
    setPage("history");
  }
  function backupWorkspace() {
    if (!snapshot.current) return;
    const blob = new Blob([JSON.stringify({ format: "optiday-workspace", version: 1,
      saved_at: new Date().toISOString(), workspace: snapshot.current }, null, 2)], { type: "application/json" });
    if (blob.size > 2_000_000) { setError("当前备份超过 2 MB。请先在输入框下方下载原文，再精简输入进行备份。原有内容仍保留。"); return; }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url;
    a.download = `optiday-workspace-${scenario}-${problem?.week_start}.json`; a.click();
    URL.revokeObjectURL(url);
    setNotice("已下载工作空间备份，可在另一台电脑恢复。");
  }
  function downloadTemplate() {
    if (!problem) return;
    const primary = problem.resources.find((r) => r.type === (scenario === "academic" ? "class" : scenario === "production" ? "machine" : scenario === "lab" ? "team" : "person")) ?? problem.resources[0];
    const csv = (value: string) => `"${value.replaceAll('"', '""')}"`;
    const rows = ["name,duration_minutes,category,resources,day,start",
      ["我的新活动", "60", scenario === "academic" ? "course" : scenario === "lab" ? "experiment" : scenario === "production" ? "operation" : scenario === "meeting" ? "meeting" : "study", primary?.id ?? "", "1", "09:00"].map(csv).join(",")];
    const url = URL.createObjectURL(new Blob(["\uFEFF" + rows.join("\n")], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `optiday-${scenario}-template.csv`; anchor.click(); URL.revokeObjectURL(url);
    setNotice("模板已包含当前资源 ID。resources 列也可填资源名称，多个资源用 | 分隔；day 为 1–7，start 留空表示灵活安排。导入会追加活动。");
  }
  async function importBackup(file: File) {
    setError(""); setBusy("正在检查备份");
    try {
      if (file.size > 2_000_000) throw new Error("备份文件不能超过 2 MB。");
      const saved = readWorkspaceBackup(await file.text());
      await api("/constraints/validate", saved.problem);
      setConfirmation(saved);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(""); if (backupFileRef.current) backupFileRef.current.value = ""; }
  }
  async function confirmReplacement() {
    if (!confirmation || !problem) return;
    const action = confirmation; setConfirmation(null);
    rememberReplacement(typeof action === "string" ? scenario : action.problem.scenario);
    if (action === "preset") { await load(scenario, true); return; }
    saveLocal(); setPage("workspace"); setSelected(null); setError("");
    if (action === "clear-all" || action === "clear-constraints" || action === "clear-activities") {
      const saved = snapshot.current;
      if (!saved) return;
      const clearingActivities = action !== "clear-constraints";
      const resourceTargets = new Set(["*", ...problem.resources.map((r) => r.id)]);
      const remainingConstraints = action === "clear-activities" ? problem.constraints.filter((c) =>
        resourceTargets.has(c.target) && c.other === null &&
        !["fixed_time", "precedence", "min_gap", "consecutive"].includes(c.type)) : [];
      restoreLocal({ ...saved,
        problem: { ...problem, activities: clearingActivities ? [] : problem.activities, constraints: remainingConstraints },
        input: action === "clear-all" ? "" : saved.input,
        appliedInput: action === "clear-all" ? "" : saved.appliedInput,
        result: null, previous: clearingActivities ? [] : saved.previous,
        ...(clearingActivities ? { previousProblem: { ...problem, activities: [], constraints: remainingConstraints } } : {}),
        reviewed: false, summary: [], warnings: [],
      });
      setNotice(action === "clear-all" ? "已清空当前输入、活动和约束，可撤销恢复。" :
        action === "clear-constraints" ? "已清空约束，活动与输入已保留，可撤销恢复。" : "已清空活动及关联约束，可撤销恢复。");
    } else if (action === "blank") {
      restoreLocal({ problem: { ...problem, name: `我的${SCENARIOS[scenario].title}`,
        week_start: mondayOf(new Date().toLocaleDateString("sv-SE")), activities: [], constraints: [] },
        result: null, previous: [], input: "", appliedInput: "", mode: "balanced", customWeights: null,
        reviewed: false, summary: [], warnings: [], inputTab: "activities", view: "calendar" });
      setNotice("已新建自己的计划。添加活动或描述需求，然后确认并生成安排。");
    } else {
      // A downloaded JSON cannot establish solver correctness or user approval.
      restoreLocal({ ...action, result: null, reviewed: false,
        previous: action.result?.assignments.length ? action.result.assignments : action.previous });
      setSummary(["已恢复备份中的任务与约束，请检查后确认并重新求解。"]);
      setNotice("备份已恢复；确认后重新生成合法计划。");
    }
  }
  async function changeWeek(value: string) {
    if (!problem || !value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return;
    const next = mondayOf(value);
    if (next === problem.week_start) return;
    const p = { ...problem, week_start: next };
    try { if (await validateDraft(p)) setNotice("已切换到所选日期所在周，请确认并重新生成计划。"); }
    catch (e) { setError((e as Error).message); }
  }
  function deleteConstraint(c: Constraint) {
    if (!problem) return;
    draft({
      ...problem,
      constraints: problem.constraints.filter((x) => x.id !== c.id),
    });
  }
  function deleteActivity(a: Activity) {
    // Group deletions are batched by React: apply each removal to the latest draft.
    draft((current) => {
      if (!current) return current;
      let activities = current.activities.filter((x) => x.id !== a.id);
      const groups = new Map<string, Activity[]>();
      activities.forEach((x) => { if (x.group) groups.set(x.group, [...(groups.get(x.group) ?? []), x]); });
      groups.forEach((items) => items.sort((x, y) => x.op_index - y.op_index));
      activities = activities.map((x) => x.group ? { ...x, op_index: groups.get(x.group)!.findIndex((item) => item.id === x.id) } : x);
      const targets = new Set(["*", ...activities.map((x) => x.id), ...activities.map((x) => x.category), ...current.resources.map((x) => x.id)]);
      return { ...current, activities, constraints: current.constraints.filter((c) =>
        targets.has(c.target) && (c.other === null || activities.some((x) => x.id === c.other))) };
    });
  }
  function exportPlan(format: "json" | "xlsx" | "pdf" = "json") {
    if (!problem || !result || busy) return;
    if (format === "json") {
      const contents = JSON.stringify({ problem, result }, null, 2);
      const url = URL.createObjectURL(
        new Blob([contents], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "optiday-plan.json";
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    // XLSX/PDF are rendered by the backend from the exact result on screen.
    setError("");
    setBusy(format === "xlsx" ? "正在导出 Excel…" : "正在导出 PDF…");
    void exportPlanRequest(format, { problem, result })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "导出失败，请重试。"),
      )
      .finally(() => setBusy(""));
  }
  const metric = result?.metrics;
  const active =
    selected && problem?.activities.find((a) => a.id === selected.activity_id);
  const activeDisplayName = active && problem && result
    ? occurrenceNames(problem, result.assignments).get(active.id) ?? active.name : active?.name;
  const totalHours =
    problem?.activities
      .filter((a) => a.category !== "sleep" && !a.optional)
      .reduce((s, a) => s + a.duration / 2, 0) ?? 0;
  const fixedCount =
    problem?.constraints.filter((c) => c.type === "fixed_time").length ?? 0;
  const title = SCENARIOS[scenario];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("workspace");
          }}
        >
          <BrandMark className="brand-mark" />
          <span>
            OptiDay
            <small>智能调度与组合优化</small>
          </span>
        </a>
        <div className="workspace-label">
          <span className="workspace-avatar">O</span>
          <div>我的工作空间</div>
        </div>
        <div className="nav-label">工作空间</div>
        <button
          disabled={!!busy}
          className={`nav-item ${page === "workspace" ? "active" : ""}`}
          onClick={() => setPage("workspace")}
        >
          <LayoutDashboard size={18} />
          调度工作台
          <ChevronRight size={15} />
        </button>
        <button
          disabled={!!busy}
          className={`nav-item ${page === "history" ? "active" : ""}`}
          onClick={openHistory}
        >
          <History size={18} />
          求解历史
        </button>
        <div className="nav-label scenarios-label">应用场景</div>
        {(Object.keys(SCENARIOS) as Scenario[]).map((s) => {
          const Icon = SCENARIO_ICONS[s];
          return (
            <button
              disabled={!!busy}
              key={s}
              className={`scenario-nav ${scenario === s ? "selected" : ""}`}
              onClick={() => void load(s)}
            >
              <Icon size={17} />
              <span>{SCENARIOS[s].title}</span>
              {scenario === s && <span className="scenario-dot" />}
            </button>
          );
        })}
        <div className="sidebar-note">
          <Workflow size={22} />
          <strong>安排任务，协调资源。</strong>
          <p>
            生成计划 · 识别冲突
            <br />
            调整安排 · 查看资源
          </p>
          <div className="mini-flow">
            <span />
            <i />
            <span />
            <i />
            <span />
            <i />
            <span />
          </div>
        </div>
        <div className="sidebar-bottom">
          <button className="nav-item" onClick={() => setHelp(true)}>
            <CircleHelp size={18} />
            使用指南
            <ArrowUpRight size={15} />
          </button>
          <div className="profile">
            <span>我</span>
            <div>
              个人工作空间<small>OptiDay{version ? ` v${version}` : ""}</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <Layers3 size={17} />
            <span>工作空间</span>
            <ChevronRight size={14} />
            <strong>{page === "history" ? "求解历史" : title.title}</strong>
          </div>
          <div className="topbar-right">
            <span className={`engine-health ${connected ? "" : "disconnected"}`}>
              <span />
              {connected ? "CP-SAT 引擎已连接" : connectionFailed ? "服务未连接" : "正在连接服务"}
            </span>
            <span className="provider-badge" title={provider === "demo" ? "当前使用有限的离线规则解析；正式安排由 CP-SAT 求解。" : !modelConfigured ? "当前未配置模型。可以手工编辑任务和约束，再生成计划。" : "模型负责理解自然语言和按事实解释；正式安排由 CP-SAT 求解。"}>
              {provider === "demo" ? "规则解析" : !modelConfigured ? "AI 未启用" : provider === "deepseek" ? "DeepSeek" : "OpenAI"}
            </span>
            <button
              className="icon-button"
              aria-label="使用指南"
              onClick={() => setHelp(true)}
            >
              <CircleHelp size={18} />
            </button>
          </div>
        </header>
        <main className="main-content">
          <div className="scenario-chips" role="tablist" aria-label="应用场景">
            {(Object.keys(SCENARIOS) as Scenario[]).map((s) => {
              const Icon = SCENARIO_ICONS[s];
              return (
                <button
                  key={s}
                  role="tab"
                  aria-selected={scenario === s}
                  disabled={!!busy}
                  className={`scenario-chip ${scenario === s ? "active" : ""}`}
                  onClick={() => void load(s)}
                >
                  <Icon size={14} />
                  {SCENARIOS[s].title}
                </button>
              );
            })}
          </div>
          <section className="page-heading">
            <div>
              <div className="eyebrow">
                {page === "history"
                  ? "SOLVE HISTORY"
                  : `${title.en} / 调度工作台`}
              </div>
              <h1>
                {page === "history" ? "求解历史" : title.title}
                <span className="heading-dot" />
              </h1>
              <p>
                {page === "history"
                  ? "仅显示当前浏览器保存的最近 12 次求解，可恢复任务、约束与安排。"
                  : title.description}
              </p>
            </div>
            <div className="heading-actions">
              <button
                className="secondary"
                disabled={!!busy}
                onClick={() => setConfirmation("preset")}
              >
                <RotateCcw size={15} />
                恢复预置方案
              </button>
              <button
                className="primary"
                disabled={!!busy || !problem}
                onClick={() => { setError(""); setAddingActivity(true); }}
              >
                <Plus size={16} />
                添加活动
              </button>
            </div>
          </section>
          <nav className="mobile-workspace-nav" aria-label="工作空间页面">
            <button className={page === "workspace" ? "active" : ""} disabled={!!busy} onClick={() => setPage("workspace")}><LayoutDashboard size={16}/>工作台</button>
            <button className={page === "history" ? "active" : ""} disabled={!!busy} onClick={openHistory}><History size={16}/>求解历史</button>
          </nav>
          {page === "workspace" && problem && <>
            <div className="workspace-tools">
              <label className="plan-name">计划名称 <input aria-label="计划名称" maxLength={120} value={problem.name} disabled={!!busy}
                onChange={(e) => { modelEpoch.current += 1; setProblem({ ...problem, name: e.target.value }); }} /></label>
              <label>所在周 <input aria-label="选择计划所在周" type="date" value={problem.week_start} disabled={!!busy}
                onChange={(e) => void changeWeek(e.target.value)} /></label>
              <div>
                <button disabled={!!busy} onClick={() => setConfirmation("blank")}><Plus size={14}/>新建自己的计划</button>
                <button disabled={!!busy} onClick={() => setResourcesOpen(true)}><Settings2 size={14}/>管理资源</button>
                <button disabled={!!busy} onClick={backupWorkspace}><Download size={14}/>备份工作空间</button>
                <button disabled={!!busy} onClick={() => backupFileRef.current?.click()}><Upload size={14}/>恢复备份</button>
              </div>
            </div>
            <div className="workflow-progress" aria-label="计划生成步骤">
              <span className={problem.activities.length ? "done" : "current"}><i>1</i>添加任务与需求</span>
              <ChevronRight size={14}/><span className={reviewed && !inputPending ? "done" : "current"}><i>2</i>{inputPending ? "需求尚待识别" : reviewed ? "约束已确认" : "检查并确认约束"}</span>
              <ChevronRight size={14}/><span className={result?.assignments.length ? "done" : ""}><i>3</i>生成与调整计划</span>
              {undo && <button disabled={!!busy} onClick={undoChange} title={`可撤销本次打开后的最近 ${undoStack.length} 次内容修改，最多保留 10 步`}><RotateCcw size={13}/>撤销修改</button>}
            </div>
          </>}
          <input ref={backupFileRef} type="file" accept=".json" aria-label="选择工作空间备份" hidden
            onChange={(e) => { if (e.target.files?.[0]) void importBackup(e.target.files[0]); }} />
          <BusyStatus busy={busy}/>
          {error && !constraintEditor && !addingActivity && !editingActivity && (
            <div className="message error" role="alert">
              <AlertTriangle size={17} />
              <span>{error}</span>
              {connectionFailed && <button onClick={() => void reconnect()}>重试连接</button>}
              {retryAction && <button disabled={!!busy || retryAction === "solve" && (!reviewed || inputPending)} onClick={() => void (retryAction === "parse" ? parse(lastParseMode.current) : optimize())}>{retryAction === "parse" ? "重试识别" : "重试生成"}</button>}
              {!problem && <button disabled={!!busy} onClick={() => void load(scenario)}>重新载入工作空间</button>}
              <button onClick={() => setError("")} aria-label="关闭错误">
                <X size={15} />
              </button>
            </div>
          )}
          {saveWarning && (
            <div className="message error storage-warning" role="alert">
              <AlertTriangle size={17} />
              <span>{saveWarning}</span>
              {!storageConflict && <button onClick={backupWorkspace}>备份当前内容</button>}
              {storageConflict && <div className="storage-conflict-actions"><button disabled={!!busy || !storageConflict.latest} onClick={() => resolveStorageConflict(true)}>打开最新内容</button><button disabled={!!busy} onClick={() => resolveStorageConflict(false)}>保留当前编辑</button><button onClick={backupWorkspace}>先备份当前内容</button></div>}
            </div>
          )}
          {unsavedScenes.some((s) => s !== scenario) && <div className="message error storage-warning" role="alert"><AlertTriangle size={17}/><span>另有场景尚未写入浏览器，草稿暂留在本次页面内存中。关闭前请打开并备份：</span>
            {unsavedScenes.filter((s) => s !== scenario).map((s) => <button key={s} disabled={!!busy} onClick={() => void load(s)}>{SCENARIOS[s].title}</button>)}
          </div>}
          {historyWarning && <div className="message error history-save-warning" role="alert"><AlertTriangle size={17}/><span>{historyWarning}</span></div>}
          {notice && !constraintEditor && !addingActivity && !editingActivity && !resourcesOpen && !help && !confirmation && !selected && !repeatActivity && !onboarding && !pendingText && !scenarioHint && !chooseParseMode && (
            <div className="toast" role="status">
              <CheckCircle2 size={17} />
              {notice}
              <button onClick={() => setNotice("")} aria-label="关闭提示">
                <X size={14} />
              </button>
            </div>
          )}
          {page === "history" ? (
            <section className="history-panel panel">
              <div className="panel-heading">
                <h2>最近求解</h2>
                <span>{history.length} 条记录</span>
              </div>
              {history.length === 0 ? (
                <div className="empty-state">
                  <History size={30} />
              <p>生成第一份计划后，求解记录会保存在这里。</p>
                </div>
              ) : (
                history.map((h) => h.workspace.result && (
                  <div className="history-entry" key={h.id}>
                  <button
                    className="history-row"
                    key={h.id}
                    disabled={!!busy}
                    onClick={() => {
                      saveLocal();
                      rememberReplacement(h.workspace.problem.scenario);
                      restoreLocal(h.workspace);
                      setPage("workspace");
                      setNotice("已恢复此浏览器中的历史计划。");
                    }}
                  >
                    <span className="history-icon">
                      <CalendarDays size={20} />
                    </span>
                    <div>
                      <strong>{h.workspace.problem.name}</strong>
                      <small>
                        {new Date(h.created_at).toLocaleString("zh-CN")} ·{" "}
                        {h.workspace.result.metrics.activities} 项活动 · {h.workspace.problem.week_start} 所在周 · {{ efficient: "高效", balanced: "均衡", robust: "稳健" }[h.workspace.mode]}
                      </small>
                    </div>
                    <span
                      className={`status-pill ${h.workspace.result.status === "INFEASIBLE" ? "bad" : ""}`}
                    >
                      {h.workspace.result.status}
                    </span>
                    <span>{h.workspace.result.metrics.solve_time}s</span>
                    <ChevronRight size={18} />
                  </button>
                  <button className="icon-button history-delete" disabled={!!busy} aria-label={`删除历史 ${h.workspace.problem.name}`} onClick={() => {
                    const warning = deleteLocalRun(h.id); setHistoryWarning(warning); setHistory(readLocalHistory());
                    if (!warning) setNotice("已删除这条历史记录，当前计划仍保留。");
                  }}><Trash2 size={16}/></button></div>
                ))
              )}
            </section>
          ) : (
            <>
              <section className="overview">
                <div>
                  <span className="stat-icon blue">
                    <Layers3 size={19} />
                  </span>
                  <div>
                    <span>待编排活动</span>
                    <strong>
                      {problem?.activities.length ?? "—"}
                      <small>项</small>
                    </strong>
                  </div>
                </div>
                <div>
                  <span className="stat-icon purple">
                    <LockKeyhole size={19} />
                  </span>
                  <div>
                    <span>显式约束</span>
                    <strong>
                      {problem?.constraints.length ?? "—"}
                      <small>条</small>
                    </strong>
                  </div>
                </div>
                <div>
                  <span className="stat-icon teal">
                    <Clock3 size={19} />
                  </span>
                  <div>
                    <span>必做任务时长</span>
                    <strong>
                      {totalHours}
                      <small>小时 · 不含睡眠</small>
                    </strong>
                  </div>
                </div>
                <div>
                  <span className="stat-icon orange">
                    <ShieldCheck size={19} />
                  </span>
                  <div>
                    <span>
                      {metric?.hard_violations === 0
                        ? "方案校验通过"
                        : "固定日程"}
                    </span>
                    <strong>
                      {metric?.hard_violations === 0 ? "0" : fixedCount}
                      <small>
                        {metric?.hard_violations === 0
                          ? "硬约束违反"
                          : "项 · 不可移动"}
                      </small>
                    </strong>
                  </div>
                </div>
              </section>
              <div className="workspace-grid">
                <InputPanel
                  key={scenario}
                  problem={problem}
                  busy={busy}
                  provider={provider}
                  input={input}
                  setInput={setInput}
                  inputPending={inputPending}
                  acknowledgeInput={() => { setAppliedInput(input); setNotice("已选择只使用现有任务与约束；输入文字未纳入本次计划。"); }}
                  clearInput={clearInput}
                  repeatActivity={setRepeatActivity}
                  downloadTemplate={downloadTemplate}
                  scheduledIds={result && ["FEASIBLE", "OPTIMAL"].includes(result.status) ? new Set(result.assignments.map((a) => a.activity_id)) : null}
                  weightsFailed={weightsFailed}
                  retryConnection={() => void reconnect()}
                  clearContent={() => setConfirmation("clear-all")}
                  clearConstraints={() => setConfirmation("clear-constraints")}
                  clearActivities={() => setConfirmation("clear-activities")}
                  parse={() => startParse()}
                  scenario={scenario}
                  summary={summary}
                  warnings={warnings}
                  inputTab={inputTab}
                  setInputTab={setInputTab}
                  setConstraintEditor={(c) => { setError(""); setConstraintEditor(c); }}
                  deleteConstraint={deleteConstraint}
                  deleteActivity={deleteActivity}
                  editActivity={(a) => { setError(""); setEditingActivity(a); }}
                  mode={mode}
                  setMode={setMode}
                  weightsMeta={weightsMeta}
                  customWeights={customWeights}
                  appliedWeights={result?.objective?.weights ?? null}
                  setCustomWeights={setCustomWeights}
                  setHelp={setHelp}
                  reviewed={reviewed}
                  setReviewed={setReviewed}
                  optimize={optimize}
                  previous={previous}
                  fileRef={fileRef}
                  importFile={importFile}
                  textFileRef={textFileRef}
                  importText={importText}
                />
                <div className="result-column">
                <button className="mobile-plan-shortcut" onClick={() => document.querySelector(".input-panel")?.scrollIntoView({ behavior: "smooth", block: "start" })}><Pencil size={14}/>返回编辑任务与需求</button>
                {baseline && problem && result && <PlanChanges before={baseline} problem={problem} result={result}/>}
                <ResultPanel
                  problem={problem}
                  result={result}
                  busy={busy}
                  view={view}
                  setView={setView}
                  summary={summary}
                  exportPlan={exportPlan}
                  repair={repair}
                  setSelected={setSelected}
                />
                </div>
              </div>
              <footer className="workspace-footer">
                <span>
                  <Clock3 size={14} />
                  时间精度：30 分钟
                  <span className="local-save-status">{saveWarning ? "本地保存不可用" : locallySaved ? "已保存在此浏览器" : "本地自动保存"}</span>
                </span>
                <button
                  onClick={() => setHelp(true)}
                >
                  <CircleHelp size={14} />
                  使用指南
                  <ArrowUpRight size={13} />
                </button>
              </footer>
            </>
          )}
        </main>
      </div>
      {chooseParseMode && problem && <Dialog title="如何处理已有任务？" onClose={() => setChooseParseMode(false)}>
        <div className="replacement-content">
          <p>当前计划已有 <strong>{problem.activities.length} 项活动、{problem.constraints.length} 条约束</strong>{problem.activities.length ? `，包括${[...new Set(problem.activities.map((a) => a.name))].slice(0, 3).join("、")}等` : ""}。</p>
          <p>保留已有任务时，文字中没有提到的任务也会继续参与排程。只使用本次描述时，将从空白活动与约束开始识别，保留资源和所选周。</p>
          {input.length > MAX_INPUT_CHARS && <p className="form-note">本次识别前 4,000 字，其余文字会保留；继续识别后续文字时，请选择保留已有任务。</p>}
          <p className="form-note">识别失败不会改变当前计划；成功后可点击“撤销修改”恢复。</p>
          <div className="replacement-actions">
            <button className="secondary" onClick={() => setChooseParseMode(false)}>取消</button>
            <button className="secondary" onClick={() => { setChooseParseMode(false); void parse("keep"); }}>保留现有任务并识别</button>
            <button className="primary" onClick={() => { setChooseParseMode(false); void parse("replace"); }}>只使用本次描述</button>
          </div>
        </div>
      </Dialog>}
      {scenarioHint && <Dialog title="这段需求更适合个人周计划" onClose={() => setScenarioHint(null)}>
        <div className="replacement-content">
          <p>当前场景是“{SCENARIOS[scenario].title}”，输入包含个人生活与学习安排。可以切换到“{SCENARIOS[scenarioHint.target].title}”，需求文字会一起带过去。</p>
          <p>各场景已有的任务会保留。切换后点击“识别约束”，再检查新识别的任务。</p>
          <div className="replacement-actions">
            <button className="secondary" disabled={!!busy} onClick={() => { const hint = scenarioHint; setScenarioHint(null); void parse(hint.mode, true); }}>仍在当前场景识别</button>
            <button className="primary" disabled={!!busy} onClick={() => { const hint = scenarioHint; setScenarioHint(null); void load(hint.target, false, hint.input); }}>切换并带入需求</button>
          </div>
        </div>
      </Dialog>}
      {pendingText && <Dialog title="导入文字到输入框" onClose={() => setPendingText(null)}>
        <div className="text-import-preview"><p><strong>{pendingText.filename}</strong> · 已提取 {pendingText.chars.toLocaleString()} 字</p>
          <pre>{pendingText.text.slice(0, 700)}{pendingText.text.length > 700 ? "\n…（其余文字会完整导入）" : ""}</pre>
          <p className="form-note">当前输入尚未改变。选择放入方式后仍需点击“识别约束”，不会自动调用模型或覆盖现有任务。</p>
          <div className="replacement-actions"><button className="secondary" onClick={() => setPendingText(null)}>取消</button>
            {input.trim() && <button className="secondary" onClick={() => applyTextImport(false)}>替换输入</button>}
            <button className="primary" onClick={() => applyTextImport(!!input.trim())}>{input.trim() ? "追加到输入" : "放入输入框"}</button></div>
        </div>
      </Dialog>}
      {onboarding && problem && <Dialog title="开始安排你的时间" onClose={() => setOnboarding(false)}>
        <div className="welcome-content"><BrandMark className="welcome-mark" /><h3>把需求变成可执行的计划</h3>
          <p>添加自己的任务，或用示例看看效果。内容会保存在此浏览器，下次回来可以继续。</p>
          <div className="welcome-options"><button className="primary" disabled={!!busy} onClick={() => { setOnboarding(false); setAddingActivity(true); }}>从我的第一个任务开始<ArrowRight size={16}/></button>
            <button className="secondary" disabled={!!busy} onClick={() => { setOnboarding(false); void load(scenario, true); }}>体验完整示例</button></div>
          <small>AI 理解需求 · 约束检查 · CP-SAT 生成合法安排</small>
        </div>
      </Dialog>}
      {problem && repeatActivity && <RepeatActivity activity={repeatActivity} problem={problem} onClose={() => { modelEpoch.current += 1; setRepeatActivity(null); }}
        onSave={async (activities, constraints) => { if (await validateDraft({ ...problem, activities: [...problem.activities, ...activities], constraints: [...problem.constraints, ...constraints] })) {
          setRepeatActivity(null); setInputTab("activities"); setNotice(`已新增 ${activities.length} 项重复活动，请检查并确认。`);
        } }}/ >}
      {problem && resourcesOpen && <Dialog title="管理资源" onClose={() => { if (!busy) { modelEpoch.current += 1; setResourcesOpen(false); } }}>
        <ResourceManager problem={problem} busy={!!busy} onSave={async (resources) => {
          const p = { ...problem, resources };
          if (!await validateDraft(p)) return; setResourcesOpen(false);
          setNotice("资源已更新，请确认约束并重新生成计划。");
        }}/>
      </Dialog>}
      {confirmation && <Dialog title={confirmation === "preset" ? "恢复预置方案？" : confirmation === "blank" ? "新建自己的计划？" :
        confirmation === "clear-all" ? "清空当前内容？" : confirmation === "clear-constraints" ? "清空所有约束？" :
        confirmation === "clear-activities" ? "清空所有活动？" : "恢复工作空间备份？"}
        onClose={() => setConfirmation(null)}>
        <div className="replacement-content">
          <p>{confirmation === "preset" ? "当前场景的任务、输入与计划将替换为预置内容。其他场景保持原样。" : confirmation === "blank" ? "清空当前场景的活动与约束，保留资源，开始安排自己的任务。" :
            confirmation === "clear-all" ? "将清空当前场景的输入文字、全部活动和约束，并移除当前计划。资源、所选周和其他场景会保留。" :
            confirmation === "clear-constraints" ? "将删除当前场景的全部约束，保留活动和输入文字。当前计划会移除，检查确认后可重新生成。" :
            confirmation === "clear-activities" ? "将删除当前场景的全部活动及其关联约束，并移除当前计划。输入文字、资源与通用约束会保留。" :
            "将打开备份对应的场景，恢复任务、约束和输入。请重新确认并求解，确保计划有效。"}</p>
          <div className="form-note">替换前可取消并下载备份。完成后可点击“撤销修改”恢复上一次内容。</div>
          <div className="replacement-actions"><button className="secondary" onClick={() => setConfirmation(null)}>取消</button>
            <button className="primary" onClick={() => void confirmReplacement()}>确认{confirmation === "blank" ? "新建" :
              typeof confirmation === "string" && confirmation.startsWith("clear-") ? "清空" : "恢复"}</button></div>
        </div>
      </Dialog>}
      {problem && constraintEditor && (
        <ConstraintEditor
          problem={problem}
          initial={constraintEditor === "new" ? undefined : constraintEditor}
          error={error}
          onClose={() => { modelEpoch.current += 1; setError(""); setConstraintEditor(null); }}
          onSave={async (c) => {
            if (!c.label.trim()) { setError("请输入约束说明，不能只填写空格。"); return; }
            setError("");
            try {
              const p = {
                ...problem,
                constraints: [
                  ...problem.constraints.filter((x) => x.id !== c.id),
                  c,
                ],
              };
              if (!await validateDraft(p)) return;
              setConstraintEditor(null);
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        />
      )}
      {problem && (addingActivity || editingActivity) && (
        <ActivityEditor
          problem={problem}
          initial={editingActivity ?? undefined}
          error={error}
          onClose={() => {
            modelEpoch.current += 1;
            setError("");
            setAddingActivity(false);
            setEditingActivity(null);
          }}
          onSave={async (a, c) => {
            if (!a.name.trim()) { setError("请输入活动名称，不能只填写空格。"); return; }
            setError("");
            try {
              const activities = editingActivity
                ? problem.activities.map((x) => (x.id === a.id ? a : x))
                : [...problem.activities, a];
              const constraints = editingActivity
                ? problem.constraints.filter(
                    (x) =>
                      !(
                        x.type === "fixed_time" &&
                        x.target === editingActivity.id
                      ),
                  )
                : problem.constraints;
              const validTargets = new Set(["*", ...activities.map((x) => x.id), ...activities.map((x) => x.category), ...problem.resources.map((r) => r.id)]);
              const p = {
                ...problem,
                activities,
                constraints: (c ? [...constraints, c] : constraints).filter((rule) => validTargets.has(rule.target)),
              };
              if (!await validateDraft(p)) return;
              setAddingActivity(false);
              setEditingActivity(null);
              setInputTab("activities");
              const removed = constraints.length + (c ? 1 : 0) - p.constraints.length;
              if (removed) setNotice(`活动已保存，${removed} 条已没有适用活动的分类约束已移除，可撤销恢复。`);
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        />
      )}
      {selected && active && problem && (
        <Dialog title={activeDisplayName ?? active.name} onClose={() => setSelected(null)}>
          {activeDisplayName !== active.name && <p className="form-note">按日历中的时间顺序显示次数；任务原名为「{active.name}」。</p>}
          <div className="event-detail">
            <span
              className={`category-badge ${(CATEGORIES[active.category] ?? CATEGORIES.study).color}`}
            >
              {(CATEGORIES[active.category] ?? CATEGORIES.study).label}
            </span>
            <h3>
              {DAYS[Math.floor(selected.start / 48)]} {clock(selected.start)}–
              {selected.end % 48 === 0 ? "24:00" : clock(selected.end)}
            </h3>
            <p>
              连续 {(selected.end - selected.start) / 2} 小时 ·{" "}
              {active.optional ? "可选活动" : "必须完成"}
            </p>
            <div className="event-detail-actions">
              <button className="secondary" disabled={!!busy} onClick={() => { setSelected(null); setEditingActivity(active); setError(""); }}><Pencil size={15}/>编辑活动</button>
              <button className="secondary" disabled={!!busy} onClick={() => { setSelected(null); setRepeatActivity(active); }}>重复到其他日期</button>
              <button className="secondary" disabled={!!busy} onClick={() => {
                const fixed = problem.constraints.find((c) => c.type === "fixed_time" && c.target === active.id);
                draft({ ...problem, constraints: fixed ? problem.constraints.filter((c) => !(c.type === "fixed_time" && c.target === active.id)) : [...problem.constraints,
                  { id: crypto.randomUUID().slice(0, 8), label: `${active.name} · 固定当前安排`, type: "fixed_time", target: active.id, level: "hard", day: Math.floor(selected.start / 48), start: selected.start % 48, end: 48, other: null, value: 1, source: "manual" }] });
                setNotice(fixed ? "已解除固定时间，请确认并重新优化。" : "已将当前安排固定，请确认约束。");
              }}><LockKeyhole size={15}/>{problem.constraints.some((c) => c.type === "fixed_time" && c.target === active.id) ? "解除固定时间" : "固定当前时间"}</button>
            </div>
            <h4>
              <Sparkles size={16} />
              为什么排在这个时间？
            </h4>
            {provider !== "demo" && !explanation?.narrative && <button className="secondary" disabled={explainBusy || !explanation} onClick={() => void narrateSelected()}>
              {explainBusy ? <Loader2 size={14} className="spin"/> : <Sparkles size={14}/>} {explainBusy ? "正在生成说明…" : "用 AI 解读安排依据"}
            </button>}
            {explanation?.narrative && (
              <div className="narrative">
                <p>{explanation.narrative.headline}</p>
                {explanation.narrative.bullets.length > 0 && (
                  <ul>
                    {explanation.narrative.bullets.map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                )}
                <small>AI 根据约束与求解结果生成说明</small>
              </div>
            )}
            {explanation ? (
              <div className="why-list">
                {explanation.reasons.map((reason, index) => (
                  <article
                    className={`why-item why-${reason.kind}`}
                    key={`${reason.kind}-${index}`}
                  >
                    <strong>{reason.title}</strong>
                    <p>{reason.detail}</p>
                  </article>
                ))}
              </div>
            ) : explainBusy ? (
              <p className="why-loading">
                <Loader2 size={15} className="spin" />
                正在根据本次求解数据生成解释…
              </p>
            ) : (
              <ul>
                <li>在该活动允许的日期与时间域内。</li>
                <li>占用资源均未超过可用并发容量。</li>
                {active.resources.map((r) => (
                  <li key={r}>
                    使用资源：{problem.resources.find((x) => x.id === r)?.name}
                  </li>
                ))}
                {selected.room_id && (
                  <li>
                    教室：
                    {
                      problem.resources.find((x) => x.id === selected.room_id)
                        ?.name
                    }
                    ，已检查类型和座位容量。
                  </li>
                )}
                {problem.constraints
                  .filter((c) =>
                    [
                      active.id,
                      active.category,
                      ...active.resources,
                      "*",
                    ].includes(c.target),
                  )
                  .map((c) => (
                    <li key={c.id}>
                      {describeConstraint(c, problem)}
                      {c.level === "soft"
                        ? "（优化偏好）"
                        : "（硬约束已通过）"}
                    </li>
                  ))}
              </ul>
            )}
            <div className="form-note">
              {explanation
                ? `单项活动时间筛选得到 ${explanation.candidate_slots_total} 个候选开始时段，未逐项验证其他活动的资源占用及先后关系。当前方案已经求解并独立校验。`
                : "这是依据求解数据生成的校验说明，不代表该时间是唯一可行选择。"}
            </div>
          </div>
        </Dialog>
      )}
      {help && (
        <Dialog title="使用 OptiDay" onClose={() => setHelp(false)}>
          <div className="help-content">
            <div className="form-note">
              工作内容自动保存在当前浏览器，刷新、重新打开及切换场景时会恢复上次内容。
              点击“恢复预置方案”只会替换当前场景的内容。不同电脑或浏览器各自保存，不会自动同步；清除网站数据或结束无痕浏览会丢失本地保存。
              使用“备份工作空间”下载 JSON 文件，在其他电脑点击“恢复备份”即可继续编辑。求解历史仅保存在此浏览器；任务与约束会提交服务器求解，使用 AI 识别时也会提交给模型服务。
              内容修改可撤销最近 10 步；刷新或切换场景后撤销记录清空，已保存的工作内容仍会恢复。
            </div>
            <ol>
              <li>
                <strong>选择一个场景</strong>
                <p>从预置方案了解操作，或点击“新建自己的计划”。选择所在周，添加活动；教师、教室、设备等信息可在“管理资源”修改。</p>
              </li>
              <li>
                <strong>描述安排或导入文件</strong>
                <p>
                  输入需求后点击“识别约束”。CSV/XLSX 可导入任务；TXT/PDF 提取文字后，再进行识别。
                  {provider === "demo" && "当前使用规则解析，无法识别的要求可手工补充。"}
                </p>
              </li>
              <li>
                <strong>检查并确认约束</strong>
                <p>
                  编辑、删除或新增约束，再勾选确认。固定事项必须给出明确时间。
                </p>
              </li>
              <li>
                <strong>生成计划与重新优化</strong>
                <p>
                  高效模式偏向紧凑，均衡模式兼顾每日负载，稳健模式优先减少已有安排变动。
                </p>
              </li>
              <li>
                <strong>处理冲突</strong>
                <p>
                  要求无法同时满足时，系统会显示冲突信息。可修改约束，或选择经过求解验证的修复建议后重新生成计划。
                </p>
              </li>
            </ol>
            <div className="form-note">
              时间精度为 30 分钟。个人计划的预置睡眠从 00:00 开始；排课预置方案按每课时 60 分钟安排。可在任务与约束中修改。优化明细显示各目标的惩罚值，数值越低代表对应目标的偏离越少。
            </div>
          </div>
        </Dialog>
      )}
    </div>
  );
}
