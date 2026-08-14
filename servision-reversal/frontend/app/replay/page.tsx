"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// ---------- Black-Scholes (model-priced chain) ----------
function normCdf(x: number) {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989423 * Math.exp(-x * x / 2);
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - p : p;
}
function bs(type: "call" | "put", S: number, K: number, T: number, sig: number, r = 0.04) {
  if (T <= 0 || sig <= 0) return type === "call" ? Math.max(0, S - K) : Math.max(0, K - S);
  const st = sig * Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + (sig * sig) / 2) * T) / st;
  const d2 = d1 - st;
  return type === "call"
    ? S * normCdf(d1) - K * Math.exp(-r * T) * normCdf(d2)
    : K * Math.exp(-r * T) * normCdf(-d2) - S * normCdf(-d1);
}
function callDelta(S: number, K: number, T: number, sig: number, r = 0.04) {
  if (T <= 0 || sig <= 0) return S > K ? 1 : 0;
  const d1 = (Math.log(S / K) + (r + (sig * sig) / 2) * T) / (sig * Math.sqrt(T));
  return normCdf(d1);
}
function strikeStep(S: number) { return S < 25 ? 1 : S < 100 ? 2.5 : S < 300 ? 5 : 10; }
const START_CASH = 10000;

type Bar = { t: number; o: number; h: number; l: number; c: number; v: number };
type Pos = { id: number; type: "call" | "put"; strike: number; entry: number; contracts: number; entryIdx: number };

