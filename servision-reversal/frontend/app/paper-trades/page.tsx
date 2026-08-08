"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Ribbon } from "@/components/Ribbon";

type Trade = {
  id: number;
  symbol: string;
  setup: string;
  instrument: string;
  entry_price: number;
  stop_price: number;
  target1: number;
  target2: number;
  status: string;
  exit_price?: number;
  exit_reason?: string;
  return_pct?: number;
  score_at_entry?: number;
};

export default function PaperTrades() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.paperTrades().then((d) => setTrades(d.paper_trades || [])).catch((e) => setErr(e.message));
  }, []);

  const open = trades.filter((t) => t.status === "open");
  const closed = trades.filter((t) => t.status === "closed");

  return (
    <>
      <div className="pagehead">
        <div>
          <div className="eyebrow">Simulation ledger</div>
          <h1>Paper trades</h1>
        </div>
      </div>
      <p className="pagesub">
        Hypothetical setups the engine recorded when a candidate qualified. These are
        simulations for measurement — never orders, never recommendations.
      </p>
      <Ribbon text="Every row is a QUALIFIED PAPER-TRADE SETUP. Outcomes are simulated with modelled slippage and a conservative stop-first fill assumption." />

      {err && <div className="empty">Backend unreachable ({err}).</div>}
      {!err && trades.length === 0 && (
        <div className="empty">No paper trades yet. They appear when a scan produces a QUALIFIED score inside the entry window.</div>
      )}

      {open.length > 0 && (
        <>
          <div className="section-title">Open · {open.length}</div>
          <TradeTable rows={open} showOutcome={false} />
        </>
      )}
      {closed.length > 0 && (
        <>
          <div className="section-title">Closed · {closed.length}</div>
          <TradeTable rows={closed} showOutcome={true} />
        </>
      )}
    </>
  );
}

function TradeTable({ rows, showOutcome }: { rows: Trade[]; showOutcome: boolean }) {
  return (
    <div className="panel" style={{ padding: 0, overflow: "hidden", marginBottom: 20 }}>
      <table className="data">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Setup</th>
            <th>Score</th>
            <th>Entry</th>
            <th>Stop</th>
            <th>T1</th>
            <th>T2</th>
            {showOutcome && <th>Exit</th>}
            {showOutcome && <th>Reason</th>}
            {showOutcome && <th>Return</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.id}>
              <td style={{ fontWeight: 600 }}>{t.symbol}</td>
              <td className="dim">{t.setup}</td>
              <td>{t.score_at_entry?.toFixed(0) ?? "—"}</td>
              <td>${t.entry_price?.toFixed(2)}</td>
              <td className="neg">${t.stop_price?.toFixed(2)}</td>
              <td className="pos">${t.target1?.toFixed(2)}</td>
              <td className="pos">${t.target2?.toFixed(2)}</td>
              {showOutcome && <td>{t.exit_price != null ? `$${t.exit_price.toFixed(2)}` : "—"}</td>}
              {showOutcome && <td className="dim">{t.exit_reason || "—"}</td>}
              {showOutcome && (
                <td className={(t.return_pct ?? 0) >= 0 ? "pos" : "neg"}>
                  {t.return_pct != null ? `${t.return_pct >= 0 ? "+" : ""}${t.return_pct.toFixed(2)}%` : "—"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
