"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

// ---------- Black-Scholes ----------
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
function strikeStep(S: number) { return S < 25 ? 1 : S < 100 ? 2.5 : S < 1000 ? 5 : 10; }
function fmtET(t: number) {
  return new Date(t * 1000).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" });
}
const START_CASH = 10000;
const TICKERS = ["AAPL","MSFT","NVDA","TSLA","AMZN","META","GOOGL","AMD","NFLX","AVGO","MU","ARM","QCOM","INTC","TSM","ORCL","CRM","ADBE","PLTR","SMCI","MSTR","COIN","HOOD","SOFI","AFRM","MARA","RIOT","NBIS","SNOW","MDB","CRWD","PANW","SHOP","UBER","ABNB","RIVN","LCID","NIO","BABA","DIS","BAC","F","PYPL","GME","AMC","CVNA","UPST","SPY","QQQ","IWM"];

type Bar = { t: number; o: number; h: number; l: number; c: number; v: number };
type Pos = { id: number; type: "call" | "put"; strike: number; entry: number; contracts: number };
type Shape = { tool: "trend" | "hline" | "box"; i1: number; p1: number; i2: number; p2: number };

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
  const [qty, setQty] = useState(1);

  const [chartType, setChartType] = useState<"line" | "candle">("candle");
  const [tool, setTool] = useState<"cursor" | "trend" | "hline" | "box">("cursor");
  const [shapes, setShapes] = useState<Shape[]>([]);
  const [selectedShape, setSelectedShape] = useState<number | null>(null);

  const [cash, setCash] = useState(START_CASH);
  const [positions, setPositions] = useState<Pos[]>([]);
  const [pid, setPid] = useState(1);
  const [ticket, setTicket] = useState<{ type: "call" | "put"; strike: number; premium: number } | null>(null);
  const [ticketQty, setTicketQty] = useState(1);

  async function load(sym = symbol, b = back) {
    setLoading(true); setErr(null); setPlaying(false);
    try {
      const d = await api.replaySession(sym.toUpperCase(), b);
      if (!d.available) { setErr(d.error || "No data"); setData(null); }
      else {
        setData(d); setIdx(Math.min(20, (d.bars?.length || 1) - 1));
        setCash(START_CASH); setPositions([]); setShapes([]);
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
  for (let k = 10; k >= -10; k--) strikes.push(atm + k * step);

  const openValue = positions.reduce((s, p) => s + bs(p.type, S, p.strike, T, iv) * 100 * p.contracts, 0);
  const equity = cash + openValue;
  const pnl = equity - START_CASH;

  function openTicket(type: "call" | "put", strike: number, premium: number) {
    if (premium <= 0.01) return;
    setTicket({ type, strike, premium }); setTicketQty(qty);
  }
  function confirmBuy() {
    if (!ticket) return;
    const add = Math.max(1, Math.floor(ticketQty));
    const cost = ticket.premium * 100 * add;
    setCash((c) => c - cost);
    setPositions((ps) => {
      const ex = ps.find((p) => p.type === ticket.type && p.strike === ticket.strike);
      if (ex) {
        const total = ex.contracts + add;
        const avg = (ex.entry * ex.contracts + ticket.premium * add) / total;
        return ps.map((p) => (p === ex ? { ...p, contracts: total, entry: avg } : p));
      }
      const np = { id: pid, type: ticket.type, strike: ticket.strike, entry: ticket.premium, contracts: add };
      setPid((x) => x + 1);
      return [...ps, np];
    });
    setQty(add); setTicket(null);
  }
  function close(id: number) {
    const p = positions.find((x) => x.id === id); if (!p) return;
    setCash((c) => c + bs(p.type, S, p.strike, T, iv) * 100 * p.contracts);
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
        Replay a real intraday session and trade a live model-priced (Black-Scholes, 0DTE) option chain.
        Drag to pan, scroll to zoom, draw levels, and watch positions react to price + time decay.
      </p>

      <div className="panel" style={{ marginBottom: 16, display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div className="field" style={{ maxWidth: 110 }}>
          <label>Symbol</label>
          <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
        </div>
        <button className="btn primary" onClick={() => { setBack(0); load(symbol, 0); }}>LOAD</button>
        <button className="btn" onClick={() => { const b = back + 1; setBack(b); load(symbol, b); }}>◀ Older</button>
        <button className="btn" onClick={() => { const b = Math.max(0, back - 1); setBack(b); load(symbol, b); }} disabled={back === 0}>Newer ▶</button>
        <div className="field" style={{ maxWidth: 130 }}>
          <label>Quick pick</label>
          <select value={TICKERS.includes(symbol) ? symbol : ""} onChange={(e) => { const v = e.target.value; if (v) { setSymbol(v); setBack(0); load(v, 0); } }}>
            <option value="">— pick —</option>
            {TICKERS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="field" style={{ maxWidth: 80 }}>
          <label>IV</label>
          <input type="number" step="0.05" value={iv} onChange={(e) => setIv(Math.max(0.05, +e.target.value))} />
        </div>
        <div className="field" style={{ maxWidth: 80 }}>
          <label>Qty</label>
          <input type="number" value={qty} onChange={(e) => setQty(Math.max(1, Math.floor(+e.target.value)))} />
        </div>
      </div>

      {err && <div className="empty">{err}</div>}

      {data && cur && (
        <div className="replay-grid">
          <div>
            <div className="panel">
              <div className="replay-readout">
                <span className="mono" style={{ fontSize: 16 }}>{data.symbol}</span>
                <span className="dim">{data.date} · {fmtET(cur.t)} ET</span>
                <span className="mono">${S.toFixed(2)}</span>
                <span className="faint">bar {idx + 1}/{n} · {Math.round(minsToClose)}m to close</span>
              </div>

              <div className="charttools">
                <div className="seg">
                  <button className={`segbtn ${chartType === "candle" ? "on" : ""}`} onClick={() => setChartType("candle")}>Candles</button>
                  <button className={`segbtn ${chartType === "line" ? "on" : ""}`} onClick={() => setChartType("line")}>Line</button>
                </div>
                <div className="seg">
                  {(["cursor", "trend", "hline", "box"] as const).map((tl) => (
                    <button key={tl} className={`segbtn ${tool === tl ? "on" : ""}`} onClick={() => setTool(tl)} title={tl}>
                      {tl === "cursor" ? "✛" : tl === "trend" ? "╱" : tl === "hline" ? "—" : "▭"}
                    </button>
                  ))}
                </div>
                <button className="btn" onClick={() => { setShapes((s) => s.slice(0, -1)); setSelectedShape(null); }}>Undo</button>
                <button className="btn" onClick={() => { setShapes([]); setSelectedShape(null); }}>Clear</button>
                <button className="btn danger" disabled={selectedShape == null}
                  onClick={() => { if (selectedShape != null) { setShapes((s) => s.filter((_, i) => i !== selectedShape)); setSelectedShape(null); } }}>Delete sel</button>
              </div>

              <ReplayChart bars={bars} idx={idx} chartType={chartType} tool={tool} shapes={shapes} setShapes={setShapes} playing={playing} selected={selectedShape} setSelected={setSelectedShape} />

              <div className="replay-controls">
                <button className="btn primary" onClick={() => setPlaying((p) => !p)}>{playing ? "❚❚ Pause" : "▶ Play"}</button>
                <button className="btn" onClick={() => setIdx((i) => Math.min(n - 1, i + 1))}>Step ▶</button>
                <button className="btn" onClick={() => { setPlaying(false); setIdx(Math.min(20, n - 1)); }}>Reset</button>
                <label className="faint" style={{ fontSize: 12 }}>Speed {(1000 / speedMs).toFixed(1)} bars/s
                  <input type="range" min={60} max={1000} step={20} value={1060 - speedMs}
                    onChange={(e) => setSpeedMs(1060 - +e.target.value)} style={{ marginLeft: 8, verticalAlign: "middle" }} />
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
              <div className="empty">No open positions. Click a call or put price in the chain to open a ticket.</div>
            ) : (
              <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
                <table className="data">
                  <thead><tr><th>Type</th><th>Strike</th><th>Avg</th><th>Qty</th><th>Cost</th><th>Now</th><th>P/L</th><th></th></tr></thead>
                  <tbody>
                    {positions.map((p) => {
                      const now = bs(p.type, S, p.strike, T, iv);
                      const cost = p.entry * 100 * p.contracts;
                      const ppl = (now - p.entry) * 100 * p.contracts;
                      return (
                        <tr key={p.id}>
                          <td className={p.type === "call" ? "pos" : "neg"}>{p.type.toUpperCase()}</td>
                          <td>{p.strike}</td>
                          <td>${p.entry.toFixed(2)}</td>
                          <td>{p.contracts}</td>
                          <td>${cost.toFixed(0)}</td>
                          <td>${now.toFixed(2)}</td>
                          <td className={ppl >= 0 ? "pos" : "neg"}>{ppl >= 0 ? "+" : ""}${ppl.toFixed(0)}</td>
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
                      <td className="buyable call" onClick={() => openTicket("call", k, cp)}>{cp.toFixed(2)}</td>
                      <td className="faint">{dl.toFixed(2)}</td>
                      <td className="strike">{k}</td>
                      <td className="buyable put" onClick={() => openTicket("put", k, pp)}>{pp.toFixed(2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="faint" style={{ fontSize: 10, marginTop: 8 }}>Click a call/put price to open a buy ticket.</div>
          </div>
        </div>
      )}

      {ticket && (
        <div className="ticket-overlay" onClick={() => setTicket(null)}>
          <div className="ticket" onClick={(e) => e.stopPropagation()}>
            <div className="ticket-head">
              <span className={`mono ${ticket.type === "call" ? "pos" : "neg"}`}>BUY {ticket.type.toUpperCase()}</span>
              <span className="mono">{data.symbol} {ticket.strike}</span>
            </div>
            <div className="ticket-row"><span className="dim">Premium</span><span className="mono">${ticket.premium.toFixed(2)}</span></div>
            <div className="field" style={{ margin: "10px 0" }}>
              <label>Contracts</label>
              <input type="number" value={ticketQty} onChange={(e) => setTicketQty(Math.max(1, Math.floor(+e.target.value)))} />
            </div>
            <div className="ticket-row"><span className="dim">Total cost</span><span className="mono">${(ticket.premium * 100 * Math.max(1, Math.floor(ticketQty))).toFixed(2)}</span></div>
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button className="btn primary" style={{ flex: 1 }} onClick={confirmBuy}>CONFIRM BUY</button>
              <button className="btn" onClick={() => setTicket(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ================= Chart =================
function ReplayChart({ bars, idx, chartType, tool, shapes, setShapes, playing, selected, setSelected }:
  { bars: Bar[]; idx: number; chartType: "line" | "candle"; tool: string; shapes: Shape[]; setShapes: (fn: (s: Shape[]) => Shape[]) => void; playing: boolean; selected: number | null; setSelected: (n: number | null) => void }) {
  const W = 760, H = 360, mL = 6, mR = 54, mT = 8, mB = 22;
  const PW = W - mL - mR, PH = H - mT - mB;
  const svgRef = useRef<SVGSVGElement>(null);

  const [viewCount, setViewCount] = useState(90);
  const [viewStart, setViewStart] = useState(0);
  const [follow, setFollow] = useState(true);
  const [cross, setCross] = useState<{ x: number; y: number } | null>(null);
  const drag = useRef<{ x: number; y: number; startView: number; moved: boolean } | null>(null);
  const draw = useRef<{ i1: number; p1: number } | null>(null);
  const [preview, setPreview] = useState<Shape | null>(null);

  const vc = Math.max(20, Math.min(viewCount, Math.max(20, idx + 1)));
  const rightPad = Math.max(3, Math.round(vc * 0.12));   // empty space on the right ("extend")
  const slots = vc + rightPad;
  useEffect(() => { if (follow) setViewStart(Math.max(0, idx + 1 - vc)); }, [idx, vc, follow]);
  useEffect(() => { if (playing) setFollow(true); }, [playing]);   // Play snaps back to live
  const clampN = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
  function zoom(f: number) {
    const center = viewStart + vc / 2;
    const nc = clampN(Math.round(vc * f), 20, Math.max(20, idx + 1));
    setViewCount(nc); setFollow(false);
    setViewStart(clampN(Math.round(center - nc / 2), 0, Math.max(0, idx + 1 - nc)));
  }
  function fit() { setViewCount(Math.max(20, idx + 1)); setFollow(true); }
  const start = Math.max(0, Math.min(viewStart, Math.max(0, idx + 1 - vc)));
  const vis = bars.slice(start, Math.min(idx + 1, start + vc));
  if (vis.length < 2) return <div className="faint" style={{ height: H }}>…</div>;

  let hi = -Infinity, lo = Infinity;
  for (const b of vis) { hi = Math.max(hi, b.h); lo = Math.min(lo, b.l); }
  const padp = (hi - lo) * 0.08 || 1; hi += padp; lo -= padp;

  const xAbs = (i: number) => mL + ((i - start) + 0.5) / slots * PW;
  const yP = (p: number) => mT + (1 - (p - lo) / (hi - lo)) * PH;
  const iFromX = (px: number) => start + ((px - mL) / PW) * slots - 0.5;
  const pFromY = (py: number) => lo + (1 - (py - mT) / PH) * (hi - lo);
  const bw = Math.max(1, (PW / slots) * 0.62);

  function distToSeg(px: number, py: number, x1: number, y1: number, x2: number, y2: number) {
    const dx = x2 - x1, dy = y2 - y1; const len2 = dx * dx + dy * dy || 1;
    let t = ((px - x1) * dx + (py - y1) * dy) / len2; t = Math.max(0, Math.min(1, t));
    const cx = x1 + t * dx, cy = y1 + t * dy; return Math.hypot(px - cx, py - cy);
  }
  function hitTest(x: number, y: number): number | null {
    for (let i = shapes.length - 1; i >= 0; i--) {
      const sh = shapes[i];
      if (sh.tool === "hline") { if (Math.abs(y - yP(sh.p1)) < 6) return i; }
      else if (sh.tool === "box") {
        const x1 = xAbs(sh.i1), x2 = xAbs(sh.i2), y1 = yP(sh.p1), y2 = yP(sh.p2);
        if (x >= Math.min(x1, x2) - 4 && x <= Math.max(x1, x2) + 4 && y >= Math.min(y1, y2) - 4 && y <= Math.max(y1, y2) + 4) return i;
      } else { if (distToSeg(x, y, xAbs(sh.i1), yP(sh.p1), xAbs(sh.i2), yP(sh.p2)) < 6) return i; }
    }
    return null;
  }

  function toLocal(e: React.MouseEvent) {
    const r = svgRef.current!.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * W, y: ((e.clientY - r.top) / r.height) * H };
  }
  function onDown(e: React.MouseEvent) {
    const { x, y } = toLocal(e);
    if (tool === "cursor") { drag.current = { x, y, startView: start, moved: false }; }
    else { draw.current = { i1: iFromX(x), p1: pFromY(y) }; }
  }
  function onMove(e: React.MouseEvent) {
    const { x, y } = toLocal(e);
    setCross({ x, y });
    if (drag.current) {
      if (Math.abs(x - drag.current.x) > 3 || Math.abs(y - drag.current.y) > 3) {
        drag.current.moved = true; setFollow(false);
        const dIdx = ((x - drag.current.x) / PW) * slots;
        setViewStart(clampN(drag.current.startView - Math.round(dIdx), 0, Math.max(0, idx + 1 - vc)));
      }
    } else if (draw.current) {
      setPreview({ tool: tool as any, i1: draw.current.i1, p1: draw.current.p1, i2: iFromX(x), p2: pFromY(y) });
    }
  }
  function onUp(e: React.MouseEvent) {
    const hasE = !!(e && "clientX" in e);
    if (draw.current && hasE) {
      const { x, y } = toLocal(e);
      setShapes((s) => [...s, { tool: tool as any, i1: draw.current!.i1, p1: draw.current!.p1, i2: iFromX(x), p2: pFromY(y) }]);
      setSelected(null); setPreview(null);
    } else if (drag.current && !drag.current.moved && hasE) {
      const { x, y } = toLocal(e);
      setSelected(hitTest(x, y));
    }
    drag.current = null; draw.current = null;
  }
  function onWheel(e: React.WheelEvent) {
    const { x } = toLocal(e);
    const iAt = iFromX(x);
    const factor = e.deltaY > 0 ? 1.15 : 0.87;
    const nc = Math.max(20, Math.min(Math.round(vc * factor), bars.length));
    setViewCount(nc); setFollow(false);
    setViewStart(Math.max(0, Math.round(iAt - ((iAt - start) * nc) / vc)));
  }

  const priceTicks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4);
  const timeTicks: number[] = [];
  for (let k = 0; k < 6; k++) timeTicks.push(Math.round(start + (vc * k) / 5));
  const drawn = preview ? [...shapes, preview] : shapes;
  const last = vis[vis.length - 1];

  return (
    <div style={{ position: "relative" }}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", cursor: tool === "cursor" ? "grab" : "crosshair", userSelect: "none" }}
        onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={() => { onUp({} as any); setCross(null); }} onWheel={onWheel}>
        {priceTicks.map((p, i) => (
          <g key={i}>
            <line x1={mL} y1={yP(p)} x2={mL + PW} y2={yP(p)} stroke="var(--line)" strokeWidth="0.5" />
            <text x={mL + PW + 4} y={yP(p) + 3} fontSize="9" fill="var(--ink-faint)" fontFamily="var(--mono)">{p.toFixed(2)}</text>
          </g>
        ))}
        {timeTicks.map((i, k) => (bars[i] ? (
          <text key={k} x={xAbs(i)} y={H - 6} fontSize="9" fill="var(--ink-faint)" textAnchor="middle" fontFamily="var(--mono)">{fmtET(bars[i].t)}</text>
        ) : null))}

        {chartType === "line" ? (
          <path d={vis.map((b, i) => `${i === 0 ? "M" : "L"} ${xAbs(start + i).toFixed(1)} ${yP(b.c).toFixed(1)}`).join(" ")}
            fill="none" stroke={last.c >= vis[0].c ? "var(--cyan)" : "var(--coral)"} strokeWidth="1.4" />
        ) : (
          vis.map((b, i) => {
            const x = xAbs(start + i); const up = b.c >= b.o;
            const col = up ? "var(--cyan)" : "var(--coral)";
            const yo = yP(b.o), yc = yP(b.c);
            return (
              <g key={i}>
                <line x1={x} y1={yP(b.h)} x2={x} y2={yP(b.l)} stroke={col} strokeWidth="1" />
                <rect x={x - bw / 2} y={Math.min(yo, yc)} width={bw} height={Math.max(1, Math.abs(yc - yo))} fill={col} />
              </g>
            );
          })
        )}

        {drawn.map((sh, i) => {
          if (sh.tool === "hline") return <g key={i}><line x1={mL} y1={yP(sh.p1)} x2={mL + PW} y2={yP(sh.p1)} stroke="var(--amber)" strokeWidth="1" strokeDasharray="4 3" /><text x={mL + PW + 4} y={yP(sh.p1) + 3} fontSize="9" fill="var(--amber)" fontFamily="var(--mono)">{sh.p1.toFixed(2)}</text></g>;
          if (sh.tool === "box") return <rect key={i} x={Math.min(xAbs(sh.i1), xAbs(sh.i2))} y={Math.min(yP(sh.p1), yP(sh.p2))} width={Math.abs(xAbs(sh.i2) - xAbs(sh.i1))} height={Math.abs(yP(sh.p2) - yP(sh.p1))} fill="rgba(111,99,166,0.12)" stroke="var(--violet)" strokeWidth="1" />;
          return <line key={i} x1={xAbs(sh.i1)} y1={yP(sh.p1)} x2={xAbs(sh.i2)} y2={yP(sh.p2)} stroke="var(--violet)" strokeWidth="1.4" />;
        })}

        {selected != null && shapes[selected] && (() => {
          const sh = shapes[selected];
          if (sh.tool === "hline") return <line x1={mL} y1={yP(sh.p1)} x2={mL + PW} y2={yP(sh.p1)} stroke="var(--cyan)" strokeWidth="2.4" />;
          if (sh.tool === "box") return <rect x={Math.min(xAbs(sh.i1), xAbs(sh.i2))} y={Math.min(yP(sh.p1), yP(sh.p2))} width={Math.abs(xAbs(sh.i2) - xAbs(sh.i1))} height={Math.abs(yP(sh.p2) - yP(sh.p1))} fill="none" stroke="var(--cyan)" strokeWidth="2.4" />;
          return <g><line x1={xAbs(sh.i1)} y1={yP(sh.p1)} x2={xAbs(sh.i2)} y2={yP(sh.p2)} stroke="var(--cyan)" strokeWidth="2.6" /><circle cx={xAbs(sh.i1)} cy={yP(sh.p1)} r="4" fill="var(--cyan)" /><circle cx={xAbs(sh.i2)} cy={yP(sh.p2)} r="4" fill="var(--cyan)" /></g>;
        })()}

        <line x1={mL} y1={yP(last.c)} x2={mL + PW} y2={yP(last.c)} stroke="var(--ink-faint)" strokeWidth="0.6" strokeDasharray="2 2" />
        {cross && (
          <g>
            <line x1={cross.x} y1={mT} x2={cross.x} y2={mT + PH} stroke="var(--ink-faint)" strokeWidth="0.5" />
            <line x1={mL} y1={cross.y} x2={mL + PW} y2={cross.y} stroke="var(--ink-faint)" strokeWidth="0.5" />
            <rect x={mL + PW} y={cross.y - 7} width={mR} height={14} fill="var(--panel-2)" />
            <text x={mL + PW + 4} y={cross.y + 3} fontSize="9" fill="var(--ink)" fontFamily="var(--mono)">{pFromY(cross.y).toFixed(2)}</text>
          </g>
        )}
      </svg>
      <div className="zoomcluster">
        <button className="btn zbtn" onClick={() => zoom(0.8)} title="Zoom in">＋</button>
        <button className="btn zbtn" onClick={() => zoom(1.25)} title="Zoom out">－</button>
        <button className="btn zbtn" onClick={fit} title="Fit all">Fit</button>
      </div>
      {!follow && <button className="btn followbtn" onClick={() => { setFollow(true); }}>⟳ Follow</button>}
    </div>
  );
}
