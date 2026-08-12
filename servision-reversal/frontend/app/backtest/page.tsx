"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Ribbon } from "@/components/Ribbon";

export default function Backtest() {
  const [res, setRes] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState(0);
  const [tickers, setTickers] = useState("");
  const [maxT, setMaxT] = useState(5);
  const [tickMsg, setTickMsg] = useState<string | null>(null);

  useEffect(() => {
    api.backtestTickers().then((d) => { setTickers(d.tickers || ""); setMaxT(d.max || 5); }).catch(() => {});
  }, []);

  async function saveTickers() {
    setTickMsg(null);
    try {
      const d = await api.setBacktestTickers(tickers, maxT);
      if (d.ok) { setTickers(d.tickers); setMaxT(d.max); setTickMsg("saved ✓"); }
      else setTickMsg(d.error || "error");
    } catch (e: any) { setTickMsg(e.message); }
  }

  const [optimizing, setOptimizing] = useState(false);
  const [opt, setOpt] = useState<any>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  async function optimize() {
    setOptimizing(true); setErr(null); setOpt(null); setSavedMsg(null);
    try {
      const r = await api.optimize();
      if (r.available) setOpt(r); else setErr(r.error || "optimize failed");
    } catch (e: any) { setErr(e.message); } finally { setOptimizing(false); }
  }
  async function saveOpt() {
    if (!opt) return;
    try {
      const label = "OPT-" + new Date().toISOString().slice(5, 16).replace(/[-:T]/g, "");
      await api.createVersion(label, opt.best_config, "auto-optimized");
      setSavedMsg("saved as new version ✓");
    } catch (e: any) { setSavedMsg(e.message); }
  }

  async function run() {
    setLoading(true);
    setErr(null);
    try {
      const r = await api.backtest({ label: "manual" });
      setRes(r);
      setSel(0);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  const s = res?.strategy;
  const rm = res?.reversal_model;
  const per: any[] = res?.per_stock || [];

  return (
    <>
      <div className="pagehead">
        <div>
          <div className="eyebrow">Historical replay · real data</div>
          <h1>Backtest</h1>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={optimize} disabled={optimizing}>
            {optimizing ? "OPTIMIZING…" : "AUTO-OPTIMIZE"}
          </button>
          <button className="btn primary" onClick={run} disabled={loading}>
            {loading ? "RUNNING…" : "RUN BACKTEST"}
          </button>
        </div>
      </div>
      <p className="pagesub">
        Replays the same scoring code over real recent intraday sessions with no
        look-ahead, then learns how big a reversal each kind of drop actually produced.
      </p>
      <Ribbon text="Research only. Reversal tiers are measured from real outcomes, not predictions. Options aims are next-Friday research signals — never orders." />

      {res?.first_candle && (
        <div className="notice" style={{ marginBottom: 22 }}>
          <div className="notice-head"><span className="mono" style={{ color: "var(--cyan)" }}>FIRST CANDLE RULE</span></div>
          <p>
            09:30–09:45 opening range → first 5-min Fair Value Gap that breaks the range →
            limit entry at the gap, stop at FVG candle&nbsp;1, fixed 2:1 target. One trade per session.
          </p>
        </div>
      )}

      <div className="panel" style={{ marginBottom: 22 }}>
        <div className="dim" style={{ fontSize: 12, marginBottom: 10 }}>Watchlist — stocks to backtest</div>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div className="field" style={{ flex: 1, minWidth: 240 }}>
            <label>Tickers (comma-separated)</label>
            <input value={tickers} onChange={(e) => setTickers(e.target.value)} placeholder="NBIS,COIN,SMCI,TSLA,AMD" />
          </div>
          <div className="field" style={{ maxWidth: 90 }}>
            <label>Max</label>
            <input type="number" value={maxT} onChange={(e) => setMaxT(+e.target.value)} />
          </div>
          <button className="btn primary" onClick={saveTickers}>SAVE</button>
          {tickMsg && <span className="mono" style={{ fontSize: 12, color: "var(--cyan)" }}>{tickMsg}</span>}
        </div>
        <div className="faint" style={{ fontSize: 11, marginTop: 8 }}>
          Each ticker is one data call per run. Saved to the app — no redeploy needed.
        </div>
      </div>

      {opt && (
        <>
          <div className="section-title">Auto-optimize result</div>
          <div className="panel" style={{ marginBottom: 22 }}>
            <div className="grid cols-2">
              <div>
                <div className="dim" style={{ fontSize: 12, marginBottom: 6 }}>Before (active version)</div>
                <MetricsMini m={opt.base_metrics} />
              </div>
              <div>
                <div className="dim" style={{ fontSize: 12, marginBottom: 6 }}>After (best found)</div>
                <MetricsMini m={opt.best_metrics} />
              </div>
            </div>
            <div className="faint" style={{ fontSize: 12, marginTop: 12 }}>
              {opt.improved
                ? "Changed: " + Object.entries(opt.changed_params || {}).map(([k, v]) => `${k}=${v}`).join(", ")
                : "No change beat the current settings on this data."}
            </div>
            <div style={{ marginTop: 12, display: "flex", gap: 10, alignItems: "center" }}>
              <button className="btn primary" onClick={saveOpt} disabled={!opt.improved}>SAVE AS NEW VERSION</button>
              {savedMsg && <span className="mono" style={{ fontSize: 12, color: "var(--cyan)" }}>{savedMsg}</span>}
            </div>
          </div>
        </>
      )}

      {err && <div className="empty">Backend unreachable ({err}).</div>}

      {res && res.available === false && (
        <div className="notice closed">
          <div className="notice-head">
            <span className="mono">REAL DATA NOT CONNECTED</span>
          </div>
          <p>{res.error}</p>
          {res.how && <p className="mono" style={{ fontSize: 12, color: "var(--cyan)" }}>{res.how}</p>}
        </div>
      )}

      {res && res.available === false && res.meta && (
        <div className="panel" style={{ marginBottom: 22 }}>
          <div className="dim" style={{ fontSize: 12, marginBottom: 8 }}>Loader diagnostics</div>
          <div className="faint" style={{ fontSize: 12, lineHeight: 1.8 }}>
            {(res.meta.per_ticker || []).map((t: any, i: number) => (
              <div key={i}>
                {t.symbol}: worst drop {t.worst_drawdown_pct}% over {t.sessions_scanned} sessions · {t.events_added} event(s)
              </div>
            ))}
            {(res.meta.skipped || []).map((t: any, i: number) => (
              <div key={"s" + i}>{t.symbol}: skipped — {t.reason}</div>
            ))}
          </div>
        </div>
      )}

      {res?.meta && (
        <div className="metastrip">
          <span className="mono">SOURCE {String(res.meta.source).toUpperCase()}</span>
          <span>{res.meta.events} events</span>
          <span className="chips">
            {(res.meta.used || []).map((u: any, i: number) => (
              <span key={i} className="tickerchip">
                {u.symbol} <span className="neg">{u.gap_pct}%</span> <span className="faint">{u.date}</span>
              </span>
            ))}
          </span>
          {(res.meta.skipped || []).length > 0 && (
            <span className="faint" style={{ fontSize: 11 }}>
              skipped: {res.meta.skipped.map((x: any) => x.symbol).join(", ")}
            </span>
          )}
        </div>
      )}

      {res?.insights && res.insights.length > 0 && (
        <>
          <div className="section-title">Recommendations</div>
          <div className="panel" style={{ marginBottom: 6 }}>
            {res.insights.map((it: any, i: number) => (
              <div key={i} className={`insight ${it.level}`}>
                <span className="dot" />
                <span>{it.text}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {!res?.first_candle && rm && rm.tiers && (
        <>
          <div className="section-title">Learned reversal tiers → next-Friday options aim</div>
          <p className="dim" style={{ fontSize: 12, margin: "-4px 0 12px", maxWidth: "70ch" }}>
            {rm.method} Expiry basis: <b>{rm.expiry_next_friday}</b>.
          </p>
          <div className="grid cols-3">
            {rm.tiers.map((t: any, i: number) => (
              <TierCard key={i} t={t} />
            ))}
            {rm.tiers.length === 0 && (
              <div className="empty" style={{ gridColumn: "1 / -1" }}>
                No qualifying gap-down events in the loaded window yet.
              </div>
            )}
          </div>
        </>
      )}

      {res?.equity_curve && res.equity_curve.length > 1 && (
        <>
          <div className="section-title">Equity curve (compounded, qualified trades)</div>
          <div className="panel">
            <EquityCurve pts={res.equity_curve.map((p: any) => p.equity)} />
          </div>
        </>
      )}

      {s && (
        <>
          <div className="section-title">Strategy metrics</div>
          <div className="grid cols-4">
            <Tile label="Qualified trades" value={`${s.trades}`} />
            <Tile label="Win rate" value={s.win_rate != null ? `${s.win_rate}%` : "—"} />
            <Tile label="Avg return" value={fmtPct(s.avg_return)} tone={sign(s.avg_return)} />
            <Tile label="Expectancy" value={fmtPct(s.expected_value)} tone={sign(s.expected_value)} />
            <Tile label="Profit factor" value={s.profit_factor != null ? s.profit_factor.toFixed(2) : "n/a"} />
            <Tile label="Max drawdown" value={fmtPct(s.max_drawdown)} tone="neg" />
            <Tile label="Avg winner" value={fmtPct(s.avg_winner)} tone="pos" />
            <Tile label="Avg loser" value={fmtPct(s.avg_loser)} tone="neg" />
            {res?.first_candle && <Tile label="Avg R" value={(s as any).avg_R != null ? `${(s as any).avg_R}R` : "—"} tone={sign((s as any).avg_R)} />}
            {res?.first_candle && <Tile label="Total R" value={(s as any).total_R != null ? `${(s as any).total_R}R` : "—"} tone={sign((s as any).total_R)} />}
          </div>
        </>
      )}

      {per.length > 0 && (
        <>
          <div className="section-title">Per-stock replay</div>
          <div className="drill">
            <div className="drill-list">
              {per.map((p, i) => (
                <button
                  key={i}
                  className={`drill-item ${i === sel ? "active" : ""}`}
                  onClick={() => setSel(i)}
                >
                  <span className="mono">{p.symbol}</span>
                  <span className="faint">{p.date}</span>
                  <span className="neg">{p.gap_pct}%</span>
                  {p.qualified ? (
                    <span className={`mono ${sign(p.return_pct)}`}>{fmtPct(p.return_pct)}</span>
                  ) : (
                    <span className="faint" style={{ fontSize: 10 }}>no entry</span>
                  )}
                </button>
              ))}
            </div>
            <div className="drill-chart panel">
              {per[sel] && <IntradayChart p={per[sel]} />}
            </div>
          </div>
        </>
      )}

      {s && (
        <>
          <div className="section-title">Controls (baselines to beat)</div>
          <div className="grid cols-2">
            <ControlPanel name="Buy the dip (no confirmation)" m={res.controls.buy_the_dip} />
            <ControlPanel name="VWAP reclaim only (no fundamentals)" m={res.controls.vwap_only} />
          </div>
        </>
      )}

      {!res && !err && (
        <div className="empty">Run a backtest to pull real recent sessions and measure reversal tiers.</div>
      )}
    </>
  );
}

function TierCard({ t }: { t: any }) {
  const aim = t.option_aim || {};
  return (
    <div className="tiercard">
      <div className="tiercard-head">
        <span className="tier-label">{t.tier}</span>
        <span className={`conf ${t.confidence}`}>{String(t.confidence).toUpperCase()} · n={t.n}</span>
      </div>
      <div className="tier-expected">
        Median reversal by close <b className={sign(t.median_reversion_pct)}>{fmtPct(t.median_reversion_pct)}</b>
      </div>
      <div className="distline">
        <span className="faint">p25 {fmtPct(t.p25_reversion_pct)}</span>
        <span className="faint">p75 {fmtPct(t.p75_reversion_pct)}</span>
      </div>
      <div className="aim">
        <div className="aim-row">
          <span className="mono cyan">{aim.direction}</span>
          <span className="faint">exp {aim.expiry_next_friday}</span>
        </div>
        <div className="aim-row">
          <span>aim <b className="pos">{fmtPct(aim.expected_move_pct)}</b></span>
          <span className="faint">stretch {fmtPct(aim.stretch_move_pct)}</span>
        </div>
      </div>
      <div className="tier-foot">Positive by close {t.positive_rate_pct}% · from {t.n} real event{t.n === 1 ? "" : "s"}</div>
    </div>
  );
}

function EquityCurve({ pts }: { pts: number[] }) {
  const w = 900, h = 160, pad = 8;
  if (!pts.length) return null;
  const min = Math.min(...pts), max = Math.max(...pts);
  const rng = max - min || 1;
  const x = (i: number) => pad + (i / (pts.length - 1 || 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - min) / rng) * (h - 2 * pad);
  const d = pts.map((v, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const up = pts[pts.length - 1] >= pts[0];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" preserveAspectRatio="none" style={{ display: "block" }}>
      <line x1={pad} y1={y(1)} x2={w - pad} y2={y(1)} stroke="var(--line)" strokeDasharray="3 3" />
      <path d={d} fill="none" stroke={up ? "var(--cyan)" : "var(--coral)"} strokeWidth="2" />
    </svg>
  );
}

function IntradayChart({ p }: { p: any }) {
  const w = 900, h = 300, pad = 30;
  const series: { t: number; c: number }[] = p.series || [];
  if (series.length < 2) return <div className="dim">No intraday data.</div>;
  const cs = series.map((b) => b.c);
  const lines = [p.prev_close, p.entry_price, p.stop_price, p.target1, p.target2].filter((v) => v != null);
  const min = Math.min(...cs, ...lines), max = Math.max(...cs, ...lines);
  const rng = max - min || 1;
  const x = (i: number) => pad + (i / (series.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - min) / rng) * (h - 2 * pad);
  const d = series.map((b, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(b.c).toFixed(1)}`).join(" ");
  const HLine = ({ v, color, label }: { v?: number; color: string; label: string }) =>
    v == null ? null : (
      <g>
        <line x1={pad} y1={y(v)} x2={w - pad} y2={y(v)} stroke={color} strokeDasharray="4 3" opacity="0.8" />
        <text x={w - pad + 2} y={y(v) + 3} fontSize="10" fill={color} fontFamily="var(--mono)">{label} {v}</text>
      </g>
    );
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <span className="mono" style={{ fontSize: 15 }}>{p.symbol}</span>
        <span className="faint">{p.date} · gap <span className="neg">{p.gap_pct}%</span>{p.qualified && p.score != null ? ` · score ${p.score}` : ""}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" style={{ display: "block" }}>
        <path d={d} fill="none" stroke="var(--ink)" strokeWidth="1.5" />
        <HLine v={p.prev_close} color="var(--ink-faint)" label="prev" />
        <HLine v={p.entry_price} color="var(--cyan)" label="entry" />
        <HLine v={p.stop_price} color="var(--coral)" label="stop" />
        <HLine v={p.target1} color="var(--amber)" label="t1" />
        <HLine v={p.target2} color="var(--amber)" label="t2" />
      </svg>
      {p.qualified ? (
        <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>
          Entered {p.entry_price} → exit {p.exit_price} ({p.exit_reason}) ·{" "}
          <span className={sign(p.return_pct)}>{fmtPct(p.return_pct)}</span>
        </div>
      ) : (
        <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>Never reached the QUALIFIED gate — no entry.</div>
      )}
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className={`value ${tone || ""}`}>{value}</div>
    </div>
  );
}

function MetricsMini({ m }: { m: any }) {
  if (!m) return <div className="faint">—</div>;
  return (
    <div className="grid cols-3">
      <Tile label="Trades" value={`${m.trades ?? "—"}`} />
      <Tile label="Win rate" value={m.win_rate != null ? `${m.win_rate}%` : "—"} />
      <Tile label="Avg ret" value={fmtPct(m.avg_return)} tone={sign(m.avg_return)} />
    </div>
  );
}

function ControlPanel({ name, m }: { name: string; m: any }) {
  return (
    <div className="panel">
      <div className="dim" style={{ fontSize: 12, marginBottom: 10 }}>{name}</div>
      <div className="grid cols-3">
        <Tile label="Trades" value={`${m.trades}`} />
        <Tile label="Win rate" value={m.win_rate != null ? `${m.win_rate}%` : "—"} />
        <Tile label="Avg ret" value={fmtPct(m.avg_return)} tone={sign(m.avg_return)} />
      </div>
    </div>
  );
}

function fmtPct(v?: number) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}
function sign(v?: number) {
  if (v == null) return "";
  return v >= 0 ? "pos" : "neg";
}
