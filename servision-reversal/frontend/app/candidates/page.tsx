"use client";
import { useEffect, useState } from "react";
import { api, Candidate } from "@/lib/api";
import { Ribbon } from "@/components/Ribbon";

export default function Candidates() {
  const [cands, setCands] = useState<Candidate[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.candidates().then((d) => setCands(d.candidates || [])).catch((e) => setErr(e.message));
  }, []);

  return (
    <>
      <div className="pagehead">
        <div>
          <div className="eyebrow">Full universe</div>
          <h1>All candidates</h1>
        </div>
      </div>
      <p className="pagesub">Every symbol from the latest scan, ranked by reversal score.</p>
      <Ribbon />

      {err && <div className="empty">Backend unreachable ({err}).</div>}
      {!err && cands.length === 0 && <div className="empty">No scan data yet — run a scan from the Scanner tab.</div>}

      {cands.length > 0 && (
        <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
          <table className="data">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Score</th>
                <th>Status</th>
                <th>Move</th>
                <th>Vol</th>
                <th>VWAP</th>
                <th>H-Low</th>
                <th>Reclaim</th>
                <th>Catalyst</th>
              </tr>
            </thead>
            <tbody>
              {cands.map((c) => (
                <tr key={c.symbol}>
                  <td style={{ fontWeight: 600 }}>{c.symbol}</td>
                  <td>{c.total.toFixed(0)}</td>
                  <td>
                    <span className={`statusbadge ${c.status}`}>{c.status}</span>
                  </td>
                  <td className={(c.move_pct ?? 0) < 0 ? "neg" : "pos"}>
                    {c.move_pct != null ? `${c.move_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td>{c.volume_ratio != null ? `${c.volume_ratio.toFixed(1)}x` : "—"}</td>
                  <td className={(c.vwap_distance_pct ?? 0) < 0 ? "neg" : "pos"}>
                    {c.vwap_distance_pct != null ? `${c.vwap_distance_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td>{c.higher_low ? "✓" : "·"}</td>
                  <td>{c.vwap_reclaim ? "✓" : "·"}</td>
                  <td className="dim">{c.catalyst || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
