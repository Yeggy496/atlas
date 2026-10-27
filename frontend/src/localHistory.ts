import { isLocalWorkspace, type LocalWorkspace } from "./localWorkspace";
import { SCENARIOS, type Scenario } from "./types";
import { LEGACY_HISTORY_KEY } from "./legacyCompatibility";

const KEY = "optiday.history.v1";
export interface LocalRun { id: string; created_at: string; workspace: LocalWorkspace }
export function readLocalHistory(): LocalRun[] {
  try {
    const data: unknown = JSON.parse(localStorage.getItem(KEY) ?? localStorage.getItem(LEGACY_HISTORY_KEY) ?? "[]");
    if (!Array.isArray(data)) return [];
    return data.filter((entry): entry is LocalRun => {
      const s = entry?.workspace?.problem?.scenario;
      return typeof entry?.id === "string" && typeof entry?.created_at === "string" &&
        Number.isFinite(Date.parse(entry.created_at)) && typeof s === "string" &&
        Object.hasOwn(SCENARIOS, s) && isLocalWorkspace(entry.workspace, s as Scenario) &&
        entry.workspace.result !== null;
    }).slice(0, 12);
  } catch { return []; }
}
export function saveLocalRun(workspace: LocalWorkspace): string {
  if (!workspace.result) return "";
  try {
    const entry = { id: workspace.result.run_id, created_at: new Date().toISOString(), workspace };
    const rows = readLocalHistory().filter((row) => row.id !== entry.id);
    localStorage.setItem(KEY, JSON.stringify([entry, ...rows].slice(0, 12)));
    return "";
  } catch { return "浏览器未能保存求解历史，当前计划仍可查看，请下载备份。"; }
}
export function deleteLocalRun(id: string): string {
  try { localStorage.setItem(KEY, JSON.stringify(readLocalHistory().filter((row) => row.id !== id))); return ""; }
  catch { return "无法删除本地记录，请检查浏览器存储权限。"; }
}
