import { useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Plus, Search, Trash2 } from "lucide-react";
import { type Problem, type Resource, DAYS, clock } from "./types";
import "./styles/resource-manager.css";
import { useDialogDraft } from "./Editors";

const RESOURCE_TYPES: Record<string, string> = {
  person: "个人 / 参与人",
  teacher: "教师",
  class: "班级",
  team: "团队",
  room: "教室 / 实验室 / 会议室",
  equipment: "仪器设备",
  machine: "机台 / 工位",
};

const ROOM_TYPES: Record<string, string> = {
  lecture: "普通教室",
  computer: "计算机实验室",
  analysis: "分析实验室",
  general: "基础实验室",
  meeting: "普通会议室",
  video: "视频会议室",
};

function references(problem: Problem, resourceId: string) {
  const activities = problem.activities.filter(
    (activity) => activity.resources.includes(resourceId)
      || Object.hasOwn(activity.demands, resourceId)
      || activity.room_options.includes(resourceId),
  );
  const constraints = problem.constraints.filter(
    (constraint) => constraint.target === resourceId || constraint.other === resourceId,
  );
  return { activities, constraints };
}

/** Content for the existing Dialog; saving updates the shared Problem in the parent. */
export function ResourceManager({
  problem,
  onSave,
  busy,
}: {
  problem: Problem;
  onSave: (resources: Resource[]) => Promise<void>;
  busy: boolean;
}) {
  const [resources, setResources] = useState<Resource[]>(
    () => problem.resources.map((resource) => ({ ...resource })),
  );
  const [expanded, setExpanded] = useState<string | null>(problem.resources[0]?.id ?? null);
  const [query, setQuery] = useState("");
  const [customRoomTypes, setCustomRoomTypes] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const original = useRef(JSON.stringify(resources));
  const [editingSearchId, setEditingSearchId] = useState<string | null>(null);
  const disabled = busy || saving;
  useDialogDraft(JSON.stringify(resources) !== original.current, disabled);
  const roomTypes = useMemo(() => [...new Set([
    ...Object.keys(ROOM_TYPES),
    ...problem.resources.map((resource) => resource.room_type),
    ...problem.activities.map((activity) => activity.room_type),
  ])].filter(Boolean), [problem]);

  function update(resourceId: string, patch: Partial<Resource>) {
    setResources((current) => current.map(
      (resource) => resource.id === resourceId ? { ...resource, ...patch } : resource,
    ));
    setError("");
  }

  function addResource() {
    if (resources.length >= 50) return;
    const type = {
      life: "person", academic: "teacher", lab: "equipment", meeting: "room", production: "machine",
    }[problem.scenario];
    const existingIds = new Set([
      ...resources.map((resource) => resource.id),
      ...problem.activities.map((activity) => activity.id),
      ...problem.constraints.map((constraint) => constraint.id),
    ]);
    let resourceId = `resource_${crypto.randomUUID().slice(0, 12)}`;
    while (existingIds.has(resourceId)) resourceId = `resource_${crypto.randomUUID().slice(0, 12)}`;
    setResources((current) => [...current, {
      id: resourceId, name: "", type, capacity: 1,
      seats: type === "room" ? 20 : 0,
      room_type: type === "room" ? "meeting" : "",
    }]);
    setQuery("");
    setExpanded(resourceId);
    setError("");
  }

  function removeResource(resource: Resource) {
    const used = references(problem, resource.id);
    if (used.activities.length || used.constraints.length) {
      setError(`「${resource.name}」仍被活动或约束使用，请先修改对应活动和约束，再删除资源。`);
      return;
    }
    setResources((current) => current.filter((item) => item.id !== resource.id));
    if (expanded === resource.id) setExpanded(null);
    setError("");
  }

  async function save() {
    if (disabled || savingRef.current) return;
    const resourceIds = new Set<string>();
    for (const resource of resources) {
      let message = "";
      if (!resource.id.trim() || resourceIds.has(resource.id)) {
        message = "资源标识为空或重复，请关闭窗口后重新打开资源管理。";
      } else if (!resource.name.trim()) {
        message = "请输入资源名称，不能只填写空格。";
      } else if (!Number.isInteger(resource.capacity) || resource.capacity < 1 || resource.capacity > 100) {
        message = "同时可用数量需为 1 到 100 的整数。";
      } else if (!Number.isInteger(resource.seats) || resource.seats < 0) {
        message = "座位数需为大于或等于 0 的整数。";
      } else if (resource.type !== "room" && problem.resources.find((originalResource) => originalResource.id === resource.id)?.type === "room" && problem.activities.some(
        (activity) => activity.room_options.includes(resource.id),
      )) {
        message = `「${resource.name}」是活动的候选场地，请保留场地类型，或先修改活动的候选场地。`;
      }
      if (message) {
        setError(message);
        setQuery("");
        setExpanded(resource.id);
        return;
      }
      resourceIds.add(resource.id);
    }
    for (const resource of problem.resources) {
      const used = references(problem, resource.id);
      if (!resourceIds.has(resource.id) && (used.activities.length || used.constraints.length)) {
        setError(`「${resource.name}」仍被活动或约束使用，无法删除。`);
        return;
      }
    }
    savingRef.current = true;
    setSaving(true);
    setError("");
    try {
      await onSave(resources.map((resource) => ({
        ...resource, name: resource.name.trim(), room_type: resource.room_type.trim(),
      })));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "保存资源失败，请重试。");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  const matching = resources.filter((resource) =>
    resource.id === editingSearchId || `${resource.name} ${resource.id} ${RESOURCE_TYPES[resource.type] ?? resource.type}`.toLocaleLowerCase()
      .includes(query.trim().toLocaleLowerCase()),
  );

  return (
    <form className="resource-manager" noValidate onSubmit={(event) => {
      event.preventDefault();
      void save();
    }}>
      <p className="resource-manager-intro">
        管理活动使用的人、场地和设备。保存后检查约束，再重新生成计划。
      </p>
      {error && <div className="message error resource-manager-error" role="alert">{error}</div>}
      <div className="resource-manager-toolbar">
        <label className="resource-manager-search">
          <Search size={15} aria-hidden="true" />
          <input aria-label="搜索资源" value={query} placeholder="搜索名称或类型"
            onChange={(event) => { setEditingSearchId(null); setQuery(event.target.value); }} disabled={disabled} />
        </label>
        <button type="button" className="secondary" onClick={addResource}
          disabled={disabled || resources.length >= 50}>
          <Plus size={14} /> 新增资源
        </button>
      </div>
      <p className="resource-manager-count">{resources.length} / 50 项资源</p>
      <div className="resource-manager-list">
        {matching.length === 0 && <div className="resource-manager-empty">
          {query.trim() ? "没有找到匹配的资源。" : "还没有资源，可先新增教师、场地或设备。"}
        </div>}
        {matching.map((resource) => {
          const used = references(problem, resource.id);
          const isExpanded = expanded === resource.id;
          const roomRequired = problem.resources.find((originalResource) => originalResource.id === resource.id)?.type === "room"
            && problem.activities.some((activity) => activity.room_options.includes(resource.id));
          const unavailable = used.constraints.filter((constraint) => constraint.type === "unavailable");
          return <section key={resource.id} className={`resource-manager-item ${isExpanded ? "expanded" : ""}`}>
            <button type="button" className="resource-manager-toggle" disabled={disabled}
              aria-expanded={isExpanded} aria-controls={`resource-fields-${resource.id}`}
              onClick={() => { setExpanded(isExpanded ? null : resource.id); if (isExpanded) setEditingSearchId(null); }}>
              <span><strong>{resource.name.trim() || "未命名资源"}</strong>
                <small>{RESOURCE_TYPES[resource.type] ?? resource.type} · {used.activities.length} 项活动使用</small>
              </span>
              <ChevronDown size={16} aria-hidden="true" />
            </button>
            {isExpanded && <div id={`resource-fields-${resource.id}`} className="resource-manager-fields">
              <label>资源名称
                <input aria-label="资源名称" maxLength={100} value={resource.name} disabled={disabled}
                  placeholder="例如：张老师 / 实验室 A / 光谱仪"
                  onFocus={() => { if (query.trim()) setEditingSearchId(resource.id); }}
                  onChange={(event) => update(resource.id, { name: event.target.value })} />
              </label>
              <p className="resource-manager-hint">导入标识：<code>{resource.id}</code>（重命名不改变关联）</p>
              <div className="resource-manager-grid">
                <label>资源类型
                  <select aria-label="资源类型" value={resource.type} disabled={disabled || roomRequired}
                    onChange={(event) => update(resource.id, { type: event.target.value })}>
                    {!RESOURCE_TYPES[resource.type] && <option value={resource.type}>{resource.type}</option>}
                    {Object.entries(RESOURCE_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label>同时可用数量
                  <input aria-label="同时可用数量" type="number" min={1} max={100} step={1}
                    value={Number.isNaN(resource.capacity) ? "" : resource.capacity} disabled={disabled}
                    onChange={(event) => update(resource.id, { capacity: event.target.valueAsNumber })} />
                </label>
              </div>
              <p className="resource-manager-hint">人或单个场地通常填 1；同类设备有 2 台可填 2。</p>
              {resource.type === "room" && <div className="resource-manager-grid">
                <label>座位数
                  <input aria-label="座位数" type="number" min={0} step={1}
                    value={Number.isNaN(resource.seats) ? "" : resource.seats} disabled={disabled}
                    onChange={(event) => update(resource.id, { seats: event.target.valueAsNumber })} />
                </label>
                <label>场地类型
                  <select aria-label="场地类型" value={customRoomTypes.has(resource.id) ? "__custom__" : resource.room_type}
                    disabled={disabled} onChange={(event) => {
                      const custom = event.target.value === "__custom__";
                      setCustomRoomTypes((current) => {
                        const next = new Set(current);
                        if (custom) next.add(resource.id); else next.delete(resource.id);
                        return next;
                      });
                      if (!custom) update(resource.id, { room_type: event.target.value });
                    }}>
                    <option value="">未指定</option>
                    {roomTypes.map((type) => <option key={type} value={type}>{ROOM_TYPES[type] ?? type}</option>)}
                    <option value="__custom__">自定义类型</option>
                  </select>
                </label>
              </div>}
              {resource.type === "room" && customRoomTypes.has(resource.id) && <label>
                自定义场地类型（与活动要求保持一致）
                <input aria-label="自定义场地类型" maxLength={100} value={resource.room_type} disabled={disabled}
                  onChange={(event) => update(resource.id, { room_type: event.target.value })} />
              </label>}
              {resource.type === "room" && <p className="resource-manager-hint">
                场地类型须与活动要求一致，系统只会分配符合要求的场地。
              </p>}
              {used.activities.length + used.constraints.length > 0 && <div className="resource-manager-usage">
                <strong>关联内容</strong>
                <p>{used.activities.length} 项活动、{used.constraints.length} 条约束正在使用此资源。</p>
                <p className="resource-manager-reference-names">
                  {used.activities.slice(0, 3).map((activity) => activity.name).join("、")}
                  {used.activities.length > 3 ? "等" : ""}
                </p>
                {unavailable.length > 0 && <ul aria-label="资源不可用时间">
                  {unavailable.map((constraint) => <li key={constraint.id}>
                    {constraint.day === null ? "每天" : DAYS[constraint.day]} {clock(constraint.start)}–{constraint.end === 48 ? "24:00" : clock(constraint.end)}
                  </li>)}
                </ul>}
                <p>不可用时段可在“约束”中添加或修改；删除资源前需先移除关联内容。</p>
              </div>}
              <div className="resource-manager-delete-row">
                <button type="button" className="resource-manager-delete" onClick={() => removeResource(resource)}
                  disabled={disabled || !!used.activities.length || !!used.constraints.length}>
                  <Trash2 size={14} /> 删除资源
                </button>
                {used.activities.length + used.constraints.length > 0 && <span>正在使用，暂不能删除</span>}
              </div>
            </div>}
          </section>;
        })}
      </div>
      <p className="resource-manager-note">保存前可关闭窗口取消本次修改。</p>
      <button type="submit" className="primary wide" disabled={disabled}>
        <Check size={16} /> {saving ? "正在保存资源…" : "保存资源"}
      </button>
    </form>
  );
}
