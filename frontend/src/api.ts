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

export async function api<T>(path: string, body?: unknown): Promise<T> {
  let response;
  try {
    response = await fetch(
    `/api${path}`,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
    );
  } catch {
    throw new Error("无法连接服务，请检查网络或确认后端已启动。");
  }
  return readResponse<T>(response);
}
