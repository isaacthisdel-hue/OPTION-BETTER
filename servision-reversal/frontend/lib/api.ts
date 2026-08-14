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
async function del(path: string) {
  const r = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export const api = {
  candidates: () => get("/api/candidates"),
  scan: (force = false) => post(`/api/scan${force ? "?force=true" : ""}`),
  marketStatus: () => get("/api/market-status"),
  paperTrades: () => get("/api/paper-trades"),
  stats: () => get("/api/stats"),
  projection: (capital = 10000, tradesPerDay = 2, days = 5) =>
    get(`/api/projection?capital=${capital}&trades_per_day=${tradesPerDay}&days=${days}`),
  backtest: (payload: Record<string, unknown> = {}) => post("/api/backtest", payload),
  versions: () => get("/api/strategy-versions"),
  activateVersion: (id: number) => post(`/api/strategy-versions/${id}/activate`),
  backtestVersion: (id: number) => post(`/api/strategy-versions/${id}/backtest`),
  createVersion: (label: string, config: Record<string, unknown>, notes = "") =>
    post("/api/strategy-versions", { label, config, notes }),
  optimize: () => post("/api/optimize", {}),
  replaySession: (symbol: string, back = 0) =>
    get(`/api/replay/session?symbol=${encodeURIComponent(symbol)}&back=${back}`),
  deleteVersion: (id: number) => del(`/api/strategy-versions/${id}`),
  savedList: () => get("/api/saved"),
  saveIdea: (idea: Record<string, unknown>) => post("/api/saved", idea),
  deleteSaved: (id: number) => del(`/api/saved/${id}`),
  refreshSaved: () => post("/api/saved/refresh"),
  backtestTickers: () => get("/api/backtest-tickers"),
  setBacktestTickers: (tickers: string, max?: number) => post("/api/backtest-tickers", { tickers, max }),
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
  estimated_reversal_pct?: number;
  reversal_tier?: string;
  reversal_confidence?: string;
  option_aim?: { direction: string; expiry_next_friday: string; expected_move_pct?: number; target_move_pct?: number };
  prediction?: string;
  direction_bias?: string;
  predicted_move_pct?: number;
  prediction_confidence?: string;
  spark?: number[];
  market_cap_billions?: number | null;
};
