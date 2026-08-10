"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function Saved() {
  const [rows, setRows] = useState<any[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try { setRows((await api.savedList()).saved || []); } catch (e: any) { setErr(e.message); }
  }
  async function refresh() {
    setBusy(true); setErr(null);
    try { setRows((await api.refreshSaved()).saved || []); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  async function remove(id: number) {
    try { await api.deleteSaved(id); load(); } catch (e: any) { setErr(e.message); }
  }
  useEffect(() => { load(); }, []);

  return (
    <>
      <div className="pagehead">
        <div>
          <div className="eyebrow">Tracked ideas</div>
          <h1>Saved</h1>
        </div>
        <button className="btn primary" onClick={refresh} disabled={busy}>
          {busy ? "REFRESHING…" : "REFRESH OUTCOMES"}
        </button>
      </div>
      <p className="pagesub">
        Stocks you saved from the scanner. Refresh pulls the latest price and marks whether
        the reversal you were aiming for has been hit yet.
      </p>

      {err && <div className="empty">Backend unreachable ({err}).</div>}
      {!err && rows.length === 0 && (
        <div className="empty">Nothing saved yet. Hit ☆ Save on a candidate in the Scanner.</div>
      )}

      {rows.length > 0 && (
        <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
          <table className="data">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Saved</th>
                <th>Entry</th>
                <th>Target</th>
                <th>Est. reversal</th>
                <th>Best so far</th>
                <th>Last</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td style={{ fontWeight: 600 }}>{r.symbol}</td>
                  <td className="dim">{r.saved_at ? r.saved_at.slice(0, 10) : "—"}</td>
                  <td>{r.entry_price != null ? `$${r.entry_price.toFixed(2)}` : "—"}</td>
                  <td>{r.target_price != null ? `$${r.target_price.toFixed(2)}` : "—"}</td>
                  <td className="pos">{r.estimated_reversal_pct != null ? `+${r.estimated_reversal_pct}%` : "—"}</td>
                  <td className={(r.best_return_pct ?? 0) >= 0 ? "pos" : "neg"}>
                    {r.best_return_pct != null ? `${r.best_return_pct >= 0 ? "+" : ""}${r.best_return_pct.toFixed(2)}%` : "—"}
                  </td>
                  <td>{r.last_price != null ? `$${r.last_price.toFixed(2)}` : "—"}</td>
                  <td><span className={`savestatus ${r.status}`}>{r.status.toUpperCase()}</span></td>
                  <td><button className="btn danger" onClick={() => remove(r.id)}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