export default function Replay() {
  const [symbol, setSymbol] = useState("AAPL");
  const [back, setBack] = useState(0);
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [idx, setIdx] = useState(20);
  const [playing, setPlaying] = useState(false);
  const [speedMs, setSpeedMs] = useState(400);
  const [iv, setIv] = useState(0.5);
  const [contracts, setContracts] = useState(1);

  const [cash, setCash] = useState(START_CASH);
  const [positions, setPositions] = useState<Pos[]>([]);
  const [pid, setPid] = useState(1);

  async function load(sym = symbol, b = back) {
    setLoading(true); setErr(null); setPlaying(false);
    try {
      const d = await api.replaySession(sym.toUpperCase(), b);
      if (!d.available) { setErr(d.error || "No data"); setData(null); }
      else {
        setData(d); setIdx(Math.min(20, (d.bars?.length || 1) - 1));
        setCash(START_CASH); setPositions([]);
      }
    } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const bars: Bar[] = data?.bars || [];
  const n = bars.length;

  useEffect(() => {
    if (!playing || !n) return;
    const t = setInterval(() => setIdx((i) => (i >= n - 1 ? i : i + 1)), speedMs);
    return () => clearInterval(t);
  }, [playing, speedMs, n]);
  useEffect(() => { if (n && idx >= n - 1) setPlaying(false); }, [idx, n]);

  if (loading) return <div className="empty">Loading session…</div>;

  const cur = bars[idx];
  const S = cur?.c ?? 0;
  const minsToClose = Math.max(0.25, 390 - idx);
  const T = minsToClose / (60 * 24 * 365);
  const step = strikeStep(S || 1);
  const atm = Math.round((S || 1) / step) * step;
  const strikes: number[] = [];
  for (let k = 6; k >= -6; k--) strikes.push(atm + k * step);

  const openValue = positions.reduce((s, p) => s + bs(p.type, S, p.strike, T, iv) * 100 * p.contracts, 0);
  const equity = cash + openValue;
  const pnl = equity - START_CASH;
  const clock = cur ? new Date(cur.t * 1000).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) : "—";

  function buy(type: "call" | "put", strike: number, premium: number) {
    if (premium <= 0.01) return;
    const cost = premium * 100 * contracts;
    setCash((c) => c - cost);
    setPositions((ps) => [...ps, { id: pid, type, strike, entry: premium, contracts, entryIdx: idx }]);
    setPid((x) => x + 1);
  }
  function close(id: number) {
    const p = positions.find((x) => x.id === id); if (!p) return;
    const val = bs(p.type, S, p.strike, T, iv) * 100 * p.contracts;
    setCash((c) => c + val);
    setPositions((ps) => ps.filter((x) => x.id !== id));
  }

  return (
    <>
      <div className="pagehead">
        <div>
          <div className="eyebrow">Options replay simulator</div>
          <h1>Replay</h1>
        </div>
      </div>
      <p className="pagesub">
        Replay a real intraday session bar-by-bar and trade a live option chain. The chain is
        model-priced (Black-Scholes) off the current price with same-day (0DTE) expiry, so it
        reacts to both price moves and time decay as you step through the day.
      </p>

      <div className="panel" style={{ marginBottom: 16, display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div className="field" style={{ maxWidth: 120 }}>
          <label>Symbol</label>
          <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
        </div>
        <button className="btn primary" onClick={() => load(symbol, 0)}>LOAD</button>
        <button className="btn" onClick={() => { const b = back + 1; setBack(b); load(symbol, b); }}>◀ Older day</button>
        <button className="btn" onClick={() => { const b = Math.max(0, back - 1); setBack(b); load(symbol, b); }} disabled={back === 0}>Newer day ▶</button>
        <div className="field" style={{ maxWidth: 90 }}>
          <label>IV</label>
          <input type="number" step="0.05" value={iv} onChange={(e) => setIv(Math.max(0.05, +e.target.value))} />
        </div>
        <div className="field" style={{ maxWidth: 90 }}>
          <label>Contracts</label>
          <input type="number" value={contracts} onChange={(e) => setContracts(Math.max(1, Math.floor(+e.target.value)))} />
        </div>
      </div>

      {err && <div className="empty">{err}</div>}

      {data && cur && (
        <div className="replay-grid">
          <div>
            <div className="panel">
              <div className="replay-readout">
                <span className="mono" style={{ fontSize: 16 }}>{data.symbol}</span>
                <span className="dim">{data.date} · {clock} ET</span>
                <span className="mono">${S.toFixed(2)}</span>
                <span className="faint">bar {idx + 1}/{n} · {Math.round(minsToClose)}m to close</span>
              </div>
              <PriceChart bars={bars} idx={idx} />
              <div className="replay-controls">
                <button className="btn primary" onClick={() => setPlaying((p) => !p)}>{playing ? "❚❚ Pause" : "▶ Play"}</button>
                <button className="btn" onClick={() => setIdx((i) => Math.min(n - 1, i + 1))}>Step ▶</button>
                <button className="btn" onClick={() => { setPlaying(false); setIdx(Math.min(20, n - 1)); }}>Reset</button>
                <label className="faint" style={{ fontSize: 12 }}>Speed
                  <input type="range" min={60} max={900} step={20} value={950 - speedMs}
                    onChange={(e) => setSpeedMs(950 - +e.target.value)} style={{ marginLeft: 8, verticalAlign: "middle" }} />
                </label>
              </div>
            </div>

            <div className="grid cols-4" style={{ marginTop: 14 }}>
              <div className="tile"><div className="label">Cash</div><div className="value">${cash.toFixed(0)}</div></div>
              <div className="tile"><div className="label">Open value</div><div className="value">${openValue.toFixed(0)}</div></div>
              <div className="tile"><div className="label">Equity</div><div className="value">${equity.toFixed(0)}</div></div>
              <div className="tile"><div className="label">Total P/L</div><div className={`value ${pnl >= 0 ? "pos" : "neg"}`}>{pnl >= 0 ? "+" : ""}${pnl.toFixed(0)}</div></div>
            </div>

            <div className="section-title">Positions · {positions.length}</div>
            {positions.length === 0 ? (
              <div className="empty">No open positions. Click a call or put price in the chain to buy.</div>
            ) : (
              <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
                <table className="data">
                  <thead><tr><th>Type</th><th>Strike</th><th>Entry</th><th>Now</th><th>P/L</th><th>Qty</th><th></th></tr></thead>
                  <tbody>
                    {positions.map((p) => {
                      const now = bs(p.type, S, p.strike, T, iv);
                      const ppl = (now - p.entry) * 100 * p.contracts;
                      return (
                        <tr key={p.id}>
                          <td className={p.type === "call" ? "pos" : "neg"}>{p.type.toUpperCase()}</td>
                          <td>{p.strike}</td>
                          <td>${p.entry.toFixed(2)}</td>
                          <td>${now.toFixed(2)}</td>
                          <td className={ppl >= 0 ? "pos" : "neg"}>{ppl >= 0 ? "+" : ""}${ppl.toFixed(0)}</td>
                          <td>{p.contracts}</td>
                          <td><button className="btn danger" onClick={() => close(p.id)}>Close</button></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="panel chain">
            <div className="dim" style={{ fontSize: 12, marginBottom: 8 }}>Option chain · 0DTE · IV {(iv * 100).toFixed(0)}%</div>
            <table className="chaintable">
              <thead><tr><th>Call</th><th>Δ</th><th>Strike</th><th>Put</th></tr></thead>
              <tbody>
                {strikes.map((k) => {
                  const cp = bs("call", S, k, T, iv);
                  const pp = bs("put", S, k, T, iv);
                  const dl = callDelta(S, k, T, iv);
                  const isAtm = Math.abs(k - atm) < 1e-6;
                  return (
                    <tr key={k} className={isAtm ? "atm" : ""}>
                      <td className="buyable call" onClick={() => buy("call", k, cp)}>{cp.toFixed(2)}</td>
                      <td className="faint">{dl.toFixed(2)}</td>
                      <td className="strike">{k}</td>
                      <td className="buyable put" onClick={() => buy("put", k, pp)}>{pp.toFixed(2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="faint" style={{ fontSize: 10, marginTop: 8 }}>Click a call/put price to buy {contracts} contract(s).</div>
          </div>
        </div>
      )}
    </>
  );
}

function PriceChart({ bars, idx }: { bars: Bar[]; idx: number }) {
  const w = 720, h = 300, pad = 8;
  const shown = bars.slice(0, idx + 1);
  if (shown.length < 2) return <div className="faint" style={{ height: h }}>…</div>;
  const cs = shown.map((b) => b.c);
  const min = Math.min(...cs), max = Math.max(...cs), rng = max - min || 1;
  const x = (i: number) => pad + (i / (bars.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - min) / rng) * (h - 2 * pad);
  const d = shown.map((b, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(b.c).toFixed(1)}`).join(" ");
  const last = shown[shown.length - 1];
  const up = last.c >= shown[0].c;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" style={{ display: "block" }}>
      <line x1={pad} y1={y(last.c)} x2={w - pad} y2={y(last.c)} stroke="var(--line)" strokeDasharray="3 3" />
      <path d={d} fill="none" stroke={up ? "var(--cyan)" : "var(--coral)"} strokeWidth="1.6" />
      <circle cx={x(shown.length - 1)} cy={y(last.c)} r="3.5" fill={up ? "var(--cyan)" : "var(--coral)"} />
      <text x={x(shown.length - 1) - 4} y={y(last.c) - 8} fontSize="11" fill="var(--ink)" textAnchor="end" fontFamily="var(--mono)">${last.c.toFixed(2)}</text>
    </svg>
  );
}
