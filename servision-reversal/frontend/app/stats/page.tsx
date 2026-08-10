"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Ribbon } from "@/components/Ribbon";

export default function Stats() {
  const [stats, setStats] = useState<any>(null);
  const [proj, setProj] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [capital, setCapital] = useState(10000);
  const [tpd, setTpd] = useState(2);
  const [days, setDays] = useState(5);

  async function loadProjection() {
    try {
      setProj(await api.projection(capital, tpd, days));
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    api.stats().then(setStats).catch((e) => setErr(e.message));
    loadProjection();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div className="pagehead">
        <div>
          <div className="eyebrow">Track record</div>
          <h1>Statistics</h1>
        </div>
      </div>
      <p className="pagesub">
        Aggregate performance of the ledger, and a forward projection from those results.
      </p>
      <Ribbon />

      {err && <div className="empty">Backend unreachable ({err}).</div>}

      {stats && stats.trades === 0 && (
        <div className="empty">No closed trades yet — statistics appear once trades resolve.</div>
      )}

      {stats && stats.trades > 0 && (
        <>
          <div className="section-title">Ledger · {stats.trades} closed</div>
          <div className="grid cols-4">
            <div className="tile"><div className="label">Win rate</div><div className="value">{stats.win_rate}%</div></div>
            <div className="tile"><div className="label">Avg return</div><div className={`value ${stats.avg_return >= 0 ? "pos" : "neg"}`}>{stats.avg_return >= 0 ? "+" : ""}{stats.avg_return}%</div></div>
            <div className="tile"><div className="label">Expectancy</div><div className={`value ${stats.expected_value >= 0 ? "pos" : "neg"}`}>{stats.expected_value >= 0 ? "+" : ""}{stats.expected_value}%</div></div>
            <div className="tile"><div className="label">Return σ</div><div className="value">{stats.return_stdev}%</div></div>
          </div>
        </>
      )}

      <div className="section-title">Estimated revenue</div>
      <div className="panel">
        <p className="dim" style={{ fontSize: 12, marginTop: 0 }}>
          Projected from your tracked expectancy over the assumptions below.
        </p>
        <div className="grid cols-3" style={{ marginBottom: 16 }}>
          <div className="field">
            <label>Capital ($)</label>
            <input type="number" value={capital} onChange={(e) => setCapital(+e.target.value)} />
          </div>
          <div className="field">
            <label>Trades / day</label>
            <input type="number" value={tpd} onChange={(e) => setTpd(+e.target.value)} />
          </div>
          <div className="field">
            <label>Days</label>
            <input type="number" value={days} onChange={(e) => setDays(+e.target.value)} />
          </div>
        </div>
        <button className="btn" onClick={loadProjection}>RECALCULATE</button>

        {proj && !proj.available && (
          <div className="empty" style={{ marginTop: 16 }}>{proj.note}</div>
        )}

        {proj && proj.available && (
          <div style={{ marginTop: 18 }}>
            <div className="grid cols-3">
              <div className="tile">
                <div className="label">Low estimate</div>
                <div className="value neg">${proj.low_estimate.toLocaleString()}</div>
              </div>
              <div className="tile" style={{ borderColor: "var(--cyan)" }}>
                <div className="label">Central estimate</div>
                <div className="value">${proj.central_estimate.toLocaleString()}</div>
                <div className="foot">over {proj.assumptions.days} days · {proj.sample_size} trade sample</div>
              </div>
              <div className="tile">
                <div className="label">High estimate</div>
                <div className="value pos">${proj.high_estimate.toLocaleString()}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
