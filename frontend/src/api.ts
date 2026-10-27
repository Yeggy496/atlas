export async function readResponse<T>(response: Response): Promise<T> {
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(
      response.ok
        ? "服务响应格式不正确，请重试。"
        : `服务暂时不可用（HTTP ${response.status}），请稍后重试。`,
    );
  }
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((x: { msg: string }) => x.msg).join("；")
          : "请求失败，请重试。",
    );
  }
  return data as T;
}

async function withDeadline<T>(work: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 150_000);
  try { return await work(controller.signal); }
  catch (error) {
    if (controller.signal.aborted) throw new Error("请求等待超时，当前内容已保留，请稍后重试。");
    if (error instanceof TypeError) throw new Error("无法连接服务，请检查网络后重试。当前内容已保留。");
    throw error;
  } finally { window.clearTimeout(timer); }
}

export function api<T>(path: string, body?: unknown): Promise<T> {
  return withDeadline(async (signal) => readResponse<T>(await fetch(`/api${path}`, body === undefined ? { signal } : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal,
  })));
}

export function upload<T>(path: string, form: FormData): Promise<T> {
  return withDeadline(async (signal) => readResponse<T>(await fetch(`/api${path}`, { method: "POST", body: form, signal })));
}

/** Download a solved plan as XLSX or PDF (MASTER_SPEC §25 P2). */
export async function exportPlan(
  format: "xlsx" | "pdf",
  body: unknown,
): Promise<void> {
  return withDeadline(async (signal) => {
    const response = await fetch(`/api/export/${format}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  if (!response.ok) {
    // The error path is JSON; fall back to a generic message if it is not.
    try {
      await readResponse(response);
    } catch (error) {
      throw error instanceof Error ? error : new Error("导出失败，请重试。");
    }
    throw new Error("导出失败，请重试。");
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename=([^;]+)/i);
  const filename = match ? match[1].trim() : `optiday-plan.${format}`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
  });
}
