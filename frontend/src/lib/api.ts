export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export type PoolItem = {
  symbol: string;
  status: "active" | "inactive";
  source: "auto" | "manual";
  tier: string | null;
  sector: string | null;
  list_tags: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type KlinePoint = {
  symbol: string;
  open_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume: number | null;
  trades: number | null;
};

export type OIPoint = {
  symbol: string;
  ts: string;
  sum_open_interest: number | null;
  sum_open_interest_value: number | null;
};

export type AssetProfile = {
  symbol: string;
  name: string | null;
  sector: string | null;
  description: string | null;
  website: string | null;
  twitter: string | null;
  extra: Record<string, unknown>;
  updated_at: string;
};

export type TaskLogItem = {
  id: number;
  task_type: string;
  status: "running" | "success" | "failed";
  scope: Record<string, unknown>;
  summary: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  error_message: string | null;
};

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export async function fetchPool(): Promise<PoolItem[]> {
  const res = await fetch(`${API_BASE}/api/pool`, { cache: "no-store" });
  const data = await parseJson<{ items: PoolItem[] }>(res);
  return data.items;
}

export async function refreshAutoPool(): Promise<unknown> {
  const res = await fetch(`${API_BASE}/api/pool/refresh-auto`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      binance_min_quote_volume: 10000000,
      candidate_max_from_sources: 100,
    }),
  });
  return parseJson<unknown>(res);
}

export async function manualAddSymbol(symbol: string): Promise<unknown> {
  const res = await fetch(`${API_BASE}/api/pool/manual-add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol }),
  });
  return parseJson<unknown>(res);
}

export async function manualRemoveSymbol(symbol: string): Promise<unknown> {
  const res = await fetch(`${API_BASE}/api/pool/manual-remove`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol }),
  });
  return parseJson<unknown>(res);
}

export async function runIncremental(): Promise<unknown> {
  const res = await fetch(`${API_BASE}/api/collect/incremental-run`, {
    method: "POST",
  });
  return parseJson<unknown>(res);
}

export async function fetchTasks(params?: {
  limit?: number;
  task_type?: string;
  status?: "running" | "success" | "failed";
}): Promise<TaskLogItem[]> {
  const qs = new URLSearchParams();
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.task_type) qs.set("task_type", params.task_type);
  if (params?.status) qs.set("status", params.status);
  const res = await fetch(`${API_BASE}/api/collect/tasks?${qs.toString()}`, { cache: "no-store" });
  const data = await parseJson<{ items: TaskLogItem[] }>(res);
  return data.items;
}

export async function fetchKline(symbol: string, interval: "15m" | "1h", limit = 200): Promise<KlinePoint[]> {
  const res = await fetch(
    `${API_BASE}/api/market/${encodeURIComponent(symbol)}/kline?interval=${interval}&limit=${limit}`,
    { cache: "no-store" },
  );
  const data = await parseJson<{ items: KlinePoint[] }>(res);
  return data.items;
}

export async function fetchOI(symbol: string, interval: "15m" | "1h", limit = 200): Promise<OIPoint[]> {
  const res = await fetch(
    `${API_BASE}/api/market/${encodeURIComponent(symbol)}/oi?interval=${interval}&limit=${limit}`,
    { cache: "no-store" },
  );
  const data = await parseJson<{ items: OIPoint[] }>(res);
  return data.items;
}

export async function fetchProfile(symbol: string, refresh = false): Promise<AssetProfile> {
  const res = await fetch(
    `${API_BASE}/api/market/${encodeURIComponent(symbol)}/profile?refresh=${refresh ? "true" : "false"}`,
    { cache: "no-store" },
  );
  return parseJson<AssetProfile>(res);
}

export function exportUrl(symbol: string, interval: "15m" | "1h", type: "kline" | "oi"): string {
  return `${API_BASE}/api/export/${encodeURIComponent(symbol)}?interval=${interval}&type=${type}&format=csv`;
}
