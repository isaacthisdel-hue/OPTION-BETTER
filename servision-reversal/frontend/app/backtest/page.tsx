"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Ribbon } from "@/components/Ribbon";

type Metrics = {
  trades: number;
  insufficient_sample?: boolean;
  win_rate?: number;
  avg_return?: number;
  median_return?: number;
  avg_winner?: number;
  avg_loser?: number;
  profit_factor?: number | null;
  max_drawdown?: number;
  sharpe_like?: number;
  expected_value?: number;
};

export default function Backtest() {
  const [res, setRes] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setErr(null);
    try {
      setRes(await api.backtest({ label: "manual" }));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  const s: Metrics | undefined = res?.strategy;

  return (
    <>
      <div className="pagehead">
        <div>
          <div className="eyebrow">Historical replay</div>
          <h1>Backtest</h1>
        </div>
        <button className="btn primary" onClick={run} disabled={loading}>
          {loading ? "RUNNING…" : "RUN BACKTEST"}
        </button>
      </div>
      <p className="pagesub">
        Replays the same scoring code over historical events with no look-ahead:
        indicators only see past bars, fundamentals only after they were public,
        outcomes only from later bars. Controls show whether the rules beat naive baselines.
      </p>
      <Ribbon text="Ships with a synthetic sample so the pipeline runs immediately. Wire in a real historical loader before trusting any number here." />

      {err && <div className="empty">Backend unreachable ({err}).</div>}

      {s && (
        <>
          {s.insufficient_sample && (
            <div className="ribbon" style={{ borderColor: "rgba(229,105,95,0.4)", color: "var(--coral)", background: "rgba(229,105,95,0.08)" }}>
              <span className="mono" style={{ color: "var(--coral)" }}>SMALL SAMPLE</span>
              <span>Only {s.trades} trades. Metrics are noise at this size — don&apos;t conclude anything yet.</span>
            </div>
          )}

          <div className="section-title">Strategy</div>
          <div className="grid cols-4">
            <Tile label="Trades" value={`${s.trades}`} />
            <Tile label="Win rate" value={s.win_rate != null ? `${s.win_rate}%` : "—"} />
            <Tile label="Avg return" value={fmtPct(s.avg_return)} tone={sign(s.avg_return)} />
            <Tile label="Expectancy" value={fmtPct(s.expected_value)} tone={sign(s.expected_value)} />
            <Tile label="Avg winner" value={fmtPct(s.avg_winner)} tone="pos" />
            <Tile label="Avg loser" value={fmtPct(s.avg_loser)} tone="neg" />
            <Tile label="Profit factor" value={s.profit_factor != null ? s.profit_factor.toFixed(2) : "∞ / n/a"} />
            <Tile label="Max drawdown" value={fmtPct(s.max_drawdown)} tone="neg" />
          </div>

          <div className="section-title">Controls (baselines to beat)</div>
          <div className="grid cols-2">
            <ControlPanel name="Buy the dip (no confirmation)" m={res.controls.buy_the_dip} />
            <ControlPanel name="VWAP reclaim only (no fundamentals)" m={res.controls.vwap_only} />
          </div>

          <div className="section-title">Breakdowns</div>
          <div className="grid cols-2">
            {Object.entries(res.breakdowns).map(([k, v]) => (
              <BreakdownPanel key={k} title={k.replace(/_/g, " ")} buckets={v as Record<string, Metrics>} />
            ))}
          </div>
        </>
      )}

      {!s && !err && <div className="empty">Run a backtest to see strategy metrics, controls, and per-bucket breakdowns.</div>}
    </>
  );
}

function Tile({ label, value, tone, foot }: { label: string; value: string; tone?: string; foot?: string }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className={`value ${tone || ""}`}>{value}</div>
      {foot && <div className="foot">{foot}</div>}
    </div>
  );
}

function ControlPanel({ name, m }: { name: string; m: Metrics }) {
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

function BreakdownPanel({ title, buckets }: { title: string; buckets: Record<string, Metrics> }) {
  return (
    <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
      <div className="dim" style={{ fontSize: 12, padding: "12px 14px", borderBottom: "1px solid var(--line)" }}>
        {title}
      </div>
      <table className="data">
        <thead>
          <tr>
            <th>Bucket</th>
            <th>Trades</th>
            <th>Win %</th>
            <th>Avg ret</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(buckets).map(([b, m]) => (
            <tr key={b}>
              <td>{b}</td>
              <td>{m.trades}</td>
              <td>{m.win_rate != null ? `${m.win_rate}%` : "—"}</td>
              <td className={sign(m.avg_return)}>{fmtPct(m.avg_return)}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
