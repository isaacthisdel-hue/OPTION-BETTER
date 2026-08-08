const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function get(path: string) {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}
async function post(path: string, body?: unknown) {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export const api = {
  candidates: () => get("/api/candidates"),
  scan: () => post("/api/scan"),
  paperTrades: () => get("/api/paper-trades"),
  stats: () => get("/api/stats"),
  projection: (capital = 10000, tradesPerDay = 2, days = 5) =>
    get(`/api/projection?capital=${capital}&trades_per_day=${tradesPerDay}&days=${days}`),
  backtest: (payload: Record<string, unknown> = {}) => post("/api/backtest", payload),
  versions: () => get("/api/strategy-versions"),
  base: BASE,
};

export type Component = { name: string; points: number; reason: string };
export type Candidate = {
  symbol: string;
  total: number;
  status: string;
  components: Component[];
  price?: number;
  move_pct?: number;
  volume_ratio?: number;
  vwap_distance_pct?: number;
  higher_low?: boolean;
  vwap_reclaim?: boolean;
  catalyst?: string;
};
